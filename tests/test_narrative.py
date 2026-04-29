"""utils.narrative 模組單元測試。"""
import json

import pytest

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
        "TIBA040": {
            "FA_CANME": "權益總額", "單位": "仟元",
            "Current": 1099433.0, "Period_2": 1000000.0,
            "Period_3": 900000.0,
        },
        "TIBC014": {
            "FA_CANME": "", "單位": "仟元",
            "Current": 100.0, "Period_2": 200.0,
            "Period_3": 300.0,
        },
    }


@pytest.fixture
def narrative_filter():
    return {
        "財務結構": [
            {"code": "TIBA009", "name": "非流動資產"},
            {"code": "TIBA040", "name": "權益總額"},
            {"code": "MISSING", "name": "不存在"},
        ],
        "現金流量": [
            {
                "code": "TIBC014",
                "name": "營業活動之淨現金流入(流出)",
            },
        ],
    }


# ── build_grouped_narrative ──────────────────────────

class TestBuildGroupedNarrative:
    def test_basic(self, report, narrative_filter):
        result = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        assert list(result.keys()) == [
            "財務結構", "現金流量",
        ]

    def test_codes_filtered(
        self, report, narrative_filter,
    ):
        result = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        assert list(result["財務結構"].keys()) == [
            "TIBA009", "TIBA040",
        ]
        assert "MISSING" not in result["財務結構"]

    def test_row_content(self, report, narrative_filter):
        result = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        row = result["財務結構"]["TIBA009"]
        assert row["FA_CANME"] == "非流動資產"
        assert row["Current"] == 924470.0
        assert row["Period_2"] == 692225.0
        assert row["Period_3"] == 728073.0
        assert row["單位"] == "仟元"

    def test_fallback_name(
        self, report, narrative_filter,
    ):
        result = narrative.build_grouped_narrative(
            report, narrative_filter,
        )
        # TIBC014 has empty FA_CANME; filter name fills in
        assert (
            result["現金流量"]["TIBC014"]["FA_CANME"]
            == "營業活動之淨現金流入(流出)"
        )

    def test_empty_section_kept(self, report):
        nf = {
            "財務結構": [
                {"code": "NOEXIST", "name": "X"},
            ],
        }
        result = narrative.build_grouped_narrative(
            report, nf,
        )
        assert "財務結構" in result
        assert result["財務結構"] == {}

    def test_empty_filter(self, report):
        result = narrative.build_grouped_narrative(
            report, {},
        )
        assert result == {}


# ── build_narrative (list-style, filter-driven) ─────

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
        item = result["財務結構"][0]
        assert item["name"] == "非流動資產"
        assert item["unit"] == "仟元"
        assert item["current"] == 924470.0
        assert item["period_2"] == 692225.0
        assert item["period_3"] == 728073.0

    def test_fallback_name(
        self, report, narrative_filter,
    ):
        result = narrative.build_narrative(
            report, narrative_filter,
        )
        assert (
            result["現金流量"][0]["name"]
            == "營業活動之淨現金流入(流出)"
        )

    def test_only_filter_codes(
        self, report, narrative_filter,
    ):
        result = narrative.build_narrative(
            report, narrative_filter,
        )
        # Filter listed 3 codes in 財務結構, 1 missing in
        # report → 2 items
        assert len(result["財務結構"]) == 2


# ── load_narrative_filter ────────────────────────────

class TestLoadNarrativeFilter:
    def test_found(self, tmp_path):
        data = {
            "7大指標": {
                "財務結構": [
                    {"code": "TIBA009", "name": "非流動資產"},
                ],
            },
        }
        path = tmp_path / "filter.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        result = narrative.load_narrative_filter(
            str(path), "7大指標",
        )
        assert result is not None
        assert "財務結構" in result

    def test_industry_not_found(self, tmp_path):
        data = {"7大指標": {}}
        path = tmp_path / "filter.json"
        path.write_text(
            json.dumps(data), encoding="utf-8",
        )
        assert narrative.load_narrative_filter(
            str(path), "X",
        ) is None

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
                "UNKNOWN_SECTION": [
                    {"code": "X", "name": "Y"},
                ],
            },
        }
        path = tmp_path / "filter.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False),
            encoding="utf-8",
        )
        with caplog.at_level(logging.WARNING):
            result = narrative.load_narrative_filter(
                str(path), "7大指標",
            )
        assert result is not None
        assert any(
            "UNKNOWN_SECTION" in r.message
            for r in caplog.records
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
