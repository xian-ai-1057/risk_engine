"""公式求值模組。

將財報代碼公式（如 TIBB013+TIBB011-TIBB012）
解析為安全的四則運算，從財報取值後計算結果。

取代原本的 eval()，僅允許數值與 +-*/ 括號運算。
"""
import logging
import re

from risk_engine import types

logger = logging.getLogger(__name__)

# ── 財報代碼解析 ────────────────────────────────────

# 匹配財報代碼（含 _PRV / _PRV2 後綴）
_CODE_PATTERN = re.compile(r"TI[A-Z0-9]+(?:_PRV2?)?")

# _PRV 後綴對應的期別（長的先匹配）
_PERIOD_MAP = {
    "_PRV2": "Period_3",
    "_PRV": "Period_2",
}

# 期別內部名稱 → 中文標籤
_PERIOD_LABELS = {
    "Current": "當期",
    "Period_2": "前期",
    "Period_3": "前前期",
}

# value_kind 常數
VALUE_KIND_CURRENT = "current"
VALUE_KIND_PERIOD_CHANGE_ABS = "period_change_abs"
VALUE_KIND_PERIOD_CHANGE_PCT = "period_change_pct"
VALUE_KIND_MULTI_PERIOD_SUM = "multi_period_sum"
VALUE_KIND_COMPOUND = "compound"


def _resolve_code(
    code_with_suffix: str,
    default_period: str,
) -> tuple[str, str]:
    """解析代碼後綴，回傳 (實際代碼, 期別)。

    Args:
        code_with_suffix: 可能含 _PRV/_PRV2 的代碼。
        default_period: 無後綴時使用的預設期別。

    Returns:
        (actual_code, period) 元組。
    """
    for suffix, mapped_period in _PERIOD_MAP.items():
        if code_with_suffix.endswith(suffix):
            actual_code = code_with_suffix[
                :-len(suffix)
            ]
            return actual_code, mapped_period
    return code_with_suffix, default_period


def _scan_periods(formula: str) -> set[str]:
    """掃描公式中所有代碼出現的期別集合。"""
    periods: set[str] = set()
    for c in _CODE_PATTERN.findall(formula):
        _, p = _resolve_code(c, "Current")
        periods.add(p)
    return periods


def classify_formula(
    formula: str,
    compare_type: str = "",
) -> str:
    """依公式結構判別 value_kind。

    回傳值為下列常數之一：
      - VALUE_KIND_COMPOUND：compare_type == "compound"
      - VALUE_KIND_CURRENT：僅使用當期值
      - VALUE_KIND_PERIOD_CHANGE_PCT：含前期與除法（變動百分比）
      - VALUE_KIND_PERIOD_CHANGE_ABS：含前期與減法（變動絕對值）
      - VALUE_KIND_MULTI_PERIOD_SUM：跨多期僅加法（多期加總）

    Args:
        formula: 公式字串。
        compare_type: 來自 rule 的 compare_type；為 "compound" 時直接回傳。

    Returns:
        value_kind 字串。
    """
    if compare_type == "compound":
        return VALUE_KIND_COMPOUND

    periods = _scan_periods(formula)
    if not periods or periods == {"Current"}:
        return VALUE_KIND_CURRENT

    has_prv = "_PRV" in formula
    has_sub = "-" in formula
    has_div = "/" in formula
    has_add = "+" in formula

    if has_prv and has_sub and has_div:
        return VALUE_KIND_PERIOD_CHANGE_PCT
    if has_prv and has_sub:
        return VALUE_KIND_PERIOD_CHANGE_ABS
    if has_prv and has_add and not has_sub:
        return VALUE_KIND_MULTI_PERIOD_SUM
    return VALUE_KIND_CURRENT


def extract_operands(
    formula: str,
    report: types.Report,
) -> list[dict]:
    """從公式抽取所有 (代碼, 期別) 配對的實際值。

    保留原始出現順序並去重。單位由呼叫端另行格式化。

    Args:
        formula: 公式字串。
        report: 財報資料。

    Returns:
        list of {code, name, period, period_label, value, unit}；
        `period` 為內部期別名（Current/Period_2/Period_3），
        `period_label` 為中文標籤（當期/前期/前前期）。
    """
    operands: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for raw in _CODE_PATTERN.findall(formula):
        actual_code, period = _resolve_code(raw, "Current")
        key = (actual_code, period)
        if key in seen:
            continue
        seen.add(key)
        row = report.get(actual_code, {})
        operands.append({
            "code": actual_code,
            "name": row.get("FA_CANME", ""),
            "period": period,
            "period_label": _PERIOD_LABELS.get(period, period),
            "value": row.get(period),
            "unit": row.get("單位", ""),
        })
    return operands


def extract_codes(formula: str) -> list[str]:
    """從公式中提取所有基礎財報代碼。

    自動去除 _PRV / _PRV2 後綴，回傳不重複的
    基礎代碼列表（保持出現順序）。

    Args:
        formula: 含財報代碼的公式字串。

    Returns:
        基礎代碼列表，例如 ["TIBB011", "TIBB018"]。
    """
    raw_codes = _CODE_PATTERN.findall(formula)
    seen: set[str] = set()
    base_codes: list[str] = []
    for c in raw_codes:
        base, _ = _resolve_code(c, "Current")
        if base not in seen:
            seen.add(base)
            base_codes.append(base)
    return base_codes


def _substitute_codes(
    formula: str,
    report: types.Report,
    period: str,
) -> str | None:
    """將公式中的財報代碼替換為數值字串。

    Args:
        formula: 含財報代碼的公式。
        report: 財報資料。
        period: 預設取值期別。

    Returns:
        替換後的純數值運算式，任一代碼缺值回傳 None。
    """
    codes = _CODE_PATTERN.findall(formula)
    if not codes:
        return None

    expr = formula
    for code_with_suffix in codes:
        actual_code, actual_period = _resolve_code(
            code_with_suffix, period,
        )
        if actual_code not in report:
            logger.warning(
                "公式 '%s': 代碼 '%s' 不存在於財報",
                formula, actual_code,
            )
            return None
        val = report[actual_code].get(actual_period)
        if val is None:
            logger.warning(
                "公式 '%s': 代碼 '%s' 期別 '%s' 無值",
                formula, actual_code, actual_period,
            )
            return None
        expr = expr.replace(
            code_with_suffix, str(val), 1,
        )
    return expr


# ── 安全四則運算 ────────────────────────────────────

# Token 類型
_TOKEN_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)"   # 數值
    r"|([+\-*/()])"       # 運算子與括號
)


def _tokenize(expr: str) -> list[str] | None:
    """將運算式切割為 token 列表。

    Args:
        expr: 純數值運算式（如 "12.5+3.0*(2-1)"）。

    Returns:
        token 列表，含非法字元回傳 None。
    """
    tokens: list[str] = []
    pos = 0
    for m in _TOKEN_PATTERN.finditer(expr):
        # 檢查 token 之間是否有非法字元
        gap = expr[pos:m.start()].strip()
        if gap:
            return None
        tokens.append(m.group())
        pos = m.end()
    # 檢查結尾
    if expr[pos:].strip():
        return None
    return tokens if tokens else None


class _Parser:
    """遞迴下降解析器，支援 +-*/ 與括號。

    文法：
        expr   = term (('+' | '-') term)*
        term   = factor (('*' | '/') factor)*
        factor = ['-'] atom
        atom   = NUMBER | '(' expr ')'
    """

    def __init__(self, tokens: list[str]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> str | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self) -> str:
        token = self._tokens[self._pos]
        self._pos += 1
        return token

    def parse(self) -> float | None:
        """解析並求值，失敗回傳 None。"""
        try:
            result = self._expr()
            if self._pos != len(self._tokens):
                return None
            return result
        except (ValueError, ZeroDivisionError,
                IndexError):
            return None

    def _expr(self) -> float:
        """expr = term (('+' | '-') term)*"""
        left = self._term()
        while self._peek() in ("+", "-"):
            op = self._consume()
            right = self._term()
            if op == "+":
                left += right
            else:
                left -= right
        return left

    def _term(self) -> float:
        """term = factor (('*' | '/') factor)*"""
        left = self._factor()
        while self._peek() in ("*", "/"):
            op = self._consume()
            right = self._factor()
            if op == "*":
                left *= right
            else:
                if right == 0:
                    raise ZeroDivisionError
                left /= right
        return left

    def _factor(self) -> float:
        """factor = ['-'] atom"""
        if self._peek() == "-":
            self._consume()
            return -self._atom()
        return self._atom()

    def _atom(self) -> float:
        """atom = NUMBER | '(' expr ')'"""
        token = self._peek()
        if token == "(":
            self._consume()
            result = self._expr()
            if self._consume() != ")":
                raise ValueError("括號不匹配")
            return result
        return float(self._consume())


def _safe_eval(expr: str) -> float | None:
    """安全求值四則運算式。

    Args:
        expr: 純數值運算式。

    Returns:
        計算結果，失敗回傳 None。
    """
    tokens = _tokenize(expr)
    if tokens is None:
        return None
    return _Parser(tokens).parse()


# ── 公開介面 ────────────────────────────────────────

def evaluate_formula(
    formula: str,
    report: types.Report,
    period: str = "Current",
) -> float | None:
    """計算公式，從財報取值後做四則運算。

    支援格式：
      - 單一代碼:  TIBB002
      - 四則運算:  TIBB013+TIBB011-TIBB012
      - 含括號:    (TIBA049+TIBA047+TIBC003)/TIBA047
      - 含前期:    TIBB011-TIBB011_PRV
      - 含前前期:  TIBB011-TIBB011_PRV2

    Args:
        formula: 公式字串。
        report: 財報資料 dict。
        period: 預設取值欄位。

    Returns:
        計算結果，任一代碼缺值或運算失敗回傳 None。
    """
    expr = _substitute_codes(formula, report, period)
    if expr is None:
        return None
    result = _safe_eval(expr)
    if result is None:
        logger.warning(
            "公式 '%s' 運算失敗，運算式: '%s'",
            formula, expr,
        )
    return result