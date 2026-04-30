"""utils.narrative 模組單元測試。"""
import json

import pytest

from risk_engine import types
from utils import narrative


# ── 共用 fixtures ────────────────────────────────────

@pytest.fixture
def report():
    return {
        "TIBA009": {
            "FA_CANME": "非流動資產", "單位": "仟元",
            "Current": 924470.0, "Period_2": 692225.0,
            "Period_3": 728073.0,
        },
        "TIBA014": {
            "FA_CANME": "其他非流動資產", "單位": "仟元",
            "Current": 4084.0, "Period_2": 3198.0,
            "Period_3": 3247.0,
        },
        "TIBA040": {
            "FA_CANME": "權益總額", "單位": "仟元",
            "Current": 1099433.0, "Period_2": 1000000.0,
            "Period_3": 900000.0,
        },
        "TIBB004": {
            "FA_CANME": "(銀行借款+短期票券+公司債)/權益總額",
            "單位": "%",
            "Current": 9.12, "Period_2": 10.22,
            "Period_3": 14.6,
        },
        "TIBB011": {
            "FA_CANME": "365/(營業收入/應收票據及帳款)",
            "單位": "天",
            "Current": 125.56, "Period_2": 88.20,
            "Period_3": 98.25,
        },
        "TIBC014": {
            "FA_CANME": "", "單位": "仟元",
            "Current": 100.0, "Period_2": 200.0,
            "Period_3": 300.0,
        },
    }


def _item(key, expression, display_name="", unit=""):
    return {
        "key": key, "expression": expression,
        "display_name": display_name, "unit": unit,
    }


@pytest.fixture
def narrative_filter():
    return {
        "財務結構": [
            _item("TIBA009", "TIBA009"),
            _item("TIBA040", "TIBA040"),
        ],
        "現金流量": [
            _item(
                "TIBC014", "TIBC014",
                display_name="營業活動之淨現金流入(流出)",
            ),
        ],
    }


# ── build_grouped_narrative ──────────────────────────

class TestBuildGroupedNarrative:
    def test_pure_account(self, report, narrative_filter):
        result = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = result["財務結構"]["TIBA040"]
        assert row["FA_CANME"] == "權益總額"
        assert row["單位"] == "仟元"
        assert row["Current"] == 1099433.0
        assert row["Period_2"] == 1000000.0
        assert row["Period_3"] == 900000.0

    def test_sections_preserved(
        self, report, narrative_filter,
    ):
        result = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        assert list(result.keys()) == [
            "財務結構", "現金流量",
        ]

    def test_display_name_override(self, report):
        nf = {
            "財務結構": [
                _item(
                    "TIBA009", "TIBA009",
                    display_name="總資產（自訂）",
                ),
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        assert (
            result["財務結構"]["TIBA009"]["FA_CANME"]
            == "總資產（自訂）"
        )

    def test_display_name_fallback(self, report):
        """display_name 留白 → 取首 code 的 FA_CANME。"""
        nf = {
            "財務結構": [_item("TIBA009", "TIBA009")],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        assert (
            result["財務結構"]["TIBA009"]["FA_CANME"]
            == "非流動資產"
        )

    def test_unit_fallback(self, report):
        """unit 留白 → 取首 code 的 單位。"""
        nf = {
            "財務結構": [_item("TIBA009", "TIBA009")],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        assert (
            result["財務結構"]["TIBA009"]["單位"]
            == "仟元"
        )

    def test_unit_override(self, report):
        nf = {
            "財務結構": [
                _item(
                    "TIBB004", "TIBB004*TIBA040/100",
                    display_name="銀行借款+短期票券+公司債",
                    unit="仟元",
                ),
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        row = result["財務結構"]["TIBB004"]
        assert row["FA_CANME"] == "銀行借款+短期票券+公司債"
        assert row["單位"] == "仟元"

    def test_derived_ratio_to_amount(self, report):
        """S2.2：TIBB004*TIBA040/100 三期計算正確。"""
        nf = {
            "財務結構": [
                _item(
                    "TIBB004", "TIBB004*TIBA040/100",
                    display_name="銀行借款+短期票券+公司債",
                    unit="仟元",
                ),
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        row = result["財務結構"]["TIBB004"]
        assert row["Current"] == pytest.approx(
            9.12 * 1099433.0 / 100, rel=1e-6,
        )
        assert row["Period_2"] == pytest.approx(
            10.22 * 1000000.0 / 100, rel=1e-6,
        )
        assert row["Period_3"] == pytest.approx(
            14.6 * 900000.0 / 100, rel=1e-6,
        )

    def test_combination_expression(self, report):
        """TIBA009 - TIBA014 三期計算正確。"""
        nf = {
            "財務結構": [
                _item(
                    "TIBA009", "TIBA009-TIBA014",
                    display_name="非流動資產（扣除其他）",
                    unit="仟元",
                ),
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        row = result["財務結構"]["TIBA009"]
        assert row["Current"] == 924470.0 - 4084.0
        assert row["Period_2"] == 692225.0 - 3198.0
        assert row["Period_3"] == 728073.0 - 3247.0

    def test_prv_suffix_transparent_to_evaluate(self, report):
        """`_PRV` 是絕對對應 Period_2（與 risk 模組相同）。

        三期評估時，無後綴代碼隨 period base 移動，
        但 `_PRV` 永遠對 Period_2 取值（透傳 evaluate_formula）。
        """
        nf = {
            "償債能力": [
                _item(
                    "TIBB011", "TIBB011-TIBB011_PRV",
                    display_name="應收帳款收現天數變動量",
                    unit="天",
                ),
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        row = result["償債能力"]["TIBB011"]
        # Current(125.56) - PRV→Period_2(88.20)
        assert row["Current"] == pytest.approx(37.36)
        # Period_2(88.20) - PRV→Period_2(88.20) = 0
        assert row["Period_2"] == pytest.approx(0.0)
        # Period_3(98.25) - PRV→Period_2(88.20)
        assert row["Period_3"] == pytest.approx(10.05)

    def test_missing_code_returns_none(self, report):
        """expression 引用不存在代碼 → 三期皆 None，不丟例外。"""
        nf = {
            "財務結構": [
                _item("BOGUS", "BOGUS+TIBA009"),
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        row = result["財務結構"]["BOGUS"]
        assert row["Current"] is None
        assert row["Period_2"] is None
        assert row["Period_3"] is None

    def test_empty_filter(self, report):
        result = narrative.build_grouped_narrative(
            report, {},
        )
        assert result == {}


# ── build_narrative (list-style) ────────────────────

class TestBuildNarrativeListStyle:
    def test_basic(self, report, narrative_filter):
        result = narrative.build_narrative(
            report, narrative_filter,
        )
        assert list(result.keys()) == [
            "財務結構", "現金流量",
        ]
        assert isinstance(result["財務結構"], list)

    def test_item_shape(self, report, narrative_filter):
        result = narrative.build_narrative(
            report, narrative_filter,
        )
        # 第一筆 (TIBA009)
        item = result["財務結構"][0]
        assert set(item.keys()) >= {
            "name", "unit", "current",
            "period_2", "period_3",
        }
        assert item["name"] == "非流動資產"
        assert item["unit"] == "仟元"
        assert item["current"] == 924470.0


# ── load_narrative_filter ────────────────────────────

class TestLoadNarrativeFilter:
    def _write(self, tmp_path, data):
        path = tmp_path / "filter.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        return str(path)

    def test_found(self, tmp_path):
        data = {
            "7大指標": {
                "財務結構": [{
                    "key": "TIBA009",
                    "display_name": "非流動資產",
                    "expression": "TIBA009",
                    "unit": "仟元",
                }],
            },
        }
        result = narrative.load_narrative_filter(
            self._write(tmp_path, data), "7大指標",
        )
        assert result is not None
        assert "財務結構" in result

    def test_industry_not_found(self, tmp_path):
        result = narrative.load_narrative_filter(
            self._write(tmp_path, {"7大指標": {}}), "X",
        )
        assert result is None

    def test_file_not_found(self):
        assert narrative.load_narrative_filter(
            "/nonexistent.json", "X",
        ) is None

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid", encoding="utf-8")
        assert narrative.load_narrative_filter(
            str(path), "X",
        ) is None

    def test_unknown_section_warning(
        self, tmp_path, caplog,
    ):
        import logging
        data = {
            "7大指標": {
                "UNKNOWN_SECTION": [{
                    "key": "X",
                    "display_name": "Y",
                    "expression": "X",
                    "unit": "",
                }],
            },
        }
        with caplog.at_level(logging.WARNING):
            result = narrative.load_narrative_filter(
                self._write(tmp_path, data), "7大指標",
            )
        assert result is not None
        assert any(
            "UNKNOWN_SECTION" in r.message
            for r in caplog.records
        )

    def test_missing_required_field_raises(
        self, tmp_path,
    ):
        """S2.1：item 缺少必要欄位 → ConfigError。"""
        data = {
            "7大指標": {
                "財務結構": [{
                    "key": "TIBA009",
                    # 缺 display_name / expression / unit
                }],
            },
        }
        with pytest.raises(types.ConfigError):
            narrative.load_narrative_filter(
                self._write(tmp_path, data), "7大指標",
            )


# ── extract_section_codes (legacy, retained) ────────

class TestExtractSectionCodesLegacy:
    def test_from_formula(self):
        rules = [
            {
                "section": "財務結構",
                "value_formula": "TIBA009 + TIBA040",
                "compare_type": "absolute",
            },
        ]
        result = narrative.extract_section_codes(rules)
        assert "財務結構" in result
        assert "TIBA009" in result["財務結構"]
        assert "TIBA040" in result["財務結構"]

    def test_narrative_codes_override(self):
        rules = [
            {
                "section": "財務結構",
                "value_formula": "TIBA009",
                "compare_type": "absolute",
                "narrative_codes": ["TIBB001", "TIBB002"],
            },
        ]
        result = narrative.extract_section_codes(rules)
        assert result["財務結構"] == [
            "TIBB001", "TIBB002",
        ]


# ── format_narrative_text ────────────────────────────

class TestFormatNarrativeText:
    def test_basic(self):
        items = [
            {
                "name": "非流動資產", "unit": "仟元",
                "current": 924470.0, "period_2": 692225.0,
                "period_3": 728073.0,
            },
        ]
        text = narrative.format_narrative_text(items)
        assert "非流動資產" in text
        assert "仟元" in text
        assert "本期" in text
        assert "924,470.00" in text

    def test_empty(self):
        assert narrative.format_narrative_text([]) == ""
