"""checker 模組單元測試。"""
import pytest

from risk_engine.checker import (
    _calc_period_change_abs,
    _calc_period_change_pct,
    check_rule,
    evaluate_node,
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
