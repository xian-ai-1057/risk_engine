"""risk_engine.api.run_report（程式化入口，無 argv）測試。

以 monkeypatch 換掉 xlsx / html / ReportPipeline / call_llm，驗證 run_report
的組裝與分支邏輯，不打真 API、不需真實 fixtures。
"""
from pathlib import Path

import pytest

from risk_engine import api, types

_SECTIONS = {k: f"{k} 段落" for k in ("4-1", "4-2", "4-3", "4-4", "4-5")}


def _write(p: Path, text: str) -> str:
    p.write_text(text, encoding="utf-8")
    return str(p)


class _StubPipe:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self):
        return {
            "narrative_prompt": "NP",
            "risk_prompt": "RP",
            "grouped_report": {"g": 1},
            "risk_report": {"r": 1},
        }


@pytest.fixture
def prompt_paths(tmp_path):
    return {
        "nu": _write(tmp_path / "nu.txt", "N {{JSON_DATA}}"),
        "ru": _write(tmp_path / "ru.txt", "R {{risk_results_1}}"),
        "ns": _write(tmp_path / "ns.txt", "NSYS"),
        "rs": _write(tmp_path / "rs.txt", "RSYS"),
    }


def _patch_common(monkeypatch):
    monkeypatch.setattr(
        "utils.xlsx_to_indicators.convert",
        lambda path: ({"7大指標": []}, {"7大指標": {}}, {"TIBA001": "X"}),
    )
    monkeypatch.setattr(
        "risk_engine.api.convert_html_files_to_dict",
        lambda files, tag_map=None: {"_period_dates": ["09/30/2024"]},
    )
    monkeypatch.setattr("risk_engine.api.ReportPipeline", _StubPipe)


class TestRunReport:
    def test_generate_returns_sections(self, monkeypatch, prompt_paths):
        _patch_common(monkeypatch)
        calls = []

        def fake_call(bu, ak, m, sys_p, user_p, **kw):
            calls.append((sys_p, user_p))
            return dict(_SECTIONS)

        monkeypatch.setattr("risk_engine.api.call_llm", fake_call)

        out = api.run_report(
            html_files=["a", "b", "c", "d"],
            industry="7大指標",
            xlsx_path="x.xlsx",
            narrative_user_prompt_path=prompt_paths["nu"],
            risk_user_prompt_path=prompt_paths["ru"],
            generate=True,
            narrative_sys_prompt_path=prompt_paths["ns"],
            risk_sys_prompt_path=prompt_paths["rs"],
            llm_base_url="http://x/v1",
            llm_api_key="k",
            llm_model="m",
            customer_id="C1",
            report_date="20240930",
        )

        assert out["narrative_sections"] == _SECTIONS
        assert out["risk_sections"] == _SECTIONS
        assert out["narrative_prompt"] == "NP"
        assert out["risk_prompt"] == "RP"
        assert out["customer_id"] == "C1"
        assert out["report_date"] == "20240930"
        # sys prompt 檔內容被讀出並配對正確的 user prompt
        assert ("NSYS", "NP") in calls
        assert ("RSYS", "RP") in calls

    def test_no_generate_has_no_sections(self, monkeypatch, prompt_paths):
        _patch_common(monkeypatch)
        monkeypatch.setattr(
            "risk_engine.api.call_llm",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("generate=False 不該呼叫模型")
            ),
        )

        out = api.run_report(
            html_files=["a", "b", "c", "d"],
            industry="7大指標",
            xlsx_path="x.xlsx",
            narrative_user_prompt_path=prompt_paths["nu"],
            risk_user_prompt_path=prompt_paths["ru"],
        )

        assert "narrative_sections" not in out
        assert "risk_sections" not in out
        assert out["risk_prompt"] == "RP"
        assert out["schema_version"] == types.EXE_SCHEMA_VERSION

    def test_unknown_industry_raises(self, monkeypatch, prompt_paths):
        _patch_common(monkeypatch)
        with pytest.raises(types.ConfigError):
            api.run_report(
                html_files=["a", "b", "c", "d"],
                industry="不存在",
                xlsx_path="x.xlsx",
                narrative_user_prompt_path=prompt_paths["nu"],
                risk_user_prompt_path=prompt_paths["ru"],
            )

    def test_generate_missing_llm_config_raises(
        self, monkeypatch, prompt_paths,
    ):
        _patch_common(monkeypatch)
        with pytest.raises(types.ConfigError):
            api.run_report(
                html_files=["a", "b", "c", "d"],
                industry="7大指標",
                xlsx_path="x.xlsx",
                narrative_user_prompt_path=prompt_paths["nu"],
                risk_user_prompt_path=prompt_paths["ru"],
                generate=True,  # 缺 llm_* / sys prompt
            )
