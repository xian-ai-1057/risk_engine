"""多規則聯合觸發模組（預留擴展）。

目前為 pass-through，待未來支援 meta-rule 後實作：
依據已觸發的 tag 集合對 meta-rule 的 ``condition_tree``
求值，將觸發結果附加至 FullReport。
"""
from typing import Any

from risk_engine import types


def apply_post_rules(
    report_result: types.FullReport,
    meta_rules: list[dict[str, Any]] | None = None,
) -> types.FullReport:
    """對已完成的報告套用多規則聯合觸發。

    Args:
        report_result: ``generate_report()`` 的輸出。
        meta_rules: meta-rule 設定列表；目前未實作，
            傳入 ``None`` 或空列表時原樣回傳。

    Returns:
        處理後的 ``FullReport``（目前未做任何修改）。
    """
    if not meta_rules:
        return report_result

    # TODO: 實作 meta-rule 求值（呼叫 checker.evaluate_node）
    return report_result
