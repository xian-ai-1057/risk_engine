"""Tests for the 風險分析Demo web layer (web/app.py).

Skipped entirely when the optional ``[web]`` deps aren't installed, so the
core engine test suite stays green without FastAPI/uvicorn present.
"""
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="web extra not installed")
pytest.importorskip("httpx", reason="fastapi TestClient needs httpx")
pytest.importorskip("multipart", reason="python-multipart not installed")

from fastapi.testclient import TestClient  # noqa: E402

from web import app as web_app  # noqa: E402
from web import services  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE = _REPO_ROOT / "inputs" / "json_sample" / "final_results.json"


@pytest.fixture()
def client() -> TestClient:
    return TestClient(web_app.app)


def _dummy_files() -> dict:
    """4 non-empty HTML uploads in the fixed slot order."""
    blob = b"<html><body></body></html>"
    return {
        "file_overview": ("overview.html", blob, "text/html"),
        "file_ratio": ("ratio.html", blob, "text/html"),
        "file_cashflow": ("cashflow.html", blob, "text/html"),
        "file_equity": ("equity.html", blob, "text/html"),
    }


def test_index_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "風險分析" in r.text


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["has_xlsx"] is True


def test_industries(client: TestClient) -> None:
    r = client.get("/api/industries")
    assert r.status_code == 200
    industries = r.json()["industries"]
    assert isinstance(industries, list)
    assert "7大指標" in industries


def test_sample_matches_fixture(client: TestClient) -> None:
    r = client.get("/api/sample")
    assert r.status_code == 200
    body = r.json()
    expected = json.loads(_SAMPLE.read_text(encoding="utf-8"))
    assert body == expected
    # shape the front-end binds against
    assert "summary" in body["risk_report"]
    assert set(body["grouped_report"]) & {"財務結構", "現金流量"}


def test_analyze_bad_industry_returns_400(client: TestClient) -> None:
    # run_report validates the industry before touching the HTML, so dummy
    # files are enough to exercise the ConfigError -> 400 mapping.
    r = client.post(
        "/api/analyze",
        files=_dummy_files(),
        data={"industry": "不存在的產業"},
    )
    assert r.status_code == 400
    assert "不存在的產業" in r.json()["detail"]


def test_analyze_empty_file_returns_400(client: TestClient) -> None:
    files = _dummy_files()
    files["file_overview"] = ("overview.html", b"", "text/html")
    r = client.post(
        "/api/analyze", files=files, data={"industry": "7大指標"},
    )
    assert r.status_code == 400
    assert "空" in r.json()["detail"]


def test_analyze_success_mocked(client: TestClient, monkeypatch) -> None:
    """Route wiring: a successful engine run is returned pass-through."""
    sample = json.loads(_SAMPLE.read_text(encoding="utf-8"))

    def _fake_analyze(inp: services.AnalyzeInputs) -> dict:
        assert len(inp.files) == 4
        assert inp.industry == "7大指標"
        return sample

    monkeypatch.setattr(services, "analyze", _fake_analyze)
    r = client.post(
        "/api/analyze", files=_dummy_files(), data={"industry": "7大指標"},
    )
    assert r.status_code == 200
    assert r.json()["risk_report"]["summary"] == sample["risk_report"]["summary"]
