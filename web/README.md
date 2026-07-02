# 風險分析Demo — Web 介面

財報風險判斷引擎的網頁介面：上傳 4 份財報 HTML、選擇產業別，直接呼叫
`risk_engine.api.run_report` 取得風險判定結果，並可選擇性呼叫 LLM 生成敘述段落。

這是**選用**模組，與核心引擎、EXE 打包完全隔離（`build/risk_analysis.spec`
的 `excludes` 顯式排除 `web` / `fastapi` / `uvicorn` 等，確保 EXE 不受影響）。

## 安裝與啟動

```bash
pip install -e ".[web]"        # 安裝 fastapi / uvicorn / python-multipart
python -m web                  # → http://127.0.0.1:8000
# 或
uvicorn web.app:app --reload
# 或（editable install 後）
risk-web
```

環境變數（皆為選用）：

| 變數 | 預設 | 說明 |
|---|---|---|
| `RISK_WEB_HOST` | `127.0.0.1` | 綁定位址 |
| `RISK_WEB_PORT` | `8000` | 綁定埠 |
| `RISK_WEB_RELOAD` | （關） | 設 `1`/`true` 開啟熱重載 |
| `RISK_WEB_RESOURCE_DIR` | `<repo>/deploy` | 指標 xlsx 與 prompt 模板所在目錄 |

指標 xlsx（`indicators_config_V*.xlsx`）與兩份 user prompt 模板
（`risk_user_prompt_V*.txt` / `narrative_user_prompt_V*.txt`）由後端從資源目錄
以版本化檔名自動探測（重用 `scripts.main._resolve_paths`）；LLM 用的 system
prompt 取自 `inputs/prompt/`。

## API

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/` | 前端單頁 |
| `GET` | `/api/health` | 伺服器資源可用性 |
| `GET` | `/api/industries` | 從指標 xlsx 取得產業別清單 |
| `GET` | `/api/sample` | 內建範例輸出（`inputs/json_sample/final_results.json`），供零輸入預覽 |
| `POST` | `/api/analyze` | `multipart/form-data`：4 份 HTML（`file_overview` / `file_ratio` / `file_cashflow` / `file_equity`）+ `industry`，選填 `customer_id` / `report_date` / `generate` / `llm_base_url` / `llm_model` / `llm_api_key` |

錯誤對應：`ConfigError` / `ReportLoadError`（產業不存在、缺 LLM 設定、財報無法解析）→ **400**；伺服器缺資源 → **500**。

## LLM 敘述生成

前端「呼叫 LLM 生成敘述段落」開關開啟後，需填入 OpenAI 相容端點的
Base URL / 模型 / API Key。金鑰僅於當次請求傳給引擎，**不會被儲存或記錄**。

## 前端

`web/static/`（原生 HTML/CSS/JS，無建置步驟）依引擎輸出的資料契約呈現：
風險摘要儀表板、五段落分頁（風險指標卡 + 多期財報趨勢表）、可折疊的 prompt
面板，以及 LLM 生成段落。狀態色：`triggered`=紅 / `not_triggered`=綠 /
`missing`=灰。

> 視覺設計以 Claude Design 稿 `風險分析Demo.dc.html`（放入 `web/design/`）為準；
> 目前為符合資料契約的預設版面，取得設計稿後再依樣式微調（見
> [`web/design/README.md`](design/README.md)）。
