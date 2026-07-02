"""FastAPI app for 風險分析Demo.

Routes:
  - ``GET  /``              → serve the single-page front-end.
  - ``GET  /static/*``      → static assets (css/js).
  - ``GET  /api/health``    → resource-availability snapshot for the UI.
  - ``GET  /api/industries``→ 產業別 list from the active指標 xlsx.
  - ``GET  /api/sample``    → bundled full-output sample (零輸入 demo path).
  - ``POST /api/analyze``   → run the real engine on 4 uploaded財報 HTML.

Error mapping mirrors the CLI's exit-code semantics as HTTP:
  ``ConfigError`` / ``ReportLoadError`` (bad 產業, missing LLM config,
  unparseable財報) → 400; missing server-side resources → 500; anything else
  → 500 with the request_id logged.
"""
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from risk_engine import types
from web import services
from web.models import HealthResponse, IndustriesResponse

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="風險分析Demo",
    description="財報風險判斷引擎 Web 介面",
    version="0.1.0",
)

app.mount(
    "/static",
    StaticFiles(directory=str(_STATIC_DIR)),
    name="static",
)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the single-page front-end."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/api/health", response_model=HealthResponse)
def api_health() -> HealthResponse:
    """Report whether the server-side resource files are present."""
    rdir = services.resource_dir()
    try:
        paths = services._resolve_paths(rdir)
        return HealthResponse(
            status="ok",
            resource_dir=rdir,
            has_xlsx=os.path.isfile(paths["xlsx"]),
            has_risk_prompt=os.path.isfile(paths["risk_user_prompt"]),
            has_narrative_prompt=os.path.isfile(
                paths["narrative_user_prompt"],
            ),
        )
    except FileNotFoundError:
        return HealthResponse(
            status="missing_resources",
            resource_dir=rdir,
            has_xlsx=False,
            has_risk_prompt=False,
            has_narrative_prompt=False,
        )


@app.get("/api/industries", response_model=IndustriesResponse)
def api_industries() -> IndustriesResponse:
    """List 產業別 from the active指標 xlsx."""
    try:
        industries = services.list_industries()
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=500, detail=f"伺服器缺少指標檔: {e}",
        )
    except (types.ConfigError, ValueError, KeyError) as e:
        raise HTTPException(
            status_code=500, detail=f"指標 xlsx 解析失敗: {e}",
        )
    return IndustriesResponse(industries=industries)


@app.get("/api/sample")
def api_sample() -> dict:
    """Return the bundled sample engine output (no engine run)."""
    try:
        return services.load_sample()
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="找不到範例輸出 (inputs/json_sample/final_results.json)",
        )


@app.post("/api/analyze")
async def api_analyze(
    file_overview: UploadFile = File(..., description="① 財務概況 HTML"),
    file_ratio: UploadFile = File(..., description="② 財務比率 HTML"),
    file_cashflow: UploadFile = File(..., description="③ 現金流量 HTML"),
    file_equity: UploadFile = File(..., description="④ 淨值調節 HTML"),
    industry: str = Form(..., description="產業別"),
    customer_id: str = Form(""),
    report_date: str = Form(""),
    generate: bool = Form(False, description="是否呼叫 LLM 生成敘述段落"),
    llm_base_url: str = Form(""),
    llm_api_key: str = Form(""),
    llm_model: str = Form(""),
) -> dict:
    """Run the real engine on the 4 uploaded財報 HTML and return its result."""
    request_id = uuid.uuid4().hex[:8]

    uploads = [file_overview, file_ratio, file_cashflow, file_equity]
    files: list[tuple[str, bytes]] = []
    for uf in uploads:
        content = await uf.read()
        if not content:
            raise HTTPException(
                status_code=400,
                detail=f"上傳檔案為空: {uf.filename or '(未命名)'}",
            )
        files.append((uf.filename or "upload.html", content))

    inp = services.AnalyzeInputs(
        files=files,
        industry=industry,
        customer_id=customer_id,
        report_date=report_date,
        request_id=request_id,
        generate=generate,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
    )

    try:
        return services.analyze(inp)
    except (types.ConfigError, types.ReportLoadError) as e:
        # bad 產業 / missing LLM config / unparseable財報 → client error
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        logger.error("resource missing (request_id=%s): %s", request_id, e)
        raise HTTPException(
            status_code=500, detail=f"伺服器缺少必要檔案: {e}",
        )
    except Exception as e:  # noqa: BLE001 — boundary handler, logs + 500
        logger.exception("analyze failed (request_id=%s)", request_id)
        raise HTTPException(
            status_code=500,
            detail=f"處理失敗 (request_id={request_id}): {e}",
        )


def main() -> None:
    """``python -m web`` / ``risk-web`` entrypoint — launch uvicorn."""
    import uvicorn

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.environ.get("RISK_WEB_HOST", "127.0.0.1")
    port = int(os.environ.get("RISK_WEB_PORT", "8000"))
    reload = os.environ.get("RISK_WEB_RELOAD", "").lower() in (
        "1", "true", "yes", "on",
    )
    logger.info("風險分析Demo → http://%s:%d", host, port)
    uvicorn.run("web.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
