"""財報風險判斷程式。

讀取財報 CSV/JSON + 指標設定檔 JSON →
輸出風險判斷結果 JSON。

Risk 與 Narrative 是兩條獨立 pipeline：
  - Risk：indicator.json (rules) → 計算 → sections
  - Narrative：narrative_filter.json → 撈報表 → grouped

Usage:
    python risk_checker.py \\
        --report 財報.csv \\
        --config indicators_config.json \\
        --industry 批發業 \\
        --customer A00001 \\
        --date 20241231 \\
        [-o output.json] \\
        [--compact] [--narrative] \\
        [--narrative-filter narrative_filter.json] \\
        [--log risk_checker.log] \\
        [--debug]
"""
import json
import logging
import sys
from typing import Any

from risk_engine import loader
from risk_engine import log_config
from risk_engine import report as report_mod
from risk_engine import post_rules
from risk_engine import types
from utils import narrative

logger = logging.getLogger(__name__)


# ── 參數解析 ────────────────────────────────────────

def parse_args(
    argv: list[str],
) -> dict[str, Any]:
    """簡易參數解析。

    Args:
        argv: sys.argv。

    Returns:
        參數 dict。
    """
    args: dict[str, Any] = {
        "report": "",
        "config": "indicators_config.json",
        "industry": "",
        "customer": "",
        "date": "",
        "output": "result.json",
        "compact": False,
        "narrative": False,
        "narrative_filter": None,
        "log": None,
        "debug": False,
    }

    flag_map = {
        "--report": "report",
        "--config": "config",
        "--industry": "industry",
        "--customer": "customer",
        "--date": "date",
        "--narrative-filter": "narrative_filter",
        "--log": "log",
        "-o": "output",
    }
    bool_flags = {"--compact": "compact",
                  "--narrative": "narrative",
                  "--debug": "debug"}

    i = 1
    while i < len(argv):
        flag = argv[i]

        if flag in bool_flags:
            args[bool_flags[flag]] = True
            i += 1
            continue

        if flag in flag_map and i + 1 < len(argv):
            args[flag_map[flag]] = argv[i + 1]
            i += 2
            continue

        i += 1

    return args


def _usage() -> None:
    """印出使用說明。"""
    print("Usage: python risk_checker.py \\")
    print("  --report <csv> --config <json> \\")
    print("  --industry <str> --customer <str>")
    print("  --date <str> [-o output.json]")
    print("  [--compact] [--narrative]")
    print("  [--narrative-filter narrative_filter.json]")
    print("  [--log risk_checker.log]")
    print("  [--debug]")


# ── 輸出 ──────────────────────────────────────────────

def _write_json(path: str, data: dict) -> None:
    """寫入 JSON 檔案。"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                data, f, ensure_ascii=False, indent=2,
            )
    except PermissionError:
        logger.error("無權限寫入檔案: %s", path)
        raise
    except OSError as e:
        logger.error(
            "寫入檔案失敗: %s — %s", path, e,
        )
        raise
    logger.info("已寫入: %s", path)


def _print_summary(
    result: dict[str, Any],
    out_path: str,
) -> None:
    """印出並記錄報告摘要。"""
    s = result["summary"]
    lines = [
        f"客戶: {result['customer_id']}",
        f"產業: {result['industry']}",
        (
            f"觸發: {s['triggered_count']} / "
            f"{s['total_rules']} 條規則"
        ),
    ]
    if s["missing_count"]:
        lines.append(
            f"缺少資料: {s['missing_count']} 條"
        )
    lines.append(f"已輸出至 {out_path}")

    for line in lines:
        print(line)
        logger.info(line)


# ── 主程式 ──────────────────────────────────────────

def main() -> None:
    """主程式入口。"""
    args = parse_args(sys.argv)

    # 設定 logging（在所有操作之前）
    log_level = (
        logging.DEBUG if args["debug"]
        else logging.INFO
    )
    log_config.setup_logging(
        log_file=args["log"], level=log_level,
    )
    logger.info("程式啟動")

    required = [
        "report", "config", "industry",
        "customer", "date",
    ]
    missing = [k for k in required if not args[k]]
    if missing:
        _usage()
        msg = f"缺少參數: {', '.join(missing)}"
        logger.error(msg)
        print(f"\n{msg}")
        sys.exit(1)

    try:
        _run(args)
    except (
        types.ReportLoadError,
        types.ConfigError,
    ) as e:
        logger.error("%s", e)
        sys.exit(1)
    except Exception:
        logger.exception("未預期的錯誤")
        sys.exit(1)


def _run(args: dict[str, Any]) -> None:
    """執行主要流程（由 main 呼叫）。"""
    # 載入資料
    report = loader.load_report(args["report"])
    rules = loader.load_config(
        args["config"], args["industry"],
    )

    # Risk 分支：完全不依賴 narrative_filter
    result = report_mod.generate_report(
        report, rules,
        args["customer"], args["date"],
        args["industry"],
    )
    result = post_rules.apply_post_rules(result)

    # Narrative 分支：純 filter-driven
    if args["narrative"]:
        if not args["narrative_filter"]:
            logger.error(
                "--narrative 開啟時必須提供"
                " --narrative-filter <json>",
            )
            sys.exit(1)
        narrative_filter = (
            narrative.load_narrative_filter(
                args["narrative_filter"],
                args["industry"],
            )
        )
        if narrative_filter is None:
            logger.error(
                "無法載入產業 '%s' 的"
                " narrative_filter",
                args["industry"],
            )
            sys.exit(1)
        result["narratives"] = (
            narrative.build_narrative(
                report, narrative_filter,
            )
        )
        result["narratives_grouped"] = (
            narrative.build_grouped_narrative(
                report, narrative_filter,
            )
        )

    # 輸出
    out_path = args["output"]
    _write_json(out_path, result)

    if args["compact"]:
        compact = report_mod.to_llm_format(
            result["sections"],
        )
        compact_path = out_path.replace(
            ".json", "_compact.json",
        )
        _write_json(compact_path, compact)

    _print_summary(result, out_path)
    logger.info("程式結束")


if __name__ == "__main__":
    main()
