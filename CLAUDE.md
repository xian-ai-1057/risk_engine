# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

財報風險判斷引擎：讀取財報（CSV/JSON/HTML/Excel）+ 指標規則設定（JSON），判定風險觸發狀態並組裝 LLM Prompt。詳細規格見 [README.md](README.md)；既有 agent 指引見 [AGENTS.md](AGENTS.md) 與 [tests/README.md](tests/README.md) — 本檔不重複其中內容，只記錄對 Claude Code 操作此專案最關鍵的事。

## `Archive/` 資料夾——不要讀取

專案內的 `Archive/` 是已棄用的舊版本：一個技術路線完全不同的「v2 pattern-mining pipeline」（embedding + HDBSCAN 確定性分群 + Wilson 統計門檻收斂，`app/` DAG、`specs/`、SDD + Agent Teams 方法論，自己的 `CLAUDE.md` / `CROSS_GENRE_VALIDATION.md`），已被本專案現行的風險判斷引擎取代。它跟本檔案描述的架構（`formula.py` / `checker.py` / `threshold.py` / `pipeline.py`）無關，也沒有可複用的邏輯或設定。**不要讀取、探索或引用 `Archive/` 底下任何檔案**；需要歷史脈絡時直接問使用者，不要自己去 `Archive/` 找答案。

## 常用指令

```bash
pip install -e .                                    # 開發模式安裝（src layout）
pytest                                              # 全部測試
pytest tests/test_formula.py                        # 單檔
pytest tests/test_checker.py::TestCheckCompound     # 單類別
pytest tests/test_formula.py::TestSafeEval::test_division_by_zero  # 單測試
pytest --cov=risk_engine --cov=utils                # 覆蓋率
pyinstaller build/risk_analysis.spec --distpath outputs/dist   # 打包 EXE（產出 outputs/dist/risk_analysis）
python scripts/risk_checker.py --report 財報.csv --config outputs/indicator.json \
    --industry 7大指標 --customer A00001 --date 20241231 -o result.json
```

`pyproject.toml` 設定 `pythonpath = ["src"]`，pytest 與 `pip install -e .` 都從 `src/` 解析 `risk_engine` 與 `utils` 套件；不要在 import 時加 `src.` 前綴。

## 架構要點（多檔協作才看得出來的設計）

**唯一對外入口是 `pipeline.ReportPipeline.run()`**，一次產出 `narrative_prompt` / `risk_prompt` / `grouped_report` / `risk_report` 四個結果。內部分為兩條獨立分支共用同一份財報：
- **敘事分支**（filter-driven）：`narrative_filter.json` → `extract_section_codes` → `filter_and_group` → 填 `{{JSON_DATA}}`。
- **風險分支**（rules-driven）：`indicators_config.json` → `generate_report` → `apply_post_rules` → `to_prompt_view` → 填 `{{risk_results_1..5}}` / `{{narrative_1..5}}`。

兩者唯一交集是財報；新增功能時要先決定屬於哪一條分支，不要把規則資料注入敘事分支。

**安全公式求值（`formula.py`）**：自寫遞迴下降解析器，**不可用 `eval()`**，僅允許 `+ - * /` 與括號。任何擴充（新運算子、函式呼叫）都要走 `_tokenize` → `_Parser`，並補測試到 `test_formula.py::TestSafeEval`。

**三值缺值傳播**：任一代碼缺失 → 公式回傳 `None` → 規則 `missing`。但條件樹採短路：**AND** 任一葉 `false` → 整棵 `not_triggered`（不會 `missing`）；**OR** 任一葉 `true` → 整棵 `triggered`（不會 `missing`）。**不要**在核心模組裡用預設值替代 `None`。

**OR 優先解析**：`threshold.py` 與 `checker.py` 對 `A AND B OR C` 先以 `\s+OR\s+` 分割、再 `\s+AND\s+`，與 SQL/Python 慣例**反向**。撰寫設定時請以括號明確化；改動分割邏輯前先讀 `test_threshold.py::TestCompoundThreshold`。

**代碼後綴慣例**：無後綴 → `Current`，`_PRV` → `Period_2`，`_PRV2` → `Period_3`。`extract_codes` 永遠回傳去重且保留出現順序的「基礎代碼」（已剝除後綴）。

**`compare_type` 四型**：`absolute` / `period_change_pct` / `period_change_abs` / `compound`。新增比較類型時：在 `checker.py` 寫 `_check_xxx`，註冊到 `_HANDLERS["my_compare"] = _check_my_compare`，再到 `threshold.py::parse_threshold` 加新 `re.match` 分支。

**Prompt 視圖剝離原始值**：`report.to_prompt_view` 刻意移除 `indicator_code`、原始 `value`、`tag_id`，且未觸發 / 缺資料的 tag 只留 `{"status": ...}`。**不要把財報代碼或浮點數送進 LLM** — 設計上避免模型把代碼當自然語言或在敘述中重新換算。修改 prompt 視圖時要對照 [`inputs/json_sample/risk_prompt_input_sample.json`](inputs/json_sample/risk_prompt_input_sample.json)。

**段落限定五項**：`財務結構` / `償債能力` / `經營效能` / `獲利能力` / `現金流量`。`combine_prompt` 的 `SECTION_MAPPING` / `NARRATIVE_MAPPING` 寫死對應 `{{risk_results_1..5}}` 與 `{{narrative_1..5}}`，新增段落必須同步更新 mapping 與 prompt 模板。

**EXE 打包路徑**：`scripts/main.py` 是 PyInstaller 入口（不是 `risk_checker.py`），`paths.py` 處理 `sys._MEIPASS`，外部資源（`indicators_config.xlsx`、兩個 prompt 模板）必須與 EXE 同目錄而非打包進去 — 設計上要能不重編譯就更新規則。三類輸入檔皆支援版本化檔名 `{base}_V{ver}.{ext}`（如 `risk_user_prompt_V1_1_1.txt`、`indicators_config_V1_1_1.xlsx`），版本號為 `V` 開頭、`_` 分隔的數字段；`_discover_versioned` 多版並存時自動挑最高版（log 印出實際選用檔名），找不到版本化檔則 fallback 到不帶版本的舊檔名。每次執行會把 xlsx 轉換結果覆寫到 EXE 同目錄的 `indicators_config.json` + `narrative_filter.json` 作為 audit。**xlsx 是唯一指標來源**（CLI `--xlsx` 優先、否則自動探測：版本化 `indicators_config_V*.xlsx` → `indicators_config.xlsx` → 唯一 `*.xlsx`），EXE 不再支援單純讀 JSON 的部署模式。**HTML 解析所需的科目對照（FA_RFNBR→FA_CANME）也由 xlsx 內 `tag_table` sheet 提供**（欄位 `FA_RFNBR / FA_CANME / 單位`，與舊 CSV 一致）；`tag_table` sheet 是唯一科目對照來源，sheet 缺席或空時 `FA_CANME` 為空字串（不報錯，但 LLM 輸出可讀性會下降）—— EXE 不再讀 `tag_table.csv`。`build/risk_analysis.spec` 的 `excludes` 必須保留 `pandas` / `numpy` 排除（`utils.xlsx_to_indicators` 改用純 `openpyxl` 解析 xlsx，避免冷凍 pandas 把 EXE 從 ~10MB 撐到 ~33MB），但 `openpyxl` 必須留在 `hiddenimports` 中；主流程不可重新引入 pandas/numpy。`utils.xlsx_to_report_json` 是 standalone CLI、仍使用 pandas，但已加入 `excludes` 避免被 hook 拉進 EXE — 若要在 EXE 中支援 xlsx 財報，請改用 openpyxl。

## 例外處理慣例

- `ReportLoadError`（財報載入失敗）與 `ConfigError`（設定載入失敗）只在 `scripts/risk_checker.py::main` / `scripts/main.py` 以 `sys.exit(1)` 終止；**核心模組不要 catch 這兩個例外**，讓它們往上傳播。
- 其他未預期例外在 CLI 層以 `logger.exception` 記錄後 exit 1。

## 全形符號

`threshold.py` 自動把 `＞` `＜` `＝` 轉半形，無需在呼叫端預處理。
