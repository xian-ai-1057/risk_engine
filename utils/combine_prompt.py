"""將風險 JSON 結果與財報敘事填入 prompt 模板。

根據預定義的 section-to-placeholder 對應表，
將 JSON sections 貼入 {{risk_results_N}}，
將敘事資料貼入 {{narrative_N}} 佔位符。

提供三種公開介面：
  render_prompt()          — 原有合併（風險 + 敘事）
  render_risk_prompt()     — 僅替換風險佔位符
  render_narrative_prompt()— 將分群報表 JSON 填入
                             {{JSON_DATA}} 佔位符

用法:
    直接修改底部 CONFIG 區塊的檔案路徑，然後執行：
    python render_prompt.py
"""

import json
import logging
from collections.abc import Callable
from typing import Any

from risk_engine import report as report_mod
from risk_engine import types
from utils.narrative import format_narrative_text

logger = logging.getLogger(__name__)

# 段落名稱 → 風險佔位符
SECTION_MAPPING: dict[str, str] = {
    "財務結構": "{{risk_results_1}}",
    "償債能力": "{{risk_results_2}}",
    "經營效能": "{{risk_results_3}}",
    "獲利能力": "{{risk_results_4}}",
    "現金流量": "{{risk_results_5}}",
}

# 段落名稱 → 敘事佔位符
NARRATIVE_MAPPING: dict[str, str] = {
    "財務結構": "{{narrative_1}}",
    "償債能力": "{{narrative_2}}",
    "經營效能": "{{narrative_3}}",
    "獲利能力": "{{narrative_4}}",
    "現金流量": "{{narrative_5}}",
}


# ── 內部輔助 ─────────────────────────────────────────

def _replace_placeholders(
    text: str,
    mapping: dict[str, str],
    source: dict,
    formatter: Callable[[Any], str],
) -> tuple[str, list[str], list[str]]:
    """依對應表替換佔位符，回傳結果與配對紀錄。

    Args:
        text: 原始模板文字。
        mapping: {段落名稱: 佔位符} 對應表。
        source: 來源資料 dict，key 為段落名稱。
        formatter: 將 source[key] 轉為替換字串的函式。

    Returns:
        (替換後文字, 已配對列表, 未配對列表)。
    """
    matched: list[str] = []
    unmatched: list[str] = []

    for section_name, placeholder in mapping.items():
        if section_name in source:
            replacement = formatter(
                source[section_name]
            )
            text = text.replace(
                placeholder, replacement,
            )
            matched.append(
                f"{placeholder}"
                f" <- \"{section_name}\""
            )
        else:
            unmatched.append(
                f"{placeholder}"
                f" -- 找不到 key \"{section_name}\""
            )

    return text, matched, unmatched


def _log_match_report(
    label: str,
    matched: list[str],
    unmatched: list[str],
) -> None:
    """以 log 輸出配對報告。"""
    for m in matched:
        logger.info("[%s] 已配對: %s", label, m)
    for u in unmatched:
        logger.warning("[%s] 未配對: %s", label, u)


def _format_risk_section(data: list) -> str:
    """將風險結果 section 轉為 JSON 字串。"""
    return json.dumps(
        data, ensure_ascii=False, indent=2,
    )


# ── 公開介面 ─────────────────────────────────────────

def render_prompt(
    prompt_text: str,
    risk_json: dict,
    narrative_json: dict[str, list] | None = None,
) -> str:
    """將風險結果與敘事資料填入 prompt 模板。

    Args:
        prompt_text: prompt 模板的完整文字。
        risk_json: 風險引擎輸出的 JSON dict，
            需包含 "sections" 欄位。
        narrative_json: 敘事資料 dict（選用），
            結構為 {段落名稱: [NarrativeItem, ...]}。

    Returns:
        替換完成的 prompt 文字。
    """
    sections = risk_json.get("sections", {})
    logger.info(
        "開始渲染 prompt，sections: %s",
        list(sections.keys()),
    )

    # 投影為 prompt 精簡版，只保留敘述必要欄位
    prompt_sections = report_mod.to_prompt_view(sections)

    # 風險佔位符替換
    result, risk_matched, risk_unmatched = (
        _replace_placeholders(
            prompt_text, SECTION_MAPPING,
            prompt_sections, _format_risk_section,
        )
    )
    _log_match_report(
        "風險", risk_matched, risk_unmatched,
    )

    # 敘事佔位符替換
    if narrative_json:
        result, narr_matched, narr_unmatched = (
            _replace_placeholders(
                result, NARRATIVE_MAPPING,
                narrative_json,
                format_narrative_text,
            )
        )
        _log_match_report(
            "敘事", narr_matched, narr_unmatched,
        )

    logger.info("prompt 渲染完成")
    return result


def render_risk_prompt(
    prompt_text: str,
    risk_json: dict,
) -> str:
    """僅將風險判定結果填入 prompt 模板。

    替換 {{risk_results_1}} ~ {{risk_results_5}}。
    委託 render_prompt() 處理，不傳入敘事資料。

    Args:
        prompt_text: 風險 prompt 模板的完整文字。
        risk_json: 風險引擎輸出的 JSON dict，
            需包含 "sections" 欄位。

    Returns:
        替換完成的 prompt 文字。
    """
    return render_prompt(prompt_text, risk_json)


def render_narrative_prompt(
    prompt_text: str,
    grouped_report: types.GroupedReport,
    period_dates: list[str] | None = None,
) -> str:
    """將分群後的原始報表 JSON 填入敘事 prompt。

    替換 {{JSON_DATA}} 佔位符。若提供 period_dates，
    會先將 GroupedReport 轉換為格式化顯示值
    （含單位、趨勢、實際日期 key）再填入。

    Args:
        prompt_text: 敘事 prompt 模板的完整文字。
        grouped_report: 過濾分群後的報表，
            結構為 {章節名: {代碼: ReportRow}}。
        period_dates: 期間日期列表（選用），順序
            對應 Current/Period_2/Period_3，
            如 ["03/31/2025", "12/31/2024", "12/31/2023"]。
            提供時會進行格式轉換；未提供則直接序列化。

    Returns:
        替換完成的 prompt 文字。
    """
    logger.info(
        "開始渲染敘事 prompt，sections: %s",
        list(grouped_report.keys()),
    )

    if "{{JSON_DATA}}" not in prompt_text:
        logger.warning(
            "模板中找不到 {{JSON_DATA}} 佔位符",
        )
        return prompt_text

    # 有 period_dates 時先轉換為格式化結構
    data_to_serialize = grouped_report
    if period_dates:
        from utils.simple_convert import (
            convert_grouped_report,
        )
        data_to_serialize = convert_grouped_report(
            grouped_report, period_dates,
        )
        logger.info(
            "已將 GroupedReport 轉換為格式化結構，"
            "期間: %s", period_dates,
        )

    replacement = json.dumps(
        data_to_serialize,
        ensure_ascii=False, indent=2,
    )
    result = prompt_text.replace(
        "{{JSON_DATA}}", replacement,
    )
    logger.info(
        "已替換 {{JSON_DATA}}，資料長度=%d",
        len(replacement),
    )

    logger.info("敘事 prompt 渲染完成")
    return result


# ── 主程式 ────────────────────────────────────────────

def main() -> None:
    """讀取檔案、渲染模板、輸出結果。"""

    company_list = [
        "財報(合併)__台揚科技",
        "財報(合併)_美達工業",
        "財報(單一)__台揚科技",
        "財報(單一)_寶閤建設",
        "財報(單一)_美達工業",
        "財報(單一)_農生企業",
    ]

    prompt_path = (
        "/home/jovyan/00_專案/報告生成/"
        "法金報告生成/02_Code/V4/DATA/prompt/"
        "user_prompt/"
        "user_prompt_template_v3.txt"
    )

    try:
        with open(prompt_path, encoding="utf-8") as f:
            prompt_text = f.read()
    except FileNotFoundError:
        logger.error("Prompt 模板不存在: %s", prompt_path)
        raise
    except OSError as e:
        logger.error(
            "讀取 Prompt 模板失敗: %s — %s",
            prompt_path, e,
        )
        raise

    for item in company_list:
        json_path = (
            f"/home/jovyan/00_專案/報告生成/"
            f"法金報告生成/02_Code/V4/DATA/"
            f"風險結果/{item}.json"
        )
        output_path = (
            f"/home/jovyan/00_專案/報告生成/"
            f"法金報告生成/02_Code/V4/DATA/"
            f"prompt/{item}.txt"
        )

        try:
            with open(json_path, encoding="utf-8") as f:
                risk_json = json.load(f)
        except FileNotFoundError:
            logger.error(
                "風險結果檔案不存在: %s", json_path,
            )
            raise
        except json.JSONDecodeError as e:
            logger.error(
                "風險結果 JSON 格式錯誤: %s — %s",
                json_path, e,
            )
            raise
        except OSError as e:
            logger.error(
                "讀取風險結果失敗: %s — %s",
                json_path, e,
            )
            raise

        rendered = render_prompt(
            prompt_text, risk_json,
        )

        try:
            with open(
                output_path, "w", encoding="utf-8",
            ) as f:
                f.write(rendered)
        except PermissionError:
            logger.error(
                "無權限寫入檔案: %s", output_path,
            )
            raise
        except OSError as e:
            logger.error(
                "寫入檔案失敗: %s — %s",
                output_path, e,
            )
            raise
        logger.info("已輸出至: %s", output_path)


if __name__ == "__main__":
    main()
