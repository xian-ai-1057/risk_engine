# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`risk_engine` — a financial-statement risk-judgement engine. It loads reports (CSV / JSON / HTML / Excel) and indicator rule configs (JSON), evaluates which risk rules trigger, and assembles narrative + risk prompts for an LLM. Primary domain language is Traditional Chinese; user-facing strings, indicator names, and threshold expressions (e.g. `>150%`, `較前期比率增加20%`, `(A) AND B OR C`) are Chinese — preserve them verbatim.

`README.md` is the authoritative spec (data shapes, formula syntax, threshold grammar, Pipeline / Function-flow / Data-flow diagrams). When changing semantics of formulas, thresholds, compare types, prompt-view stripping rules, or the LLM compact format, update README.md alongside the code.

## Layout

- `src/` is a src-layout package; tests and CLIs depend on `conftest.py` (repo root) and `pyproject.toml`'s `pythonpath = ["src"]` to resolve imports. Don't move or delete `conftest.py`.
- `src/risk_engine/` — core library. Public API is re-exported from `risk_engine/__init__.py`; prefer extending those exports rather than reaching into submodules from external code.
- `src/utils/` — converters and prompt assembly (Excel/HTML/CSV → Report JSON, narrative builders, `combine_prompt`). Treated as a sibling top-level package, not a subpackage of `risk_engine`.
- `scripts/risk_checker.py` — CLI entry point (also exposed as `risk-checker` console script).
- `data/` — sample indicator configs, prompt templates, tag tables. `data/prompt/*.txt` templates rely on placeholders `{{JSON_DATA}}`, `{{risk_results_1..5}}`, `{{narrative_1..5}}`.
- `build/` — PyInstaller spec + sample resources for the `risk_analysis.exe` distribution. EXE-aware path logic lives in `risk_engine/log_config.py` and `risk_engine/paths.py` (checks `sys.frozen`); keep that compatibility when touching path resolution.

## Architecture invariants

These cross-file rules matter more than any single function:

- **`None` propagates to `missing`.** Any missing operand → `evaluate_formula` returns `None` → rule status becomes `missing`. Never substitute defaults silently. Compound trees use three-valued short-circuit (see README "缺值傳播").
- **OR-before-AND parsing** in both `threshold._build_tree` and `checker` compound parsing — opposite of SQL/Python precedence. When adding compound logic, parenthesize tests explicitly.
- **Safe formula evaluator only.** `formula._safe_eval` is a hand-rolled recursive-descent parser (`_tokenize` + `_Parser`) allowing only `+ - * /` and parentheses. Never reintroduce `eval()` / `ast.literal_eval` on user-supplied formulas, and don't expand the operator set without updating `constants.OP_PATTERN` and the parser together.
- **Code suffix conventions.** `_PRV` → `Period_2`, `_PRV2` → `Period_3`, no suffix → `Current`. Resolution lives in `formula._resolve_code`; `extract_codes` strips suffixes and dedupes while preserving order.
- **Strategy dispatch for compare types.** `checker._HANDLERS` maps `compare_type` → handler. Add new compare types by writing `_check_xxx` and registering in `_HANDLERS`; don't branch on `compare_type` elsewhere.
- **Two prompt projections, kept distinct.**
  - `report.to_llm_format` — short-key compact format (`n`/`cur`/`prev`/`s`/`th`/`d`, statuses `T`/`N`/`M`). Used by CLI `--compact`.
  - `report.to_prompt_view` — strips raw codes/floats, keeps only `display`; non-triggered tags collapse to `{"status": "not_triggered"}`. This feeds `combine_prompt.render_prompt` for `{{risk_results_N}}`. Don't leak raw `indicator_code` or floats into LLM prompts.
- **Section → placeholder mapping is fixed.** `combine_prompt.SECTION_MAPPING` / `NARRATIVE_MAPPING` bind sections to placeholder indices 1..5 in this order: `財務結構`, `償債能力`, `經營效能`, `獲利能力`, `現金流量`. Section names outside this set silently fail to render — keep this list in sync if extended.
- **Risk vs Narrative are independent pipelines** sharing only the report. Risk is driven by `indicator.json` (rules); Narrative is driven by `narrative_filter.json` (per-section code lists). `ReportPipeline.run` composes both.
- **Custom exceptions for boundary failures.** `types.ReportLoadError` / `types.ConfigError` are caught in `risk_checker.main` and exit 1; raise these (not generic `Exception`) for load/config failures.

## Common commands

```bash
# Run all tests (≈92 tests; testpaths=tests, pythonpath=src configured in pyproject.toml)
pytest

# Single file / class / test
pytest tests/test_formula.py
pytest tests/test_checker.py::TestCheckCompound
pytest tests/test_formula.py::TestSafeEval::test_division_by_zero

# Coverage
pytest --cov=risk_engine --cov=utils

# CLI smoke run
python scripts/risk_checker.py \
    --report 財報.csv --config data/indicators_config_v3.json \
    --industry 7大指標 --customer A00001 --date 20241231 \
    -o result.json [--compact] [--narrative --narrative-filter <path>] [--debug]

# End-to-end smoke scripts (POSIX / Windows)
bash scripts/smoke_test.sh
pwsh scripts/smoke_test.ps1

# Excel → indicator.json + narrative_filter.json (utils is a top-level package)
python -m utils.xlsx_to_indicators 指標.xlsx \
    --config-out data/indicator.json --filter-out data/narrative_filter.json

# PyInstaller build (Windows)
pyinstaller build/risk_analysis.spec   # produces dist/risk_analysis.exe
```

There is no separate lint/format config; match surrounding style. Python ≥ 3.10 is required (uses `TypedDict`, `dict[str, Any]` PEP 604 syntax, etc.).

## When adding features

- **New compare type:** add `_check_<name>` in `checker.py`, register in `_HANDLERS`, add a `compare_type` branch in `threshold.parse_threshold` if it needs new Chinese surface syntax, add tests in `test_checker.py` and `test_threshold.py`.
- **New Chinese threshold pattern:** add a `re.match` branch in `threshold.parse_threshold` returning a dict with `compare_type`. Full-width `＞`/`＜`/`＝` are normalized upstream.
- **New unit formatter:** extend `utils/simple_convert.UNIT_FORMATTERS`. Unit inference rules (formula-level) live in `formula.classify_formula` — same-unit division becomes dimensionless; trailing `*<const>` rescales but keeps operand units.
- **Meta-rules (multi-rule joint triggers):** scaffolded in `post_rules.py`. The intended extension point is a `node_type == "tag_ref"` branch in `checker.evaluate_node`; `apply_post_rules` is currently pass-through.
