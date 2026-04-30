# 打包與部署 — `risk_analysis.exe`

本目錄收錄 EXE 化所需的資產：

| 檔案 / 目錄 | 用途 |
|------|------|
| `risk_analysis.spec` | PyInstaller 打包規格 |
| `sample/` | 範例同層資源（設定檔、prompt 模板、tag table） |
| 本檔 | 打包步驟、部署目錄結構說明 |

> **Smoke test 腳本**：見 `../scripts/smoke_test.sh`（POSIX）／`../scripts/smoke_test.ps1`（Windows）。

---

## 1. 打包步驟

需求：Windows + Python ≥ 3.10。

```powershell
# 在乾淨 venv 內安裝
python -m venv .venv
.venv\Scripts\activate
pip install pyinstaller

# 從 repo root 執行
pyinstaller build\risk_analysis.spec
```

成功後產出：`dist\risk_analysis.exe`

特性：
- onefile：單一 exe，方便上游部署
- console 模式：可由 stdout 讀回 JSON
- 排除 `pandas` / `numpy` / `docx` 等業務外依賴，控制 exe 體積

---

## 2. 部署目錄結構

把 `dist\risk_analysis.exe` 複製到部署目錄，**並在同層放置以下檔案**：

```
deploy/
├── risk_analysis.exe
├── indicators_config.json       # 必要：指標規則
├── risk_user_prompt.txt         # 必要：風險 prompt 模板
├── narrative_user_prompt.txt    # 必要：敘事 prompt 模板
├── tag_table.csv                # 選用：科目代碼對照
├── log/                         # 自動建立：每次執行寫入 timestamp + request_id 命名的 log
└── output/                      # 自動建立：未指定 -o 時的預設產出目錄
```

`sample/` 子目錄提供一組可直接搬到部署目錄的範本（除 4 個 HTML 財報檔需自備）。

---

## 3. 介面契約

詳見 `scripts/main.py` 開頭 docstring 與 `tests/test_main.py`。重點：

**輸入**
- CLI 模式：`risk_analysis.exe <h1> <h2> <h3> <h4> --industry <name> [--customer ...] [--date ...] [--request-id ...] [-o ...] [--stdout] [--debug]`
- stdin 模式：`echo '{...}' | risk_analysis.exe --stdin [--stdout]`

**成功輸出 JSON**
```json
{
  "schema_version": "1.0",
  "request_id": "...",
  "industry": "...",
  "narrative_prompt": "...",
  "risk_prompt": "...",
  "grouped_report": { ... },
  "risk_report": { ... },
  "customer_id": "...",       // 選填
  "report_date": "..."        // 選填
}
```

**錯誤 JSON**（`--stdout` 時）
```json
{
  "error": "...",
  "error_code": "INVALID_ARGS | MISSING_FILE | CONFIG_ERROR | PROCESSING_ERROR",
  "request_id": "..."
}
```

**Exit code**

| code | 意義 |
|------|------|
| 0 | 成功 |
| 1 | `INVALID_ARGS` 參數驗證或 stdin 解析錯誤 |
| 2 | `MISSING_FILE` / `CONFIG_ERROR` 設定或檔案問題 |
| 3 | `PROCESSING_ERROR` 其他未預期錯誤 |

---

## 4. 併發呼叫保證

- `request_id` 預設自動產生 8 碼 hex；上游可覆寫以便追蹤
- log 檔名：`log/<timestamp>_<request_id>.log` — 不同請求互不覆蓋
- 預設 output 檔名：`output/result_<request_id>_<timestamp>.json`，**寫入路徑相對於 exe 同層而非 cwd**，避免上游併發呼叫時把產出檔寫到呼叫方目錄
- `setup_logging` 對同一 process 多次呼叫冪等；不會清掉外部已掛上的 handler

---

## 5. Smoke test

```bash
# 在 dist/ 中放好同層檔案 + 4 個 HTML 後
bash scripts/smoke_test.sh ./dist/risk_analysis path/to/sample
```

該腳本會：
1. 用 `--stdout` 跑一次 exe
2. 用 `jq` 驗證 JSON 含必要欄位（`schema_version`、`risk_prompt`、`narrative_prompt` 等）
3. 平行跑 5 份併發呼叫（不同 `request_id`），驗證輸出檔互不覆蓋
