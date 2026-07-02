"""程式化入口：在 Python 程式中直接呼叫，毋須 CLI/argv。

一支 ``run_report(...)`` 把「HTML → 組 prompt →（選填）呼叫模型生成段落」
跑完，回傳一個 dict（結構同 EXE 輸出）。所有輸入以參數傳入，不讀環境變數、
不做檔名版本探測——路徑由呼叫端自己決定。

範例::

    from risk_engine.api import run_report

    result = run_report(
        html_files=[
            "財報_1財務概況.html", "財報_2財務比率.html",
            "財報_3現金流量.html", "財報_4淨值調節.html",
        ],
        industry="7大指標",
        xlsx_path="deploy/indicators_config_V1_1_1.xlsx",
        narrative_user_prompt_path="narrative_user_prompt.txt",
        risk_user_prompt_path="risk_user_prompt.txt",
        # 以下為串接模型（選填）
        generate=True,
        narrative_sys_prompt_path="inputs/prompt/財報敘事_sys_prompt.txt",
        risk_sys_prompt_path="inputs/prompt/財報風險_sys_prompt.txt",
        llm_base_url="https://<openai-compatible>/v1",
        llm_api_key="sk-...",
        llm_model="gpt-4o",
        customer_id="23295097",
        report_date="20240930",
    )

    print(result["risk_sections"]["4-1"])      # 模型生成的段落
    print(result["narrative_prompt"])           # 也拿得到組好的 prompt

HTML 順序固定為：①財務概況 ②財務比率 ③現金流量 ④淨值調節。
"""
import json
import urllib.request
import uuid
from typing import Any

from risk_engine import types
from risk_engine.loader import build_report_row
from risk_engine.pipeline import ReportPipeline
from utils.html_to_json import convert_html_files_to_dict

# ── 段落 4-1 ~ 4-5 結構化輸出 schema（OpenAI 相容 response_format）──
_SECTION_KEYS = ("4-1", "4-2", "4-3", "4-4", "4-5")
_SECTION_DESC = {
    "4-1": "4-1:財務結構段落的內容",
    "4-2": "4-2:償債能力段落的內容",
    "4-3": "4-3:經營效能段落的內容",
    "4-4": "4-4:獲利能力段落的內容",
    "4-5": "4-5:現金流量段落的內容",
}
SECTIONS_SCHEMA: dict[str, Any] = {
    "type": "json_schema",
    "json_schema": {
        "name": "sections_output",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                k: {"type": "string", "description": _SECTION_DESC[k]}
                for k in _SECTION_KEYS
            },
            "required": list(_SECTION_KEYS),
            "additionalProperties": False,
        },
    },
}

# html_to_json 夾帶的非代碼 metadata key（`_period_dates` 另行 pop）。
_META_KEYS = {"skipped"}


def call_llm(
    base_url: str,
    api_key: str,
    model: str,
    sys_prompt: str,
    user_prompt: str,
    *,
    timeout: int = 120,
) -> dict[str, str]:
    """呼叫 OpenAI 相容 ``/chat/completions``，回傳 4-1~4-5 段落 dict。

    以 ``SECTIONS_SCHEMA`` 強制結構化輸出；回應 content ``json.loads`` 後即為
    ``{"4-1": ..., ..., "4-5": ...}``。純標準庫（urllib），不加第三方套件。
    """
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "response_format": SECTIONS_SCHEMA,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    content = raw["choices"][0]["message"]["content"]
    return json.loads(content)


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def run_report(
    *,
    html_files: list[str],
    industry: str,
    xlsx_path: str,
    narrative_user_prompt_path: str,
    risk_user_prompt_path: str,
    generate: bool = False,
    narrative_sys_prompt_path: str = "",
    risk_sys_prompt_path: str = "",
    llm_base_url: str = "",
    llm_api_key: str = "",
    llm_model: str = "",
    customer_id: str = "",
    report_date: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    """跑完整條流程並回傳結果 dict。

    Args:
        html_files: 4 份財報 HTML 路徑，順序為 概況/比率/現金流量/淨值調節。
        industry: 產業別，需存在於指標 xlsx。
        xlsx_path: 指標 xlsx 路徑（含 指標/敘事/tag_table 三 sheet）。
        narrative_user_prompt_path / risk_user_prompt_path: 兩份 user prompt 模板路徑。
        generate: 為 True 時額外呼叫模型生成段落。
        narrative_sys_prompt_path / risk_sys_prompt_path: 生成時的 system prompt 路徑。
        llm_base_url / llm_api_key / llm_model: OpenAI 相容端點設定。
        customer_id / report_date / request_id: 選填 metadata。

    Returns:
        dict：含 ``narrative_prompt`` / ``risk_prompt`` / ``grouped_report`` /
        ``risk_report``；``generate=True`` 時另含 ``narrative_sections`` /
        ``risk_sections``（各為 ``4-1``~``4-5`` → 段落文字）。

    Raises:
        types.ConfigError: 產業不存在，或 ``generate=True`` 但缺 LLM 設定 / sys prompt。
    """
    # openpyxl 依賴延後到呼叫時才 import，讓沒有 openpyxl 也能 import 本模組。
    from utils.xlsx_to_indicators import convert as xlsx_convert

    request_id = request_id or uuid.uuid4().hex[:8]

    # 1. xlsx → rules / narrative_filter / tag_map
    config_dict, filter_dict, tag_map = xlsx_convert(xlsx_path)
    if industry not in config_dict:
        available = ", ".join(config_dict.keys()) or "(無)"
        raise types.ConfigError(
            f"產業 '{industry}' 不在指標 xlsx。可用: {available}"
        )
    rules = config_dict[industry]
    narrative_filter = filter_dict.get(industry)

    # 2. HTML → Report
    raw_report = convert_html_files_to_dict(html_files, tag_map=tag_map)
    period_dates = raw_report.pop("_period_dates", [])
    report: types.Report = {
        code: build_report_row(data)
        for code, data in raw_report.items()
        if code not in _META_KEYS
    }

    # 3. Pipeline：組出兩段 prompt + 判定結果
    pipe = ReportPipeline(
        report=report,
        rules=rules,
        narrative_prompt_template=_read(narrative_user_prompt_path),
        risk_prompt_template=_read(risk_user_prompt_path),
        narrative_filter=narrative_filter,
        customer_id=customer_id,
        report_date=report_date,
        industry=industry,
        period_dates=period_dates or None,
    )
    result = pipe.run()

    output: dict[str, Any] = {
        "schema_version": types.EXE_SCHEMA_VERSION,
        "request_id": request_id,
        "industry": industry,
        "narrative_prompt": result["narrative_prompt"],
        "risk_prompt": result["risk_prompt"],
        "grouped_report": result["grouped_report"],
        "risk_report": result["risk_report"],
    }
    if customer_id:
        output["customer_id"] = customer_id
    if report_date:
        output["report_date"] = report_date

    # 4.（選填）呼叫模型生成段落
    if generate:
        if not (llm_base_url and llm_api_key and llm_model):
            raise types.ConfigError(
                "generate=True 需提供 llm_base_url / llm_api_key / llm_model"
            )
        if not (narrative_sys_prompt_path and risk_sys_prompt_path):
            raise types.ConfigError(
                "generate=True 需提供 narrative_sys_prompt_path / "
                "risk_sys_prompt_path"
            )
        output["narrative_sections"] = call_llm(
            llm_base_url, llm_api_key, llm_model,
            _read(narrative_sys_prompt_path), result["narrative_prompt"],
        )
        output["risk_sections"] = call_llm(
            llm_base_url, llm_api_key, llm_model,
            _read(risk_sys_prompt_path), result["risk_prompt"],
        )

    return output
