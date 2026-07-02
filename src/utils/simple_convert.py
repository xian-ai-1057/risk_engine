"""財務數據預處理模組。

將原始財務 JSON 預處理為 LLM 可直接引用的扁平格式，
數值依單位（仟元/%/天/倍）轉為顯示字串，模型只需原樣引用。

使用方式：
    import json
    from preprocess_financial_data import preprocess

    with open("input.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    result = preprocess(raw)

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
"""

import logging
from copy import deepcopy

logger = logging.getLogger(__name__)


# ── 金額換算 ──────────────────────────────────────


def convert_thousand_ntd(
    value: float,
    display_absolute: bool = False,
) -> str:
    """將仟元數值換算為顯示格式字串。

    Args:
        value: 原始數值（單位：仟元）。
        display_absolute: True 時永遠以絕對值顯示（不加負號、不加括號）。
            供「發放現金股利」等科目名稱已表達流出方向的指標使用，避免在
            顯示時重複帶會計式括號。

    Returns:
        格式化後的金額字串。

    規則：
        0                       → "NTD 0元"
        > 0                     → "NTD 1,234仟元"
        < 0 且非 display_absolute → "NTD (1,234)仟元"（會計式括號）
        < 0 且 display_absolute  → "NTD 1,234仟元"
        |value| < 1 時改用 "元" 為單位（× 1,000 取整）
    """
    if value == 0:
        return "NTD 0元"

    wrap_parens = value < 0 and not display_absolute
    abs_val = abs(value)

    if abs_val >= 1:
        num_str = f"{abs_val:,.0f}"
        unit = "仟元"
    else:
        num_str = f"{round(abs_val * 1_000):,}"
        unit = "元"

    if wrap_parens:
        return f"NTD ({num_str}){unit}"
    return f"NTD {num_str}{unit}"


# ── 比率/天數/倍數格式化 ─────────────────────────


def format_percent(
    value: float, display_absolute: bool = False,
) -> str:
    """將小數轉為百分比字串。負值以會計式括號表示。"""
    num = f"{abs(value):.2f}"
    if value < 0 and not display_absolute:
        return f"({num})%"
    return f"{num}%"


def format_days(
    value: float, display_absolute: bool = False,
) -> str:
    """格式化天數。負值以會計式括號表示。"""
    num = f"{abs(value):.2f}"
    if value < 0 and not display_absolute:
        return f"({num})天"
    return f"{num}天"


def format_times(
    value: float, display_absolute: bool = False,
) -> str:
    """格式化倍數。負值以會計式括號表示。"""
    num = f"{abs(value):.2f}"
    if value < 0 and not display_absolute:
        return f"({num})倍"
    return f"{num}倍"


def format_freq(
    value: float, display_absolute: bool = False,
) -> str:
    """格式化次數。負值以會計式括號表示。"""
    num = f"{abs(value):.2f}"
    if value < 0 and not display_absolute:
        return f"({num})次"
    return f"{num}次"


UNIT_FORMATTERS = {
    "仟元": convert_thousand_ntd,
    "%": format_percent,
    "天": format_days,
    "倍": format_times,
    "次": format_freq,
}


def format_with_unit(
    value: float,
    unit: str,
    *,
    display_absolute: bool = False,
) -> str | None:
    """依單位字串選對應 formatter，統一傳遞 display_absolute。

    所有 formatter 均支援 ``display_absolute``：負值加括號；
    旗標為 ``True`` 時取絕對值、不加括號。
    """
    formatter = UNIT_FORMATTERS.get(unit)
    if formatter is None:
        return None
    return formatter(value, display_absolute=display_absolute)


# ── 日期排序輔助 ──────────────────────────────────


def _date_sort_key(date_str: str) -> tuple[int, int, int]:
    """將 MM/DD/YYYY 格式轉為可排序的 tuple。"""
    parts = date_str.split("/")
    month, day, year = int(parts[0]), int(parts[1]), int(parts[2])
    return (year, month, day)


_META_KEYS = {"FA_CANME", "單位"}


def _extract_date_keys(indicator: dict) -> list[str]:
    """從指標 dict 中提取日期 key，由舊至新排序。跳過值為 None 的期間。"""
    date_keys = [
        k for k in indicator
        if k not in _META_KEYS and indicator[k] is not None
    ]
    return sorted(date_keys, key=_date_sort_key)


# ── 主函式 ────────────────────────────────────────


def _is_indicator(value: dict) -> bool:
    """判斷一個 dict 是否為指標（含 FA_CANME 欄位）。"""
    return isinstance(value, dict) and "FA_CANME" in value


def _process_indicators(indicators: dict) -> dict:
    """處理一組指標 dict，回傳轉換後的結果。"""
    result = {}

    for code, indicator in indicators.items():
        if not _is_indicator(indicator):
            continue

        unit = indicator.get("單位", "")
        formatter = UNIT_FORMATTERS.get(unit)
        date_keys = _extract_date_keys(indicator)

        if not date_keys:
            continue

        new_indicator = {"FA_CANME": indicator["FA_CANME"]}

        if formatter:
            for dk in date_keys:
                new_indicator[dk] = formatter(indicator[dk])
        else:
            for dk in date_keys:
                new_indicator[dk] = str(indicator[dk])

        result[code] = new_indicator

    return result


def preprocess(data: dict) -> dict:
    """預處理整份財務數據 JSON。

    自動偵測輸入結構：
    - 雙層結構：{ section: { code: { "FA_CANME", ... } } }
    - 單層結構：{ code: { "FA_CANME", ... } }

    兩種結構皆支援，輸出結構與輸入一致。

    Args:
        data: 原始財務 JSON。

    Returns:
        轉換後的 JSON，日期值為格式化顯示字串。
    """
    first_value = next(iter(data.values()), None)

    # 單層結構：最外層的 value 直接就是指標 dict
    if _is_indicator(first_value):
        return _process_indicators(data)

    # 雙層結構：最外層是 section，內層才是指標
    result = {}

    for section_name, section in data.items():
        if not isinstance(section, dict):
            continue
        processed = _process_indicators(section)
        if processed:
            result[section_name] = processed

    return result


# ── 期間 key 映射 ────────────────────────────────

# ReportRow 中固定 key 與期間日期的對應順序
_PERIOD_KEYS = ("Current", "Period_2", "Period_3")

# 缺值與運算未定義時的顯示字串，讓 LLM 可在敘述中精確指出
# 「資料缺失」(原始資料未提供) 與「無法計算」(運算結果未定義，
# 例如分母為零) 兩種情境的差異。
_MISSING_DISPLAY = "資料缺失"
_UNDEFINED_DISPLAY = "無法計算"

_REASON_TO_DISPLAY = {
    "missing": _MISSING_DISPLAY,
    "undefined": _UNDEFINED_DISPLAY,
    "error": _UNDEFINED_DISPLAY,
}


def convert_grouped_report(
    grouped_report: dict,
    period_dates: list[str],
) -> dict:
    """將 GroupedReport 轉為 LLM 可讀的格式化結構。

    將 Current/Period_2/Period_3 映射為實際日期 key，
    數值格式化為含單位的顯示字串。若 row 帶有
    ``parent_key`` 且同段落內存在對應父項，則該 row 會被
    nest 到父項的 ``sub_items`` 子 dict 下（讓 LLM 用
    「，其中…」句型自然串接）；找不到父項時退化為平項並
    記 warning。

    Args:
        grouped_report: pipeline 輸出的分群報表，
            結構為 {section: {code: ReportRow}}。
            ReportRow 含 FA_CANME、單位、
            Current、Period_2、Period_3、選填 parent_key。
        period_dates: 期間日期列表，順序對應
            Current/Period_2/Period_3，
            如 ["03/31/2025", "12/31/2024", "12/31/2023"]。

    Returns:
        轉換後的 dict，結構為
        {section: {code: {FA_CANME, date: "顯示值",
        [sub_items: {code: {...}}]}}}。
    """
    result = {}

    for section_name, section in grouped_report.items():
        if not isinstance(section, dict):
            continue

        # 第一輪：把每個 row 轉成顯示用 new_row（不分父子）
        converted: dict[str, dict] = {}
        parent_of: dict[str, str] = {}
        for code, row in section.items():
            if not isinstance(row, dict):
                continue
            if "FA_CANME" not in row:
                continue

            unit = row.get("單位", "")
            reasons = row.get("reasons", {}) or {}
            display_absolute = bool(
                row.get("display_absolute", False),
            )

            # 收集各期間的「日期 + 顯示值」配對。
            # 有值 → formatter；無值 → 依 reasons[期] 分流為
            # 「資料缺失」/「無法計算」（無 reasons 時 fallback 為「資料缺失」）。
            dated_displays: list[tuple[str, str]] = []
            for i, pkey in enumerate(_PERIOD_KEYS):
                if i >= len(period_dates):
                    continue
                date_str = period_dates[i]
                val = row.get(pkey)
                if val is not None:
                    formatted = format_with_unit(
                        val, unit,
                        display_absolute=display_absolute,
                    )
                    display = (
                        formatted if formatted is not None
                        else str(val)
                    )
                else:
                    reason = reasons.get(pkey, "missing")
                    display = _REASON_TO_DISPLAY.get(
                        reason, _MISSING_DISPLAY,
                    )
                dated_displays.append((date_str, display))

            # 由舊至新排序
            dated_displays.sort(
                key=lambda x: _date_sort_key(x[0]),
            )

            new_row: dict = {
                "FA_CANME": row["FA_CANME"],
            }
            for date_str, display in dated_displays:
                new_row[date_str] = display

            converted[code] = new_row
            parent_key = row.get("parent_key")
            if parent_key:
                parent_of[code] = parent_key

        if not converted:
            continue

        # 第二輪：把子項 nest 到父項的 sub_items 下；找不到
        # 父項則退化為平項（不丟資料）
        nested: dict[str, dict] = {}
        for code, new_row in converted.items():
            parent_key = parent_of.get(code)
            if parent_key is None:
                nested[code] = new_row
                continue
            parent_row = converted.get(parent_key)
            if parent_row is None or parent_key == code:
                logger.warning(
                    "段落 '%s' 中 code '%s' 指向父項 '%s'，"
                    "但該段落內找不到父項；退化為平項",
                    section_name, code, parent_key,
                )
                nested[code] = new_row
                continue
            parent_row.setdefault("sub_items", {})[code] = new_row

        # 移除「只剩 sub_items 但沒被當作頂層出現」的父項（不應發生，
        # 因為父項自身在第一輪也加進 converted 了）。這裡僅保留出現
        # 順序：先父項、子項已 nest 進去。
        ordered: dict[str, dict] = {}
        for code in converted.keys():
            if code in nested:
                ordered[code] = nested[code]

        if ordered:
            result[section_name] = ordered

    return result


if __name__ == "__main__":
    import json

    report_type = ["單一", "合併"]
    
    for item in report_type:
        with open(f"inputs/json_sample/財報({item})__美達工業_group.json", "r", encoding="utf-8") as f:
            raw = json.load(f)

        result = preprocess(raw)

        # For API
        formatted = json.dumps(result, ensure_ascii=False, indent=4)
        escaped = json.dumps(formatted, ensure_ascii=False)

        with open(f"outputs/json/財報({item})__美達工業.txt", "w", encoding="utf-8") as f:
            f.write(escaped)