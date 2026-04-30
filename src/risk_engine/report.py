"""報告產生模組。

負責將規則判斷結果組裝為完整報告 JSON，
並提供 LLM 精簡格式轉換。
"""
import logging
from collections import OrderedDict
from typing import Any

from risk_engine import types
from risk_engine import formula as formula_mod
from risk_engine import checker as checker_mod
from utils.simple_convert import UNIT_FORMATTERS

logger = logging.getLogger(__name__)


# value_kind → 給 LLM 的中文語義標籤
_VALUE_LABEL_MAP: dict[str, str] = {
    formula_mod.VALUE_KIND_CURRENT: "當期值",
    formula_mod.VALUE_KIND_PERIOD_CHANGE_ABS: "較前期之變動",
    formula_mod.VALUE_KIND_PERIOD_CHANGE_PCT: "較前期變動率",
    formula_mod.VALUE_KIND_MULTI_PERIOD_SUM: "多期加總",
    formula_mod.VALUE_KIND_COMPOUND: "複合條件",
}


def _round2(val: float | None) -> float | None:
    """輸出用：四捨五入到小數點兩位，None 原樣回傳。"""
    return round(val, 2) if val is not None else None


def _infer_unit(
    formula: str,
    report: types.Report,
) -> str:
    """從公式與財報推斷計算結果的單位。

    規則：
      - 提取公式中所有基礎代碼的「單位」欄位。
      - 全部代碼單位一致且公式不含除法 → 該單位。
      - 全部代碼單位一致但含除法且為仟元 → 無量綱。
      - 其他 → 空字串（無法推斷）。

    Args:
        formula: 指標公式字串。
        report: 財報資料。

    Returns:
        推斷出的單位字串，無法推斷時回傳 ``""``。
    """
    codes = formula_mod.extract_codes(formula)
    if not codes:
        return ""

    units = {
        report[c].get("單位", "")
        for c in codes if c in report
    }
    if len(units) != 1:
        return ""

    unit = units.pop()
    if not unit:
        return ""

    # 含除法的仟元公式 → 結果為比率，無量綱
    if "/" in formula and unit == "仟元":
        return ""

    return unit


def _format_display(
    val: float | None,
    unit: str,
) -> str | None:
    """將數值格式化為含單位的顯示字串。

    Args:
        val: 數值，None 時直接回傳 None。
        unit: 單位字串（如 "仟元"、"%"）。

    Returns:
        格式化顯示字串，或 None。
    """
    if val is None:
        return None
    formatter = UNIT_FORMATTERS.get(unit)
    if formatter:
        return formatter(val)
    return str(round(val, 2))


# ── 報告產生 ────────────────────────────────────────

def generate_report(
    report: types.Report,
    rules: list[dict[str, Any]],
    customer_id: str,
    report_date: str,
    industry: str,
) -> types.FullReport:
    """產生風險判斷報告。

    Args:
        report: 財報資料。
        rules: 該產業的指標規則列表。
        customer_id: 客戶代碼。
        report_date: 報表日期。
        industry: 產業別。

    Returns:
        完整的 FullReport dict。
    """
    logger.info(
        "開始產生報告: 客戶=%s, 產業=%s",
        customer_id, industry,
    )

    # 找出需要前期值的指標
    needs_prev = _collect_needs_prev(rules)

    # 依 section → indicator_code 分組
    grouped = _group_rules(rules)

    # 逐一判斷
    sections, counters, indicator_names = (
        _evaluate_all(grouped, report, needs_prev)
    )

    logger.info(
        "報告產生完成: 段落=%d, 指標=%d,"
        " 觸發=%d, 未觸發=%d, 缺資料=%d",
        len(sections), len(indicator_names),
        counters["triggered"],
        counters["not_triggered"],
        counters["missing"],
    )

    return {
        "customer_id": customer_id,
        "report_date": report_date,
        "industry": industry,
        "summary": {
            "total_sections": len(sections),
            "total_indicators": len(indicator_names),
            "triggered_count": (
                counters["triggered"]
            ),
            "not_triggered_count": (
                counters["not_triggered"]
            ),
            "missing_count": counters["missing"],
            "total_rules": counters["total_rules"],
        },
        "sections": sections,
    }


def _collect_needs_prev(
    rules: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    """收集需要前期值的 (section, code) 組合。"""
    needs: set[tuple[str, str]] = set()
    for r in rules:
        compare = r.get("compare_type", "")
        if compare.startswith("period_change"):
            needs.add(
                (r["section"], r["indicator_code"])
            )
    return needs


def _group_rules(
    rules: list[dict[str, Any]],
) -> OrderedDict[str, OrderedDict[str, list]]:
    """依 section → indicator_code 分組。"""
    grouped: OrderedDict[
        str, OrderedDict[str, list]
    ] = OrderedDict()

    for r in rules:
        sec = r["section"]
        code = r["indicator_code"]
        grouped.setdefault(sec, OrderedDict())
        grouped[sec].setdefault(code, [])
        grouped[sec][code].append(r)

    return grouped


def _evaluate_all(
    grouped: OrderedDict,
    report: types.Report,
    needs_prev: set[tuple[str, str]],
) -> tuple[
    dict[str, list], dict[str, int], set[tuple]
]:
    """逐指標執行判斷，回傳結果。

    Returns:
        (sections, counters, indicator_names)
    """
    sections: dict[str, list] = OrderedDict()
    counters = {
        "triggered": 0,
        "not_triggered": 0,
        "missing": 0,
        "total_rules": 0,
    }
    indicator_names: set[tuple[str, str]] = set()

    for sec, indicators in grouped.items():
        section_list = []
        for code, code_rules in indicators.items():
            entry = _evaluate_indicator(
                sec, code, code_rules,
                report, needs_prev, counters,
            )
            section_list.append(entry)
            indicator_names.add(
                (sec, code_rules[0]["indicator_name"])
            )
        sections[sec] = section_list

    return sections, counters, indicator_names


def _enrich_condition_details(
    tag: dict[str, Any],
    report: types.Report,
) -> None:
    """就地為 condition_details 的每筆明細補上 subject 與單位顯示。

    subject 取自子公式第一個基礎代碼的 FA_CANME，
    display 依子公式推斷的 value_kind 決定單位（含百分比）。
    """
    details = tag.get("condition_details")
    if not details:
        return
    for d in details:
        sub_formula = d.get("formula", "")
        bases = formula_mod.extract_codes(sub_formula)
        subject = ""
        if bases:
            subject = report.get(
                bases[0], {},
            ).get("FA_CANME", "")
        d["subject"] = subject

        sub_kind = formula_mod.classify_formula(
            sub_formula, "",
        )
        if sub_kind == formula_mod.VALUE_KIND_PERIOD_CHANGE_PCT:
            unit = "%"
        else:
            unit = (
                report.get(bases[0], {}).get("單位", "")
                if bases else ""
            )
        d["display"] = _format_display(d.get("value"), unit)


def _evaluate_indicator(
    sec: str,
    code: str,
    code_rules: list[dict[str, Any]],
    report: types.Report,
    needs_prev: set[tuple[str, str]],
    counters: dict[str, int],
) -> types.IndicatorEntry:
    """判斷單一指標下的所有規則。"""
    is_compound = any(
        r.get("compare_type") == "compound"
        for r in code_rules
    )
    compare_type = code_rules[0].get("compare_type", "")

    if is_compound:
        current_val = None
        prev_val = None
    else:
        current_val = formula_mod.evaluate_formula(
            code, report, "Current",
        )
        has_prev = (sec, code) in needs_prev
        prev_val = (
            formula_mod.evaluate_formula(
                code, report, "Period_2",
            )
            if has_prev else None
        )

    # 取得單位：優先用 config 的 result_unit，否則推斷
    unit = (
        code_rules[0].get("result_unit", "")
        or (_infer_unit(code, report)
            if not is_compound else "")
    )
    current_display = _format_display(current_val, unit)
    previous_display = _format_display(prev_val, unit)

    # 判別語義 kind（允許 config override）
    value_kind = (
        code_rules[0].get("value_kind")
        or formula_mod.classify_formula(
            code, compare_type,
        )
    )
    value_label = _VALUE_LABEL_MAP.get(
        value_kind, value_kind,
    )

    # 擷取公式運算元（compound 略過，明細由 condition_details 帶）
    operands: list[types.Operand] = []
    if not is_compound:
        for op in formula_mod.extract_operands(
            code, report,
        ):
            op_unit = op.get("unit", "")
            op["display"] = _format_display(
                op.get("value"), op_unit,
            )
            op["value"] = _round2(op.get("value"))
            operands.append(op)

    taggings = []
    for r in code_rules:
        result = checker_mod.check_rule(
            current_val, prev_val, r,
            report=report,
        )
        _enrich_condition_details(result, report)
        taggings.append(result)
        counters["total_rules"] += 1
        counters[result["status"]] = (
            counters.get(result["status"], 0) + 1
        )

    return {
        "indicator_name": (
            code_rules[0]["indicator_name"]
        ),
        "indicator_code": code,
        "current_value": _round2(current_val),
        "current_display": current_display,
        "previous_value": _round2(prev_val),
        "previous_display": previous_display,
        "value_kind": value_kind,
        "value_label": value_label,
        "operands": operands,
        "taggings": taggings,
    }


# ── LLM 精簡格式 ───────────────────────────────────

_STATUS_MAP = {
    "triggered": "T",
    "not_triggered": "N",
    "missing": "M",
}


def to_llm_format(
    sections: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """將完整報告 sections 轉為 LLM 精簡格式。

    精簡規則：
      - key 縮短: n/cur/prev/s/th/d
      - 狀態縮寫: T/N/M
      - 未觸發 tag 只保留 {"s": "N"}
      - prev 為 None 時省略
      - 刪除 indicator_code, tag_id,
        condition_details

    Args:
        sections: generate_report() 的 sections。

    Returns:
        精簡版的 sections dict。
    """
    result: dict[str, list] = {}

    for sec_name, indicators in sections.items():
        compact_list = []
        for ind in indicators:
            entry = _compact_indicator(ind)
            compact_list.append(entry)
        result[sec_name] = compact_list

    return result


def _compact_indicator(
    ind: dict[str, Any],
) -> dict[str, Any]:
    """轉換單一指標為精簡格式。"""
    entry: dict[str, Any] = {
        "n": ind["indicator_name"],
        "cur": ind["current_value"],
    }

    if ind.get("previous_value") is not None:
        entry["prev"] = ind["previous_value"]

    tags = []
    for t in ind.get("taggings", []):
        tags.append(_compact_tag(t))
    entry["tags"] = tags

    return entry


def _compact_tag(
    tag: dict[str, Any],
) -> dict[str, Any]:
    """轉換單一 tag 為精簡格式。"""
    status = tag.get("status", "missing")
    short_status = _STATUS_MAP.get(status, status)

    if status == "triggered":
        return {
            "s": short_status,
            "th": tag.get("threshold", ""),
            "d": tag.get("description", ""),
        }

    # not_triggered / missing: 只保留狀態
    return {"s": short_status}


# ── Prompt 精簡視圖 ───────────────────────────────

def to_prompt_view(
    sections: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """將完整報告 sections 投影為給 LLM 的精簡版本。

    原始 JSON 保留完整欄位供 debug；此函式只挑出
    敘述必要欄位，並剝除代碼與原始數值：
      - 保留 indicator_name, value_kind, value_label,
        current_display, operands[{period_label,name,display}],
        taggings[{status,..}]
      - 移除 indicator_code, current_value,
        previous_value, previous_display,
        operands[].code, operands[].value,
        tag_id, not_triggered/missing 的 threshold/desc

    Args:
        sections: generate_report() 的 sections。

    Returns:
        精簡版 sections dict，供 prompt 組裝使用。
    """
    result: dict[str, list] = {}
    for sec_name, indicators in sections.items():
        result[sec_name] = [
            _prompt_indicator(ind) for ind in indicators
        ]
    return result


def _prompt_indicator(
    ind: dict[str, Any],
) -> dict[str, Any]:
    """轉換單一指標為 prompt 精簡格式。"""
    entry: dict[str, Any] = {
        "indicator_name": ind.get("indicator_name", ""),
        "value_kind": ind.get("value_kind", ""),
        "value_label": ind.get("value_label", ""),
        "current_display": ind.get("current_display"),
    }
    operands = [
        {
            "period": op.get("period_label", ""),
            "name": op.get("name", ""),
            "display": op.get("display"),
        }
        for op in ind.get("operands", [])
    ]
    if operands:
        entry["operands"] = operands

    entry["taggings"] = [
        _prompt_tag(t) for t in ind.get("taggings", [])
    ]
    return entry


def _prompt_tag(
    tag: dict[str, Any],
) -> dict[str, Any]:
    """轉換單一 tag 為 prompt 精簡格式。

    複合條件的 top-level threshold 含原始代碼，不輸出；
    非複合條件的 threshold（如 ">150.0"）可安全保留。
    """
    status = tag.get("status", "missing")
    if status != "triggered":
        return {"status": status}

    out: dict[str, Any] = {
        "status": "triggered",
        "description": tag.get("description", ""),
    }
    details = tag.get("condition_details")
    if details:
        out["condition_details"] = [
            _prompt_condition_detail(d) for d in details
        ]
    else:
        out["threshold"] = tag.get("threshold", "")
    return out


def _prompt_condition_detail(
    detail: dict[str, Any],
) -> dict[str, Any]:
    """將單一條件明細轉為精簡可讀格式。

    用 classify_formula 推導子條件的語義 kind，並引用
    預先補上的 subject / display，避免把 formula 原文
    或原始代碼送給 LLM。
    """
    sub_formula = detail.get("formula", "")
    kind = formula_mod.classify_formula(sub_formula, "")
    kind_label = _VALUE_LABEL_MAP.get(kind, "")
    return {
        "subject": detail.get("subject", ""),
        "kind_label": kind_label,
        "display": detail.get("display"),
        "operator": detail.get("operator", ""),
        "threshold": detail.get("threshold", ""),
        "result": detail.get("result"),
    }