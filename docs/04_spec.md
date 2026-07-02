# 04 規格（Spec）

本檔提供條列式規格摘要，供查閱用。完整敘述見專案根 [README.md](../README.md)；正式型別見 [src/risk_engine/types.py](../src/risk_engine/types.py)。

## 1 輸入

### 1.1 EXE 流程（生產）

| 項目 | 來源 | 必填欄位 / 約束 |
|------|------|-----------------|
| 財報 | 4 份 HTML（Big5） | 由 [`utils.html_to_json`](../src/utils/html_to_json.py) 解析；附帶 `_period_dates` metadata。 |
| 指標 + 敘事 | 一份 xlsx | 必含 `指標` / `敘事指標` 兩個 sheet（找不到時 fallback 為 `Sheet1` / `Sheet2`），由 [`utils.xlsx_to_indicators`](../src/utils/xlsx_to_indicators.py) 一次轉成 rules + narrative_filter。預設檔名 `指標.xlsx`，可用 `--xlsx` 指定。 |
| Prompt 模板 | `risk_user_prompt.txt`、`narrative_user_prompt.txt` | 敘事模板需含 `{{JSON_DATA}}`；風險模板需含 `{{risk_results_1..5}}`，可選含 `{{narrative_1..5}}`。 |
| Tag 對照 | `tag_table.csv`（選用） | HTML 解析輔助；缺檔自動退化為 None。 |

### 1.2 Python API / Legacy CLI

底層 [`risk_engine.loader.load_report`](../src/risk_engine/loader.py) 接受 CSV / JSON 財報；[`load_config`](../src/risk_engine/loader.py) 讀分離的 indicator JSON。僅供 debug，**正式 EXE 流程不再支援**。

---

## 2 公式語法

| 形式 | 範例 |
|------|------|
| 單一代碼 | `TIBB002` |
| 四則運算 | `TIBB013+TIBB011-TIBB012` |
| 含括號 | `(TIBA049+TIBA047+TIBC003)/TIBA047` |
| 含前期 | `TIBB011-TIBB011_PRV` |
| 含前前期 | `TIBB011-TIBB011_PRV2` |

代碼後綴慣例：

| 後綴 | 對應期別 |
|------|---------|
| 無後綴 | `Current`（呼叫端可指定預設期別） |
| `_PRV` | `Period_2` |
| `_PRV2` | `Period_3` |

公式安全性：僅允許 `+ - * /` 與括號；非法字元、未配對括號、除以零都回傳 `None`（見 [`formula._safe_eval`](../src/risk_engine/formula.py)）。

---

## 3 門檻語法

`compare_type` 共四型，由 [`threshold.parse_threshold`](../src/risk_engine/threshold.py) 解析：

| 類型 | 範例 | `compare_type` |
|------|------|----------------|
| 絕對值 | `>150%` / `<0` / `<=180天` | `absolute` |
| 前期比率變動 | `較前期比率增加20%` | `period_change_pct` |
| 前期絕對變動 | `較前期增加60天` | `period_change_abs` |
| 複合條件 | `(A) AND B OR C` | `compound` |

複合條件：

- 依「OR 優先分割、AND 次之」建為樹狀 `condition_tree`。
- 由 [`checker.evaluate_node`](../src/risk_engine/checker.py) 遞迴求值。
- 全形符號 `＞` `＜` `＝` 自動轉半形（見 [`threshold._normalize`](../src/risk_engine/threshold.py)）。

---

## 4 輸出

### 4.1 段落（硬編碼五項）

`財務結構` / `償債能力` / `經營效能` / `獲利能力` / `現金流量`

對應佔位符（見 [`utils.combine_prompt`](../src/utils/combine_prompt.py)）：

| 段落 | 風險佔位符 | 敘事佔位符 |
|------|-----------|-----------|
| 財務結構 | `{{risk_results_1}}` | `{{narrative_1}}` |
| 償債能力 | `{{risk_results_2}}` | `{{narrative_2}}` |
| 經營效能 | `{{risk_results_3}}` | `{{narrative_3}}` |
| 獲利能力 | `{{risk_results_4}}` | `{{narrative_4}}` |
| 現金流量 | `{{risk_results_5}}` | `{{narrative_5}}` |

### 4.2 `TagResult.status`

`triggered` / `not_triggered` / `missing`

`missing` 包含：缺資料、不支援的 `compare_type`、運算溢位。

### 4.3 風險判定結果（FullReport）

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
          { "tag_id": "...",
            "status": "triggered|not_triggered|missing",
            "threshold": ">1.0",
            "description": "..." }
        ]
      }
    ]
  }
}
```

完整型別見 [`types.FullReport`](../src/risk_engine/types.py)、[`types.IndicatorEntry`](../src/risk_engine/types.py)、[`types.TagResult`](../src/risk_engine/types.py)。

### 4.4 EXE 輸出（ExeOutput）

`schema_version="1.0"` + `request_id` + `industry` + `narrative_prompt` + `risk_prompt` + `grouped_report` + `risk_report`，外加選填 `customer_id` / `report_date`。型別見 [`types.ExeOutput`](../src/risk_engine/types.py)。

### 4.5 LLM 精簡格式（`to_llm_format`，`--compact`）

| 縮寫 | 全名 |
|------|------|
| `n` | indicator_name |
| `cur` | current_value |
| `prev` | previous_value |
| `s` | status |
| `th` | threshold |
| `d` | description |
| `T` | triggered |
| `N` | not_triggered |
| `M` | missing |

未觸發 tag 僅留 `{"s": "N"}`。

### 4.6 Prompt 精簡視圖（`to_prompt_view`）

組合到風險 Prompt 的版本：

- 移除 `indicator_code`、`operands[].code`、`operands[].value`、`tag_id`。
- 未觸發 / 缺資料的 tag 只留 `{"status": ...}`。
- 觸發保留 `description` + `threshold`（compound 改為 `condition_details`）。

對照範例見 [README.md#prompt-精簡視圖to_prompt_view](../README.md#prompt-精簡視圖to_prompt_view)、[`inputs/json_sample/risk_prompt_input_sample.json`](../inputs/json_sample/risk_prompt_input_sample.json)。

---

## 5 不變式（必讀）

| 不變式 | 影響範圍 | 來源 |
|--------|---------|------|
| **None 即缺資料**：任何階段出現 `None` 一律向上傳播至 `status == "missing"`，不會被預設值替代。 | 所有核心模組 | [`formula._substitute_codes`](../src/risk_engine/formula.py)、[`checker.evaluate_node`](../src/risk_engine/checker.py) |
| **三值短路**：AND 任一葉 `false` → 整體 `not_triggered`（不會 `missing`）；OR 任一葉 `true` → 整體 `triggered`（不會 `missing`）。 | 複合條件 | [`checker.evaluate_node`](../src/risk_engine/checker.py) |
| **OR 優先解析**：`A AND B OR C` → `or(and(A,B), C)`，與 SQL/Python 反向。 | 設定撰寫 | [`threshold._build_tree`](../src/risk_engine/threshold.py) |
| **不可變代碼集**：[`extract_codes`](../src/risk_engine/formula.py) 永遠回傳去重且保留出現順序的「基礎代碼」（`_PRV` / `_PRV2` 已剝除）。 | 公式解析 | [`formula.extract_codes`](../src/risk_engine/formula.py) |
| **Prompt 視圖剝離**：[`to_prompt_view`](../src/risk_engine/report.py) 移除原始代碼/浮點，避免 LLM 把代碼當自然語言或重新換算。 | 風險分支 | [`report._prompt_indicator`](../src/risk_engine/report.py)、[`_prompt_tag`](../src/risk_engine/report.py)、[`_prompt_condition_detail`](../src/risk_engine/report.py) |
| **段落限定五項**：`SECTION_MAPPING` / `NARRATIVE_MAPPING` 寫死對應 `{{risk_results_1..5}}` / `{{narrative_1..5}}`。新增段落必須同步更新 mapping 與 prompt 模板。 | 整個系統 | [`utils.combine_prompt`](../src/utils/combine_prompt.py) |

---

## 6 例外與錯誤碼

### 6.1 自訂例外

| 例外 | 觸發時機 | 來源 |
|------|---------|------|
| `ReportLoadError` | 財報載入失敗（檔案不存在、CSV 缺 `FA_RFNBR`、JSON 解析失敗等） | [`types.ReportLoadError`](../src/risk_engine/types.py) |
| `ConfigError` | 指標設定載入失敗（檔案不存在、JSON 解析失敗、產業不存在） | [`types.ConfigError`](../src/risk_engine/types.py) |

**核心模組（`src/risk_engine/`）不得 catch 這兩個例外**，讓它們往上傳播。只在 `scripts/main.py` / `scripts/risk_checker.py` 的入口層處理。

### 6.2 EXE 錯誤碼（`ERROR_CODES`）

對應 `--stdout` 模式的 `ExeError` JSON：

| `error_code` | 觸發時機 | exit code |
|--------------|---------|-----------|
| `INVALID_ARGS` | 參數驗證 / stdin 解析錯誤 | 1 |
| `MISSING_FILE` | 必要檔案不存在 | 2 |
| `CONFIG_ERROR` | 設定 / 報表載入錯誤 | 2 |
| `PROCESSING_ERROR` | 其他未預期錯誤 | 3 |

定義於 [`types.ERROR_CODES`](../src/risk_engine/types.py)、處理於 [`scripts/main.py::_exit_error`](../scripts/main.py)。

### 6.3 Legacy CLI

`scripts/risk_checker.py::main` 把所有例外統一以 `sys.exit(1)` 結束、`logger.exception` 記錄。

---

## 7 Logging

- Console + 檔案雙輸出，格式 `%(asctime)s [%(levelname)s] %(name)s - %(message)s`。
- 預設 INFO；CLI `--debug` 切為 DEBUG。
- 未指定 `--log` 時寫入 `<base_dir>/outputs/log/<YYYYMMDD_HHMMSS>[_<request_id>].log`。
- EXE 環境（`sys.frozen`）的 `base_dir` 為執行檔目錄；非 EXE 為 src/ 上層（見 [`paths.get_base_dir`](../src/risk_engine/paths.py)）。

---

## 下一步

- 看呼叫鏈細節 → [05_function_flow.md](05_function_flow.md)
- 看資料流轉換 → [06_data_flow.md](06_data_flow.md)
