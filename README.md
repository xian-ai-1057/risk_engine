# risk_engine

財報風險判斷引擎。讀取財報資料（CSV / JSON / HTML / Excel）與指標規則設定（JSON），依規則判斷風險觸發狀態，並可進一步組裝給 LLM 使用的敘事與風險 Prompt。

---

## 特色

- **安全公式求值**：以遞迴下降解析器取代 `eval()`，僅允許 `+ - * /` 與括號，杜絕注入風險。
- **中文門檻解析**：自動將「`>150%`」、「`較前期比率增加20%`」、「`A AND B OR C`」等中文門檻轉為結構化規則。
- **策略分派 + 條件樹**：四種比較類型（`absolute` / `period_change_pct` / `period_change_abs` / `compound`）以策略表分派，複合條件以 AND/OR 樹遞迴求值。
- **Pipeline 一條龍**：從原始財報到敘事 Prompt 與風險 Prompt 一次產出。
- **多種資料來源**：支援 CSV、JSON、HTML（Big5）、Excel 格式財報，以及單位（仟元 / % / 天 / 倍）格式化與趨勢推斷。

---

## 專案結構

```
risk_engine/
├── __init__.py              # 公開 API 匯出
├── risk_checker.py          # CLI 主入口
├── pipeline.py              # ReportPipeline：過濾分群 + 敘事 Prompt + 風險 Prompt
├── loader.py                # 財報 / 指標設定載入
├── formula.py               # 安全公式求值、代碼解析、value_kind 推斷
├── threshold.py             # 中文門檻解析（含 compound 樹建構）
├── checker.py               # 門檻比較（策略 + 遞迴樹求值）
├── report.py                # 報告產生、LLM 精簡格式、Prompt 精簡視圖
├── post_rules.py            # 多規則聯合觸發（meta-rule，預留）
├── types.py                 # TypedDict 與自訂例外
├── constants.py             # 共用 regex（OP_PATTERN）
├── log_config.py            # 統一 logging 設定（含 EXE 打包相容）
├── data/
│   ├── indicators_config_v3.json   # 範例指標設定（7大指標）
│   ├── json/                       # 風險結果範例 JSON
│   └── prompt/                     # 敘事 / 風險 sys & user prompt 模板
├── tests/                   # pytest 單元測試（92 tests）
└── utils/
    ├── combine_prompt.py    # 將風險結果 + 敘事填入 Prompt 模板
    ├── narrative.py         # 段落代碼擷取、敘事資料建構
    ├── convert_indicators.py# 指標 CSV → 結構化 JSON 設定
    ├── convert_report.py    # JSON TXT → 段落格式批次轉換
    ├── simple_convert.py    # 單位格式化、趨勢推斷、GroupedReport 轉換
    ├── html_to_json.py      # 財報 HTML（Big5）→ Report JSON
    ├── csv_to_report_json.py# 多家測試案例 CSV → 個別 Report JSON
    ├── xlsx_to_report_json.py# Excel 財報 → Report JSON
    └── convert_to_docx.py   # 分析結果 TXT → Word 文件
```

---

## 快速開始

### 1. CLI 直接執行

```bash
python risk_checker.py \
    --report 財報.csv \
    --config data/indicators_config_v3.json \
    --industry 7大指標 \
    --customer A00001 \
    --date 20241231 \
    -o result.json \
    [--compact] \
    [--narrative] \
    [--tag-table tag_table.csv] \
    [--log risk_checker.log] \
    [--debug]
```

| 旗標 | 說明 |
|------|------|
| `--report` | 財報檔案路徑（`.csv` / `.json`，依副檔名自動判斷）。 |
| `--config` | 指標設定 JSON 路徑。 |
| `--industry` | 產業名稱（必須存在於設定檔）。 |
| `--customer` | 客戶代碼。 |
| `--date` | 報表日期。 |
| `-o` | 輸出 JSON 路徑（預設 `result.json`）。 |
| `--compact` | 額外輸出 LLM 精簡格式（檔名加 `_compact` 後綴）。 |
| `--narrative` | 同時產出財報敘事段落（需配合 `--tag-table`）。 |
| `--tag-table` | tag_table CSV，補齊財報代碼中文名稱。 |
| `--log` | 自訂 log 檔；未指定時寫入 `log/<timestamp>.log`。 |
| `--debug` | 開啟 DEBUG 級別 log。 |

### 2. Python API

```python
from risk_engine import loader
from risk_engine.pipeline import ReportPipeline

report = loader.load_report("財報.csv")
rules  = loader.load_config("data/indicators_config_v3.json", "7大指標")

with open("data/prompt/財報敘事_user_prompt.txt", encoding="utf-8") as f:
    narrative_template = f.read()
with open("data/prompt/財報風險_user_prompt.txt", encoding="utf-8") as f:
    risk_template = f.read()

pipe = ReportPipeline(
    report=report,
    rules=rules,
    narrative_prompt_template=narrative_template,
    risk_prompt_template=risk_template,
    customer_id="A00001",
    report_date="20241231",
    industry="7大指標",
)
result = pipe.run()
# result["narrative_prompt"]  → 合併後的敘事 Prompt
# result["risk_prompt"]       → 合併後的風險 Prompt
# result["grouped_report"]    → 過濾分群後的報表
# result["risk_report"]       → 風險判定結果
```

也可直接使用低階模組：

```python
from risk_engine import (
    load_report, load_config,
    generate_report, to_llm_format,
    apply_post_rules,
)

report = load_report("財報.csv")
rules  = load_config("indicators_config.json", "7大指標")
risk   = generate_report(report, rules, "A00001", "20241231", "7大指標")
risk   = apply_post_rules(risk)
compact = to_llm_format(risk["sections"])
```

---

## 資料格式

### 財報（Report）

以財報代碼（`FA_RFNBR`）為 key，每筆含中文名稱、單位、與三期數值：

```json
{
  "TIBA040": {
    "FA_CANME": "權益總額",
    "單位": "仟元",
    "Current": 1099433.0,
    "Period_2": 1050000.0,
    "Period_3": 980000.0
  }
}
```

CSV 載入時必須具備 `FA_RFNBR` 欄位；JSON 結構直接以代碼為 key。

### 指標設定（Config）

以產業為 key，每筆規則描述一條判斷邏輯：

```json
{
  "7大指標": [
    {
      "section": "財務結構",
      "indicator_name": "負債權益比",
      "indicator_code": "TIBB002",
      "tag_id": "TIBB002_TAG1",
      "value_formula": "TIBB002",
      "compare_type": "absolute",
      "operator": ">",
      "threshold": 150.0,
      "risk_description": "負債比偏高",
      "result_unit": "%"
    }
  ]
}
```

### 公式語法

| 形式 | 範例 |
|------|------|
| 單一代碼 | `TIBB002` |
| 四則運算 | `TIBB013+TIBB011-TIBB012` |
| 含括號 | `(TIBA049+TIBA047+TIBC003)/TIBA047` |
| 含前期 | `TIBB011-TIBB011_PRV` |
| 含前前期 | `TIBB011-TIBB011_PRV2` |

`_PRV` → `Period_2`，`_PRV2` → `Period_3`，無後綴 → `Current`。

### 門檻語法（中文 → 結構化）

| 類型 | 範例 | `compare_type` |
|------|------|----------------|
| 絕對值 | `>150%` / `<0` / `<=180天` | `absolute` |
| 前期比率變動 | `較前期比率增加20%` | `period_change_pct` |
| 前期絕對變動 | `較前期增加60天` | `period_change_abs` |
| 複合條件 | `(A) AND B OR C` | `compound` |

複合條件依「OR 優先分割、AND 次之」建為樹狀 `condition_tree`，由 `checker.evaluate_node` 遞迴求值；任一葉節點缺資料即整棵樹回傳 `missing`。

### 風險判定結果（FullReport）

```json
{
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
        "indicator_name": "...",
        "indicator_code": "...",
        "current_value": 0.55,
        "current_display": "0.55倍",
        "previous_value": null,
        "previous_display": null,
        "value_kind": "current",
        "value_label": "當期值",
        "operands": [...],
        "taggings": [
          { "tag_id": "...", "status": "triggered|not_triggered|missing",
            "threshold": ">1.0", "description": "..." }
        ]
      }
    ]
  }
}
```

---

## Pipeline 流程

```
            ┌────────────────────────────┐
            │ load_report / load_config  │
            └─────────────┬──────────────┘
                          ▼
            ┌────────────────────────────┐
            │  Step 1: filter & group    │  從 rules 萃取每段落用到的代碼，
            │  (extract_section_codes)   │  從財報過濾並按 section 分群
            └──────┬──────────────┬──────┘
                   │              │
          (Step 2a)│              │(Step 2b)
                   ▼              ▼
       ┌─────────────────┐  ┌────────────────────┐
       │ render_         │  │ generate_report +  │
       │ narrative_      │  │ apply_post_rules + │
       │ prompt          │  │ render_risk_prompt │
       └────────┬────────┘  └─────────┬──────────┘
                │                     │
                ▼                     ▼
        narrative_prompt        risk_prompt
```

`combine_prompt` 模組會把分群報表填入 `{{JSON_DATA}}` 佔位符（敘事），並把風險結果依段落填入 `{{risk_results_1..5}}`、敘事資料填入 `{{narrative_1..5}}`（合併）。

---

## 工具腳本（utils/）

| 腳本 | 用途 |
|------|------|
| `convert_indicators.py` | 將原始指標 CSV 轉為 `indicators_config.json`，自動解析中文門檻並建立 compound 樹。 |
| `html_to_json.py` | 將 Big5 編碼的 4 個財報 HTML 解析為 Report JSON。 |
| `xlsx_to_report_json.py` | 解析單一公司 Excel 財報 → Report JSON（依工作表配置代碼前綴 `TIBA`/`TIBB`/`TIBC`/`TIBD`）。 |
| `csv_to_report_json.py` | 從多家測試案例 CSV 萃取指定公司，輸出個別 Report JSON。 |
| `simple_convert.py` | 預處理財務 JSON：單位格式化（`仟元`/`%`/`天`/`倍`）、計算趨勢、`GroupedReport` 轉為含實際日期 key 的格式。 |
| `combine_prompt.py` | 將風險結果與敘事填入 prompt 模板，提供 `render_prompt`/`render_risk_prompt`/`render_narrative_prompt` 三個介面。 |
| `narrative.py` | 從 rules 提取每段落財報代碼、結合 tag_table 中文名稱、輸出敘事結構（亦可獨立 CLI 執行）。 |
| `convert_report.py` | 批次將 LLM 回傳的 JSON TXT 轉為帶章節標題的段落格式。 |
| `convert_to_docx.py` | 將分析結果 TXT 整理為 Word 文件。 |

---

## 測試

```bash
pytest                                    # 全部 92 個測試
pytest tests/test_formula.py              # 單檔
pytest tests/test_checker.py::TestCheckCompound  # 單類別
pytest --cov=risk_engine --cov=utils      # 覆蓋率
```

詳細測試組成請參考 [`tests/README.md`](tests/README.md)。

---

## 擴展指南

### 新增比較類型

1. 在 `checker.py` 撰寫 `_check_xxx(current_val, prev_val, rule, report)` 函式。
2. 在 `_HANDLERS` 新增一行註冊：

```python
_HANDLERS["my_compare"] = _check_my_compare
```

### 新增中文門檻格式

在 `threshold.py` 的 `parse_threshold()` 加入新的 `re.match` 分支，回傳含 `compare_type` 的 dict。

### 新增 meta-rule（多規則聯合觸發）

`post_rules.py` 已預留接口，並於 docstring 中描述設計骨架：定義 `meta_rule` 設定 → 在 `checker.evaluate_node` 加入 `node_type == "tag_ref"` 分支 → 實作 `apply_post_rules()`。

---

## Logging

`risk_engine.log_config.setup_logging()` 統一設定 root logger，同時輸出至 console 與檔案；未指定路徑時預設寫入程式所在目錄的 `log/<timestamp>_<request_id>.log`，相容 PyInstaller 打包後的 EXE 環境。
