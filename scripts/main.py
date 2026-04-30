"""財報風險分析 EXE 入口。

支援兩種輸入模式：
  A. CLI 參數（手動執行/除錯用）
  B. --stdin JSON（後端程式呼叫用）

支援兩種輸出模式：
  - 寫入 JSON 檔案（預設）
  - --stdout 輸出至標準輸出

Usage:
    # CLI 模式（最精簡）
    risk_analysis.exe f1.html f2.html f3.html f4.html \\
        --industry 批發業 \\
        [-o output.json] [--stdout] [--debug]

    # CLI 模式（含選填 metadata）
    risk_analysis.exe f1.html f2.html f3.html f4.html \\
        --industry 批發業 \\
        [--customer A00001] [--date 20241231] \\
        [--request-id trace-001] \\
        [-o output.json] [--stdout] [--debug]

    # stdin 模式
    echo '{"html_files":[...], "industry":"批發業"}' \\
        | risk_analysis.exe --stdin [--stdout]
"""
import json
import logging
import os
import sys
import uuid
from typing import Any
from datetime import datetime

from risk_engine import loader, log_config, types
from risk_engine.loader import build_report_row
from risk_engine.paths import get_base_dir
from risk_engine.pipeline import ReportPipeline
from risk_engine.types import EXE_SCHEMA_VERSION
from utils.html_to_json import convert_html_files_to_dict

logger = logging.getLogger(__name__)

# ── 路徑解析 ──────────────────────────────────────

def _resolve_paths(base_dir: str) -> dict[str, str]:
    """自動發現 EXE 同目錄下的設定檔與 prompt 檔。

    Returns:
        包含所有外部檔案路徑的 dict。

    Raises:
        FileNotFoundError: 必要檔案不存在。
    """

    paths = {
        "config": os.path.join(
            base_dir, "indicators_config.json",
        ),
        "tag_table": os.path.join(
            base_dir, "tag_table.csv",
        ),
        "risk_user_prompt": os.path.join(
            base_dir, "risk_user_prompt.txt",
        ),
        "narrative_user_prompt": os.path.join(
            base_dir, "narrative_user_prompt.txt",
        ),
    }

    # tag_table 為選用
    optional = {"tag_table"}
    missing = [
        k for k, v in paths.items()
        if k not in optional and not os.path.isfile(v)
    ]
    if missing:
        detail = "\n".join(
            f"  - {k}: {paths[k]}" for k in missing
        )
        raise FileNotFoundError(
            f"缺少必要檔案:\n{detail}"
        )

    # tag_table 不存在時設為 None
    if not os.path.isfile(paths["tag_table"]):
        paths["tag_table"] = None  # type: ignore[assignment]

    return paths


# ── 參數解析 ──────────────────────────────────────

def _parse_cli_args(
    argv: list[str],
) -> dict[str, Any]:
    """從 CLI 參數解析輸入。"""
    args: dict[str, Any] = {
        "html_files": [],
        "industry": "",
        "customer": "",
        "date": "",
        "request_id": "",
        "output": None,
        "stdout": False,
        "debug": False,
        "stdin": False,
    }

    flag_map = {
        "--industry": "industry",
        "--customer": "customer",
        "--date": "date",
        "--request-id": "request_id",
        "-o": "output",
        "--output": "output",
    }
    bool_flags = {
        "--stdout": "stdout",
        "--debug": "debug",
        "--stdin": "stdin",
    }

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

        # 非 flag 參數視為 HTML 檔案路徑
        if not flag.startswith("-"):
            args["html_files"].append(flag)

        i += 1

    return args


def _parse_stdin_args() -> dict[str, Any]:
    """從 stdin JSON 解析輸入。"""
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"stdin JSON 格式錯誤: {e}"
        ) from e

    html_files = data.get("html_files", [])
    if not isinstance(html_files, list):
        raise ValueError(
            "html_files 須為陣列格式"
        )
    if html_files and not all(
        isinstance(f, str) for f in html_files
    ):
        raise ValueError(
            "html_files 中的每個元素須為字串"
        )

    return {
        "html_files": html_files,
        "industry": str(data.get("industry", "")),
        "customer": str(data.get("customer", "")),
        "date": str(data.get("date", "")),
        "request_id": str(
            data.get("request_id", "")
        ),
        "output": data.get("output"),
        "stdout": False,
        "debug": bool(data.get("debug", False)),
        "stdin": True,
    }


def _validate_args(args: dict[str, Any]) -> None:
    """驗證必要參數。

    必填：html_files（4 個）、industry。
    選填：customer、date、request_id。
    """
    errors: list[str] = []

    if len(args["html_files"]) != 4:
        errors.append(
            f"須提供 4 個 HTML 檔案，"
            f"實際收到 {len(args['html_files'])} 個"
        )

    if not args["industry"]:
        errors.append("缺少參數: --industry")

    if errors:
        raise ValueError("\n".join(errors))


# ── 主流程 ────────────────────────────────────────

# html_to_json 在 raw dict 中夾帶的 metadata key。
# `_period_dates` 在下方會明確 pop 出來；`skipped` 用於
# 過濾被忽略的代碼資訊。
_META_KEYS = {"skipped"}


def _read_prompt_template(path: str, label: str) -> str:
    """讀取 prompt 模板檔。

    Args:
        path: 模板檔路徑。
        label: 用於錯誤訊息的友善名稱（例如 "敘事"）。

    Raises:
        FileNotFoundError: 檔案不存在或無法讀取。
    """
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise FileNotFoundError(
            f"無法讀取{label} prompt 模板: {path} — {e}"
        ) from e


def _run(
    args: dict[str, Any],
    request_id: str,
) -> types.ExeOutput:
    """執行主要處理流程。"""
    base_dir = get_base_dir()
    paths = _resolve_paths(base_dir)

    # 1. HTML → dict（純記憶體）
    logger.info("開始轉換 HTML 財報")
    raw_report = convert_html_files_to_dict(
        args["html_files"],
        tag_table_path=paths["tag_table"],
    )

    # 1b. 提取期間日期 metadata
    period_dates: list[str] = raw_report.pop(
        "_period_dates", [],
    )
    logger.info("期間日期: %s", period_dates)

    # 2. 正規化為 Report
    report: types.Report = {
        code: build_report_row(data)
        for code, data in raw_report.items()
        if code not in _META_KEYS
    }
    logger.info("財報載入完成，代碼數: %d", len(report))

    # 3. 載入規則
    rules = loader.load_config(
        paths["config"], args["industry"],
    )

    # 4. 讀取 user prompt 模板
    narrative_tmpl = _read_prompt_template(
        paths["narrative_user_prompt"], "敘事",
    )
    risk_tmpl = _read_prompt_template(
        paths["risk_user_prompt"], "風險",
    )

    # 5. 執行 Pipeline（period_dates 由 pipeline 統一處理）
    pipe = ReportPipeline(
        report=report,
        rules=rules,
        narrative_prompt_template=narrative_tmpl,
        risk_prompt_template=risk_tmpl,
        customer_id=args.get("customer", ""),
        report_date=args.get("date", ""),
        industry=args["industry"],
        period_dates=period_dates or None,
    )
    result = pipe.run()

    # 6. 組裝最終輸出
    output: types.ExeOutput = {
        "schema_version": EXE_SCHEMA_VERSION,
        "request_id": request_id,
        "industry": args["industry"],
        "narrative_prompt": result["narrative_prompt"],
        "risk_prompt": result["risk_prompt"],
        "grouped_report": result["grouped_report"],
        "risk_report": result["risk_report"],
    }

    # 選填 metadata：有值才寫入
    customer = args.get("customer", "")
    date = args.get("date", "")
    if customer:
        output["customer_id"] = customer
    if date:
        output["report_date"] = date

    return output


def _default_output_path(request_id: str) -> str:
    """產生預設 output 路徑。

    位於 ``get_base_dir()/output/`` 下，與 cwd 無關，避免
    上游併發呼叫時把產出檔寫到呼叫方的 cwd。檔名帶
    ``request_id`` + per-request timestamp，併發不互相覆蓋。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(
        get_base_dir(),
        "output",
        f"result_{request_id}_{ts}.json",
    )


def _write_output(
    output: types.ExeOutput,
    output_path: str | None,
    to_stdout: bool,
    request_id: str,
) -> None:
    """寫入輸出結果。"""
    json_str = json.dumps(
        output, ensure_ascii=False, indent=2,
    )

    # 寫入檔案
    if output_path is None:
        output_path = _default_output_path(request_id)

    if output_path:
        try:
            os.makedirs(
                os.path.dirname(output_path) or ".",
                exist_ok=True,
            )
            with open(
                output_path, "w", encoding="utf-8",
            ) as f:
                f.write(json_str)
        except PermissionError:
            logger.error(
                "無權限寫入輸出檔案: %s", output_path,
            )
            raise
        except OSError as e:
            logger.error(
                "寫入輸出檔案失敗: %s — %s",
                output_path, e,
            )
            raise
        logger.info("已寫入: %s", output_path)

    # stdout 輸出
    if to_stdout:
        print(json_str)


def _usage() -> None:
    """印出使用說明。"""
    print(
        "Usage:\n"
        "  risk_analysis.exe "
        "<html_1> <html_2> <html_3> <html_4>\n"
        "    --industry <str>\n"
        "    [--customer <str>] [--date <str>]\n"
        "    [--request-id <str>]\n"
        "    [-o output.json] [--stdout] [--debug]\n"
        "\n"
        "  echo '{...}' | "
        "risk_analysis.exe --stdin [--stdout]\n"
    )


# ── 入口 ──────────────────────────────────────────

def main() -> None:
    """EXE 主入口。"""
    # 解析參數
    cli_args = _parse_cli_args(sys.argv)

    if cli_args["stdin"]:
        try:
            args = _parse_stdin_args()
        except ValueError as e:
            # stdin 解析失敗時尚無 request_id
            fallback_id = uuid.uuid4().hex[:8]
            print(
                json.dumps(
                    {"error": str(e),
                     "error_code": "INVALID_ARGS",
                     "request_id": fallback_id},
                    ensure_ascii=False,
                ),
            )
            sys.exit(1)
        # 保留 CLI 的 --stdout 和 --debug
        args["stdout"] = cli_args["stdout"]
        args["debug"] = (
            args["debug"] or cli_args["debug"]
        )
    else:
        args = cli_args

    # request_id：優先使用傳入值，沒有才自動產生
    request_id = (
        args.get("request_id", "")
        or uuid.uuid4().hex[:8]
    )

    # 設定 logging（log 不混入 stdout）
    log_level = (
        logging.DEBUG if args["debug"]
        else logging.INFO
    )
    log_config.setup_logging(
        level=log_level, request_id=request_id,
    )
    logger.info(
        "程式啟動 (request_id=%s)", request_id,
    )

    # 驗證參數
    try:
        _validate_args(args)
    except ValueError as e:
        logger.error("參數錯誤: %s", e)
        if args.get("stdout"):
            _exit_error(
                str(e), "INVALID_ARGS",
                request_id, args,
            )
        else:
            _usage()
            print(f"\n{e}", file=sys.stderr)
        sys.exit(1)

    # 執行
    try:
        output = _run(args, request_id)
    except FileNotFoundError as e:
        logger.error("檔案錯誤: %s", e)
        _exit_error(
            str(e), "MISSING_FILE", request_id, args,
        )
        sys.exit(2)
    except (
        types.ReportLoadError,
        types.ConfigError,
    ) as e:
        logger.error("設定錯誤: %s", e)
        _exit_error(
            str(e), "CONFIG_ERROR", request_id, args,
        )
        sys.exit(2)
    except Exception as e:
        logger.exception("處理錯誤")
        _exit_error(
            str(e), "PROCESSING_ERROR", request_id, args,
        )
        sys.exit(3)

    # 輸出
    _write_output(
        output,
        args.get("output"),
        args.get("stdout", False),
        request_id,
    )

    logger.info("程式結束 (request_id=%s)", request_id)


def _exit_error(
    msg: str,
    error_code: str,
    request_id: str,
    args: dict[str, Any],
) -> None:
    """錯誤時的輸出處理。

    Args:
        msg: 錯誤訊息（人類可讀）。
        error_code: ``types.ERROR_CODES`` 中的代碼，
            供上游程式分流。
        request_id: 本次請求識別碼。
        args: 已解析的參數 dict（用來判斷是否走 ``--stdout``）。
    """
    if args.get("stdout"):
        payload: types.ExeError = {
            "error": msg,
            "error_code": error_code,
            "request_id": request_id,
        }
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"錯誤: {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
