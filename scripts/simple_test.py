"""simple_test — 以 Python 腳本模擬 main.py 流程（從 JSON 報表開始）。"""
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from risk_engine import ReportPipeline, loader
from risk_engine.loader import _build_report_row
from risk_engine.types import ExeOutput
from utils.combine_prompt import render_narrative_prompt
from utils.narrative import load_narrative_filter


# ── 測試參數（可自行修改）──────────────────────────
REPORT_PATH = r"data\report\新測試案例_json\Samson Paper Company_單一.json"
CONFIG_PATH = r"data\indicators_config.json"
NARRATIVE_FILTER_PATH = r"data\narrative_filter.json"
INDUSTRY = "7大指標"
CUSTOMER_ID = "Samson Paper Company_單一"
REPORT_DATE = "20260430"
NARR_PROMPT_PATH = r"data\prompt\財報敘事_user_prompt.txt"
RISK_PROMPT_PATH = r"data\prompt\財報風險_user_prompt.txt"
# ─────────────────────────────────────────────────

REQUEST_ID = CUSTOMER_ID or uuid.uuid4().hex[:8]
TIME_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

_META_KEYS = {"skipped", "_period_dates"}


def main() -> None:
    # 1. 載入資料（保留 _period_dates，與 main.py 一致）
    with open(REPORT_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    period_dates: list[str] = raw.pop("_period_dates", [])
    report = {
        code: _build_report_row(data)
        for code, data in raw.items()
        if code not in _META_KEYS
    }
    rules = loader.load_config(CONFIG_PATH, INDUSTRY)
    narrative_filter = load_narrative_filter(
        NARRATIVE_FILTER_PATH, INDUSTRY,
    )
    if narrative_filter is None:
        raise SystemExit(
            f"無法載入 narrative_filter: {NARRATIVE_FILTER_PATH}"
            f" (產業: {INDUSTRY})",
        )

    # 2. 讀取 Prompt 模板
    with open(NARR_PROMPT_PATH, encoding="utf-8") as f:
        narr_template = f.read()
    with open(RISK_PROMPT_PATH, encoding="utf-8") as f:
        risk_template = f.read()

    # 3. 執行 Pipeline
    pipe = ReportPipeline(
        report=report,
        rules=rules,
        narrative_prompt_template=narr_template,
        risk_prompt_template=risk_template,
        narrative_filter=narrative_filter,
        customer_id=CUSTOMER_ID,
        report_date=REPORT_DATE,
        industry=INDUSTRY,
    )
    result = pipe.run()

    # 3b. 若有 period_dates，重新渲染敘事 prompt（格式化版）
    narrative_prompt = result["narrative_prompt"]
    if period_dates:
        narrative_prompt = render_narrative_prompt(
            narr_template,
            result["grouped_report"],
            period_dates=period_dates,
        )

    # 4. 組裝 ExeOutput（與 main.py 一致）
    output: ExeOutput = {
        "request_id": REQUEST_ID,
        "industry": INDUSTRY,
        "narrative_prompt": narrative_prompt,
        "risk_prompt": result["risk_prompt"],
        "grouped_report": result["grouped_report"],
        "risk_report": result["risk_report"],
    }
    if CUSTOMER_ID:
        output["customer_id"] = CUSTOMER_ID
    if REPORT_DATE:
        output["report_date"] = REPORT_DATE

    # 5. 輸出
    out_path = f"output/result_{REQUEST_ID}_{TIME_STAMP}.json"
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"已輸出: {out_path}")


if __name__ == "__main__":
    main()
