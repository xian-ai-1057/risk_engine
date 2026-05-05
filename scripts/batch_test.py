"""batch_test — 批次執行指定資料夾內所有報告 JSON，產出風險與敘事 Prompt。

與 EXE 入口（``scripts/main.py``）共用「xlsx 為指標唯一來源」的流程，
讓你能在不打包 EXE 的情況下，先針對既有的 ``data/report/新測試案例_json``
逐一跑完整 pipeline 驗證功能。

執行方式：
    python scripts/batch_test.py

輸出結果寫入 output/json/新測試案例/result_{customer_id}_{timestamp}.json。
"""
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from risk_engine import ReportPipeline
from risk_engine.loader import build_report_row
from risk_engine.types import ExeOutput
from utils import narrative as narrative_mod
from utils.xlsx_to_indicators import convert as xlsx_convert

# ── 批次參數（可自行修改）─────────────────────────
REPORT_DIR = _REPO / "data" / "report" / "新測試案例_json"
XLSX_PATH = _REPO / "data" / "20260504_7大關鍵指標.xlsx"
INDUSTRY = "7大指標"                           # 產業別（對應 xlsx 指標 sheet）
REPORT_DATE = datetime.now().strftime("%Y-%m-%d")
NARR_PROMPT_PATH = _REPO / "data" / "prompt" / "財報敘事_user_prompt.txt"
RISK_PROMPT_PATH = _REPO / "data" / "prompt" / "財報風險_user_prompt.txt"
OUTPUT_DIR = _REPO / "output" / "json" / "新測試案例"
# 可選：把每次 xlsx 轉換結果落成 audit JSON（與 EXE 行為一致）。
# 設成 None 表示不寫 audit。
AUDIT_DIR: Path | None = _REPO / "output" / "audit"
# ─────────────────────────────────────────────────

TIME_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
_META_KEYS = {"skipped", "_period_dates"}


def _write_output(out_path: Path, output: ExeOutput) -> None:
    """建立目錄並將結果序列化為 UTF-8 JSON 檔案。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, ensure_ascii=False, indent=2, fp=f)


def _write_audit_json(path: Path, data: object) -> None:
    """把 xlsx 轉換結果寫到 audit 目錄；失敗只警告。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"  (warn) audit 寫入失敗 {path}: {e}")


def run_single(
    report_path: Path,
    customer_id: str,
    rules: list,
    narrative_filter: dict | None,
    narr_template: str,
    risk_template: str,
) -> None:
    """對單一報告 JSON 執行完整 pipeline，並將結果寫入輸出目錄。"""
    with open(report_path, encoding="utf-8") as f:
        raw = json.load(f)

    period_dates: list[str] = raw.pop("_period_dates", [])
    report = {
        code: build_report_row(data)
        for code, data in raw.items()
        if code not in _META_KEYS
    }

    result = ReportPipeline(
        report=report,
        rules=rules,
        narrative_filter=narrative_filter,
        narrative_prompt_template=narr_template,
        risk_prompt_template=risk_template,
        customer_id=customer_id,
        report_date=REPORT_DATE,
        industry=INDUSTRY,
        period_dates=period_dates or None,
    ).run()

    output: ExeOutput = {
        "request_id": customer_id,
        "customer_id": customer_id,
        "report_date": REPORT_DATE,
        "industry": INDUSTRY,
        "narrative_prompt": result["narrative_prompt"],
        "risk_prompt": result["risk_prompt"],
        "grouped_report": result["grouped_report"],
        "risk_report": result["risk_report"],
    }
    _write_output(
        OUTPUT_DIR / f"result_{customer_id}_{TIME_STAMP}.json",
        output,
    )


def main() -> None:
    """載入共用資源後，依序對每個報告執行 pipeline，最後印出執行摘要。"""
    json_files = sorted(glob.glob(str(REPORT_DIR / "*.json")))
    total = len(json_files)
    if total == 0:
        print(f"在 {REPORT_DIR} 中找不到任何 JSON 檔案。")
        return

    if not XLSX_PATH.is_file():
        print(f"找不到指標 xlsx: {XLSX_PATH}")
        sys.exit(1)

    print(f"讀取指標 xlsx: {XLSX_PATH}")
    config_dict, filter_dict = xlsx_convert(str(XLSX_PATH))

    if AUDIT_DIR is not None:
        _write_audit_json(
            AUDIT_DIR / "indicators_config.json", config_dict,
        )
        _write_audit_json(
            AUDIT_DIR / "narrative_filter.json", filter_dict,
        )

    if INDUSTRY not in config_dict:
        available = ", ".join(config_dict.keys())
        print(
            f"產業 '{INDUSTRY}' 不存在於 xlsx 指標工作表。"
            f" 可用: {available}"
        )
        sys.exit(1)
    rules = config_dict[INDUSTRY]
    print(f"  指標 [{INDUSTRY}]: {len(rules)} 條規則")

    narrative_filter = filter_dict.get(INDUSTRY)
    if narrative_filter is None:
        available = ", ".join(filter_dict.keys()) or "(無)"
        print(
            f"  (warn) xlsx 敘事工作表沒有產業 '{INDUSTRY}'，"
            f"敘事 prompt 將為空。可用: {available}"
        )
    else:
        narrative_mod.validate_filter_sections(
            narrative_filter, INDUSTRY,
        )
        total_items = sum(
            len(v) for v in narrative_filter.values()
        )
        print(
            f"  敘事 [{INDUSTRY}]: {len(narrative_filter)} 段落, "
            f"{total_items} 項目"
        )

    narr_template = NARR_PROMPT_PATH.read_text(encoding="utf-8")
    risk_template = RISK_PROMPT_PATH.read_text(encoding="utf-8")

    print(f"\n共找到 {total} 個報告，開始批次執行...\n")

    succeeded, failed = [], []
    for idx, path in enumerate(json_files, 1):
        customer_id = os.path.splitext(os.path.basename(path))[0]
        print(f"[{idx}/{total}] {customer_id} ... ", end="", flush=True)
        try:
            run_single(
                Path(path), customer_id, rules,
                narrative_filter, narr_template, risk_template,
            )
            succeeded.append(customer_id)
            print("OK")
        except Exception as e:
            failed.append((customer_id, str(e)))
            print(f"FAILED: {e}")

    # 摘要
    print(f"\n{'='*60}")
    print(f"完成: {len(succeeded)}/{total} 成功, {len(failed)} 失敗")
    if failed:
        print("\n失敗清單:")
        for name, err in failed:
            print(f"  - {name}: {err}")


if __name__ == "__main__":
    main()
