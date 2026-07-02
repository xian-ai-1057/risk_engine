"""post_rules 模組單元測試。

`apply_post_rules` 目前是 pass-through 預留 API（標記為 deprecated，
等 meta-rule 規格定案後啟用）。本檔案鎖定 pass-through 行為，
確保未來實作變動時不會無聲破壞現況。
"""
import warnings

from risk_engine.post_rules import apply_post_rules


def _sample_full_report():
    return {
        "customer_id": "C001",
        "report_date": "20260101",
        "industry": "7大指標",
        "sections": {
            "財務結構": [
                {
                    "indicator_name": "X",
                    "taggings": [
                        {"tag_id": "T1", "status": "triggered"},
                    ],
                },
            ],
        },
        "summary": {
            "triggered": 1,
            "not_triggered": 0,
            "missing": 0,
        },
    }


class TestApplyPostRulesPassThrough:
    def test_none_meta_rules_returns_input(self):
        report = _sample_full_report()
        assert apply_post_rules(report, None) is report

    def test_empty_meta_rules_returns_input(self):
        report = _sample_full_report()
        assert apply_post_rules(report, []) is report

    def test_non_empty_meta_rules_warns_and_passes_through(self):
        report = _sample_full_report()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            result = apply_post_rules(
                report,
                [{"meta_tag_id": "META_001"}],
            )
        # pass-through: report 不被修改
        assert result is report
        # DeprecationWarning 應觸發
        assert any(
            issubclass(w.category, DeprecationWarning)
            for w in caught
        )
