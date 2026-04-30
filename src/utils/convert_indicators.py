"""將 指標_orig.csv 轉換為結構化 JSON 設定檔。

轉換後的 JSON 讓 risk_checker.py 只需做
「查值 → 算式 → 比大小」，不必再解析中文門檻。

門檻字串解析直接重用 ``risk_engine.threshold.parse_threshold``，
保證寫入設定檔的格式與執行時讀回的格式一致。

Usage:
    python convert_indicators.py 指標_orig.csv -o indicators_config.json
"""
import csv
import json
import logging
import sys
from typing import Any

from risk_engine.threshold import parse_threshold

logger = logging.getLogger(__name__)


# ── CSV 讀取與轉換 ──────────────────────────────────

def load_csv(csv_path: str) -> list[dict[str, str]]:
    """讀取 CSV，回傳 list of dict。"""
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    except FileNotFoundError:
        logger.error("指標 CSV 不存在: %s", csv_path)
        raise
    except OSError as e:
        logger.error(
            "讀取指標 CSV 失敗: %s — %s", csv_path, e,
        )
        raise


def row_to_rule(
    row: dict[str, str],
) -> tuple[list[str], dict[str, Any]]:
    """將單列指標資料轉為 (產業列表, rule dict)。

    供 CSV 與 Excel 兩條轉換路徑共用。

    Args:
        row: 來自 CSV 或 Excel 的單列 dict。

    Returns:
        (industries, rule)：產業列表與單條規則 dict。
    """
    industries = [
        ind.strip()
        for ind in row["產業別"].split("\n")
        if ind.strip()
    ]
    threshold_info = parse_threshold(
        row["指標判斷門檻值"]
    )

    rule: dict[str, Any] = {
        "section": row["財務分析指標"],
        "indicator_name": row["指標名稱"],
        "indicator_code": row["指標對應財報欄位"],
        "tag_id": row["指標編號"],
        "value_formula": row["指標對應財報欄位"],
        **threshold_info,
        "risk_description": row["風險情境"],
        "result_unit": row.get(
            "結果單位", ""
        ).strip(),
    }

    raw_narrative = row.get("敘事代碼", "").strip()
    if raw_narrative:
        rule["narrative_codes"] = [
            c.strip()
            for c in raw_narrative.split(",")
            if c.strip()
        ]

    return industries, rule


def convert(csv_path: str) -> dict[str, list[dict]]:
    """將指標 CSV 轉換為以產業為 key 的結構化設定。

    Args:
        csv_path: 指標 CSV 檔案路徑。

    Returns:
        {產業名: [rule, rule, ...], ...}
    """
    rows = load_csv(csv_path)
    config: dict[str, list[dict]] = {}

    for row in rows:
        industries, rule = row_to_rule(row)
        for ind in industries:
            config.setdefault(ind, []).append(
                rule.copy()
            )

    return config


# ── 主程式 ──────────────────────────────────────────

def main() -> None:
    """CLI 入口：讀取指標 CSV、輸出結構化 JSON 設定檔。

    參數：
        argv[1]      ：指標 CSV 路徑（必填）。
        ``-o <path>``：輸出 JSON 路徑（選填，預設 indicators_config.json）。
    """
    if len(sys.argv) < 2:
        print("Usage: python convert_indicators.py <csv>")
        print("       [-o output.json]")
        sys.exit(1)

    csv_path = sys.argv[1]
    out_path = "indicators_config.json"
    if "-o" in sys.argv:
        o_idx = sys.argv.index("-o")
        if o_idx + 1 >= len(sys.argv):
            print(
                "錯誤: -o 後須指定輸出路徑",
                file=sys.stderr,
            )
            sys.exit(1)
        out_path = sys.argv[o_idx + 1]

    config = convert(csv_path)

    try:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(
                config, f, ensure_ascii=False, indent=2,
            )
    except PermissionError:
        logger.error("無權限寫入檔案: %s", out_path)
        raise
    except OSError as e:
        logger.error(
            "寫入檔案失敗: %s — %s", out_path, e,
        )
        raise

    for industry, rules in config.items():
        compound_count = sum(
            1 for r in rules
            if r.get("compare_type") == "compound"
        )
        suffix = (
            f" (含 {compound_count} 條複合條件)"
            if compound_count else ""
        )
        print(
            f"  {industry}: {len(rules)} 條規則{suffix}"
        )
    print(f"\n已輸出至 {out_path}")


if __name__ == "__main__":
    main()
