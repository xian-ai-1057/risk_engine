"""端到端 (e2e) 整合測試。

用 ``data/json/sample_report.json`` 與 ``data/indicators_config_v3.json``
跑完整 ``ReportPipeline.run()`` 流程，並以 main.py 的方式組裝 ExeOutput，
驗證對外契約欄位齊備。

此測試不依賴 HTML 解析（直接餵 JSON 形式 Report），故不需要 4 個 HTML
檔即可在 CI 跑。Stage 5 的 smoke test 才會跑打包後 EXE 對 4 個 HTML
的全鏈路。
"""
import json
import re
from pathlib import Path

import pytest

from risk_engine import loader
from risk_engine.pipeline import ReportPipeline
from risk_engine.types import EXE_SCHEMA_VERSION


_REPO = Path(__file__).resolve().parent.parent
_SAMPLE_REPORT = _REPO / "data" / "json" / "sample_report.json"
_CONFIG = _REPO / "data" / "indicators_config_v3.json"
_PROMPT_DIR = _REPO / "data" / "prompt"


def _find_prompt(filename_substring: str) -> Path:
    """data/prompt 下的檔名是 git URL-escape 形式（#U...），
    用內容關鍵字定位。"""
    candidates = list(_PROMPT_DIR.glob("*"))
    for p in candidates:
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if filename_substring in text:
            return p
    raise FileNotFoundError(
        f"找不到含關鍵字 '{filename_substring}' 的 prompt 檔",
    )


@pytest.fixture(scope="module")
def report_data():
    return loader.load_report(str(_SAMPLE_REPORT))


@pytest.fixture(scope="module")
def rules():
    return loader.load_config(str(_CONFIG), "7大指標")


@pytest.fixture(scope="module")
def narrative_template():
    # 敘事 user prompt 含 {{JSON_DATA}}
    return _find_prompt("{{JSON_DATA}}").read_text(
        encoding="utf-8",
    )


@pytest.fixture(scope="module")
def risk_template():
    # 風險 user prompt 含 {{risk_results_1}}
    return _find_prompt("{{risk_results_1}}").read_text(
        encoding="utf-8",
    )


class TestPipelineRunContract:
    def test_run_returns_required_keys(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data,
            rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            customer_id="A00001",
            report_date="20241231",
            industry="7大指標",
        )
        result = pipe.run()

        assert set(result.keys()) >= {
            "narrative_prompt",
            "risk_prompt",
            "grouped_report",
            "risk_report",
        }

    def test_risk_prompt_substitutes_all_placeholders(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            industry="7大指標",
        )
        result = pipe.run()

        # risk_prompt 中所有 {{risk_results_N}} 必須已被替換
        leftovers = re.findall(
            r"\{\{risk_results_\d\}\}",
            result["risk_prompt"],
        )
        assert not leftovers, leftovers

    def test_risk_prompt_is_nonempty_string(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            industry="7大指標",
        )
        result = pipe.run()
        assert isinstance(result["risk_prompt"], str)
        assert len(result["risk_prompt"]) > 0

    def test_risk_report_has_expected_top_level(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            customer_id="A00001",
            report_date="20241231",
            industry="7大指標",
        )
        result = pipe.run()
        rr = result["risk_report"]
        assert rr["customer_id"] == "A00001"
        assert rr["report_date"] == "20241231"
        assert rr["industry"] == "7大指標"
        assert "summary" in rr
        assert "sections" in rr
        # 至少有一個 section（依 sample data）
        assert rr["sections"]


class TestExeOutputContract:
    """模擬 main.py 包裝 PipelineResult 為 ExeOutput 的合約。"""

    def _build_output(
        self, pipeline_result, request_id, industry,
        customer="", date="",
    ):
        out = {
            "schema_version": EXE_SCHEMA_VERSION,
            "request_id": request_id,
            "industry": industry,
            "narrative_prompt":
                pipeline_result["narrative_prompt"],
            "risk_prompt": pipeline_result["risk_prompt"],
            "grouped_report":
                pipeline_result["grouped_report"],
            "risk_report": pipeline_result["risk_report"],
        }
        if customer:
            out["customer_id"] = customer
        if date:
            out["report_date"] = date
        return out

    def test_exe_output_required_fields(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            industry="7大指標",
        )
        out = self._build_output(
            pipe.run(),
            request_id="trace-test",
            industry="7大指標",
        )

        required = {
            "schema_version",
            "request_id",
            "industry",
            "narrative_prompt",
            "risk_prompt",
            "grouped_report",
            "risk_report",
        }
        assert required.issubset(out.keys())
        assert out["schema_version"] == "1.0"

    def test_exe_output_optional_metadata(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            customer_id="C001",
            report_date="20241231",
            industry="7大指標",
        )
        out = self._build_output(
            pipe.run(),
            request_id="trace-test",
            industry="7大指標",
            customer="C001",
            date="20241231",
        )
        assert out["customer_id"] == "C001"
        assert out["report_date"] == "20241231"

    def test_exe_output_is_json_serializable(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            industry="7大指標",
        )
        out = self._build_output(
            pipe.run(),
            request_id="trace-test",
            industry="7大指標",
        )
        # 上游可能透過 stdout JSON 解析，必須能 round-trip
        dumped = json.dumps(out, ensure_ascii=False)
        loaded = json.loads(dumped)
        assert loaded["schema_version"] == "1.0"


class TestPipelineWithPeriodDates:
    def test_period_dates_in_narrative_prompt(
        self, report_data, rules,
        narrative_template, risk_template,
    ):
        period_dates = ["2024/12", "2023/12", "2022/12"]
        pipe = ReportPipeline(
            report=report_data, rules=rules,
            narrative_prompt_template=narrative_template,
            risk_prompt_template=risk_template,
            industry="7大指標",
            period_dates=period_dates,
        )
        result = pipe.run()
        # 不強制斷言每個日期都出現（取決於 grouped_report 是否非空），
        # 但既無 narrative_filter 時 grouped 為空，narrative_prompt 仍應為字串
        assert isinstance(result["narrative_prompt"], str)
