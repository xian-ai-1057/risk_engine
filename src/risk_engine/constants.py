"""共用常數與輕量輔助工具。

本模組存放跨模組共用、無相依的小型公用件，避免散落在各檔重複實作：

- ``OP_PATTERN``：比較運算子 regex（``>=``、``<=``、``>``、``<``）。
- ``normalize_op_text()``：門檻字串正規化（全形→半形、去頭尾空白）。
- ``UNIT_FORMATTERS`` 及其組成函式：依單位格式化數值為顯示字串。

設計原則：
  - 不可 import 其他 ``risk_engine`` 模組，以免循環相依。
  - 函式以「純資料變換」為限，不做 IO、不做 logging。
"""
import re


# ── 比較運算子 ──────────────────────────────────────

# 比較運算子 regex：>=, <=, >, <
OP_PATTERN = re.compile(r"(>=|<=|>|<)")


# ── 文字正規化 ──────────────────────────────────────

_FULLWIDTH_OP_MAP = {"＞": ">", "＜": "<", "＝": "="}


def normalize_op_text(text: str) -> str:
    """將比較運算子的全形符號轉半形並去除頭尾空白。

    用於統一處理使用者輸入或試算表貼來的中文門檻字串，
    讓後續的 regex / 解析器能直接比對 ``>``、``<``、``=``。

    Args:
        text: 原始字串。

    Returns:
        正規化後的字串。
    """
    for full, half in _FULLWIDTH_OP_MAP.items():
        text = text.replace(full, half)
    return text.strip()


# ── 數值格式化（依單位） ────────────────────────────

def convert_thousand_ntd(value: float) -> str:
    """將仟元數值轉為含單位的顯示字串。

    Args:
        value: 原始數值（單位：仟元）。

    Returns:
        格式化後的金額字串，例如 ``"NTD 15,950仟元"``、
        ``"NTD 0元"``、``"-NTD 30元"``。

    規則：
        - ``value == 0`` → ``"NTD 0元"``。
        - ``abs(value) >= 1`` → ``"NTD x,xxx仟元"``（含千分位）。
        - ``0 < abs(value) < 1`` → 換算為元，四捨五入取整。
        - 負值前綴 ``"-"``。
    """
    if value == 0:
        return "NTD 0元"

    sign = "-" if value < 0 else ""
    abs_val = abs(value)

    if abs_val >= 1:
        return f"{sign}NTD {abs_val:,.0f}仟元"
    converted = round(abs_val * 1_000)
    return f"{sign}NTD {converted:,}元"


def format_percent(value: float) -> str:
    """格式化為百分比字串（保留兩位小數）。"""
    return f"{value:.2f}%"


def format_days(value: float) -> str:
    """格式化為天數字串（保留兩位小數）。"""
    return f"{value:.2f}天"


def format_times(value: float) -> str:
    """格式化為倍數字串（保留兩位小數）。"""
    return f"{value:.2f}倍"


# 單位 → 對應 formatter 的對照表。
# 由 ``risk_engine.report`` 與 ``utils.simple_convert`` 共用，
# 確保所有輸出端的顯示格式一致。
UNIT_FORMATTERS = {
    "仟元": convert_thousand_ntd,
    "%": format_percent,
    "天": format_days,
    "倍": format_times,
}
