"""門檻比較模組。

依 compare_type 分派至對應 handler，
compound 條件使用遞迴樹求值。

新增比較類型只需：
  1. 寫一個 _check_xxx() 函式
  2. 在 _HANDLERS 加一行註冊
"""
import logging
from typing import Any, Callable

from risk_engine import types
from risk_engine import formula as formula_mod

logger = logging.getLogger(__name__)


# ── 比較運算子 ──────────────────────────────────────

OPERATORS: dict[str, Callable[[float, float], bool]] = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


# ── 結果建構 ────────────────────────────────────────

def _tag_result(
    tag_id: str,
    status: str,
    threshold: str,
    description: str,
) -> types.TagResult:
    """建構 TagResult dict。"""
    return {
        "tag_id": tag_id,
        "status": status,
        "threshold": threshold,
        "description": description,
    }


# ── 前期變動計算 ────────────────────────────────────

def _calc_period_change_pct(
    current: float,
    prev: float,
    direction: str,
) -> float | None:
    """計算前期百分比變動。"""
    current = abs(current)
    prev = abs(prev)
    if prev == 0:
        return None
    if direction == "increase":
        return (current - prev) / prev * 100
    return (prev - current) / prev * 100


def _calc_period_change_abs(
    current: float,
    prev: float,
    direction: str,
) -> float:
    """計算前期絕對值變動。"""
    if direction == "increase":
        return current - prev
    return prev - current


# ── 樹狀條件遞迴求值 ───────────────────────────────

def evaluate_node(
    node: dict[str, Any],
    report: types.Report,
) -> tuple[bool | None, list[dict[str, Any]]]:
    """遞迴求值條件樹。

    Args:
        node: ConditionNode（葉節點或邏輯節點）。
        report: 財報資料。

    Returns:
        (result, details) 元組。
        result: bool 或 None（缺資料）。
        details: 各葉節點的求值明細列表。
    """
    node_type = node["node_type"]

    # ── 葉節點 ──
    if node_type == "condition":
        return _evaluate_leaf(node, report)

    # ── 邏輯節點 ──
    children = node.get("children", [])
    all_details: list[dict[str, Any]] = []
    child_results: list[bool | None] = []

    for child in children:
        result, details = evaluate_node(
            child, report,
        )
        child_results.append(result)
        all_details.extend(details)

    if any(r is None for r in child_results):
        return None, all_details

    if node_type == "and":
        final = all(child_results)
    elif node_type == "or":
        final = any(child_results)
    else:
        final = None

    return final, all_details


def _evaluate_leaf(
    node: dict[str, Any],
    report: types.Report,
) -> tuple[bool | None, list[dict[str, Any]]]:
    """求值單一葉節點。"""
    node_formula = node["value_formula"]
    operator = node["operator"]
    threshold = node["threshold"]

    val = formula_mod.evaluate_formula(
        node_formula, report, "Current",
    )
    op_fn = OPERATORS.get(operator)

    detail: dict[str, Any] = {
        "formula": node_formula,
        "value": round(val, 2) if val is not None else None,
        "operator": operator,
        "threshold": threshold,
        "result": None,
    }

    if val is None:
        return None, [detail]

    passed = op_fn(val, threshold) if op_fn else False
    detail["result"] = passed
    return passed, [detail]


# ── 策略 handler ────────────────────────────────────

def _check_absolute(
    current_val: float | None,
    prev_val: float | None,
    rule: dict[str, Any],
    report: types.Report | None,
) -> types.TagResult:
    """絕對門檻比較。"""
    tag_id = rule["tag_id"]
    op_str = rule["operator"]
    threshold = rule["threshold"]
    threshold_display = f"{op_str}{threshold}"

    if current_val is None:
        logger.warning(
            "tag '%s': 缺少本期資料，跳過判斷",
            tag_id,
        )
        return _tag_result(
            tag_id, "missing", threshold_display,
            "缺少資料，無法判斷",
        )

    op_fn = OPERATORS.get(op_str)
    if op_fn and op_fn(current_val, threshold):
        return _tag_result(
            tag_id, "triggered",
            threshold_display,
            rule["risk_description"],
        )
    return _tag_result(
        tag_id, "not_triggered",
        threshold_display, "不滿足條件",
    )


def _check_period_change(
    current_val: float | None,
    prev_val: float | None,
    rule: dict[str, Any],
    report: types.Report | None,
) -> types.TagResult:
    """前期比較（百分比或絕對值）。"""
    tag_id = rule["tag_id"]
    op_str = rule["operator"]
    threshold = rule["threshold"]
    threshold_display = f"{op_str}{threshold}"
    compare_type = rule["compare_type"]
    direction = rule.get("direction", "increase")

    if current_val is None:
        logger.warning(
            "tag '%s': 缺少本期資料，跳過判斷",
            tag_id,
        )
        return _tag_result(
            tag_id, "missing", threshold_display,
            "缺少資料，無法判斷",
        )
    if prev_val is None:
        logger.warning(
            "tag '%s': 缺少前期資料，跳過判斷",
            tag_id,
        )
        return _tag_result(
            tag_id, "missing", threshold_display,
            "缺少前期資料，無法判斷",
        )

    # 方向性檢查
    if (direction == "increase"
            and current_val <= prev_val):
        return _tag_result(
            tag_id, "not_triggered",
            threshold_display, "不滿足條件",
        )
    if (direction == "decrease"
            and current_val >= prev_val):
        return _tag_result(
            tag_id, "not_triggered",
            threshold_display, "不滿足條件",
        )

    # 計算變動量
    if compare_type == "period_change_pct":
        change_val = _calc_period_change_pct(
            current_val, prev_val, direction,
        )
    else:
        change_val = _calc_period_change_abs(
            current_val, prev_val, direction,
        )

    if change_val is None:
        return _tag_result(
            tag_id, "missing", threshold_display,
            "前期值為零，無法計算變動率",
        )

    op_fn = OPERATORS.get(op_str)
    if op_fn and op_fn(change_val, threshold):
        return _tag_result(
            tag_id, "triggered",
            threshold_display,
            rule["risk_description"],
        )
    return _tag_result(
        tag_id, "not_triggered",
        threshold_display, "不滿足條件",
    )


def _check_compound(
    current_val: float | None,
    prev_val: float | None,
    rule: dict[str, Any],
    report: types.Report | None,
) -> types.TagResult:
    """複合條件判斷（遞迴樹求值）。"""
    tag_id = rule["tag_id"]
    desc_triggered = rule["risk_description"]

    if report is None:
        return _tag_result(
            tag_id, "missing", "",
            "缺少財報資料，無法判斷",
        )

    condition_tree = rule.get("condition_tree", {})
    final, details = evaluate_node(
        condition_tree, report,
    )

    # 建立門檻顯示字串
    threshold_display = _build_threshold_display(
        condition_tree,
    )

    if final is None:
        status = "missing"
        desc = "缺少資料，無法判斷"
    elif final:
        status = "triggered"
        desc = desc_triggered
    else:
        status = "not_triggered"
        desc = "不滿足條件"

    result = _tag_result(
        tag_id, status, threshold_display, desc,
    )
    result["condition_details"] = details
    return result


def _build_threshold_display(
    node: dict[str, Any],
) -> str:
    """從條件樹建構門檻顯示字串。"""
    node_type = node.get("node_type", "")

    if node_type == "condition":
        f = node.get("value_formula", "")
        o = node.get("operator", "")
        t = node.get("threshold", "")
        return f"{f}{o}{t}"

    children = node.get("children", [])
    if not children:
        return ""

    logic = "AND" if node_type == "and" else "OR"
    parts = [
        _build_threshold_display(c)
        for c in children
    ]
    joiner = f" {logic} "
    return joiner.join(
        f"({p})" if " " in p else p
        for p in parts
    )


# ── 策略註冊表 ──────────────────────────────────────

_HANDLERS: dict[str, Callable] = {
    "absolute": _check_absolute,
    "period_change_pct": _check_period_change,
    "period_change_abs": _check_period_change,
    "compound": _check_compound,
}


# ── 公開介面 ────────────────────────────────────────

def check_rule(
    current_val: float | None,
    prev_val: float | None,
    rule: dict[str, Any],
    report: types.Report | None = None,
) -> types.TagResult:
    """依規則判斷是否觸發門檻。

    Args:
        current_val: 本期公式計算結果。
        prev_val: 前期公式計算結果。
        rule: 指標規則 dict。
        report: 財報資料（compound 時需要）。

    Returns:
        TagResult dict。
    """
    compare_type = rule.get("compare_type", "")
    handler = _HANDLERS.get(compare_type)

    if handler is None:
        logger.error(
            "tag '%s': 不支援的比較類型 '%s'",
            rule.get("tag_id", ""), compare_type,
        )
        return _tag_result(
            rule.get("tag_id", ""),
            "missing",
            "",
            f"不支援的比較類型: {compare_type}",
        )

    return handler(
        current_val, prev_val, rule, report,
    )