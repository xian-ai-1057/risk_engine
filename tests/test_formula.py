"""formula 模組單元測試。"""
import pytest

from risk_engine.formula import (
    VALUE_KIND_COMPOUND,
    VALUE_KIND_CURRENT,
    VALUE_KIND_MULTI_PERIOD_SUM,
    VALUE_KIND_PERIOD_CHANGE_ABS,
    VALUE_KIND_PERIOD_CHANGE_PCT,
    _resolve_code,
    _safe_eval,
    _tokenize,
    classify_formula,
    evaluate_formula,
    extract_codes,
    extract_operands,
)


# ── extract_codes ─────────────────────────────────────

class TestExtractCodes:
    def test_single_code(self):
        assert extract_codes("TIBB002") == ["TIBB002"]

    def test_multi_code_arithmetic(self):
        result = extract_codes("TIBB013+TIBB011-TIBB012")
        assert result == ["TIBB013", "TIBB011", "TIBB012"]

    def test_strips_prv_suffix(self):
        result = extract_codes("TIBB011-TIBB011_PRV")
        assert result == ["TIBB011"]

    def test_strips_prv2_suffix(self):
        result = extract_codes("TIBB011-TIBB011_PRV2")
        assert result == ["TIBB011"]

    def test_mixed_suffixes(self):
        result = extract_codes("TIBB011+TIBB018_PRV-TIBC003_PRV2")
        assert result == ["TIBB011", "TIBB018", "TIBC003"]

    def test_no_codes(self):
        assert extract_codes("1+2+3") == []

    def test_with_parentheses(self):
        result = extract_codes("(TIBA049+TIBA047)/TIBA047")
        assert result == ["TIBA049", "TIBA047"]


# ── _resolve_code ─────────────────────────────────────

class TestResolveCode:
    def test_no_suffix(self):
        assert _resolve_code("TIBB011", "Current") == (
            "TIBB011", "Current",
        )

    def test_prv_suffix(self):
        assert _resolve_code("TIBB011_PRV", "Current") == (
            "TIBB011", "Period_2",
        )

    def test_prv2_suffix(self):
        assert _resolve_code("TIBB011_PRV2", "Current") == (
            "TIBB011", "Period_3",
        )


# ── _tokenize ─────────────────────────────────────────

class TestTokenize:
    def test_simple_expression(self):
        assert _tokenize("1+2") == ["1", "+", "2"]

    def test_decimal(self):
        assert _tokenize("3.14*2") == ["3.14", "*", "2"]

    def test_parentheses(self):
        assert _tokenize("(1+2)*3") == [
            "(", "1", "+", "2", ")", "*", "3",
        ]

    def test_illegal_characters(self):
        assert _tokenize("1+abc") is None

    def test_empty_string(self):
        assert _tokenize("") is None


# ── _safe_eval ────────────────────────────────────────

class TestSafeEval:
    def test_addition(self):
        assert _safe_eval("1+2") == 3.0

    def test_subtraction(self):
        assert _safe_eval("10-3") == 7.0

    def test_multiplication(self):
        assert _safe_eval("4*5") == 20.0

    def test_division(self):
        assert _safe_eval("10/4") == 2.5

    def test_parentheses(self):
        assert _safe_eval("(1+2)*3") == 9.0

    def test_nested_parentheses(self):
        assert _safe_eval("((2+3)*4)/2") == 10.0

    def test_negative_number(self):
        assert _safe_eval("-5+3") == -2.0

    def test_division_by_zero(self):
        assert _safe_eval("1/0") is None

    def test_complex_expression(self):
        result = _safe_eval("100.5+200.3-50.1")
        assert result == pytest.approx(250.7)

    def test_invalid_expression(self):
        assert _safe_eval("1++2") is None

    def test_single_number(self):
        assert _safe_eval("42") == 42.0


# ── evaluate_formula ──────────────────────────────────

class TestEvaluateFormula:
    @pytest.fixture()
    def sample_report(self):
        return {
            "TIBB011": {
                "FA_CANME": "應收帳款週轉天數",
                "單位": "天",
                "Current": 58.72,
                "Period_2": 47.9,
                "Period_3": 73.53,
            },
            "TIBB018": {
                "FA_CANME": "存貨週轉天數",
                "單位": "天",
                "Current": 30.0,
                "Period_2": 25.0,
                "Period_3": None,
            },
        }

    def test_single_code(self, sample_report):
        result = evaluate_formula("TIBB011", sample_report)
        assert result == 58.72

    def test_arithmetic(self, sample_report):
        result = evaluate_formula(
            "TIBB011+TIBB018", sample_report,
        )
        assert result == pytest.approx(88.72)

    def test_subtraction(self, sample_report):
        result = evaluate_formula(
            "TIBB011-TIBB018", sample_report,
        )
        assert result == pytest.approx(28.72)

    def test_cross_period(self, sample_report):
        result = evaluate_formula(
            "TIBB011-TIBB011_PRV", sample_report,
        )
        assert result == pytest.approx(58.72 - 47.9)

    def test_prv2_period(self, sample_report):
        result = evaluate_formula(
            "TIBB011_PRV2", sample_report,
        )
        assert result == 73.53

    def test_missing_code(self, sample_report):
        result = evaluate_formula(
            "TIBB999", sample_report,
        )
        assert result is None

    def test_missing_value(self, sample_report):
        result = evaluate_formula(
            "TIBB018_PRV2", sample_report,
        )
        assert result is None

    def test_explicit_period(self, sample_report):
        result = evaluate_formula(
            "TIBB011", sample_report, period="Period_2",
        )
        assert result == 47.9


# ── classify_formula ─────────────────────────────────

class TestClassifyFormula:
    def test_compound_short_circuit(self):
        # compound 直接回傳，不看 formula
        assert classify_formula(
            "TIBB011,TIBA041", "compound",
        ) == VALUE_KIND_COMPOUND

    def test_single_current(self):
        assert classify_formula("TIBB002") == (
            VALUE_KIND_CURRENT
        )

    def test_arithmetic_current(self):
        assert classify_formula(
            "(TIBA009-TIBA014)/(TIBA040+TIBA026)"
        ) == VALUE_KIND_CURRENT

    def test_period_change_abs_simple(self):
        assert classify_formula(
            "TIBB002-TIBB002_PRV"
        ) == VALUE_KIND_PERIOD_CHANGE_ABS

    def test_period_change_abs_composite(self):
        # CCC 的期間差
        assert classify_formula(
            "(TIBB013+TIBB011-TIBB012)"
            "-(TIBB013_PRV+TIBB011_PRV-TIBB012_PRV)"
        ) == VALUE_KIND_PERIOD_CHANGE_ABS

    def test_period_change_pct(self):
        assert classify_formula(
            "(TIBB018-TIBB018_PRV)/TIBB018_PRV"
        ) == VALUE_KIND_PERIOD_CHANGE_PCT

    def test_period_change_pct_with_mult(self):
        assert classify_formula(
            "(TIBA041-TIBA041_PRV)/TIBA041_PRV*100"
        ) == VALUE_KIND_PERIOD_CHANGE_PCT

    def test_multi_period_sum(self):
        assert classify_formula(
            "(TIBC014+TIBC014_PRV+TIBC014_PRV2)"
            "+(TIBC022+TIBC022_PRV+TIBC022_PRV2)"
        ) == VALUE_KIND_MULTI_PERIOD_SUM

    def test_empty_formula_fallback(self):
        assert classify_formula("") == VALUE_KIND_CURRENT


# ── extract_operands ─────────────────────────────────

class TestExtractOperands:
    @pytest.fixture()
    def sample_report(self):
        return {
            "TIBB002": {
                "FA_CANME": "負債總額/權益總額",
                "單位": "%",
                "Current": 386.73,
                "Period_2": 435.28,
                "Period_3": 430.95,
            },
            "TIBC014": {
                "FA_CANME": "營業活動現金流",
                "單位": "仟元",
                "Current": 100.0,
                "Period_2": 50.0,
                "Period_3": 20.0,
            },
        }

    def test_single_current(self, sample_report):
        result = extract_operands("TIBB002", sample_report)
        assert len(result) == 1
        assert result[0]["code"] == "TIBB002"
        assert result[0]["period"] == "Current"
        assert result[0]["period_label"] == "當期"
        assert result[0]["value"] == 386.73
        assert result[0]["name"] == "負債總額/權益總額"

    def test_yoy_pair(self, sample_report):
        result = extract_operands(
            "TIBB002-TIBB002_PRV", sample_report,
        )
        assert len(result) == 2
        assert [o["period_label"] for o in result] == [
            "當期", "前期",
        ]
        assert [o["value"] for o in result] == [
            386.73, 435.28,
        ]

    def test_three_periods_dedup(self, sample_report):
        # TIBC014 有 _PRV 與 _PRV2，應該三筆
        result = extract_operands(
            "TIBC014+TIBC014_PRV+TIBC014_PRV2",
            sample_report,
        )
        assert len(result) == 3
        labels = [o["period_label"] for o in result]
        assert labels == ["當期", "前期", "前前期"]

    def test_missing_code_value_none(self, sample_report):
        result = extract_operands(
            "TIBB999", sample_report,
        )
        assert len(result) == 1
        assert result[0]["value"] is None
        assert result[0]["name"] == ""

    def test_dedup_same_code_same_period(
        self, sample_report,
    ):
        # (X - X_PRV) / X_PRV 中 X_PRV 出現兩次，應去重
        result = extract_operands(
            "(TIBB002-TIBB002_PRV)/TIBB002_PRV",
            sample_report,
        )
        assert len(result) == 2
