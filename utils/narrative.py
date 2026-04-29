"""財報科目敘事模組。

從指標規則中提取各段落所需的財報代碼，
結合財報數值與中文科目名稱，產出結構化的
敘事資料供 LLM 生成財務分析敘述。

用法（獨立執行）:
    python -m utils.narrative \
        --report 財報.csv \
        --config indicators_config.json \
        --industry 批發業 \
        [--tag-table tag_table.csv] \
        [-o narrative.json]

用法（作為模組）:
    from utils.narrative import build_narrative
    result = build_narrative(report, rules, tag_table_path)
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


# ── tag_table 載入 ────────────────────────────────────

def load_tag_table(
    csv_path: str,
) -> dict[str, str]:
    """載入 tag_table.csv，回傳代碼→中文名稱對應。

    Args:
        csv_path: tag_table CSV 路徑。

    Returns:
        {代碼: 中文名稱} dict。
    """
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


# ── 代碼提取 ─────────────────────────────────────────

def _collect_formulas_from_tree(
    node: dict[str, Any],
) -> list[str]:
    """遞迴收集 condition_tree 中所有葉節點的公式。

    Args:
        node: 條件樹節點（condition / and / or）。

    Returns:
        所有葉節點的 value_formula 列表。
    """
    node_type = node.get("node_type", "")

    if node_type == "condition":
        formula = node.get("value_formula", "")
        return [formula] if formula else []

    # and / or 節點
    formulas: list[str] = []
    for child in node.get("children", []):
        formulas.extend(
            _collect_formulas_from_tree(child)
        )
    return formulas


def _extract_codes_from_rule(
    rule: dict[str, Any],
) -> list[str]:
    """從單條規則的公式中提取財報代碼。

    處理一般規則的 value_formula 及 compound
    規則的 condition_tree。

    Args:
        rule: 單條指標規則。

    Returns:
        去重的財報代碼列表。
    """
    formulas: list[str] = []

    if rule.get("compare_type") == "compound":
        tree = rule.get("condition_tree")
        if tree:
            formulas = _collect_formulas_from_tree(
                tree
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
    """從規則中按段落提取所有財報代碼。

    優先使用規則的 narrative_codes 欄位（明確指定），
    若無則回退到從公式中解析代碼。
    同一段落下多條規則的代碼自動合併去重。

    Args:
        rules: 該產業的指標規則列表。

    Returns:
        {段落名稱: [代碼1, 代碼2, ...]}。
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


# ── 敘事建構 ─────────────────────────────────────────

def _resolve_name(
    code: str,
    report: types.Report,
    tag_lookup: dict[str, str],
) -> str:
    """取得財報代碼的中文名稱。

    優先從財報資料取得，其次從 tag_table 取得。

    Args:
        code: 財報代碼。
        report: 財報資料。
        tag_lookup: tag_table 對應表。

    Returns:
        中文名稱，找不到時回傳空字串。
    """
    if code in report:
        name = report[code].get("FA_CANME", "")
        if name:
            return name
    name = tag_lookup.get(code, "")
    if not name:
        logger.warning(
            "代碼 '%s': 找不到中文名稱", code,
        )
    return name


def build_narrative(
    report: types.Report,
    rules: list[dict[str, Any]],
    tag_table_path: str | None = None,
) -> types.NarrativeSections:
    """建構各段落的財報科目敘事資料。

    Args:
        report: 財報資料。
        rules: 該產業的指標規則列表。
        tag_table_path: tag_table CSV 路徑（選用）。

    Returns:
        {段落名稱: [NarrativeItem, ...]} dict。
    """
    logger.info("開始建構財報敘事")

    tag_lookup: dict[str, str] = {}
    if tag_table_path:
        tag_lookup = load_tag_table(tag_table_path)

    section_codes = extract_section_codes(rules)

    result: types.NarrativeSections = OrderedDict()

    for sec, codes in section_codes.items():
        items: list[types.NarrativeItem] = []
        for code in codes:
            name = _resolve_name(
                code, report, tag_lookup,
            )
            if not name:
                continue

            item: types.NarrativeItem = {"name": name}

            if code in report:
                row = report[code]
                item["unit"] = row.get("單位", "")
                item["current"] = row.get("Current")
                item["period_2"] = row.get("Period_2")
                item["period_3"] = row.get("Period_3")

            items.append(item)
        result[sec] = items

    total = sum(len(v) for v in result.values())
    logger.info(
        "敘事建構完成: 段落=%d, 科目=%d",
        len(result), total,
    )
    return result


def format_narrative_text(
    items: list[types.NarrativeItem],
) -> str:
    """將單一段落的敘事資料格式化為可讀文字。

    只顯示中文科目名稱，不顯示代碼。
    數值以千分位格式呈現。

    Args:
        items: 該段落的 NarrativeItem 列表。

    Returns:
        格式化後的文字區塊。
    """
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
        "config": "indicators_config.json",
        "industry": "",
        "tag_table": None,
        "output": "narrative.json",
    }

    flag_map = {
        "--report": "report",
        "--config": "config",
        "--industry": "industry",
        "--tag-table": "tag_table",
        "-o": "output",
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


def main() -> None:
    """獨立執行：產生財報敘事 JSON。"""
    from risk_engine import log_config
    log_config.setup_logging()

    args = _parse_args(sys.argv)

    required = ["report", "config", "industry"]
    missing = [k for k in required if not args[k]]
    if missing:
        print(
            "Usage: python -m utils.narrative \\"
        )
        print("  --report <csv> --config <json> \\")
        print("  --industry <str> \\")
        print("  [--tag-table tag_table.csv] \\")
        print("  [-o narrative.json]")
        print(f"\n缺少參數: {', '.join(missing)}")
        sys.exit(1)

    try:
        from risk_engine import loader

        report = loader.load_report(args["report"])
        rules = loader.load_config(
            args["config"], args["industry"],
        )

        result = build_narrative(
            report, rules, args["tag_table"],
        )

        out_path = args["output"]
        with open(
            out_path, "w", encoding="utf-8",
        ) as f:
            json.dump(
                result, f,
                ensure_ascii=False, indent=2,
            )

        logger.info("已輸出至 %s", out_path)

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
