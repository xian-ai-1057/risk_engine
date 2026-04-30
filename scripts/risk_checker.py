"""財報風險判斷 CLI。

讀取財報（CSV/JSON）+ 指標設定（JSON），輸出風險判斷結果 JSON；
若加上 ``--narrative`` 並指定 ``--narrative-filter``，
另外輸出敘事用的分群結果（``narratives`` / ``narratives_grouped``）。

Risk 與 Narrative 為兩條獨立的 pipeline：
  - Risk：``indicators_config.json`` 的規則 → 計算 → ``sections``
  - Narrative：``narrative_filter.json`` → 撈報表 → grouped

Usage:
    python risk_checker.py \\
        --report 財報.csv --config indicators_config.json \\
        --industry 批發業 --customer A00001 --date 20241231 \\
        [-o output.json] [--compact] \\
        [--narrative --narrative-filter narrative_filter.json] \\
        [--log risk_checker.log] [--debug]
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from risk_engine import loader
from risk_engine import log_config
from risk_engine import report as report_mod
from risk_engine import post_rules
from risk_engine import types
from utils import narrative

logger = logging.getLogger(__name__)


# ── 參數解析 ────────────────────────────────────────

def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令列參數。

    Args:
        argv: 完整 ``sys.argv``（含程式名）。

    Returns:
        ``argparse.Namespace``，欄位對應 CLI 參數名（``-`` 轉 ``_``）。
    """
    parser = argparse.ArgumentParser(
        prog="risk_checker",
        description="財報風險判斷程式",
    )
    parser.add_argument("--report", required=True, help="財報 CSV/JSON 路徑")
    parser.add_argument(
        "--config", default="indicators_config.json",
        help="指標設定 JSON 路徑（預設：indicators_config.json）",
    )
    parser.add_argument("--industry", required=True, help="產業別")
    parser.add_argument("--customer", required=True, help="客戶代碼")
    parser.add_argument("--date", required=True, help="報表日期")
    parser.add_argument(
        "-o", "--output", default="result.json",
        help="輸出 JSON 路徑（預設：result.json）",
    )
    parser.add_argument(
        "--compact", action="store_true",
        help="同時輸出 LLM 精簡格式（_compact.json）",
    )
    parser.add_argument(
        "--narrative", action="store_true",
        help="啟用敘事分支（需搭配 --narrative-filter）",
    )
    parser.add_argument(
        "--narrative-filter",
        help="敘事篩選設定 JSON 路徑",
    )
    parser.add_argument("--log", help="log 檔案路徑")
    parser.add_argument(
        "--debug", action="store_true", help="啟用 DEBUG 等級 log",
    )
    return parser.parse_args(argv[1:])


# ── 輸出 ──────────────────────────────────────────────

def _write_json(path: str, data: dict) -> None:
    """以 UTF-8、indent=2 寫入 JSON 檔案，記錄 IO 錯誤後重新 raise。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except PermissionError:
        logger.error("無權限寫入檔案: %s", path)
        raise
    except OSError as e:
        logger.error("寫入檔案失敗: %s — %s", path, e)
        raise
    logger.info("已寫入: %s", path)


def _print_summary(result: dict[str, Any], out_path: str) -> None:
    """印出（並寫入 log）報告摘要：客戶、產業、觸發數、缺資料數。"""
    s = result["summary"]
    lines = [
        f"客戶: {result['customer_id']}",
        f"產業: {result['industry']}",
        f"觸發: {s['triggered_count']} / {s['total_rules']} 條規則",
    ]
    if s["missing_count"]:
        lines.append(f"缺少資料: {s['missing_count']} 條")
    lines.append(f"已輸出至 {out_path}")

    for line in lines:
        print(line)
        logger.info(line)


# ── 主程式 ──────────────────────────────────────────

def main() -> None:
    """CLI 入口：解析參數、設定 logging、執行 pipeline。"""
    args = parse_args(sys.argv)

    log_level = logging.DEBUG if args.debug else logging.INFO
    log_config.setup_logging(log_file=args.log, level=log_level)
    logger.info("程式啟動")

    if args.narrative and not args.narrative_filter:
        logger.error("--narrative 開啟時必須提供 --narrative-filter <json>")
        sys.exit(1)

    try:
        _run(args)
    except (types.ReportLoadError, types.ConfigError) as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception:
        logger.exception("未預期的錯誤")
        sys.exit(1)


def _run(args: argparse.Namespace) -> None:
    """主流程：載入資料 → Risk pipeline →（選用）Narrative pipeline → 輸出。

    Args:
        args: ``parse_args()`` 的結果。
    """
    report = loader.load_report(args.report)
    rules = loader.load_config(args.config, args.industry)

    # Risk 分支：完全不依賴 narrative_filter
    result = report_mod.generate_report(
        report, rules, args.customer, args.date, args.industry,
    )
    result = post_rules.apply_post_rules(result)

    # Narrative 分支：純 filter-driven
    if args.narrative:
        narrative_filter = narrative.load_narrative_filter(
            args.narrative_filter, args.industry,
        )
        if narrative_filter is None:
            logger.error(
                "無法載入產業 '%s' 的 narrative_filter", args.industry,
            )
            sys.exit(1)
        result["narratives"] = narrative.build_narrative(
            report, narrative_filter,
        )
        result["narratives_grouped"] = narrative.build_grouped_narrative(
            report, narrative_filter,
        )

    out_path = args.output
    _write_json(out_path, result)

    if args.compact:
        compact = report_mod.to_llm_format(result["sections"])
        compact_path = out_path.replace(".json", "_compact.json")
        _write_json(compact_path, compact)

    _print_summary(result, out_path)
    logger.info("程式結束")


if __name__ == "__main__":
    main()
