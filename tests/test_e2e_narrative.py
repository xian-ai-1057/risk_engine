"""端到端：narrative_filter (新 schema) + 真實 sample_report → 比對 S4.3。

Spec 對應：plan Phase 4 / S4.1〜S4.3。

不依賴 pandas / xlsx I/O — filter 直接以 dict 內存構造，
等同於 xlsx_to_indicators.parse_filter_sheet 產出的形狀，
聚焦 narrative 模組對 sample_report 的計算正確性。
"""
from pathlib import Path

import pytest

from risk_engine import loader
from utils import narrative

SAMPLE_REPORT = (
    Path(__file__).resolve().parents[1]
    / "data" / "json" / "sample_report.json"
)


@pytest.fixture(scope="module")
def report():
    return loader.load_report(str(SAMPLE_REPORT))


@pytest.fixture
def narrative_filter():
    """對應 plan S4.2 的假 Excel `敘事指標` sheet。"""
    return {
        "財務結構": [
            {
                "key": "TIBA040",
                "display_name": "",
                "expression": "TIBA040",
                "unit": "",
            },
            {
                "key": "TIBA009",
                "display_name": "非流動資產（扣除其他非流動資產）",
                "expression": "TIBA009-TIBA014",
                "unit": "仟元",
            },
            {
                "key": "TIBB004",
                "display_name": "銀行借款+短期票券+公司債",
                "expression": "TIBB004*TIBA040/100",
                "unit": "仟元",
            },
        ],
        "償債能力": [
            {
                "key": "TIBB011",
                "display_name": "",
                "expression": "TIBB011",
                "unit": "",
            },
            {
                "key": "TIBB011_2",
                "display_name": "應收帳款收現天數變動量",
                "expression": "TIBB011-TIBB011_PRV",
                "unit": "天",
            },
        ],
    }


# ── 共用 ground truth（plan S4.1） ────────────────────

# (FA_CANME, 單位, Current, Period_2, Period_3)
GROUND_TRUTH = {
    "TIBA040": (
        "權益總額", "仟元",
        34_682_804.0, 32_579_930.0, 29_618_536.0,
    ),
    "TIBA009": (
        "非流動資產", "仟元",
        17_248_221.0, 18_081_568.0, 18_835_330.0,
    ),
    "TIBA014": (
        "其他非流動資產", "仟元",
        2_627_562.0, 1_741_996.0, 1_834_784.0,
    ),
    "TIBB004": (
        "(銀行借款+短期票券+公司債)/權益總額", "%",
        9.12, 10.22, 14.60,
    ),
    "TIBB011": (
        "365/(營業收入/應收票據及帳款)", "天",
        125.56, 88.20, 98.25,
    ),
}


class TestSampleReportGroundTruth:
    """先確認 sample_report.json 內容仍與 plan S4.1 一致。"""

    @pytest.mark.parametrize("code", list(GROUND_TRUTH))
    def test_value(self, report, code):
        name, unit, c, p2, p3 = GROUND_TRUTH[code]
        row = report[code]
        assert row["FA_CANME"] == name
        assert row["單位"] == unit
        assert row["Current"] == pytest.approx(c)
        assert row["Period_2"] == pytest.approx(p2)
        assert row["Period_3"] == pytest.approx(p3)


class TestE2ENarrative:
    """plan S4.3 端到端對拍。"""

    def test_pure_account_with_fallback(
        self, report, narrative_filter,
    ):
        grouped = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = grouped["財務結構"]["TIBA040"]
        # display_name / unit 留白 → fallback 至首 code
        assert row["FA_CANME"] == "權益總額"
        assert row["單位"] == "仟元"
        assert row["Current"] == pytest.approx(34_682_804.0)
        assert row["Period_2"] == pytest.approx(32_579_930.0)
        assert row["Period_3"] == pytest.approx(29_618_536.0)

    def test_combination_expression(
        self, report, narrative_filter,
    ):
        grouped = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = grouped["財務結構"]["TIBA009"]
        assert row["FA_CANME"] == (
            "非流動資產（扣除其他非流動資產）"
        )
        assert row["單位"] == "仟元"
        # TIBA009 - TIBA014
        assert row["Current"] == pytest.approx(
            17_248_221.0 - 2_627_562.0,
        )
        assert row["Period_2"] == pytest.approx(
            18_081_568.0 - 1_741_996.0,
        )
        assert row["Period_3"] == pytest.approx(
            18_835_330.0 - 1_834_784.0,
        )

    def test_ratio_to_amount_is_core_use_case(
        self, report, narrative_filter,
    ):
        """核心需求：TIBB004 比率 → 絕對金額。"""
        grouped = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = grouped["財務結構"]["TIBB004"]
        assert row["FA_CANME"] == "銀行借款+短期票券+公司債"
        assert row["單位"] == "仟元"
        assert row["Current"] == pytest.approx(
            9.12 * 34_682_804.0 / 100, rel=1e-9,
        )
        assert row["Period_2"] == pytest.approx(
            10.22 * 32_579_930.0 / 100, rel=1e-9,
        )
        assert row["Period_3"] == pytest.approx(
            14.60 * 29_618_536.0 / 100, rel=1e-9,
        )
        # 大致數值（plan S4.3）
        assert int(row["Current"]) == 3_163_071
        assert int(row["Period_2"]) == 3_329_668
        assert int(row["Period_3"]) == 4_324_306

    def test_pure_account_no_overrides(
        self, report, narrative_filter,
    ):
        grouped = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = grouped["償債能力"]["TIBB011"]
        # display_name / unit 全 fallback
        assert row["FA_CANME"] == (
            "365/(營業收入/應收票據及帳款)"
        )
        assert row["單位"] == "天"
        assert row["Current"] == pytest.approx(125.56)
        assert row["Period_2"] == pytest.approx(88.20)
        assert row["Period_3"] == pytest.approx(98.25)

    def test_prv_transparent_semantics(
        self, report, narrative_filter,
    ):
        """`_PRV` 永遠對應 Period_2，不隨三期 base 漂移。"""
        grouped = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = grouped["償債能力"]["TIBB011_2"]
        assert row["FA_CANME"] == "應收帳款收現天數變動量"
        assert row["單位"] == "天"
        # Current(125.56) - PRV→Period_2(88.20)
        assert row["Current"] == pytest.approx(37.36)
        # Period_2(88.20) - PRV→Period_2(88.20)
        assert row["Period_2"] == pytest.approx(0.0)
        # Period_3(98.25) - PRV→Period_2(88.20)
        assert row["Period_3"] == pytest.approx(10.05)

    def test_grouped_structure_compatible_with_simple_convert(
        self, report, narrative_filter,
    ):
        """S-G3：每筆 row 必含 simple_convert 預期的 5 鍵。"""
        grouped = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        for section, rows in grouped.items():
            for key, row in rows.items():
                assert set(row.keys()) >= {
                    "FA_CANME", "單位",
                    "Current", "Period_2", "Period_3",
                }, f"{section}/{key} 缺鍵"
