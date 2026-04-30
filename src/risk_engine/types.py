"""型別定義模組。

集中定義所有資料結構與自訂例外，供各模組共用。
使用 TypedDict 讓 dict 具備型別提示，
同時保持與 JSON 序列化的相容性。
"""
from typing import Any, TypedDict


# ── 自訂例外 ────────────────────────────────────────

class ConfigError(Exception):
    """指標設定檔相關錯誤（檔案不存在、產業不存在等）。"""


class ReportLoadError(Exception):
    """財報載入錯誤（檔案不存在、格式錯誤等）。"""


# ── 財報資料 ────────────────────────────────────────

class ReportRow(TypedDict, total=False):
    """單一財報代碼的多期數值。"""

    FA_CANME: str
    單位: str
    Current: float | None
    Period_2: float | None
    Period_3: float | None


Report = dict[str, ReportRow]
"""財報資料，以 FA_RFNBR 為 key。"""


# ── 條件樹節點 ──────────────────────────────────────

class ConditionLeaf(TypedDict):
    """葉節點：單一比較條件。"""

    node_type: str          # "condition"
    value_formula: str
    operator: str           # >, <, >=, <=
    threshold: float


class LogicNode(TypedDict):
    """邏輯節點：AND / OR 組合。"""

    node_type: str          # "and" / "or"
    children: list[Any]     # ConditionLeaf | LogicNode


ConditionNode = ConditionLeaf | LogicNode
"""條件樹的任意節點。"""


# ── 指標規則 ────────────────────────────────────────

class Rule(TypedDict, total=False):
    """單條指標規則（由 convert_indicators 產出）。"""

    section: str
    indicator_name: str
    indicator_code: str
    tag_id: str
    value_formula: str
    compare_type: str
    operator: str
    threshold: float
    direction: str
    risk_description: str
    condition_tree: ConditionNode  # compound 專用
    narrative_codes: list[str]     # 敘事用財報代碼


# ── 判斷結果 ────────────────────────────────────────

class TagResult(TypedDict, total=False):
    """單條規則的判斷結果。"""

    tag_id: str
    status: str             # triggered / not_triggered / missing
    threshold: str
    description: str
    condition_details: list[dict[str, Any]]


class Operand(TypedDict, total=False):
    """單一公式運算元的原始值與期別。"""

    code: str
    name: str
    period: str          # Current / Period_2 / Period_3
    period_label: str    # 當期 / 前期 / 前前期
    value: float | None
    display: str | None


class IndicatorEntry(TypedDict, total=False):
    """單一指標的完整判斷結果。"""

    indicator_name: str
    indicator_code: str
    current_value: float | None
    current_display: str | None
    previous_value: float | None
    previous_display: str | None
    value_kind: str
    value_label: str
    operands: list[Operand]
    taggings: list[TagResult]


class Summary(TypedDict):
    """報告摘要統計。"""

    total_sections: int
    total_indicators: int
    triggered_count: int
    not_triggered_count: int
    missing_count: int
    total_rules: int


class FullReport(TypedDict):
    """完整風險判斷報告。"""

    customer_id: str
    report_date: str
    industry: str
    summary: Summary
    sections: dict[str, list[IndicatorEntry]]


# ── 財報敘事 ────────────────────────────────────────

class NarrativeItem(TypedDict, total=False):
    """單一財報科目的敘事資料。"""

    name: str
    unit: str
    current: float | None
    period_2: float | None
    period_3: float | None


NarrativeSections = dict[str, list[NarrativeItem]]
"""各段落的敘事資料，以 section 名稱為 key。"""


# ── Pipeline ─────────────────────────────────────

GroupedReport = dict[str, dict[str, ReportRow]]
"""過濾分群後的報表：{章節名: {代碼: ReportRow}}。"""


class PipelineResult(TypedDict):
    """Pipeline 完整輸出。"""

    narrative_prompt: str
    risk_prompt: str
    grouped_report: GroupedReport
    risk_report: FullReport


# ── EXE 輸出 ─────────────────────────────────────

EXE_SCHEMA_VERSION = "1.0"
"""EXE 輸出 schema 版本。上游可據此做相容性檢查。"""


class ExeOutput(TypedDict, total=False):
    """EXE 最終輸出結構。

    必填：``schema_version``、``request_id``、``industry``、
    ``narrative_prompt``、``risk_prompt``、``grouped_report``、
    ``risk_report``。

    選填：``customer_id``、``report_date``（呼叫端未提供
    則不寫入）。
    """

    schema_version: str
    request_id: str
    customer_id: str
    report_date: str
    industry: str
    narrative_prompt: str
    risk_prompt: str
    grouped_report: GroupedReport
    risk_report: FullReport


# ── EXE 錯誤輸出 ─────────────────────────────────

ERROR_CODES = (
    "INVALID_ARGS",
    "MISSING_FILE",
    "CONFIG_ERROR",
    "PROCESSING_ERROR",
)
"""EXE ``--stdout`` 模式錯誤 JSON 的合法 ``error_code`` 集合。

對應關係：
  - ``INVALID_ARGS``    參數驗證 / stdin 解析錯誤   (exit 1)
  - ``MISSING_FILE``    必要檔案不存在               (exit 2)
  - ``CONFIG_ERROR``    設定 / 報表載入錯誤          (exit 2)
  - ``PROCESSING_ERROR`` 其他未預期錯誤              (exit 3)
"""


class ExeError(TypedDict):
    """EXE ``--stdout`` 模式下的錯誤 JSON 結構。"""

    error: str
    error_code: str
    request_id: str
