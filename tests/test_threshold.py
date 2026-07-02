"""threshold 模組單元測試。"""
import pytest

from risk_engine.threshold import parse_threshold


class TestAbsoluteThreshold:
    def test_greater_than_percentage(self):
        result = parse_threshold(">150%")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == ">"
        assert result["threshold"] == 150.0

    def test_less_than_zero(self):
        result = parse_threshold("<0")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == "<"
        assert result["threshold"] == 0.0

    def test_greater_equal(self):
        result = parse_threshold(">=30")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == ">="
        assert result["threshold"] == 30.0

    def test_less_equal_days(self):
        result = parse_threshold("<=180天")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == "<="
        assert result["threshold"] == 180.0

    def test_negative_threshold(self):
        result = parse_threshold(">-10")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == ">"
        assert result["threshold"] == -10.0


class TestPeriodChangeThreshold:
    def test_increase_percentage(self):
        result = parse_threshold("較前期比率增加20%")
        assert result["compare_type"] == "period_change_pct"
        assert result["direction"] == "increase"
        assert result["threshold"] == 20.0

    def test_decrease_percentage(self):
        result = parse_threshold("較前期比率減少15.5%")
        assert result["compare_type"] == "period_change_pct"
        assert result["direction"] == "decrease"
        assert result["threshold"] == 15.5

    def test_increase_absolute_days(self):
        result = parse_threshold("較前期增加60天")
        assert result["compare_type"] == "period_change_abs"
        assert result["direction"] == "increase"
        assert result["threshold"] == 60.0

    def test_decrease_absolute(self):
        result = parse_threshold("較前期減少30")
        assert result["compare_type"] == "period_change_abs"
        assert result["direction"] == "decrease"
        assert result["threshold"] == 30.0


class TestCompoundThreshold:
    def test_and_condition(self):
        result = parse_threshold(
            "TIBB011-TIBB011_PRV >= 15 AND TIBB011 >= 90"
        )
        assert result["compare_type"] == "compound"
        tree = result["condition_tree"]
        assert tree["node_type"] == "and"
        assert len(tree["children"]) == 2

    def test_or_condition(self):
        result = parse_threshold(
            "TIBB011 >= 90 OR TIBB018 >= 60"
        )
        assert result["compare_type"] == "compound"
        tree = result["condition_tree"]
        assert tree["node_type"] == "or"
        assert len(tree["children"]) == 2

    def test_and_children_values(self):
        result = parse_threshold(
            "TIBB011-TIBB011_PRV >= 15 AND TIBB011 >= 90"
        )
        children = result["condition_tree"]["children"]
        assert children[0]["operator"] == ">="
        assert children[0]["threshold"] == 15.0
        assert children[1]["operator"] == ">="
        assert children[1]["threshold"] == 90.0


class TestFullwidthNormalization:
    def test_fullwidth_greater(self):
        result = parse_threshold("＞150%")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == ">"
        assert result["threshold"] == 150.0

    def test_fullwidth_less_equal(self):
        result = parse_threshold("＜＝30")
        assert result["compare_type"] == "absolute"
        assert result["operator"] == "<="
        assert result["threshold"] == 30.0


class TestUnknownThreshold:
    def test_unparseable(self):
        result = parse_threshold("無法解析的字串")
        assert result["compare_type"] == "unknown"

    def test_multiline_takes_first(self):
        result = parse_threshold(">100\n這是註解")
        assert result["compare_type"] == "absolute"
        assert result["threshold"] == 100.0


class TestOrPrecedence:
    """CLAUDE.md 設計：A AND B OR C → or(and(A,B), C)。

    與 SQL/Python 慣例相反，先依 OR 切再依 AND 切。
    """

    def test_and_or_parses_as_or_outermost(self):
        result = parse_threshold(
            "TIBA001 > 1 AND TIBA002 > 2 OR TIBA003 > 3"
        )
        assert result["compare_type"] == "compound"
        tree = result["condition_tree"]
        # 最外層必為 OR
        assert tree["node_type"] == "or"
        assert len(tree["children"]) == 2
        # 第一個子節點為 AND（左側兩個條件）
        left = tree["children"][0]
        assert left["node_type"] == "and"
        assert len(left["children"]) == 2
        assert left["children"][0]["threshold"] == 1.0
        assert left["children"][1]["threshold"] == 2.0
        # 第二個子節點為單一條件 C
        right = tree["children"][1]
        assert right["node_type"] == "condition"
        assert right["threshold"] == 3.0

    def test_or_or_chain_flat(self):
        """A OR B OR C → 單一 OR 節點，三個子節點。"""
        result = parse_threshold(
            "TIBA001 > 1 OR TIBA002 > 2 OR TIBA003 > 3"
        )
        tree = result["condition_tree"]
        assert tree["node_type"] == "or"
        assert len(tree["children"]) == 3


class TestThresholdValidation:
    """非數值門檻不應靜默退化為 0.0。"""

    def test_non_numeric_threshold_raises(self):
        with pytest.raises(ValueError, match="無法轉為數值"):
            parse_threshold(
                "TIBB011 >= 不是數字 AND TIBB018 >= 60"
            )
