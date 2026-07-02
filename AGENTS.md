# risk_engine — Agent Instructions

財報風險判斷引擎：讀取財報資料，依指標規則判斷風險觸發狀態，並組裝供 LLM 使用的 Prompt。

- 完整系統規格 → [README.md](README.md)
- 詳細架構文件 → [docs/](docs/README.md)（overview / architecture / spec / module reference / extending）
- 測試說明 → [tests/README.md](tests/README.md)
- EXE 打包與部署 → [build/README.md](build/README.md)
- 核心型別定義 → [src/risk_engine/types.py](src/risk_engine/types.py)
- 指標設定範例 → [inputs/archive/indicators_config.json](inputs/archive/indicators_config.json)

---

## Build & Test

```bash
pip install -e .          # 安裝（開發模式，一次即可）
pytest                    # 執行所有測試（92 個）
pytest tests/test_formula.py                        # 單一檔案
pytest tests/test_checker.py::TestCheckCompound     # 單類別
pytest --cov=risk_engine --cov=utils                # 含覆蓋率
```

`conftest.py` 與 `pyproject.toml` 已設定 `pythonpath = ["src"]`，無需額外處理路徑。  
import 時**不加** `src.` 前綴（正確：`from risk_engine.pipeline import ...`）。

---

## 架構速覽

唯一對外入口：**`pipeline.ReportPipeline.run()`**，一次產出 `PipelineResult`（`narrative_prompt` / `risk_prompt` / `grouped_report` / `risk_report`）。內部兩條分支共用同一份財報：

| 分支 | 設定來源 | 輸出 Prompt 佔位符 |
|------|----------|-------------------|
| 敘事（filter-driven） | `narrative_filter.json` | `{{JSON_DATA}}` |
| 風險（rules-driven） | `indicators_config.json` | `{{risk_results_1..5}}` / `{{narrative_1..5}}` |

五個固定段落：`財務結構` / `償債能力` / `經營效能` / `獲利能力` / `現金流量`（對應 `{{risk_results_1..5}}`，寫死於 `utils/combine_prompt.py::SECTION_MAPPING`）。**新增段落**須同時更新 mapping 與 prompt 模板。

---

## 非直覺慣例（必讀）

### `compare_type` 四種型態
- `absolute`：與固定門檻比較（`> 1.0`）
- `period_change_pct`：較前期比率增減（「較前期增加 20%」）
- `period_change_abs`：較前期絕對值增減
- `compound`：AND/OR 組合；門檻字串由 `threshold.py` 解析為條件樹

### 財報代碼後綴
- 無後綴 → `Current`；`_PRV` → `Period_2`；`_PRV2` → `Period_3`

### 三值邏輯缺值傳播
- 任一代碼缺失 → 公式 `None` → 規則 `missing`
- AND 樹：任一葉 `false` → 整體 `not_triggered`（優先於 `missing`）
- OR 樹：任一葉 `true` → 整體 `triggered`（優先於 `missing`）
- `threshold.py` 自動將 `＞ ＜ ＝` 正規化為半形

### compound AND/OR 分割順序（⚠️ 與 Python/SQL 反向）
- 先以 `\s+OR\s+` 分割，再以 `\s+AND\s+` 分割（OR 優先）
- 撰寫 `compound` 門檻時**請以括號明確化優先序**，避免歧義
- 修改分割邏輯前先讀 `tests/test_threshold.py::TestCompoundThreshold`

### 安全公式求值
- `formula.py` 使用自寫遞迴下降解析器，**禁止使用 `eval()`**
- 僅支援 `+ - * /` 與括號；非法字元、除以零皆回傳 `None`
- 新增運算子或函式：走 `_tokenize` → `_Parser`，並補測試到 `test_formula.py::TestSafeEval`

### Prompt 視圖刻意剝離資料
- `report.to_prompt_view()` **移除** `indicator_code`、原始 `value`、`tag_id`
- 未觸發 / 缺資料的 tag 只留 `{"s": "N"}` / `{"s": "M"}`
- 修改 prompt 視圖時對照 [`inputs/json_sample/risk_prompt_input_sample.json`](inputs/json_sample/risk_prompt_input_sample.json)

### 例外處理原則
- `ReportLoadError` / `ConfigError` 只在 `scripts/risk_checker.py::main` / `scripts/main.py` 以 `sys.exit(1)` 終止
- **核心模組（`src/risk_engine/`）不得 catch 這兩個例外**，讓它們往上傳播

### EXE 部署（`scripts/main.py`）
- `paths.py` 處理 `sys._MEIPASS`；外部資源（xlsx、prompt 模板、`tag_table.csv`）須與 EXE 同目錄
- **xlsx 是唯一指標來源**（CLI `--xlsx` > 預設 `指標.xlsx`）；EXE 不支援純 JSON 部署模式
- 每次執行覆寫 `indicators_config.json` + `narrative_filter.json` 到 EXE 同目錄作為 audit

### 測試慣例
- 以 `_make_rule()` / `_nf_item()` 等小型 helper 建立測試資料
- 以 `class Test<Feature>` 分組；斷言訊息描述預期行為

---

## 新增規則 / 指標

1. 編輯 `inputs/archive/indicators_config.json`，在對應產業 key 下新增規則物件（必填欄位見 [README.md](README.md#輸入)）
2. `compound` 型態門檻格式：`條件A AND/OR 條件B`（自動解析）
3. `pytest tests/test_checker.py tests/test_threshold.py` 確認未破壞現有邏輯
4. 有新比較行為時，在 `checker.py` 新增 `_check_xxx` 並註冊到 `_HANDLERS`，補 `test_checker.py` 測試

## 新增比較型態

1. `checker.py`：實作 `_check_xxx`，加到 `_HANDLERS["my_compare"]`
2. `threshold.py::parse_threshold`：新增對應 `re.match` 分支
3. `pytest tests/test_checker.py tests/test_threshold.py`
