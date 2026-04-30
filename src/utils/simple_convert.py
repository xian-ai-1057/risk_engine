"""財務數據預處理模組。

將原始財務 JSON 預處理為 LLM 可直接引用的扁平格式，
包含顯示值與趨勢判斷，讓模型完全不需要做任何數學運算。

使用方式：
    import json
    from preprocess_financial_data import preprocess

    with open("input.json", "r", encoding="utf-8") as f:
        raw = json.load(f)

    result = preprocess(raw)

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
"""

from copy import deepcopy


# ── 金額換算 ──────────────────────────────────────


def convert_thousand_ntd(value: float) -> str:
    """將仟元數值換算為顯示格式字串。

    Args:
        value: 原始數值（單位：仟元）。

    Returns:
        格式化後的金額字串，如 "NTD 15.95億元"。

    規則：
        >= 10,000    → 億元（÷ 100,000，兩位小數）
        >= 1         → 仟元（原值，千分位逗號）
        > 0 且 < 1   → 元（× 1,000，取整）
        0            → "NTD 0元"
    """
    if value == 0:
        return "NTD 0元"

    sign = "-" if value < 0 else ""
    abs_val = abs(value)

    # if abs_val >= 10_000:
    #     converted = abs_val / 100_000
    #     return f"{sign}NTD {converted:,.2f}億元"
    if abs_val >= 1:
        return f"{sign}NTD {abs_val:,.0f}仟元"
    else:
        converted = round(abs_val * 1_000)
        return f"{sign}NTD {converted:,}元"


# ── 比率/天數/倍數格式化 ─────────────────────────


def format_percent(value: float) -> str:
    """將小數轉為百分比字串。0.1293 → '12.93%'。"""
    return f"{value:.2f}%"


def format_days(value: float) -> str:
    """格式化天數。保留兩位小數。"""
    return f"{value:.2f}天"


def format_times(value: float) -> str:
    """格式化倍數。保留兩位小數。"""
    return f"{value:.2f}倍"


UNIT_FORMATTERS = {
    "仟元": convert_thousand_ntd,
    "%": format_percent,
    "天": format_days,
    "倍": format_times,
}


# ── 趨勢判斷 ─────────────────────────────────────


def _calc_trend(values: list[float]) -> str:
    """根據數值序列（由舊至新）判斷趨勢。

    Args:
        values: 至少 2 個數值的序列，由舊到新排列。

    Returns:
        趨勢描述字串。
    """
    if len(values) < 2:
        return ""

    changes = []
    for i in range(1, len(values)):
        prev = values[i - 1]
        curr = values[i]
        if prev == 0:
            changes.append("up" if curr > 0 else "flat")
            continue
        pct = (curr - prev) / abs(prev)
        if pct > 0.05:
            changes.append("up")
        elif pct < -0.05:
            changes.append("down")
        else:
            changes.append("flat")

    unique = set(changes)

    if unique == {"flat"}:
        return "大致持平"
    if unique == {"up"}:
        return "逐期上升" if len(values) > 2 else "上升"
    if unique == {"down"}:
        return "逐期下降" if len(values) > 2 else "下降"

    direction_map = {"up": "升", "down": "降", "flat": "平"}
    parts = [direction_map[c] for c in changes]

    simplified = [parts[0]]
    for p in parts[1:]:
        if p != simplified[-1]:
            simplified.append(p)

    return f"呈先{'後'.join(simplified)}走勢"


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

        raw_values = [indicator[dk] for dk in date_keys]

        new_indicator = {"FA_CANME": indicator["FA_CANME"]}
        new_indicator["趨勢"] = _calc_trend(raw_values)

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
        轉換後的 JSON，日期值為格式化顯示字串，
        含預計算的「趨勢」欄位。
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


def convert_grouped_report(
    grouped_report: dict,
    period_dates: list[str],
) -> dict:
    """將 GroupedReport 轉為 LLM 可讀的格式化結構。

    將 Current/Period_2/Period_3 映射為實際日期 key，
    數值格式化為含單位的顯示字串，並計算趨勢。

    Args:
        grouped_report: pipeline 輸出的分群報表，
            結構為 {section: {code: ReportRow}}。
            ReportRow 含 FA_CANME、單位、
            Current、Period_2、Period_3。
        period_dates: 期間日期列表，順序對應
            Current/Period_2/Period_3，
            如 ["03/31/2025", "12/31/2024", "12/31/2023"]。

    Returns:
        轉換後的 dict，結構為
        {section: {code: {FA_CANME, 趨勢, date: "顯示值"}}}。
    """
    result = {}

    for section_name, section in grouped_report.items():
        if not isinstance(section, dict):
            continue

        converted = {}
        for code, row in section.items():
            if not isinstance(row, dict):
                continue
            if "FA_CANME" not in row:
                continue

            unit = row.get("單位", "")
            formatter = UNIT_FORMATTERS.get(unit)

            # 收集有值的期間（由舊至新排列，供趨勢計算）
            dated_values: list[
                tuple[str, float]
            ] = []
            for i, pkey in enumerate(_PERIOD_KEYS):
                val = row.get(pkey)
                if val is not None and i < len(period_dates):
                    dated_values.append(
                        (period_dates[i], val)
                    )

            if not dated_values:
                continue

            # 由舊至新排序（用 _date_sort_key）
            dated_values.sort(
                key=lambda x: _date_sort_key(x[0]),
            )

            new_row: dict = {
                "FA_CANME": row["FA_CANME"],
            }

            # 計算趨勢（由舊至新）
            raw_values = [v for _, v in dated_values]
            new_row["趨勢"] = _calc_trend(raw_values)

            # 格式化各期間數值
            for date_str, val in dated_values:
                if formatter:
                    new_row[date_str] = formatter(val)
                else:
                    new_row[date_str] = str(val)

            converted[code] = new_row

        if converted:
            result[section_name] = converted

    return result


if __name__ == "__main__":
    import json

    report_type = ["單一", "合併"]
    
    for item in report_type:
        with open(f"DATA/JSON/財報({item})__美達工業_group.json", "r", encoding="utf-8") as f:
            raw = json.load(f)

        result = preprocess(raw)

        # JSON results
        with open(f"DATA/JSON/財報({item})__美達工業.txt", "w", encoding="utf-8") as f:
            json.dumps(result, ensure_ascii=False, indent=4)

        # For API
        formatted = json.dumps(result, ensure_ascii=False, indent=4)
        escaped = json.dumps(formatted, ensure_ascii=False)

        with open(f"DATA/JSON/財報({item})__美達工業.txt", "w", encoding="utf-8") as f:
            f.write(escaped)