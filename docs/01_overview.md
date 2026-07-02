# 01 系統定位

## 一句話

**risk_engine 是一個讀財報、套規則、組 LLM Prompt 的引擎**：給它三期財報數據與一份指標規則，它告訴你哪些風險被觸發，並且把結果整理成可以直接送進 LLM 的 Prompt。

## 一個範例輸入

EXE 流程的輸入是「四份 Big5 編碼的財報 HTML」+「一份 xlsx 指標檔」+「兩份 Prompt 模板」：

```
exe_dir/
├── risk_analysis           # PyInstaller 打包後的 EXE
├── 指標.xlsx               # 唯一指標來源（『指標』+『敘事指標』兩個 sheet）
├── risk_user_prompt.txt    # 風險 Prompt 模板（含 {{risk_results_1..5}}）
├── narrative_user_prompt.txt # 敘事 Prompt 模板（含 {{JSON_DATA}}）
├── tag_table.csv           # （選用）HTML 解析輔助
├── 財務概況.html
├── 財務比率.html
├── 現金流量.html
└── 淨值調節.html
```

對應的指標規則在 xlsx 的「指標」sheet 中以一列描述一條規則，例如：

| 產業別 | 段落 | 指標名稱 | 公式 | 門檻 | 風險情境 |
|--------|------|---------|------|------|---------|
| 7大指標 | 財務結構 | 負債權益比 | `TIBB002` | `>150%` | 負債比偏高 |
| 7大指標 | 償債能力 | 應收帳款週轉天數變動 | `TIBB011` | `較前期增加60天` | 收款效率惡化 |
| 7大指標 | 經營效能 | 多重風險 | `TIBB011` | `>150 AND <200 OR >300` | 異常波動 |

## 一個範例輸出

```json
{
  "schema_version": "1.0",
  "request_id": "ab12cd34",
  "industry": "7大指標",
  "narrative_prompt": "（已填入財報 JSON 的敘事 Prompt 文字）",
  "risk_prompt": "（已填入風險判定結果的風險 Prompt 文字）",
  "grouped_report": {
    "財務結構": {"TIBA040": {"FA_CANME": "權益總額", "Current": 1099433.0, ...}},
    "償債能力": {"TIBB011": {...}},
    "經營效能": {...},
    "獲利能力": {...},
    "現金流量": {...}
  },
  "risk_report": {
    "customer_id": "A00001",
    "report_date": "20241231",
    "industry": "7大指標",
    "summary": {
      "total_sections": 5,
      "total_indicators": 18,
      "triggered_count": 5,
      "not_triggered_count": 20,
      "missing_count": 1,
      "total_rules": 26
    },
    "sections": {
      "財務結構": [
        {
          "indicator_name": "負債權益比",
          "current_value": 175.2,
          "current_display": "175.2%",
          "value_kind": "current",
          "value_label": "當期值",
          "operands": [...],
          "taggings": [
            {
              "tag_id": "STRUCT_TAG1",
              "status": "triggered",
              "threshold": ">150.0",
              "description": "負債比偏高"
            }
          ]
        }
      ]
    }
  }
}
```

正式型別定義見 [src/risk_engine/types.py::ExeOutput](../src/risk_engine/types.py)。

---

## 兩個對外實體

risk_engine 有兩條呼叫路徑，**用途不同，新人不要混用**：

### 1. EXE 流程（生產）

入口：[scripts/main.py](../scripts/main.py)::`main`

- 給上游後端整合呼叫，PyInstaller 打包成 `risk_analysis` EXE。
- 唯一指標來源是 **xlsx**（不再支援只讀 JSON 的部署模式）。
- 每次執行會把 xlsx 即時轉成 `indicators_config.json` + `narrative_filter.json` 落地到 EXE 同層作 audit。
- 失敗時 exit code 1/2/3 對應 `INVALID_ARGS` / `MISSING_FILE` / `CONFIG_ERROR` / `PROCESSING_ERROR`（見 [src/risk_engine/types.py](../src/risk_engine/types.py) 的 `ERROR_CODES`）。

### 2. Python API / Legacy CLI（debug）

入口：[scripts/risk_checker.py](../scripts/risk_checker.py)::`main` 或 `from risk_engine.pipeline import ReportPipeline`

- 給開發者快速回歸用，可以吃 CSV / JSON 財報 + 分離的 indicator JSON / narrative_filter JSON。
- **不打包進 EXE**。
- 任何例外都統一以 `sys.exit(1)` 結束。

兩條路徑的差異一目了然見 [03_architecture.md](03_architecture.md)。

---

## 五段落硬性約束

整個系統把所有指標限定在以下五個段落，**不能新增段落而不改程式碼**：

1. `財務結構`
2. `償債能力`
3. `經營效能`
4. `獲利能力`
5. `現金流量`

原因：[src/utils/combine_prompt.py](../src/utils/combine_prompt.py) 中 `SECTION_MAPPING` / `NARRATIVE_MAPPING` 寫死對應 `{{risk_results_1..5}}` / `{{narrative_1..5}}`。新增段落必須同步更新 mapping、prompt 模板的 placeholder。詳見 [09_extending.md](09_extending.md)。

---

## 適用場景

| 場景 | 是否適用 |
|------|---------|
| 從財報 + 規則產出制式風險報告 | ✓ |
| 把規則判定結果送 LLM 做敘事描述 | ✓ |
| 新增 / 修改規則但不重編譯 EXE | ✓（改 xlsx 即可） |
| 任意自由文字的財報摘要 | ✗（需要規則化的指標） |
| 即時 streaming 風險告警 | ✗（單次批次處理） |

---

## 下一步

→ [02_quickstart.md](02_quickstart.md) 安裝並跑通第一個 sample。

> 想看完整的輸入輸出契約定義（含所有欄位的型別約束），請看專案根 [README.md](../README.md) 的「系統規格」章節。
