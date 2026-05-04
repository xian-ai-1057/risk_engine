"""report 模組單元測試。"""
from risk_engine.report import _infer_unit


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
