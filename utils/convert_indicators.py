"""將 指標_orig.csv 轉換為結構化 JSON 設定檔。

轉換後的 JSON 讓 risk_checker.py 只需做
「查值 → 算式 → 比大小」，不用解析中文門檻。

Usage:
    python convert_indicators.py 指標_orig.csv -o indicators_config.json
"""
import csv
import json
import logging
import re
import sys
from typing import Any

logger = logging.getLogger(__name__)


# ── 文字正規化 ──────────────────────────────────────

def _normalize(text: str) -> str:
    """全形符號轉半形、去除多餘空白。"""
    mapping = {"＞": ">", "＜": "<", "＝": "="}
    for full, half in mapping.items():
        text = text.replace(full, half)
    return text.strip()


# ── compound 子條件解析 ─────────────────────────────

from risk_engine.constants import OP_PATTERN as _OP_PATTERN


def _parse_sub_condition(expr: str) -> dict[str, Any]:
    """解析單一子條件表達式。

    格式: "公式 運算子 數值"
    範例:
      "TIBB011 - TIBB011_PRV >= 30"
      "TIBB017 <= 0"
      "TIBA041/(TIBA004+TIBA005) >= 6"

    Args:
        expr: 去除外層括號後的子條件字串。

    Returns:
        {"value_formula": str,
         "operator": str, "threshold": float}
    """
    expr = expr.strip()
    # 去除最外層括號（如有）
    if expr.startswith("(") and expr.endswith(")"):
        # 確認是完整包覆的括號才去除
        depth = 0
        is_wrapper = True
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                is_wrapper = False
                break
        if is_wrapper:
            expr = expr[1:-1].strip()

    # 從右邊找比較運算子（避免與公式中的 - 混淆）
    matches = list(_OP_PATTERN.finditer(expr))
    if not matches:
        return {
            "node_type": "condition",
            "value_formula": expr,
            "operator": "",
            "threshold": 0.0,
            "_parse_error": True,
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


def _parse_compound(text: str) -> dict[str, Any]:
    """解析 AND/OR 複合條件為 condition_tree。

    格式:
      "(TIBB011 - TIBB011_PRV >= 30) AND TIBB017 <= 0"
      "TIBA041/(TIBA004+TIBA005) >= 6 OR TIBB011 <= 60"

    Args:
        text: 門檻值字串。

    Returns:
        {"compare_type": "compound",
         "condition_tree": {node_type, children}}
    """
    parts = re.split(r"\s+(AND|OR)\s+", text)
    children: list[dict[str, Any]] = []
    operators: list[str] = []

    for part in parts:
        part = part.strip()
        if part in ("AND", "OR"):
            operators.append(part)
        elif part:
            children.append(
                _parse_sub_condition(part)
            )

    if len(children) == 1:
        tree = children[0]
    else:
        op = operators[0].lower() if operators else "and"
        tree = {
            "node_type": op,
            "children": children,
        }

    return {
        "compare_type": "compound",
        "condition_tree": tree,
    }


# ── 門檻值解析（主入口） ───────────────────────────

def parse_threshold(raw: str) -> dict[str, Any]:
    """解析門檻值字串，回傳結構化 dict。

    支援格式：
      絕對值:  >150%  <100%  <0  >180天
      前期比較: 較前期比率增加20%  較前期比率減少20%
               較前期增加60天
      複合條件: ... AND ...  / ... OR ...

    Args:
        raw: 原始門檻值字串（可能含多行註解）。

    Returns:
        結構化的門檻設定 dict。
    """
    first_line = _normalize(raw.split("\n")[0])

    # ── 複合條件（含 AND / OR） ──
    if re.search(r"\b(AND|OR)\b", first_line):
        return _parse_compound(first_line)

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

        # 敘事代碼（選用欄位，逗號分隔）
        raw_narrative = row.get(
            "敘事代碼", ""
        ).strip()
        if raw_narrative:
            rule["narrative_codes"] = [
                c.strip()
                for c in raw_narrative.split(",")
                if c.strip()
            ]

        for ind in industries:
            config.setdefault(ind, []).append(
                rule.copy()
            )

    return config


# ── 主程式 ──────────────────────────────────────────

def main() -> None:
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
