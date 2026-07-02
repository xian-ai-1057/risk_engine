"""utils.simple_convert 模組單元測試。

涵蓋：
- 各單位格式化器（仟元 / % / 天 / 倍）
- preprocess 雙層 / 單層結構
- convert_grouped_report 期間映射與排序
- 確認輸出**不含**「趨勢」欄位（移除趨勢判斷後的不變式）
"""

import pytest

from utils.simple_convert import (
    convert_grouped_report,
    convert_thousand_ntd,
    format_days,
    format_freq,
    format_percent,
    format_times,
    format_with_unit,
    preprocess,
)


# ── 格式化器 ──────────────────────────────────────


class TestConvertThousandNTD:

    def test_zero(self):
        assert convert_thousand_ntd(0) == "NTD 0元"

    def test_positive_thousand(self):
        assert convert_thousand_ntd(347500) == "NTD 347,500仟元"

    def test_negative_thousand(self):
        # 負值以會計式半形括號包住數字本身（幣別與單位在外）
        assert convert_thousand_ntd(-1234) == "NTD (1,234)仟元"

    def test_below_one_rounds_to_yuan(self):
        # 0.5 仟元 = 500 元
        assert convert_thousand_ntd(0.5) == "NTD 500元"

    def test_negative_below_one(self):
        assert convert_thousand_ntd(-0.123) == "NTD (123)元"

    def test_no_decimal_for_thousand(self):
        # 整數仟元不帶小數
        assert convert_thousand_ntd(1000) == "NTD 1,000仟元"

    def test_negative_with_display_absolute(self):
        # 科目名稱已含流出方向時，負值取絕對值顯示（不加負號、不加括號）
        assert convert_thousand_ntd(
            -1234, display_absolute=True,
        ) == "NTD 1,234仟元"

    def test_positive_with_display_absolute(self):
        # 旗標對正值無影響
        assert convert_thousand_ntd(
            1234, display_absolute=True,
        ) == "NTD 1,234仟元"

    def test_zero_with_display_absolute(self):
        # 0 與旗標無關
        assert convert_thousand_ntd(
            0, display_absolute=True,
        ) == "NTD 0元"

    def test_negative_below_one_with_display_absolute(self):
        assert convert_thousand_ntd(
            -0.123, display_absolute=True,
        ) == "NTD 123元"


class TestFormatWithUnit:

    def test_thousand_negative_default_wraps_parens(self):
        assert format_with_unit(-1234, "仟元") == "NTD (1,234)仟元"

    def test_thousand_negative_absolute_strips_sign(self):
        assert format_with_unit(
            -1234, "仟元", display_absolute=True,
        ) == "NTD 1,234仟元"

    def test_percent_negative_wraps_parens(self):
        assert format_with_unit(-12.34, "%") == "(12.34)%"

    def test_percent_display_absolute_strips_parens(self):
        assert format_with_unit(
            -12.34, "%", display_absolute=True,
        ) == "12.34%"

    def test_days_negative_wraps_parens(self):
        assert format_with_unit(-125.56, "天") == "(125.56)天"

    def test_days_display_absolute_strips_parens(self):
        assert format_with_unit(
            -125.56, "天", display_absolute=True,
        ) == "125.56天"

    def test_unknown_unit_returns_none(self):
        assert format_with_unit(123, "未知單位") is None


class TestRatioFormatters:

    def test_format_percent(self):
        assert format_percent(17.38) == "17.38%"

    def test_format_percent_rounding(self):
        assert format_percent(12.345) == "12.35%"  # banker's? actually .35

    def test_format_percent_negative(self):
        assert format_percent(-12.34) == "(12.34)%"

    def test_format_percent_negative_display_absolute(self):
        assert format_percent(-12.34, display_absolute=True) == "12.34%"

    def test_format_days(self):
        assert format_days(125.56) == "125.56天"

    def test_format_days_negative(self):
        assert format_days(-125.56) == "(125.56)天"

    def test_format_days_negative_display_absolute(self):
        assert format_days(-125.56, display_absolute=True) == "125.56天"

    def test_format_times(self):
        assert format_times(2.5) == "2.50倍"

    def test_format_times_negative(self):
        assert format_times(-2.5) == "(2.50)倍"

    def test_format_freq_negative(self):
        assert format_freq(-2.34) == "(2.34)次"


# ── preprocess ─────────────────────────────────────


@pytest.fixture
def two_layer_input():
    return {
        "財務結構": {
            "TIBA041": {
                "FA_CANME": "營業收入",
                "單位": "仟元",
                "12/31/2023": 386800.0,
                "12/31/2024": 347500.0,
                "03/31/2025": 65600.0,
            },
            "TIBB018": {
                "FA_CANME": "營業毛利率",
                "單位": "%",
                "12/31/2023": 17.38,
                "12/31/2024": 18.83,
                "03/31/2025": 15.51,
            },
        },
    }


@pytest.fixture
def single_layer_input():
    return {
        "TIBA041": {
            "FA_CANME": "營業收入",
            "單位": "仟元",
            "12/31/2024": 347500.0,
            "03/31/2025": 65600.0,
        },
    }


def _assert_no_trend_key(obj):
    """遞迴檢查任何 dict 都不含 '趨勢' key。"""
    if isinstance(obj, dict):
        assert "趨勢" not in obj, (
            f"unexpected 趨勢 key in {list(obj.keys())}"
        )
        for v in obj.values():
            _assert_no_trend_key(v)


class TestPreprocess:

    def test_two_layer_structure(self, two_layer_input):
        out = preprocess(two_layer_input)
        assert "財務結構" in out
        section = out["財務結構"]
        assert section["TIBA041"]["FA_CANME"] == "營業收入"
        assert section["TIBA041"]["12/31/2023"] == "NTD 386,800仟元"
        assert section["TIBB018"]["12/31/2023"] == "17.38%"

    def test_single_layer_structure(self, single_layer_input):
        out = preprocess(single_layer_input)
        # 單層結構：頂層直接是指標
        assert "TIBA041" in out
        assert out["TIBA041"]["12/31/2024"] == "NTD 347,500仟元"

    def test_output_has_no_trend_key(self, two_layer_input):
        out = preprocess(two_layer_input)
        _assert_no_trend_key(out)

    def test_none_period_skipped(self):
        data = {
            "TIBA041": {
                "FA_CANME": "營業收入",
                "單位": "仟元",
                "12/31/2023": 100.0,
                "12/31/2024": None,
                "03/31/2025": 200.0,
            },
        }
        out = preprocess(data)
        row = out["TIBA041"]
        assert "12/31/2023" in row
        assert "03/31/2025" in row
        assert "12/31/2024" not in row

    def test_dates_sorted_oldest_to_newest(self, two_layer_input):
        out = preprocess(two_layer_input)
        # dict 在 Python 3.7+ 保留插入順序
        keys = [
            k for k in out["財務結構"]["TIBA041"].keys()
            if k != "FA_CANME"
        ]
        assert keys == ["12/31/2023", "12/31/2024", "03/31/2025"]

    def test_meta_keys_not_treated_as_dates(self):
        data = {
            "TIBA041": {
                "FA_CANME": "營業收入",
                "單位": "仟元",
                "12/31/2024": 100.0,
            },
        }
        out = preprocess(data)
        assert "單位" not in out["TIBA041"]
        # FA_CANME 仍保留（在 new dict 第一欄）
        assert out["TIBA041"]["FA_CANME"] == "營業收入"

    def test_unknown_unit_falls_back_to_str(self):
        data = {
            "X": {
                "FA_CANME": "未知單位指標",
                "單位": "未知",
                "12/31/2024": 42.5,
            },
        }
        out = preprocess(data)
        assert out["X"]["12/31/2024"] == "42.5"

    def test_indicator_without_dates_skipped(self):
        data = {
            "FOO": {"FA_CANME": "空指標", "單位": "仟元"},
            "BAR": {
                "FA_CANME": "正常",
                "單位": "%",
                "12/31/2024": 1.5,
            },
        }
        out = preprocess(data)
        assert "FOO" not in out
        assert out["BAR"]["12/31/2024"] == "1.50%"

    def test_non_indicator_value_skipped(self):
        # 雙層情境下，section 內混入非 indicator dict 也應被跳過
        data = {
            "段落A": {
                "TIBA041": {
                    "FA_CANME": "營業收入",
                    "單位": "仟元",
                    "12/31/2024": 100.0,
                },
                "noise": "not a dict",
            },
        }
        out = preprocess(data)
        assert "TIBA041" in out["段落A"]
        assert "noise" not in out["段落A"]


# ── convert_grouped_report ─────────────────────────


@pytest.fixture
def grouped_report():
    return {
        "財務結構": {
            "TIBA041": {
                "FA_CANME": "營業收入",
                "單位": "仟元",
                "Current": 65600.0,
                "Period_2": 347500.0,
                "Period_3": 386800.0,
            },
            "TIBB018": {
                "FA_CANME": "營業毛利率",
                "單位": "%",
                "Current": 15.51,
                "Period_2": 18.83,
                "Period_3": 17.38,
            },
        },
    }


@pytest.fixture
def period_dates():
    # 對應 Current / Period_2 / Period_3
    return ["03/31/2025", "12/31/2024", "12/31/2023"]


class TestConvertGroupedReport:

    def test_period_keys_mapped_to_dates(
        self, grouped_report, period_dates,
    ):
        out = convert_grouped_report(
            grouped_report, period_dates,
        )
        row = out["財務結構"]["TIBA041"]
        assert row["03/31/2025"] == "NTD 65,600仟元"
        assert row["12/31/2024"] == "NTD 347,500仟元"
        assert row["12/31/2023"] == "NTD 386,800仟元"

    def test_output_has_no_trend_key(
        self, grouped_report, period_dates,
    ):
        out = convert_grouped_report(
            grouped_report, period_dates,
        )
        _assert_no_trend_key(out)

    def test_dates_sorted_oldest_to_newest(
        self, grouped_report, period_dates,
    ):
        out = convert_grouped_report(
            grouped_report, period_dates,
        )
        keys = list(out["財務結構"]["TIBA041"].keys())
        # 第一個應為 FA_CANME，接著日期由舊至新
        assert keys[0] == "FA_CANME"
        assert keys[1:] == [
            "12/31/2023", "12/31/2024", "03/31/2025",
        ]

    def test_period_with_none_value_shows_missing(self, period_dates):
        gr = {
            "財務結構": {
                "TIBA041": {
                    "FA_CANME": "營業收入",
                    "單位": "仟元",
                    "Current": 100.0,
                    "Period_2": None,
                    "Period_3": 200.0,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        row = out["財務結構"]["TIBA041"]
        # 缺值不再 skip：對應期間填入「資料缺失」字串，
        # 由 LLM 在敘述中明確帶出資料缺失情形。
        assert row["03/31/2025"] == "NTD 100仟元"
        assert row["12/31/2023"] == "NTD 200仟元"
        assert row["12/31/2024"] == "資料缺失"

    def test_period_with_none_undefined_reason_shows_uncomputable(self, period_dates):
        gr = {
            "財務結構": {
                "TIBA041": {
                    "FA_CANME": "負債權益比",
                    "單位": "%",
                    "Current": 50.0,
                    "Period_2": None,
                    "Period_3": None,
                    "reasons": {
                        "Current": "ok",
                        "Period_2": "undefined",
                        "Period_3": "missing",
                    },
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        row = out["財務結構"]["TIBA041"]
        assert row["03/31/2025"] == "50.00%"
        assert row["12/31/2024"] == "無法計算"
        assert row["12/31/2023"] == "資料缺失"

    def test_all_undefined_row_shows_uncomputable(self, period_dates):
        gr = {
            "獲利能力": {
                "X": {
                    "FA_CANME": "(營業利益+折舊)/營業收入",
                    "單位": "%",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                    "reasons": {
                        "Current": "undefined",
                        "Period_2": "undefined",
                        "Period_3": "undefined",
                    },
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        row = out["獲利能力"]["X"]
        for d in period_dates:
            assert row[d] == "無法計算"

    def test_error_reason_falls_back_to_uncomputable(self, period_dates):
        gr = {
            "S": {
                "X": {
                    "FA_CANME": "公式錯誤",
                    "單位": "%",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                    "reasons": {
                        "Current": "error",
                        "Period_2": "error",
                        "Period_3": "error",
                    },
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        row = out["S"]["X"]
        for d in period_dates:
            assert row[d] == "無法計算"

    def test_no_reasons_falls_back_to_missing(self, period_dates):
        gr = {
            "S": {
                "X": {
                    "FA_CANME": "全 None 但無 reasons",
                    "單位": "仟元",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        row = out["S"]["X"]
        for d in period_dates:
            assert row[d] == "資料缺失"

    def test_skips_row_without_fa_canme(self, period_dates):
        gr = {
            "財務結構": {
                "BAD": {
                    "單位": "仟元",
                    "Current": 100.0,
                },
                "TIBA041": {
                    "FA_CANME": "營業收入",
                    "單位": "仟元",
                    "Current": 100.0,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        assert "BAD" not in out["財務結構"]
        assert "TIBA041" in out["財務結構"]

    def test_preserves_row_with_no_dated_values(self, period_dates):
        gr = {
            "財務結構": {
                "EMPTY": {
                    "FA_CANME": "全 None",
                    "單位": "仟元",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        # 三期皆 None 仍保留 row，三個期間都填入「資料缺失」
        row = out["財務結構"]["EMPTY"]
        assert row["FA_CANME"] == "全 None"
        for d in period_dates:
            assert row[d] == "資料缺失"

    def test_preserves_section_when_all_rows_missing(self, period_dates):
        gr = {
            "現金流量": {
                "X": {
                    "FA_CANME": "營業活動現金流",
                    "單位": "仟元",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                },
                "Y": {
                    "FA_CANME": "投資活動現金流",
                    "單位": "仟元",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        # 整個 section 全部缺值時，section 仍應存在且兩個指標都列出
        assert "現金流量" in out
        assert set(out["現金流量"].keys()) == {"X", "Y"}
        for code in ("X", "Y"):
            for d in period_dates:
                assert out["現金流量"][code][d] == "資料缺失"

    def test_missing_row_dates_sorted_oldest_to_newest(self, period_dates):
        gr = {
            "S": {
                "Z": {
                    "FA_CANME": "全缺",
                    "單位": "%",
                    "Current": None,
                    "Period_2": None,
                    "Period_3": None,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        keys = list(out["S"]["Z"].keys())
        # FA_CANME 在最前，後面三個日期由舊至新
        assert keys[0] == "FA_CANME"
        assert keys[1:] == ["12/31/2023", "12/31/2024", "03/31/2025"]

    def test_unknown_unit_falls_back_to_str(self, period_dates):
        gr = {
            "S": {
                "X": {
                    "FA_CANME": "未知單位",
                    "單位": "未知",
                    "Current": 42.5,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        assert out["S"]["X"]["03/31/2025"] == "42.5"

    def test_period_dates_shorter_than_period_keys(self):
        # 只給兩個期間，Period_3 應被忽略
        gr = {
            "S": {
                "X": {
                    "FA_CANME": "營業收入",
                    "單位": "仟元",
                    "Current": 100.0,
                    "Period_2": 200.0,
                    "Period_3": 300.0,
                },
            },
        }
        out = convert_grouped_report(
            gr, ["03/31/2025", "12/31/2024"],
        )
        row = out["S"]["X"]
        assert "03/31/2025" in row
        assert "12/31/2024" in row
        assert len(
            [k for k in row if k != "FA_CANME"]
        ) == 2

    def test_negative_wraps_parens_by_default(
        self, period_dates,
    ):
        # 敘事 row 未標 display_absolute → 負值走會計式括號
        gr = {
            "現金流量": {
                "X": {
                    "FA_CANME": "本期淨利",
                    "單位": "仟元",
                    "Current": -1234.0,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        assert (
            out["現金流量"]["X"]["03/31/2025"]
            == "NTD (1,234)仟元"
        )

    def test_display_absolute_strips_sign_on_negative(
        self, period_dates,
    ):
        # 敘事 row 標 display_absolute → 負值取絕對值顯示
        # （「發放現金股利」情境：科目名稱已表達流出方向）
        gr = {
            "現金流量": {
                "TIBC027": {
                    "FA_CANME": "發放現金股利",
                    "單位": "仟元",
                    "Current": -1000.0,
                    "Period_2": -800.0,
                    "display_absolute": True,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        row = out["現金流量"]["TIBC027"]
        assert row["03/31/2025"] == "NTD 1,000仟元"
        assert row["12/31/2024"] == "NTD 800仟元"

    def test_display_absolute_keeps_positive_intact(
        self, period_dates,
    ):
        # 旗標對正值無影響
        gr = {
            "現金流量": {
                "TIBC027": {
                    "FA_CANME": "發放現金股利",
                    "單位": "仟元",
                    "Current": 1000.0,
                    "display_absolute": True,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        assert (
            out["現金流量"]["TIBC027"]["03/31/2025"]
            == "NTD 1,000仟元"
        )

    def test_parent_key_nests_child_under_sub_items(
        self, period_dates,
    ):
        gr = {
            "現金流量": {
                "TIBC033": {
                    "FA_CANME": "籌資活動之現金流入(流出)",
                    "單位": "仟元",
                    "Current": -800.0,
                    "Period_2": 2500.0,
                    "Period_3": -1000.0,
                },
                "TIBC029": {
                    "FA_CANME": "現金增(減)資",
                    "單位": "仟元",
                    "Current": 2000.0,
                    "Period_2": 3500.0,
                    "Period_3": 3000.0,
                    "parent_key": "TIBC033",
                },
                "TIBC027": {
                    "FA_CANME": "發放現金股利",
                    "單位": "仟元",
                    "Current": -2800.0,
                    "Period_2": -1000.0,
                    "Period_3": -4000.0,
                    "parent_key": "TIBC033",
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        section = out["現金流量"]
        # 子項不再出現於 section 頂層
        assert set(section.keys()) == {"TIBC033"}
        parent = section["TIBC033"]
        assert parent["FA_CANME"] == "籌資活動之現金流入(流出)"
        assert "sub_items" in parent
        sub = parent["sub_items"]
        # 保留子項在 filter 中的出現順序
        assert list(sub.keys()) == ["TIBC029", "TIBC027"]
        assert sub["TIBC029"]["FA_CANME"] == "現金增(減)資"
        assert sub["TIBC029"]["03/31/2025"] == "NTD 2,000仟元"
        assert sub["TIBC027"]["FA_CANME"] == "發放現金股利"

    def test_parent_key_missing_parent_falls_back_flat(
        self, period_dates, caplog,
    ):
        """parent_key 指向同段落內找不到的 code → 退化為平項 + warning。"""
        gr = {
            "現金流量": {
                "TIBC029": {
                    "FA_CANME": "現金增(減)資",
                    "單位": "仟元",
                    "Current": 2000.0,
                    "parent_key": "TIBC999",
                },
            },
        }
        with caplog.at_level("WARNING"):
            out = convert_grouped_report(gr, period_dates)
        assert "TIBC029" in out["現金流量"]
        assert "sub_items" not in out["現金流量"]["TIBC029"]
        assert any(
            "找不到父項" in rec.message
            for rec in caplog.records
        )

    def test_no_parent_key_keeps_flat(self, period_dates):
        """沒有 parent_key 的 row 保持平結構，不應產生 sub_items。"""
        gr = {
            "現金流量": {
                "TIBC014": {
                    "FA_CANME": "營業活動之淨現金流入(流出)",
                    "單位": "仟元",
                    "Current": 5000.0,
                },
            },
        }
        out = convert_grouped_report(gr, period_dates)
        assert "sub_items" not in out["現金流量"]["TIBC014"]
