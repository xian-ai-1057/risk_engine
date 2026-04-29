"""多規則聯合觸發模組（預留擴展）。

未來用途：當多個 tag 同時觸發時，
觸發上層 meta-rule。

目前為 pass-through，不做任何修改。

擴展方式：
  1. 定義 meta-rule 設定格式
     {"meta_tag_id": "META_001",
      "condition_tree": {
          "node_type": "and",
          "children": [
              {"node_type": "tag_ref",
               "tag_id": "TAG_001",
               "expected_status": "triggered"},
              {"node_type": "tag_ref",
               "tag_id": "TAG_005",
               "expected_status": "triggered"},
          ]
      },
      "risk_description": "多項指標同時觸發..."}

  2. 在 checker.evaluate_node() 中新增
     node_type == "tag_ref" 的分支

  3. 在本模組實作 apply_post_rules()，
     遍歷 meta-rules 並呼叫 evaluate_node()
"""
from typing import Any

from risk_engine import types


def apply_post_rules(
    report_result: types.FullReport,
    meta_rules: list[dict[str, Any]] | None = None,
) -> types.FullReport:
    """對已完成的報告套用多規則聯合觸發。

    Args:
        report_result: generate_report() 的輸出。
        meta_rules: meta-rule 設定列表。
            目前未實作，傳入 None 即可。

    Returns:
        處理後的 FullReport（目前原樣回傳）。
    """
    if not meta_rules:
        return report_result

    # TODO: 未來實作 meta-rule 邏輯
    # 1. 收集所有已觸發的 tag_id
    # 2. 對每條 meta-rule 呼叫
    #    checker.evaluate_node()
    # 3. 將結果附加至 report_result

    return report_result