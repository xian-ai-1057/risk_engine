"""將 Excel 指標檔轉換為 indicator.json + narrative_filter.json。

Excel 須包含兩個工作表：
  - 指標 (Sheet1)：與既有 CSV 相同欄位 — 產業別、財務分析指標、
                   指標名稱、指標對應財報欄位、指標編號、
                   指標判斷門檻值、風險情境、結果單位、敘事代碼（選用）
  - 敘事指標 (Sheet2)：產業別、段落、會計科目、會計科目代碼

輸出：
  - indicator.json：{產業: [rule, ...]}（與 convert_indicators.py 相容）
  - narrative_filter.json：{產業: {段落: [{code, name}, ...]}}

用法:
    python -m utils.xlsx_to_indicators 指標.xlsx \\
        --config-out data/indicator.json \\
        --filter-out data/narrative_filter.json \\
        [--indicator-sheet 指標] \\
        [--filter-sheet 敘事指標]
"""
import json
import logging
import sys
from typing import Any

import pandas as pd

from utils.convert_indicators import row_to_rule

logger = logging.getLogger(__name__)


# 預設 sheet 名稱與 fallback
_INDICATOR_SHEET_DEFAULT = "指標"
_FILTER_SHEET_DEFAULT = "敘事指標"
_INDICATOR_SHEET_FALLBACK = "Sheet1"
_FILTER_SHEET_FALLBACK = "Sheet2"

# Sheet 1 欄位（與 CSV 一致）
_INDICATOR_COLUMNS = [
    "產業別", "財務分析指標", "指標名稱",
    "指標對應財報欄位", "指標編號",
    "指標判斷門檻值", "風險情境",
]

# Sheet 2 欄位
_FILTER_COLUMNS = [
    "產業別", "段落", "會計科目", "會計科目代碼",
]


def _read_sheet(
    xlsx_path: str,
    primary: str,
    fallback: str,
) -> pd.DataFrame:
    """讀取指定 sheet，找不到時 fallback。"""
    try:
        return pd.read_excel(
            xlsx_path, sheet_name=primary, dtype=str,
        )
    except (ValueError, KeyError):
        logger.warning(
            "找不到工作表 '%s'，改用 '%s'",
            primary, fallback,
        )
        return pd.read_excel(
            xlsx_path, sheet_name=fallback, dtype=str,
        )


def _row_to_dict(row: pd.Series) -> dict[str, str]:
    """pandas row → str dict，NaN 轉空字串。"""
    out: dict[str, str] = {}
    for k, v in row.items():
        if pd.isna(v):
            out[str(k)] = ""
        else:
            out[str(k)] = str(v).strip()
    return out


def parse_indicator_sheet(
    df: pd.DataFrame,
) -> dict[str, list[dict]]:
    """Sheet 1 → {產業: [rule, ...]}。

    Args:
        df: 指標工作表的 DataFrame。

    Returns:
        與 convert_indicators.convert() 相同的結構。
    """
    missing = [
        c for c in _INDICATOR_COLUMNS
        if c not in df.columns
    ]
    if missing:
        raise ValueError(
            f"指標工作表缺少欄位: {', '.join(missing)}"
        )

    config: dict[str, list[dict]] = {}
    for _, row in df.iterrows():
        row_dict = _row_to_dict(row)
        if not row_dict.get("產業別"):
            continue
        industries, rule = row_to_rule(row_dict)
        for ind in industries:
            config.setdefault(ind, []).append(
                rule.copy(),
            )
    return config


def parse_filter_sheet(
    df: pd.DataFrame,
) -> dict[str, dict[str, list[dict[str, str]]]]:
    """Sheet 2 → {產業: {段落: [{code, name}, ...]}}。

    保留出現順序、去重（同段落內同 code 只保留首次）。

    Args:
        df: 敘事指標工作表的 DataFrame。

    Returns:
        敘事過濾結構。
    """
    missing = [
        c for c in _FILTER_COLUMNS
        if c not in df.columns
    ]
    if missing:
        raise ValueError(
            f"敘事指標工作表缺少欄位: {', '.join(missing)}"
        )

    result: dict[
        str, dict[str, list[dict[str, str]]]
    ] = {}

    for _, row in df.iterrows():
        row_dict = _row_to_dict(row)
        industries_raw = row_dict.get("產業別", "")
        section = row_dict.get("段落", "")
        name = row_dict.get("會計科目", "")
        code = row_dict.get("會計科目代碼", "")

        if not (industries_raw and section and code):
            continue

        industries = [
            ind.strip()
            for ind in industries_raw.split("\n")
            if ind.strip()
        ]

        for ind in industries:
            ind_bucket = result.setdefault(ind, {})
            sec_bucket = ind_bucket.setdefault(
                section, [],
            )
            if any(
                item["code"] == code
                for item in sec_bucket
            ):
                continue
            sec_bucket.append(
                {"code": code, "name": name},
            )

    return result


def convert(
    xlsx_path: str,
    indicator_sheet: str = _INDICATOR_SHEET_DEFAULT,
    filter_sheet: str = _FILTER_SHEET_DEFAULT,
) -> tuple[
    dict[str, list[dict]],
    dict[str, dict[str, list[dict[str, str]]]],
]:
    """讀取 Excel，回傳 (指標 config, 敘事 filter)。"""
    indicator_df = _read_sheet(
        xlsx_path, indicator_sheet,
        _INDICATOR_SHEET_FALLBACK,
    )
    filter_df = _read_sheet(
        xlsx_path, filter_sheet,
        _FILTER_SHEET_FALLBACK,
    )

    config = parse_indicator_sheet(indicator_df)
    narrative_filter = parse_filter_sheet(filter_df)
    return config, narrative_filter


# ── CLI ──────────────────────────────────────────────

def _parse_args(argv: list[str]) -> dict[str, Any]:
    args: dict[str, Any] = {
        "xlsx": "",
        "config_out": "indicator.json",
        "filter_out": "narrative_filter.json",
        "indicator_sheet": _INDICATOR_SHEET_DEFAULT,
        "filter_sheet": _FILTER_SHEET_DEFAULT,
    }
    flag_map = {
        "--config-out": "config_out",
        "--filter-out": "filter_out",
        "--indicator-sheet": "indicator_sheet",
        "--filter-sheet": "filter_sheet",
    }
    i = 1
    while i < len(argv):
        flag = argv[i]
        if flag in flag_map and i + 1 < len(argv):
            args[flag_map[flag]] = argv[i + 1]
            i += 2
            continue
        if not flag.startswith("--") and not args["xlsx"]:
            args["xlsx"] = flag
        i += 1
    return args


def _usage() -> None:
    print(
        "Usage: python -m utils.xlsx_to_indicators "
        "<xlsx> \\",
    )
    print("  [--config-out indicator.json] \\")
    print("  [--filter-out narrative_filter.json] \\")
    print("  [--indicator-sheet 指標] \\")
    print("  [--filter-sheet 敘事指標]")


def _write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data, f, ensure_ascii=False, indent=2,
        )


def main() -> None:
    from risk_engine import log_config
    log_config.setup_logging()

    args = _parse_args(sys.argv)
    if not args["xlsx"]:
        _usage()
        sys.exit(1)

    try:
        config, narrative_filter = convert(
            args["xlsx"],
            indicator_sheet=args["indicator_sheet"],
            filter_sheet=args["filter_sheet"],
        )
    except (FileNotFoundError, ValueError) as e:
        logger.error("轉換失敗: %s", e)
        sys.exit(1)

    _write_json(args["config_out"], config)
    _write_json(args["filter_out"], narrative_filter)

    for ind, rules in config.items():
        print(f"  指標 [{ind}]: {len(rules)} 條規則")
    for ind, sections in narrative_filter.items():
        total = sum(len(v) for v in sections.values())
        print(
            f"  敘事 [{ind}]: {len(sections)} 段落, "
            f"{total} 科目",
        )

    print(f"\n已輸出指標設定至 {args['config_out']}")
    print(f"已輸出敘事過濾至 {args['filter_out']}")


if __name__ == "__main__":
    main()
