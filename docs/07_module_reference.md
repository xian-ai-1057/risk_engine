# 07 模組速查

各模組的公開函式與職責。標註 **EXE / Legacy / Util** 以便新人判斷修改的影響面。模組之間如何互動的全景見 [03_architecture.md](03_architecture.md)；正式型別契約見 [`types.py`](../src/risk_engine/types.py) 與專案根 [README.md](../README.md)。

## risk_engine 套件

### [`risk_engine/__init__.py`](../src/risk_engine/__init__.py)

公開 API 匯出。新增公開函式時要在這裡加 `__all__`。

### [`risk_engine/types.py`](../src/risk_engine/types.py)

| 名稱 | 角色 |
|------|------|
| `ConfigError` / `ReportLoadError` | 自訂例外。核心模組**不得 catch**。 |
| `ReportRow` | 單一財報代碼的多期數值。 |
| `Report` | `dict[str, ReportRow]`。 |
| `ConditionLeaf` / `LogicNode` / `ConditionNode` | 複合條件樹節點。 |
| `Rule` | 單條規則（含 `condition_tree` 給 compound 用）。 |
| `TagResult` | 單條規則的判定結果。 |
| `Operand` / `IndicatorEntry` / `Summary` / `FullReport` | 風險判定輸出層級。 |
| `NarrativeItem` / `NarrativeSections` | 敘事資料結構。 |
| `GroupedReport` / `PipelineResult` | Pipeline 中間/最終型別。 |
| `EXE_SCHEMA_VERSION = "1.0"` | EXE 輸出 schema 版本。 |
| `ExeOutput` / `ERROR_CODES` / `ExeError` | EXE 對外契約。 |

### [`risk_engine/loader.py`](../src/risk_engine/loader.py)

| 函式 | 用途 | 例外 |
|------|------|------|
| `load_report(path)` | 自動偵測 CSV / JSON 載入財報 → `Report`。 | `ReportLoadError` |
| `load_config(config_path, industry)` | 讀 indicator JSON 並按產業過濾 → `list[Rule]`。 | `ConfigError` |
| `build_report_row(data)` | 把 dict 轉 `ReportRow`，數值用 `_to_float` 正規化。 | — |
| `load_csv(csv_path)` | 通用 CSV → `list[dict[str, str]]`，給 `convert_indicators` 用。 | — |

關鍵：`_to_float` 視 `None` / 空字串 / 無法 parse 為 `None`（**不是 0**）。

### [`risk_engine/formula.py`](../src/risk_engine/formula.py)

| 函式 | 用途 |
|------|------|
| `evaluate_formula(formula, report, period="Current")` | 主入口：代碼後綴解析 → 替換為數值 → 安全求值。 |
| `classify_formula(formula, compare_type)` | 由結構推斷 `value_kind` / `value_label`（當期值 / 較前期變動 / 變動率 / 多期加總 / 複合條件）。 |
| `extract_operands(formula, report)` | 回傳 `Operand` list（含 period_label / display），按 (code, period) 去重保序。 |
| `extract_codes(formula)` | 回傳去重保序的基礎代碼（`_PRV` / `_PRV2` 已剝除）。 |
| `_resolve_code(code, default_period)` | 後綴 → 期別。 |
| `_safe_eval(expr)` | 內部：tokenize + 遞迴下降；**不可改為 `eval()`**。 |
| `_Parser` | 內部：`expr → term → factor → atom`。 |

### [`risk_engine/threshold.py`](../src/risk_engine/threshold.py)

| 函式 | 用途 |
|------|------|
| `parse_threshold(raw)` | 主入口：中文字串 → 結構化 dict（含 compound 樹）。 |
| `_normalize(text)` | 全形 `＞ ＜ ＝` → 半形。 |
| `_build_tree(text)` | 依「OR 優先、AND 次之」遞迴建樹。 |
| `_parse_sub_condition(expr)` | 葉節點解析：右起最後一個比較運算子切公式與門檻。 |

### [`risk_engine/checker.py`](../src/risk_engine/checker.py)

| 函式 / 名稱 | 用途 |
|-------------|------|
| `check_rule(current_val, prev_val, rule, report=None)` | 主入口：依 `compare_type` 從 `_HANDLERS` 分派 → `TagResult`。 |
| `evaluate_node(node, report)` | 遞迴條件樹求值，回 `(bool|None, details_list)`。 |
| `_HANDLERS` | 策略表 `dict[str, Callable]`：新增 `compare_type` 在這裡註冊。 |
| `_check_absolute` / `_check_period_change` / `_check_compound` | 三類比對實作。 |
| `_calc_period_change_pct` / `_calc_period_change_abs` | 變動量計算（pct 用 `abs(prev)` 為分母）。 |

### [`risk_engine/report.py`](../src/risk_engine/report.py)

| 函式 | 用途 |
|------|------|
| `generate_report(report, rules, customer_id, report_date, industry)` | 主入口：分組 → 逐指標求值 → `FullReport`。 |
| `_collect_needs_prev(rules)` | 先掃所有規則決定哪些指標要算 Period_2。 |
| `_group_rules(rules)` | `OrderedDict[section][indicator_code][rules]`。 |
| `_evaluate_indicator(...)` | 單一指標：取 operands、套規則、組 `IndicatorEntry`。 |
| `_infer_unit(formula, codes_units, has_div, has_trailing_mul, result_unit)` | 推斷顯示單位。 |
| `_enrich_condition_details(details, report)` | 補 compound 葉節點的 `subject` / `display`。 |
| `to_llm_format(sections)` | 縮寫鍵格式（`n` / `cur` / `s` / ...）。 |
| `to_prompt_view(sections)` | 剝除原始代碼/浮點的 LLM 視圖。 |
| `_prompt_indicator` / `_prompt_tag` / `_prompt_condition_detail` | 投影層三層處理。 |

### [`risk_engine/post_rules.py`](../src/risk_engine/post_rules.py)

| 函式 | 用途 |
|------|------|
| `apply_post_rules(report_result, meta_rules=None)` | **預留**：目前 pass-through，給 meta-rule（多規則聯合觸發）用。 |

設計骨架見檔案 docstring；擴展方式見 [09_extending.md#meta-rule](09_extending.md#meta-rule多規則聯合觸發)。

### [`risk_engine/pipeline.py`](../src/risk_engine/pipeline.py)

| 名稱 | 用途 |
|------|------|
| `ReportPipeline.__init__(...)` | 接 report / rules / templates / narrative_filter / period_dates。 |
| `ReportPipeline.filter_and_group()` | Step 1：依 `narrative_filter` 分群（**不碰 rules**）。 |
| `ReportPipeline.build_narrative_prompt(grouped)` | Step 2a：填 `{{JSON_DATA}}`。 |
| `ReportPipeline.build_risk_prompt()` | Step 2b：用完整報表做風險判定 + 填風險模板。 |
| `ReportPipeline.run()` | 一次執行三步驟，回 `PipelineResult`。 |

### [`risk_engine/constants.py`](../src/risk_engine/constants.py)

| 名稱 | 用途 |
|------|------|
| `OP_PATTERN` | 比較運算子 regex（`>=` / `<=` / `>` / `<`），threshold + checker 共用。 |

### [`risk_engine/log_config.py`](../src/risk_engine/log_config.py)

| 函式 | 用途 |
|------|------|
| `setup_logging(log_file=None, level=INFO, request_id="")` | 統一設 root logger。**只移除自家 handler**（標 `_risk_engine_owned`），不會擾動 pytest caplog。 |

### [`risk_engine/paths.py`](../src/risk_engine/paths.py)

| 函式 | 用途 |
|------|------|
| `get_base_dir()` | EXE (`sys.frozen`) 回 EXE 目錄，否則回 src/ 上層。所有「同層檔案探測」都從這裡出發。 |

---

## utils 套件

### [`utils/combine_prompt.py`](../src/utils/combine_prompt.py) — Util

| 名稱 | 用途 |
|------|------|
| `SECTION_MAPPING` | `{段落: {{risk_results_N}}}` 寫死五項。 |
| `NARRATIVE_MAPPING` | `{段落: {{narrative_N}}}` 寫死五項。 |
| `render_prompt(...)` | 通用：依 mapping + formatter 替換 placeholder。 |
| `render_risk_prompt(template, risk_report)` | 依 `to_prompt_view` 投影後填 `{{risk_results_1..5}}`。 |
| `render_narrative_prompt(template, grouped, period_dates=None)` | 填 `{{JSON_DATA}}` 與 `{{narrative_1..5}}`。 |
| `main()` | CLI 入口（`python -m utils.combine_prompt`）。 |

### [`utils/narrative.py`](../src/utils/narrative.py) — Util

| 函式 | 用途 |
|------|------|
| `build_grouped_narrative(report, narrative_filter)` | filter-driven 分群：`{section: {code: ReportRow}}`。 |
| `build_narrative(report, rules, tag_table=None)` | rules-driven：從規則公式抽 codes，組敘事資料 `NarrativeSections`。 |
| `format_narrative_text(items)` | 把 `NarrativeItem` list 渲染成自然語言文字。 |
| `extract_section_codes(rules)` | 從規則 `narrative_codes` 欄位收集 `{section: [code]}`。 |
| `load_narrative_filter(path, industry)` | 載入 narrative_filter JSON 並按產業過濾。 |
| `main()` | CLI 入口。 |

### [`utils/xlsx_to_indicators.py`](../src/utils/xlsx_to_indicators.py) — **EXE**

xlsx → rules + narrative_filter 的**唯一轉換器**。EXE 流程每次執行都呼叫這個。

| 函式 | 用途 |
|------|------|
| `convert(xlsx_path, indicator_sheet=..., filter_sheet=..., config_out=None, filter_out=None)` | 主入口。 |
| `parse_indicator_sheet(sheet)` | 解析「指標」sheet → `{industry: [Rule]}`。 |
| `parse_filter_sheet(sheet)` | 解析「敘事指標」sheet → narrative_filter。 |
| `main(argv=None)` | CLI 入口（debug 用，把轉換結果落地）。 |

### [`utils/html_to_json.py`](../src/utils/html_to_json.py) — **EXE**

| 函式 | 用途 |
|------|------|
| `convert_html_files_to_dict(html_files, tag_table=None)` | 主入口：4 份 HTML → `Report`（含 `_period_dates`、`_skipped` notes）。 |
| `convert_html_to_json(html_files, output_path, tag_table=None)` | 連同寫檔。 |
| `main(argv=None)` | CLI 入口（4 個位置參數）。 |

### [`utils/simple_convert.py`](../src/utils/simple_convert.py) — Util

| 函式 | 用途 |
|------|------|
| `preprocess(data, period_dates=None)` | 預處理：單位格式化 + 趨勢推斷 + 期別 key → 日期 key。 |
| `convert_grouped_report(grouped, period_dates)` | `GroupedReport` → 含實際日期 key 的格式。 |
| `UNIT_FORMATTERS` | `{單位: 格式化函式}` 對應表（仟元 / % / 天 / 倍）。 |

### [`utils/convert_indicators.py`](../src/utils/convert_indicators.py) — Legacy

舊版 CSV → indicator JSON 轉換器。`xlsx_to_indicators` 內部仍會呼叫部分共用解析邏輯，但 EXE 入口已改吃 xlsx。

### [`utils/xlsx_to_report_json.py`](../src/utils/xlsx_to_report_json.py) — One-off

單一公司 Excel 財報 → Report JSON（依工作表配置代碼前綴 `TIBA`/`TIBB`/`TIBC`/`TIBD`）。dev-only，不在 EXE 路徑。

### [`utils/csv_to_report_json.py`](../src/utils/csv_to_report_json.py) — One-off

從多家測試案例 CSV 萃取指定公司，輸出個別 Report JSON。dev-only。

### [`utils/convert_report.py`](../src/utils/convert_report.py) — Legacy / One-off

批次將 LLM 回傳的 JSON TXT 轉為帶章節標題的段落格式。

### [`utils/convert_to_docx.py`](../src/utils/convert_to_docx.py) — One-off

將分析結果 TXT 整理為 Word 文件。

---

## scripts/ 入口

### [`scripts/main.py`](../scripts/main.py) — **EXE 入口**

PyInstaller 打包成 `risk_analysis`。流程：

| 函式 | 用途 |
|------|------|
| `main()` | CLI / stdin 兩種模式分派。 |
| `_parse_cli_args` / `_parse_stdin_args` | 兩種輸入解析。 |
| `_validate_args` | 必填檢查。 |
| `_resolve_paths` | 找 xlsx + 兩份 prompt 模板 + tag_table。 |
| `_load_rules_and_filter` | 呼叫 `xlsx_to_indicators.convert` 並落地 audit JSON。 |
| `build_report_from_html` | 呼叫 `html_to_json.convert_html_files_to_dict`。 |
| `run_pipeline` | 建構 `ReportPipeline` 並 `run`。 |
| `assemble_exe_output` | 包成 `ExeOutput`。 |
| `_write_output` | 寫檔 / `--stdout`。 |
| `_exit_error` | 例外 → `ExeError` JSON + exit 1/2/3。 |

### [`scripts/risk_checker.py`](../scripts/risk_checker.py) — Legacy CLI

JSON-driven 流程，僅供 debug 與回歸。**不打包 EXE**。

### [`scripts/batch_test.py`](../scripts/batch_test.py) — Util

讀 `inputs/report/新測試案例_json/*.json` 跑回歸，產出 ExeOutput。打包前驗證用。

### [`scripts/report_gen.py`](../scripts/report_gen.py) — One-off

將 risk/narrative prompts 送 LLM API，回傳格式化段落。**外部工具**，不屬主流程。

### [`scripts/simple_test.py`](../scripts/simple_test.py) — One-off

從 pre-cached report JSON 跑類 main.py 流程，dev 快速迭代用。

---

## 分類速查

| 類別 | 檔案 |
|------|------|
| **EXE 路徑必經** | `scripts/main.py`、`utils/xlsx_to_indicators.py`、`utils/html_to_json.py`、`utils/combine_prompt.py`、`utils/narrative.py`、`risk_engine/*` |
| **Legacy（debug 保留）** | `scripts/risk_checker.py`、`utils/convert_indicators.py`、`utils/convert_report.py` |
| **One-off 工具** | `scripts/batch_test.py`、`scripts/report_gen.py`、`scripts/simple_test.py`、`utils/xlsx_to_report_json.py`、`utils/csv_to_report_json.py`、`utils/convert_to_docx.py`、`utils/simple_convert.py`（部分） |

新人若不確定改哪個，先看是否屬於「EXE 路徑必經」。
