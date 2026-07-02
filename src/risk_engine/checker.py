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


def _missing_or_undefined(reason: str) -> str:
    """依 reason 決定 None 結果應對應的 status。

    - ``"undefined"`` → ``"undefined"``（除零或運算未定義）
    - ``"error"`` → ``"undefined"``（解析錯誤統一以無法計算呈現）
    - 其他 (含 ``"missing"`` / ``"ok"``) → ``"missing"``
    """
    if reason in (formula_mod.REASON_UNDEFINED,
                  formula_mod.REASON_ERROR):
        return "undefined"
    return "missing"


# ── 前期變動計算 ────────────────────────────────────

def _calc_period_change_pct(
    current: float,
    prev: float,
    direction: str,
) -> float | None:
    """計算前期百分比變動（以「規模」絕對值為比較基準）。

    語意：先取 ``abs(current)`` / ``abs(prev)`` 再做百分比變動。
    這對齊 ``inputs/indicators/20260507_7大關鍵指標.xlsx`` 的指標公式設計
    與風險敘述（多數金融比率以「規模放大／縮小」評估，
    不分數值正負）。**修改本函式前，請回查 xlsx 對應指標
    的計算公式與風險敘述，確認語意一致。**

    若 ``prev == 0`` 無法計算變動率，回傳 None；上層會以
    ``missing`` 狀態呈現。

    Args:
        current: 本期值。
        prev: 前期值。
        direction: ``"increase"`` 或 ``"decrease"``。

    Returns:
        百分比變動值（如 30.0 代表 30%），或 None。
    """
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
    """計算前期絕對值變動（不取 abs，保留正負號意義）。

    與 :func:`_calc_period_change_pct` 不同，本函式直接
    用原始值相減；多數應用於「天數變動」等以原值方向
    為主的指標。修改前請回查 xlsx 指標公式。
    """
    if direction == "increase":
        return current - prev
    return prev - current


# ── 樹狀條件遞迴求值 ───────────────────────────────

def evaluate_node(
    node: dict[str, Any],
    report: types.Report,
) -> tuple[bool | None, list[dict[str, Any]]]:
    """遞迴求值條件樹（向後相容介面，僅回 ``(result, details)``）。

    需要區分 None 是 missing 或 undefined 時，請改用
    :func:`evaluate_node_detailed`。
    """
    final, _, details = evaluate_node_detailed(node, report)
    return final, details


def evaluate_node_detailed(
    node: dict[str, Any],
    report: types.Report,
) -> tuple[bool | None, str, list[dict[str, Any]]]:
    """遞迴求值條件樹，並回傳 ``(result, reason, details)``。

    - ``result`` 為 True / False / None。
    - ``reason`` 在 ``result is not None`` 時為 ``"ok"``；
      ``result is None`` 時為 ``"undefined"``（任一葉除零）或
      ``"missing"``（其他缺值）。短路規則優先：AND 任一葉
      False 直接 ``(False, "ok", ...)``；OR 任一葉 True 直接
      ``(True, "ok", ...)``，不會升級為 undefined。
    """
    node_type = node["node_type"]

    if node_type == "condition":
        return _evaluate_leaf_detailed(node, report)

    children = node.get("children", [])
    all_details: list[dict[str, Any]] = []
    child_results: list[bool | None] = []
    child_reasons: list[str] = []

    for child in children:
        result, reason, details = evaluate_node_detailed(
            child, report,
        )
        child_results.append(result)
        child_reasons.append(reason)
        all_details.extend(details)

    if node_type == "and":
        if any(r is False for r in child_results):
            return False, formula_mod.REASON_OK, all_details
        if any(r is None for r in child_results):
            final_reason = (
                formula_mod.REASON_UNDEFINED
                if any(
                    rs == formula_mod.REASON_UNDEFINED
                    or rs == formula_mod.REASON_ERROR
                    for rs in child_reasons
                )
                else formula_mod.REASON_MISSING
            )
            return None, final_reason, all_details
        return True, formula_mod.REASON_OK, all_details

    if node_type == "or":
        if any(r is True for r in child_results):
            return True, formula_mod.REASON_OK, all_details
        if any(r is None for r in child_results):
            final_reason = (
                formula_mod.REASON_UNDEFINED
                if any(
                    rs == formula_mod.REASON_UNDEFINED
                    or rs == formula_mod.REASON_ERROR
                    for rs in child_reasons
                )
                else formula_mod.REASON_MISSING
            )
            return None, final_reason, all_details
        return False, formula_mod.REASON_OK, all_details

    return None, formula_mod.REASON_MISSING, all_details


def _evaluate_leaf_detailed(
    node: dict[str, Any],
    report: types.Report,
) -> tuple[bool | None, str, list[dict[str, Any]]]:
    """求值單一葉節點，回傳 ``(result, reason, [detail])``。"""
    node_formula = node["value_formula"]
    operator = node["operator"]
    threshold = node["threshold"]

    val, reason = formula_mod.evaluate_formula_detailed(
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
        return None, reason, [detail]

    passed = op_fn(val, threshold) if op_fn else False
    detail["result"] = passed
    return passed, formula_mod.REASON_OK, [detail]


def _evaluate_leaf(
    node: dict[str, Any],
    report: types.Report,
) -> tuple[bool | None, list[dict[str, Any]]]:
    """向後相容 wrapper（僅回 ``(result, details)``）。"""
    result, _, details = _evaluate_leaf_detailed(node, report)
    return result, details


# ── 策略 handler ────────────────────────────────────

def _check_absolute(
    current_val: float | None,
    prev_val: float | None,
    rule: dict[str, Any],
    report: types.Report | None,
    current_reason: str = formula_mod.REASON_OK,
    prev_reason: str = formula_mod.REASON_OK,
) -> types.TagResult:
    """絕對門檻比較。"""
    tag_id = rule["tag_id"]
    op_str = rule["operator"]
    threshold = rule["threshold"]
    threshold_display = f"{op_str}{threshold}"

    if current_val is None:
        status = _missing_or_undefined(current_reason)
        desc = (
            "本期運算未定義（如分母為零），無法計算"
            if status == "undefined"
            else "缺少資料，無法判斷"
        )
        logger.warning(
            "tag '%s': 本期值無法取得 (status=%s, reason=%s)",
            tag_id, status, current_reason,
        )
        return _tag_result(
            tag_id, status, threshold_display, desc,
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
    current_reason: str = formula_mod.REASON_OK,
    prev_reason: str = formula_mod.REASON_OK,
) -> types.TagResult:
    """前期比較（百分比或絕對值）。"""
    tag_id = rule["tag_id"]
    op_str = rule["operator"]
    threshold = rule["threshold"]
    threshold_display = f"{op_str}{threshold}"
    compare_type = rule["compare_type"]
    direction = rule.get("direction", "increase")

    if current_val is None:
        status = _missing_or_undefined(current_reason)
        desc = (
            "本期運算未定義（如分母為零），無法計算"
            if status == "undefined"
            else "缺少資料，無法判斷"
        )
        logger.warning(
            "tag '%s': 本期值無法取得 (status=%s, reason=%s)",
            tag_id, status, current_reason,
        )
        return _tag_result(
            tag_id, status, threshold_display, desc,
        )
    if prev_val is None:
        status = _missing_or_undefined(prev_reason)
        desc = (
            "前期運算未定義（如分母為零），無法計算"
            if status == "undefined"
            else "缺少前期資料，無法判斷"
        )
        logger.warning(
            "tag '%s': 前期值無法取得 (status=%s, reason=%s)",
            tag_id, status, prev_reason,
        )
        return _tag_result(
            tag_id, status, threshold_display, desc,
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
        # _calc_period_change_pct 在 prev=0 時回 None：
        # 屬於「無法計算變動率」(undefined)，不是資料缺失。
        return _tag_result(
            tag_id, "undefined", threshold_display,
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
    current_reason: str = formula_mod.REASON_OK,
    prev_reason: str = formula_mod.REASON_OK,
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
    final, tree_reason, details = evaluate_node_detailed(
        condition_tree, report,
    )

    # 建立門檻顯示字串
    threshold_display = _build_threshold_display(
        condition_tree,
    )

    if final is None:
        status = _missing_or_undefined(tree_reason)
        desc = (
            "條件樹葉節點運算未定義（如分母為零），"
            "無法計算"
            if status == "undefined"
            else "缺少資料，無法判斷"
        )
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
    current_reason: str = formula_mod.REASON_OK,
    prev_reason: str = formula_mod.REASON_OK,
) -> types.TagResult:
    """依規則判斷是否觸發門檻。

    Args:
        current_val: 本期公式計算結果。
        prev_val: 前期公式計算結果。
        rule: 指標規則 dict。
        report: 財報資料（compound 時需要）。
        current_reason: 本期值的 reason（``"ok"`` / ``"missing"`` /
            ``"undefined"`` / ``"error"``），用以區分 None 結果應
            回報為 ``status: "missing"`` 或 ``"undefined"``。
        prev_reason: 前期值的 reason，語意同 ``current_reason``。

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
        current_reason=current_reason,
        prev_reason=prev_reason,
    )