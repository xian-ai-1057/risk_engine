"""checker 模組單元測試。"""
import pytest

from risk_engine.checker import (
    _calc_period_change_abs,
    _calc_period_change_pct,
    check_rule,
    evaluate_node,
    evaluate_node_detailed,
)
from risk_engine.formula import (
    REASON_ERROR,
    REASON_MISSING,
    REASON_OK,
    REASON_UNDEFINED,
)


# ── check_rule: absolute ─────────────────────────────

class TestCheckAbsolute:
    def _make_rule(self, op, threshold):
        return {
            "tag_id": "T001",
            "compare_type": "absolute",
            "operator": op,
            "threshold": threshold,
            "risk_description": "觸發",
        }

    def test_triggered(self):
        result = check_rule(160.0, None, self._make_rule(">", 150))
        assert result["status"] == "triggered"

    def test_not_triggered(self):
        result = check_rule(100.0, None, self._make_rule(">", 150))
        assert result["status"] == "not_triggered"

    def test_missing_current(self):
        result = check_rule(None, None, self._make_rule(">", 150))
        assert result["status"] == "missing"

    def test_greater_equal(self):
        result = check_rule(150.0, None, self._make_rule(">=", 150))
        assert result["status"] == "triggered"

    def test_less_than(self):
        result = check_rule(-5.0, None, self._make_rule("<", 0))
        assert result["status"] == "triggered"


# ── check_rule: period_change_pct ─────────────────────

class TestCheckPeriodChangePct:
    def _make_rule(self, threshold, direction="increase"):
        return {
            "tag_id": "T002",
            "compare_type": "period_change_pct",
            "operator": ">",
            "threshold": threshold,
            "direction": direction,
            "risk_description": "觸發",
        }

    def test_triggered_increase(self):
        # 100 -> 130 = 30% increase
        result = check_rule(130.0, 100.0, self._make_rule(20))
        assert result["status"] == "triggered"

    def test_not_triggered_increase(self):
        # 100 -> 105 = 5% increase
        result = check_rule(105.0, 100.0, self._make_rule(20))
        assert result["status"] == "not_triggered"

    def test_missing_prev(self):
        result = check_rule(130.0, None, self._make_rule(20))
        assert result["status"] == "missing"

    def test_wrong_direction(self):
        # current < prev, direction=increase → not triggered
        result = check_rule(90.0, 100.0, self._make_rule(20))
        assert result["status"] == "not_triggered"

    def test_decrease_direction(self):
        # 100 -> 70 = 30% decrease
        result = check_rule(70.0, 100.0, self._make_rule(20, "decrease"))
        assert result["status"] == "triggered"


# ── check_rule: period_change_abs ─────────────────────

class TestCheckPeriodChangeAbs:
    def _make_rule(self, threshold, direction="increase"):
        return {
            "tag_id": "T003",
            "compare_type": "period_change_abs",
            "operator": ">",
            "threshold": threshold,
            "direction": direction,
            "risk_description": "觸發",
        }

    def test_triggered(self):
        result = check_rule(90.0, 50.0, self._make_rule(30))
        assert result["status"] == "triggered"

    def test_not_triggered(self):
        result = check_rule(60.0, 50.0, self._make_rule(30))
        assert result["status"] == "not_triggered"


# ── check_rule: compound ──────────────────────────────

class TestCheckCompound:
    @pytest.fixture()
    def report(self):
        return {
            "TIBB011": {
                "FA_CANME": "test",
                "單位": "天",
                "Current": 100.0,
                "Period_2": 50.0,
                "Period_3": None,
            },
            "TIBB018": {
                "FA_CANME": "test2",
                "單位": "天",
                "Current": 80.0,
                "Period_2": 40.0,
                "Period_3": None,
            },
        }

    def test_and_both_true(self, report):
        rule = {
            "tag_id": "T004",
            "compare_type": "compound",
            "risk_description": "觸發",
            "condition_tree": {
                "node_type": "and",
                "children": [
                    {
                        "node_type": "condition",
                        "value_formula": "TIBB011",
                        "operator": ">=",
                        "threshold": 90.0,
                    },
                    {
                        "node_type": "condition",
                        "value_formula": "TIBB018",
                        "operator": ">=",
                        "threshold": 70.0,
                    },
                ],
            },
        }
        result = check_rule(None, None, rule, report)
        assert result["status"] == "triggered"

    def test_and_one_false(self, report):
        rule = {
            "tag_id": "T004",
            "compare_type": "compound",
            "risk_description": "觸發",
            "condition_tree": {
                "node_type": "and",
                "children": [
                    {
                        "node_type": "condition",
                        "value_formula": "TIBB011",
                        "operator": ">=",
                        "threshold": 200.0,
                    },
                    {
                        "node_type": "condition",
                        "value_formula": "TIBB018",
                        "operator": ">=",
                        "threshold": 70.0,
                    },
                ],
            },
        }
        result = check_rule(None, None, rule, report)
        assert result["status"] == "not_triggered"

    def test_or_one_true(self, report):
        rule = {
            "tag_id": "T005",
            "compare_type": "compound",
            "risk_description": "觸發",
            "condition_tree": {
                "node_type": "or",
                "children": [
                    {
                        "node_type": "condition",
                        "value_formula": "TIBB011",
                        "operator": ">=",
                        "threshold": 200.0,
                    },
                    {
                        "node_type": "condition",
                        "value_formula": "TIBB018",
                        "operator": ">=",
                        "threshold": 70.0,
                    },
                ],
            },
        }
        result = check_rule(None, None, rule, report)
        assert result["status"] == "triggered"

    def test_missing_report(self):
        rule = {
            "tag_id": "T006",
            "compare_type": "compound",
            "risk_description": "觸發",
            "condition_tree": {},
        }
        result = check_rule(None, None, rule, None)
        assert result["status"] == "missing"


# ── check_rule: unknown type ─────────────────────────

class TestCheckUnknownType:
    def test_unknown_compare_type(self):
        rule = {
            "tag_id": "T999",
            "compare_type": "nonexistent",
        }
        result = check_rule(100.0, None, rule)
        assert result["status"] == "missing"


# ── evaluate_node ─────────────────────────────────────

class TestEvaluateNode:
    @pytest.fixture()
    def report(self):
        return {
            "TIBB011": {
                "FA_CANME": "test",
                "單位": "天",
                "Current": 100.0,
                "Period_2": 50.0,
                "Period_3": None,
            },
        }

    def test_leaf_true(self, report):
        node = {
            "node_type": "condition",
            "value_formula": "TIBB011",
            "operator": ">=",
            "threshold": 90.0,
        }
        result, details = evaluate_node(node, report)
        assert result is True
        assert len(details) == 1

    def test_leaf_false(self, report):
        node = {
            "node_type": "condition",
            "value_formula": "TIBB011",
            "operator": ">=",
            "threshold": 200.0,
        }
        result, details = evaluate_node(node, report)
        assert result is False

    def test_leaf_missing(self, report):
        node = {
            "node_type": "condition",
            "value_formula": "TIBB999",
            "operator": ">=",
            "threshold": 10.0,
        }
        result, _ = evaluate_node(node, report)
        assert result is None


# ── Phase 2: 三值短路邏輯 ─────────────────────────────

class TestThreeValuedLogic:
    """compound 條件的 AND/OR 應採三值短路：

      AND: 任一 false → False；否則任一 None → None；皆 True → True
      OR : 任一 true  → True ；否則任一 None → None；皆 False → False
    """

    @pytest.fixture()
    def report(self):
        # 必須使用 TI* 前綴才會被 _CODE_PATTERN 識別為代碼
        return {
            "TIX001": {
                "FA_CANME": "x", "單位": "",
                "Current": 100.0,
            },
            "TIZ001": {
                "FA_CANME": "z", "單位": "",
                "Current": 5.0,
            },
        }

    def _leaf(self, formula, op, threshold):
        return {
            "node_type": "condition",
            "value_formula": formula,
            "operator": op,
            "threshold": threshold,
        }

    def test_and_missing_and_false(self, report):
        # missing AND false → not_triggered (False 主宰 AND)
        node = {
            "node_type": "and",
            "children": [
                self._leaf("TIM999", ">", 0.0),
                self._leaf("TIZ001", ">", 100.0),
            ],
        }
        result, _ = evaluate_node(node, report)
        assert result is False

    def test_and_missing_and_true(self, report):
        # missing AND true → missing
        node = {
            "node_type": "and",
            "children": [
                self._leaf("TIM999", ">", 0.0),
                self._leaf("TIX001", ">", 0.0),
            ],
        }
        result, _ = evaluate_node(node, report)
        assert result is None

    def test_or_missing_or_true(self, report):
        # missing OR true → triggered (True 主宰 OR)
        node = {
            "node_type": "or",
            "children": [
                self._leaf("TIM999", ">", 0.0),
                self._leaf("TIX001", ">", 0.0),
            ],
        }
        result, _ = evaluate_node(node, report)
        assert result is True

    def test_or_missing_or_false(self, report):
        # missing OR false → missing
        node = {
            "node_type": "or",
            "children": [
                self._leaf("TIM999", ">", 0.0),
                self._leaf("TIZ001", ">", 100.0),
            ],
        }
        result, _ = evaluate_node(node, report)
        assert result is None

    def test_and_missing_and_missing(self, report):
        node = {
            "node_type": "and",
            "children": [
                self._leaf("TIM998", ">", 0.0),
                self._leaf("TIM997", ">", 0.0),
            ],
        }
        result, _ = evaluate_node(node, report)
        assert result is None


# ── helper functions ──────────────────────────────────

class TestCalcPeriodChange:
    def test_pct_increase(self):
        result = _calc_period_change_pct(130, 100, "increase")
        assert result == pytest.approx(30.0)

    def test_pct_decrease(self):
        result = _calc_period_change_pct(70, 100, "decrease")
        assert result == pytest.approx(30.0)

    def test_pct_zero_prev(self):
        assert _calc_period_change_pct(100, 0, "increase") is None

    def test_abs_increase(self):
        assert _calc_period_change_abs(90, 50, "increase") == 40

    def test_abs_decrease(self):
        assert _calc_period_change_abs(50, 90, "decrease") == 40

    # ── 鎖定 abs() 語意（對齊 xlsx 公式設計） ──
    # CLAUDE.md / inputs/indicators/20260507_7大關鍵指標.xlsx：
    # _calc_period_change_pct 比較的是「規模」絕對值的變動率，
    # 不分數值正負。改邏輯前請回查 xlsx 對應指標的公式與風險敘述。

    def test_pct_both_negative_increase_in_magnitude(self):
        # current=-200, prev=-100, direction=increase
        # 規模從 100 放大到 200 → +100%
        result = _calc_period_change_pct(
            -200, -100, "increase",
        )
        assert result == pytest.approx(100.0)

    def test_pct_negative_to_positive_uses_abs(self):
        # current=50, prev=-100, direction=decrease
        # |50| < |-100| 故規模縮小：(100-50)/100 = 50%
        result = _calc_period_change_pct(
            50, -100, "decrease",
        )
        assert result == pytest.approx(50.0)

    def test_pct_zero_current_decrease(self):
        # current=0, prev=100, direction=decrease → -100% 縮小
        result = _calc_period_change_pct(
            0, 100, "decrease",
        )
        assert result == pytest.approx(100.0)


# ── undefined status (除零 vs 真缺值) ─────────────────

class TestUndefinedStatus:
    """區分『真缺值』(missing) 與『運算未定義』(undefined)。"""

    def _abs_rule(self):
        return {
            "tag_id": "T_ABS",
            "compare_type": "absolute",
            "operator": ">",
            "threshold": 100,
            "risk_description": "觸發",
        }

    def _pct_rule(self):
        return {
            "tag_id": "T_PCT",
            "compare_type": "period_change_pct",
            "operator": ">",
            "threshold": 30,
            "direction": "increase",
            "risk_description": "觸發",
        }

    def test_absolute_undefined_when_current_reason_is_undefined(self):
        # 本期 None 但 reason 為 undefined（除零）→ status: undefined
        result = check_rule(
            None, None, self._abs_rule(),
            current_reason=REASON_UNDEFINED,
        )
        assert result["status"] == "undefined"

    def test_absolute_missing_when_current_reason_is_missing(self):
        # 本期 None 且 reason 為 missing（真缺值）→ status: missing
        result = check_rule(
            None, None, self._abs_rule(),
            current_reason=REASON_MISSING,
        )
        assert result["status"] == "missing"

    def test_absolute_default_reason_treats_none_as_missing(self):
        # 沒帶 reason（預設 ok）但 val 是 None：fallback 為 missing
        result = check_rule(None, None, self._abs_rule())
        assert result["status"] == "missing"

    def test_absolute_error_reason_maps_to_undefined(self):
        # error 視為「無法計算」，與 undefined 同一 status
        result = check_rule(
            None, None, self._abs_rule(),
            current_reason=REASON_ERROR,
        )
        assert result["status"] == "undefined"

    def test_period_change_undefined_from_current_reason(self):
        result = check_rule(
            None, 100.0, self._pct_rule(),
            current_reason=REASON_UNDEFINED,
        )
        assert result["status"] == "undefined"

    def test_period_change_undefined_from_prev_reason(self):
        result = check_rule(
            100.0, None, self._pct_rule(),
            prev_reason=REASON_UNDEFINED,
        )
        assert result["status"] == "undefined"

    def test_period_change_missing_when_prev_reason_missing(self):
        result = check_rule(
            100.0, None, self._pct_rule(),
            prev_reason=REASON_MISSING,
        )
        assert result["status"] == "missing"

    def test_period_change_pct_zero_prev_marks_undefined(self):
        # 兩期值都有，但前期 0 導致變動率分母為零 → undefined
        # （之前版本誤標 missing，現修正）
        result = check_rule(
            150.0, 0.0, self._pct_rule(),
        )
        assert result["status"] == "undefined"


# ── evaluate_node_detailed: 條件樹 reason 傳遞 ────────

class TestEvaluateNodeDetailed:
    def test_leaf_ok(self):
        report = {"TIBA001": {"Current": 50.0}}
        node = {
            "node_type": "condition",
            "value_formula": "TIBA001",
            "operator": ">",
            "threshold": 30,
        }
        result, reason, details = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (True, REASON_OK)

    def test_leaf_undefined_propagates(self):
        report = {
            "TIBA001": {"Current": 1.0},
            "TIBA002": {"Current": 0.0},
        }
        node = {
            "node_type": "condition",
            "value_formula": "TIBA001/TIBA002",
            "operator": ">",
            "threshold": 1,
        }
        result, reason, _ = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (None, REASON_UNDEFINED)

    def test_leaf_missing_propagates(self):
        report = {"TIBA001": {"Current": None}}
        node = {
            "node_type": "condition",
            "value_formula": "TIBA001",
            "operator": ">",
            "threshold": 1,
        }
        result, reason, _ = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (None, REASON_MISSING)

    def test_and_short_circuit_false_overrides_undefined(self):
        # AND 內一葉 False、一葉 undefined → 整體 False（短路）
        report = {
            "TIBA001": {"Current": 1.0},
            "TIBA002": {"Current": 0.0},
            "TIBA003": {"Current": 5.0},
        }
        node = {
            "node_type": "and",
            "children": [
                {
                    "node_type": "condition",
                    "value_formula": "TIBA001/TIBA002",
                    "operator": ">", "threshold": 1,
                },
                {
                    "node_type": "condition",
                    "value_formula": "TIBA003",
                    "operator": ">", "threshold": 100,
                },
            ],
        }
        result, reason, _ = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (False, REASON_OK)

    def test_or_short_circuit_true_overrides_undefined(self):
        report = {
            "TIBA001": {"Current": 1.0},
            "TIBA002": {"Current": 0.0},
            "TIBA003": {"Current": 200.0},
        }
        node = {
            "node_type": "or",
            "children": [
                {
                    "node_type": "condition",
                    "value_formula": "TIBA001/TIBA002",
                    "operator": ">", "threshold": 1,
                },
                {
                    "node_type": "condition",
                    "value_formula": "TIBA003",
                    "operator": ">", "threshold": 100,
                },
            ],
        }
        result, reason, _ = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (True, REASON_OK)

    def test_and_propagates_undefined_when_no_short_circuit(self):
        # 所有葉節點都 undefined → 整棵 undefined
        report = {
            "TIBA001": {"Current": 1.0},
            "TIBA002": {"Current": 0.0},
        }
        node = {
            "node_type": "and",
            "children": [
                {
                    "node_type": "condition",
                    "value_formula": "TIBA001/TIBA002",
                    "operator": ">", "threshold": 1,
                },
                {
                    "node_type": "condition",
                    "value_formula": "TIBA001/TIBA002",
                    "operator": "<", "threshold": 1,
                },
            ],
        }
        result, reason, _ = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (None, REASON_UNDEFINED)

    def test_undefined_dominates_missing_in_mixed_children(self):
        # 一葉 missing、一葉 undefined → 整棵 undefined
        # （只要任一葉是除零，整體就以 undefined 呈現）
        report = {
            "TIBA001": {"Current": None},
            "TIBA002": {"Current": 1.0},
            "TIBA003": {"Current": 0.0},
        }
        node = {
            "node_type": "and",
            "children": [
                {
                    "node_type": "condition",
                    "value_formula": "TIBA001",
                    "operator": ">", "threshold": 1,
                },
                {
                    "node_type": "condition",
                    "value_formula": "TIBA002/TIBA003",
                    "operator": ">", "threshold": 1,
                },
            ],
        }
        result, reason, _ = evaluate_node_detailed(
            node, report,
        )
        assert (result, reason) == (None, REASON_UNDEFINED)
