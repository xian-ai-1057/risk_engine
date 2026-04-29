"""ReportPipeline 單元測試。"""
import pytest

from risk_engine.pipeline import ReportPipeline


@pytest.fixture
def report():
    return {
        "TIBA009": {
            "FA_CANME": "非流動資產", "單位": "仟元",
            "Current": 924470.0, "Period_2": 692225.0,
            "Period_3": 728073.0,
        },
        "TIBA040": {
            "FA_CANME": "權益總額", "單位": "仟元",
            "Current": 1099433.0, "Period_2": 1000000.0,
            "Period_3": 900000.0,
        },
    }


@pytest.fixture
def rules():
    return [
        {
            "section": "財務結構",
            "indicator_name": "負債權益比",
            "indicator_code": "TIBA009",
            "tag_id": "T1",
            "value_formula": "TIBA009",
            "compare_type": "absolute",
            "operator": ">",
            "threshold": 0.0,
            "risk_description": "X",
            "result_unit": "",
        },
    ]


class TestFilterAndGroup:
    def test_with_filter(self, report, rules):
        nf = {
            "財務結構": [
                {"code": "TIBA009", "name": "非流動資產"},
                {"code": "TIBA040", "name": "權益總額"},
            ],
        }
        pipe = ReportPipeline(
            report=report,
            rules=rules,
            narrative_prompt_template="X",
            risk_prompt_template="X",
            narrative_filter=nf,
        )
        grouped = pipe.filter_and_group()
        assert list(grouped.keys()) == ["財務結構"]
        assert list(grouped["財務結構"].keys()) == [
            "TIBA009", "TIBA040",
        ]

    def test_without_filter_returns_empty(
        self, report, rules,
    ):
        pipe = ReportPipeline(
            report=report,
            rules=rules,
            narrative_prompt_template="X",
            risk_prompt_template="X",
        )
        grouped = pipe.filter_and_group()
        assert grouped == {}

    def test_filter_skips_missing_codes(
        self, report, rules,
    ):
        nf = {
            "財務結構": [
                {"code": "TIBA009", "name": "非流動資產"},
                {"code": "MISSING", "name": "缺失"},
            ],
        }
        pipe = ReportPipeline(
            report=report,
            rules=rules,
            narrative_prompt_template="X",
            risk_prompt_template="X",
            narrative_filter=nf,
        )
        grouped = pipe.filter_and_group()
        assert list(grouped["財務結構"].keys()) == [
            "TIBA009",
        ]


class TestRiskPathIndependence:
    """Risk 路徑不應依賴 narrative_filter。"""

    def test_risk_works_without_filter(
        self, report, rules,
    ):
        pipe = ReportPipeline(
            report=report,
            rules=rules,
            narrative_prompt_template="X",
            risk_prompt_template="X",
        )
        risk_report, _ = pipe.build_risk_prompt()
        assert "sections" in risk_report
        assert "財務結構" in risk_report["sections"]

    def test_risk_unaffected_by_filter(
        self, report, rules,
    ):
        nf = {
            "財務結構": [
                {"code": "TIBA040", "name": "權益總額"},
            ],
        }
        pipe_no_filter = ReportPipeline(
            report=report, rules=rules,
            narrative_prompt_template="X",
            risk_prompt_template="X",
        )
        pipe_with_filter = ReportPipeline(
            report=report, rules=rules,
            narrative_prompt_template="X",
            risk_prompt_template="X",
            narrative_filter=nf,
        )
        rr1, _ = pipe_no_filter.build_risk_prompt()
        rr2, _ = pipe_with_filter.build_risk_prompt()
        assert rr1["sections"] == rr2["sections"]
