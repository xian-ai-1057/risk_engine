"""財報科目敘事模組（filter-driven）。

Narrative 路徑與 Risk 路徑完全解耦：
  - 輸入：財報 + narrative_filter（{section: [{code, name}, ...]}）
  - 輸出：依段落分組的敘事資料（grouped 與 list 兩種 view）

Filter 是單一資料來源，不再從指標公式抽取代碼。

用法（獨立執行）:
    python -m utils.narrative \\
        --report 財報.json \\
        --narrative-filter narrative_filter.json \\
        --industry 7大指標 \\
        [-o narrative.json]

用法（作為模組）:
    from utils.narrative import (
        load_narrative_filter,
        build_grouped_narrative,
        build_narrative,
    )
"""
import csv
import json
import logging
import sys
from collections import OrderedDict
from typing import Any

from risk_engine import formula as formula_mod
from risk_engine import types

logger = logging.getLogger(__name__)


# 容許的段落（與 combine_prompt.NARRATIVE_MAPPING 對齊）
_KNOWN_SECTIONS = {
    "財務結構", "償債能力", "經營效能",
    "獲利能力", "現金流量",
}


# ── tag_table 載入（保留供舊路徑使用） ────────────────

def load_tag_table(
    csv_path: str,
) -> dict[str, str]:
    """載入 tag_table.csv，回傳代碼→中文名稱對應。"""
    logger.info("載入 tag_table: %s", csv_path)
    mapping: dict[str, str] = {}
    try:
        with open(
            csv_path, encoding="utf-8-sig",
        ) as f:
            for row in csv.DictReader(f):
                code = row["FA_RFNBR"].strip()
                name = row.get(
                    "FA_CANME", "",
                ).strip()
                if code and name:
                    mapping[code] = name
    except (FileNotFoundError, KeyError) as e:
        logger.error(
            "tag_table 載入失敗: %s — %s",
            csv_path, e,
        )
        return mapping
    logger.info(
        "tag_table 載入完成，共 %d 筆",
        len(mapping),
    )
    return mapping


# ── 從 rules 抽 codes（退役但保留） ───────────────────

def _collect_formulas_from_tree(
    node: dict[str, Any],
) -> list[str]:
    """遞迴收集 condition_tree 中所有葉節點的公式。"""
    node_type = node.get("node_type", "")

    if node_type == "condition":
        formula = node.get("value_formula", "")
        return [formula] if formula else []

    formulas: list[str] = []
    for child in node.get("children", []):
        formulas.extend(
            _collect_formulas_from_tree(child),
        )
    return formulas


def _extract_codes_from_rule(
    rule: dict[str, Any],
) -> list[str]:
    """從單條規則的公式中提取財報代碼。"""
    formulas: list[str] = []

    if rule.get("compare_type") == "compound":
        tree = rule.get("condition_tree")
        if tree:
            formulas = _collect_formulas_from_tree(
                tree,
            )
    else:
        vf = rule.get("value_formula", "")
        if vf:
            formulas = [vf]

    seen: set[str] = set()
    codes: list[str] = []
    for f in formulas:
        for c in formula_mod.extract_codes(f):
            if c not in seen:
                seen.add(c)
                codes.append(c)
    return codes


def extract_section_codes(
    rules: list[dict[str, Any]],
) -> OrderedDict[str, list[str]]:
    """從規則中按段落提取所有財報代碼（已退役）。

    保留供向後相容；新流程改用 narrative_filter。
    """
    section_codes: OrderedDict[
        str, list[str]
    ] = OrderedDict()

    for r in rules:
        sec = r["section"]
        if sec not in section_codes:
            section_codes[sec] = []

        narrative = r.get("narrative_codes")
        if narrative:
            codes = list(narrative)
        else:
            codes = _extract_codes_from_rule(r)

        for c in codes:
            if c not in section_codes[sec]:
                section_codes[sec].append(c)

    return section_codes


# ── narrative_filter 載入 ────────────────────────────

def load_narrative_filter(
    path: str,
    industry: str,
) -> dict[str, list[dict[str, str]]] | None:
    """載入 narrative_filter.json 並取出單一產業。

    Args:
        path: filter JSON 檔案路徑。
        industry: 產業名稱。

    Returns:
        {段落: [{code, name}, ...]}；產業找不到回 None。
    """
    logger.info(
        "載入 narrative_filter: %s (產業: %s)",
        path, industry,
    )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error(
            "narrative_filter 不存在: %s", path,
        )
        return None
    except json.JSONDecodeError as e:
        logger.error(
            "narrative_filter JSON 格式錯誤:"
            " %s — %s", path, e,
        )
        return None

    if industry not in data:
        available = ", ".join(data.keys())
        logger.warning(
            "產業 '%s' 不在 narrative_filter 中。"
            " 可用: %s", industry, available,
        )
        return None

    sections = data[industry]
    for sec in sections.keys():
        if sec not in _KNOWN_SECTIONS:
            logger.warning(
                "段落 '%s' 不在已知段落 (財務結構 / "
                "償債能力 / 經營效能 / 獲利能力 / "
                "現金流量) 中，prompt 替換可能無對應"
                " placeholder", sec,
            )

    return sections


# ── grouped narrative 建構（filter-driven） ─────────

def build_grouped_narrative(
    report: types.Report,
    narrative_filter: dict[str, list[dict[str, str]]],
) -> types.GroupedReport:
    """依 filter 撈 report，輸出 {section: {code: ReportRow}}。

    輸出格式同 group_sample.json。

    Args:
        report: 財報資料。
        narrative_filter: 單一產業的 filter
            ({section: [{code, name}, ...]})。

    Returns:
        {段落: {代碼: ReportRow}} 結構。
    """
    logger.info("開始建構 grouped narrative")

    grouped: types.GroupedReport = OrderedDict()

    for section, items in narrative_filter.items():
        sec_data: dict[str, types.ReportRow] = (
            OrderedDict()
        )
        for item in items:
            code = item.get("code", "").strip()
            fallback_name = item.get("name", "").strip()
            if not code:
                continue
            if code not in report:
                logger.warning(
                    "代碼 '%s' 不存在於財報中"
                    "（段落: %s）",
                    code, section,
                )
                continue
            row = report[code]
            if not row.get("FA_CANME") and fallback_name:
                row = dict(row)
                row["FA_CANME"] = fallback_name
            sec_data[code] = row
        grouped[section] = sec_data

    total = sum(len(v) for v in grouped.values())
    logger.info(
        "grouped narrative 建構完成: 段落=%d, 科目=%d",
        len(grouped), total,
    )
    return grouped


# ── list-style narrative（filter-driven） ──────────

def build_narrative(
    report: types.Report,
    narrative_filter: dict[str, list[dict[str, str]]],
) -> types.NarrativeSections:
    """依 filter 建構 list-style 敘事資料。

    內部以 build_grouped_narrative 為單一來源，
    再展平成 {section: [NarrativeItem, ...]}，
    供 combine_prompt.format_narrative_text 使用。

    Args:
        report: 財報資料。
        narrative_filter: 單一產業的 filter。

    Returns:
        {段落: [NarrativeItem, ...]}。
    """
    grouped = build_grouped_narrative(
        report, narrative_filter,
    )

    result: types.NarrativeSections = OrderedDict()
    for section, codes_map in grouped.items():
        items: list[types.NarrativeItem] = []
        for _code, row in codes_map.items():
            name = row.get("FA_CANME", "")
            if not name:
                continue
            item: types.NarrativeItem = {"name": name}
            item["unit"] = row.get("單位", "")
            item["current"] = row.get("Current")
            item["period_2"] = row.get("Period_2")
            item["period_3"] = row.get("Period_3")
            items.append(item)
        result[section] = items
    return result


def format_narrative_text(
    items: list[types.NarrativeItem],
) -> str:
    """將單一段落的敘事資料格式化為可讀文字。"""
    lines: list[str] = []
    for item in items:
        name = item.get("name", "")
        unit = item.get("unit", "")
        current = item.get("current")
        period_2 = item.get("period_2")
        period_3 = item.get("period_3")

        label = f"科目: {name}"
        if unit:
            label += f" ({unit})"

        parts = [label]
        if current is not None:
            parts.append(f"本期: {current:,.2f}")
        if period_2 is not None:
            parts.append(f"前一期: {period_2:,.2f}")
        if period_3 is not None:
            parts.append(f"前兩期: {period_3:,.2f}")

        lines.append(", ".join(parts))

    return "\n".join(lines)


# ── CLI 獨立執行 ─────────────────────────────────────

def _parse_args(
    argv: list[str],
) -> dict[str, Any]:
    """解析命令列參數。"""
    args: dict[str, Any] = {
        "report": "",
        "narrative_filter": "",
        "industry": "",
        "output": "narrative.json",
        "grouped_output": "",
    }

    flag_map = {
        "--report": "report",
        "--narrative-filter": "narrative_filter",
        "--industry": "industry",
        "-o": "output",
        "--grouped-output": "grouped_output",
    }

    i = 1
    while i < len(argv):
        flag = argv[i]
        if flag in flag_map and i + 1 < len(argv):
            args[flag_map[flag]] = argv[i + 1]
            i += 2
            continue
        i += 1

    return args


def _usage() -> None:
    print("Usage: python -m utils.narrative \\")
    print(
        "  --report <json> "
        "--narrative-filter <json> \\",
    )
    print("  --industry <str> \\")
    print(
        "  [-o narrative.json] "
        "[--grouped-output grouped.json]",
    )


def main() -> None:
    """獨立執行：產生財報敘事 JSON。"""
    from risk_engine import log_config
    log_config.setup_logging()

    args = _parse_args(sys.argv)

    required = [
        "report", "narrative_filter", "industry",
    ]
    missing = [k for k in required if not args[k]]
    if missing:
        _usage()
        print(f"\n缺少參數: {', '.join(missing)}")
        sys.exit(1)

    try:
        from risk_engine import loader

        report = loader.load_report(args["report"])
        narrative_filter = load_narrative_filter(
            args["narrative_filter"], args["industry"],
        )
        if narrative_filter is None:
            logger.error(
                "找不到產業 '%s' 的 narrative_filter",
                args["industry"],
            )
            sys.exit(1)

        result = build_narrative(
            report, narrative_filter,
        )

        with open(
            args["output"], "w", encoding="utf-8",
        ) as f:
            json.dump(
                result, f,
                ensure_ascii=False, indent=2,
            )
        logger.info("已輸出 list-style 至 %s", args["output"])

        if args["grouped_output"]:
            grouped = build_grouped_narrative(
                report, narrative_filter,
            )
            with open(
                args["grouped_output"], "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    grouped, f,
                    ensure_ascii=False, indent=2,
                )
            logger.info(
                "已輸出 grouped 至 %s",
                args["grouped_output"],
            )

    except (
        types.ReportLoadError,
        types.ConfigError,
    ) as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception:
        logger.exception("未預期的錯誤")
        sys.exit(1)


if __name__ == "__main__":
    main()
