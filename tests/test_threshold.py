"""threshold 模組單元測試。"""
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
