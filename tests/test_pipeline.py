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


def _nf_item(key, expression, display_name="", unit=""):
    return {
        "key": key, "expression": expression,
        "display_name": display_name, "unit": unit,
    }


class TestFilterAndGroup:
    def test_with_filter(self, report, rules):
        nf = {
            "財務結構": [
                _nf_item(
                    "TIBA009", "TIBA009",
                    display_name="非流動資產", unit="仟元",
                ),
                _nf_item(
                    "TIBA040", "TIBA040",
                    display_name="權益總額", unit="仟元",
                ),
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
        # ReportRow 形狀仍維持 simple_convert 相容
        row = grouped["財務結構"]["TIBA040"]
        assert set(row.keys()) >= {
            "FA_CANME", "單位",
            "Current", "Period_2", "Period_3",
        }

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

    def test_missing_code_kept_with_none(
        self, report, rules,
    ):
        """S-G4：缺值靜默 — 缺漏代碼仍保留 row，三期皆 None。"""
        nf = {
            "財務結構": [
                _nf_item(
                    "TIBA009", "TIBA009",
                    display_name="非流動資產", unit="仟元",
                ),
                _nf_item(
                    "MISSING", "MISSING",
                    display_name="缺失", unit="仟元",
                ),
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
            "TIBA009", "MISSING",
        ]
        row = grouped["財務結構"]["MISSING"]
        assert row["Current"] is None
        assert row["Period_2"] is None
        assert row["Period_3"] is None


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
                _nf_item(
                    "TIBA040", "TIBA040",
                    display_name="權益總額", unit="仟元",
                ),
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
