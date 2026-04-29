"""門檻值解析模組。

將中文門檻描述字串解析為結構化 dict，
compound 條件輸出遞迴樹狀結構（ConditionNode）。

支援格式：
  絕對值:    >150%  <100%  <0  >180天
  前期比較:  較前期比率增加20%  較前期增加60天
  複合條件:  ... AND ...  / ... OR ...
"""
import re
from typing import Any

from risk_engine.constants import OP_PATTERN as _OP_PATTERN


# ── 文字正規化 ──────────────────────────────────────

_FULLWIDTH_MAP = {"＞": ">", "＜": "<", "＝": "="}


def _normalize(text: str) -> str:
    """全形符號轉半形、去除多餘空白。"""
    for full, half in _FULLWIDTH_MAP.items():
        text = text.replace(full, half)
    return text.strip()


# ── 子條件解析 ──────────────────────────────────────

def _strip_outer_parens(expr: str) -> str:
    """去除完整包覆的最外層括號。"""
    expr = expr.strip()
    if not (expr.startswith("(") and expr.endswith(")")):
        return expr
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0 and i < len(expr) - 1:
            return expr  # 括號不是完整包覆
    return expr[1:-1].strip()


def _parse_sub_condition(expr: str) -> dict[str, Any]:
    """解析單一子條件為葉節點。

    格式: "公式 運算子 數值"
    範例: "TIBB011 - TIBB011_PRV >= 30"

    Args:
        expr: 子條件字串。

    Returns:
        ConditionLeaf dict。
    """
    expr = _strip_outer_parens(expr)

    # 從右邊找比較運算子
    matches = list(_OP_PATTERN.finditer(expr))
    if not matches:
        return {
            "node_type": "condition",
            "value_formula": expr,
            "operator": "",
            "threshold": 0.0,
        }

    last_match = matches[-1]
    formula = expr[:last_match.start()].strip()
    operator = last_match.group(1)
    threshold_str = expr[last_match.end():].strip()

    try:
        threshold_val = float(threshold_str)
    except ValueError:
        threshold_val = 0.0

    return {
        "node_type": "condition",
        "value_formula": formula,
        "operator": operator,
        "threshold": threshold_val,
    }


# ── 樹狀 compound 解析 ─────────────────────────────

def _build_tree(text: str) -> dict[str, Any]:
    """將 compound 字串解析為遞迴樹狀結構。

    AND 優先於 OR：先依 OR 分割，再依 AND 分割。
    "A AND B OR C" → or(and(A, B), C)

    Args:
        text: 門檻值字串。

    Returns:
        ConditionNode dict（樹狀結構）。
    """
    # 第一層：依 OR 分割
    or_parts = re.split(r"\s+OR\s+", text)
    if len(or_parts) > 1:
        children = [
            _build_tree(part) for part in or_parts
        ]
        return {
            "node_type": "or",
            "children": children,
        }

    # 第二層：依 AND 分割
    and_parts = re.split(r"\s+AND\s+", text)
    if len(and_parts) > 1:
        children = [
            _parse_sub_condition(part)
            for part in and_parts
        ]
        return {
            "node_type": "and",
            "children": children,
        }

    # 單一條件
    return _parse_sub_condition(text)


# ── 主入口 ──────────────────────────────────────────

def parse_threshold(raw: str) -> dict[str, Any]:
    """解析門檻值字串，回傳結構化 dict。

    Args:
        raw: 原始門檻值字串（可能含多行註解）。

    Returns:
        結構化的門檻設定 dict。
    """
    first_line = _normalize(raw.split("\n")[0])

    # ── 複合條件（含 AND / OR） ──
    if re.search(r"\b(AND|OR)\b", first_line):
        tree = _build_tree(first_line)
        return {
            "compare_type": "compound",
            "condition_tree": tree,
        }

    # ── 前期比較：比率（百分比） ──
    m = re.match(
        r"較前期比率(增加|減少)(\d+(?:\.\d+)?)%",
        first_line,
    )
    if m:
        direction = (
            "increase" if m.group(1) == "增加"
            else "decrease"
        )
        return {
            "compare_type": "period_change_pct",
            "direction": direction,
            "operator": ">",
            "threshold": float(m.group(2)),
        }

    # ── 前期比較：絕對值（天數等） ──
    m = re.match(
        r"較前期(增加|減少)(\d+(?:\.\d+)?)(天)?",
        first_line,
    )
    if m:
        direction = (
            "increase" if m.group(1) == "增加"
            else "decrease"
        )
        return {
            "compare_type": "period_change_abs",
            "direction": direction,
            "operator": ">",
            "threshold": float(m.group(2)),
        }

    # ── 絕對門檻 ──
    m = re.match(
        r"([><]=?)(-?\d+(?:\.\d+)?)[%天]?$",
        first_line,
    )
    if m:
        return {
            "compare_type": "absolute",
            "operator": m.group(1),
            "threshold": float(m.group(2)),
        }

    # 無法解析
    return {
        "compare_type": "unknown",
        "raw": first_line,
        "operator": "",
        "threshold": 0.0,
    }