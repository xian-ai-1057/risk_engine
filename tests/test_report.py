"""report 模組單元測試。"""
from risk_engine.report import (
    _format_display,
    _infer_unit,
    to_prompt_view,
)


# ── _infer_unit ─────────────────────────────────────

class TestInferUnit:
    """單位推斷規則：
    - 公式不含除法 → 採用 operands 共同單位。
    - 公式含除法且 operands 單位相同 → 視為無量綱（回傳 ""）。
    - operands 單位不一致 → ""。
    """

    def _report(self, *codes_units):
        return {
            code: {
                "FA_CANME": "x", "單位": unit,
                "Current": 1.0, "Period_2": 1.0,
            }
            for code, unit in codes_units
        }

    def test_no_division_keeps_unit(self):
        report = self._report(("TIBB011", "天"))
        assert _infer_unit("TIBB011", report) == "天"

    def test_thousand_ntd_division_strips_unit(self):
        report = self._report(
            ("TIBA001", "仟元"), ("TIBA002", "仟元"),
        )
        assert _infer_unit(
            "TIBA001/TIBA002", report,
        ) == ""

    def test_percent_division_strips_unit(self):
        """Phase 3: 百分比 ÷ 百分比 應視為無量綱。"""
        report = self._report(
            ("TIBB018", "%"), ("TIBB019", "%"),
        )
        assert _infer_unit(
            "(TIBB018-TIBB019)/TIBB019", report,
        ) == ""

    def test_days_division_strips_unit(self):
        """Phase 3: 天 ÷ 天 應視為無量綱。"""
        report = self._report(
            ("TIBB011", "天"), ("TIBB013", "天"),
        )
        assert _infer_unit(
            "TIBB011/TIBB013", report,
        ) == ""

    def test_division_with_outer_x100_keeps_unit(self):
        """(X-X_PRV)/X_PRV*100 末端有外層 *常數，
        代表將純比率重新放大為原單位（百分點），
        應沿用 operands 的 % 單位，避免破壞 Phase 1 的
        毛利率較前期變動 (-17.63%) 顯示。
        """
        report = self._report(("TIBB018", "%"))
        assert _infer_unit(
            "(TIBB018-TIBB018_PRV)/TIBB018_PRV*100",
            report,
        ) == "%"

    def test_mixed_units_returns_empty(self):
        report = self._report(
            ("TIBB011", "天"), ("TIBA001", "仟元"),
        )
        assert _infer_unit(
            "TIBB011+TIBA001", report,
        ) == ""

    def test_no_codes_returns_empty(self):
        assert _infer_unit("1+2", {}) == ""


# ── _format_display ─────────────────────────────────

class TestFormatDisplay:
    """_format_display 把旗標傳給 utils 端的 format_with_unit。"""

    def test_negative_thousand_default_wraps_parens(self):
        assert _format_display(-1000, "仟元") == "NTD (1,000)仟元"

    def test_negative_thousand_with_display_absolute(self):
        # 發放現金股利情境：值為負，但顯示時取絕對值
        assert _format_display(
            -1000, "仟元", display_absolute=True,
        ) == "NTD 1,000仟元"

    def test_positive_thousand_with_display_absolute(self):
        assert _format_display(
            1000, "仟元", display_absolute=True,
        ) == "NTD 1,000仟元"

    def test_percent_display_absolute_strips_parens(self):
        assert _format_display(
            -12.34, "%", display_absolute=True,
        ) == "12.34%"

    def test_none_returns_none(self):
        assert _format_display(None, "仟元") is None
        assert _format_display(
            None, "仟元", display_absolute=True,
        ) is None

    def test_unknown_unit_negative_wraps_parens(self):
        assert _format_display(-0.13, "") == "(0.13)"

    def test_unknown_unit_positive_no_parens(self):
        assert _format_display(0.13, "") == "0.13"

    def test_unknown_unit_negative_display_absolute_strips_parens(self):
        assert _format_display(-0.13, "", display_absolute=True) == "0.13"


# ── to_prompt_view ──────────────────────────────────

class TestToPromptViewStripping:
    """CLAUDE.md 設計：prompt 視圖刻意剝離原始值，
    避免把財報代碼或浮點數送進 LLM。
    對照 ``inputs/json_sample/risk_prompt_input_sample.json`` 確認結構。
    """

    def _full_section(self):
        return {
            "財務結構": [
                {
                    "indicator_name": "固定長期適合率",
                    "indicator_code": "(TIBA009-TIBA014)/(TIBA040+TIBA026)",
                    "value_kind": "current",
                    "value_label": "當期值",
                    "current_value": 123.45,
                    "current_display": "123.45%",
                    "previous_value": 100.0,
                    "previous_display": "100.00%",
                    "operands": [
                        {
                            "code": "TIBA009",
                            "name": "固定資產",
                            "period_label": "當期",
                            "value": 1000.0,
                            "display": "NTD 1,000仟元",
                        },
                    ],
                    "taggings": [
                        {
                            "tag_id": "TAG_001",
                            "status": "triggered",
                            "threshold": ">100",
                            "description": "觸發",
                        },
                        {
                            "tag_id": "TAG_002",
                            "status": "not_triggered",
                            "threshold": ">200",
                            "description": "不觸發",
                        },
                        {
                            "tag_id": "TAG_003",
                            "status": "missing",
                            "threshold": "",
                            "description": "缺資料",
                        },
                    ],
                },
            ],
        }

    def test_strips_indicator_code(self):
        view = to_prompt_view(self._full_section())
        ind = view["財務結構"][0]
        assert "indicator_code" not in ind

    def test_strips_raw_values(self):
        view = to_prompt_view(self._full_section())
        ind = view["財務結構"][0]
        assert "current_value" not in ind
        assert "previous_value" not in ind
        assert "previous_display" not in ind

    def test_strips_operand_code_and_value(self):
        view = to_prompt_view(self._full_section())
        op = view["財務結構"][0]["operands"][0]
        assert "code" not in op
        assert "value" not in op
        # 但保留可讀欄位
        assert op["name"] == "固定資產"
        assert op["display"] == "NTD 1,000仟元"

    def test_strips_tag_id_always(self):
        view = to_prompt_view(self._full_section())
        for tag in view["財務結構"][0]["taggings"]:
            assert "tag_id" not in tag

    def test_non_triggered_tag_keeps_only_status(self):
        """not_triggered / missing 的 tag 只保留 status，
        threshold / description 都剝除。"""
        view = to_prompt_view(self._full_section())
        tags = view["財務結構"][0]["taggings"]
        non_triggered = [
            t for t in tags
            if t["status"] != "triggered"
        ]
        assert len(non_triggered) == 2
        for t in non_triggered:
            assert set(t.keys()) == {"status"}

    def test_triggered_tag_keeps_threshold_and_desc(self):
        view = to_prompt_view(self._full_section())
        triggered = [
            t for t in view["財務結構"][0]["taggings"]
            if t["status"] == "triggered"
        ]
        assert len(triggered) == 1
        assert triggered[0]["description"] == "觸發"
        assert triggered[0]["threshold"] == ">100"
