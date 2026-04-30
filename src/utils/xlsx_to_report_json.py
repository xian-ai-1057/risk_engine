"""將單一公司 Excel 財報檔轉為 Report JSON。

用法:
    python xlsx_to_report_json.py <xlsx_path> [tag_table.csv] [output_dir]

Excel 檔名需為 '{公司名稱}_{單一|合併}[_].xlsx'，
輸出檔: '{公司名稱}_{單一|合併}.json'
"""
import csv
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict

import pandas as pd


# Excel 用的 ⻑ (U+2ED1) 屬 CJK Radical Long One，NFKC 不會正規化，手動補
_MANUAL_CHAR_MAP = {"\u2ed1": "長"}

# 工作表 → (代碼前綴, 三期金額欄位索引)
# 財務及經營概況欄位結構為 [項目, 值1, %, 值2, %, 值3, %]，故取 1/3/5
_SHEET_SPEC: dict[str, tuple[str, list[int]]] = {
    "財務及經營概況": ("TIBA", [1, 3, 5]),
    "財務比率分析": ("TIBB", [1, 2, 3]),
    "現金流量表": ("TIBC", [1, 2, 3]),
    "淨值調節表": ("TIBD", [1, 2, 3]),
}

_PERIOD_LABELS = ["Current", "Period_2", "Period_3"]


def normalize_name(s: str) -> str:
    """NFKC 正規化 + 手動補相容字 + 去空白。"""
    s = unicodedata.normalize("NFKC", str(s)).strip()
    for k, v in _MANUAL_CHAR_MAP.items():
        s = s.replace(k, v)
    return s


def parse_filename(path: str) -> tuple[str, str]:
    """解析 '{公司名稱}_{單一|合併}[_].xlsx'。"""
    base = os.path.splitext(os.path.basename(path))[0].rstrip("_")
    parts = base.split("_")
    if len(parts) < 2:
        raise ValueError(f"檔名格式錯誤 (需為 公司名稱_類型): {base}")
    return parts[0], parts[1]


def load_tag_table(
    path: str,
) -> dict[str, dict[str, tuple[str, str]]]:
    """載入 tag_table，依代碼前綴分群。

    Returns:
        {代碼前綴(TIBA/TIBB/...): {會科科目: (代碼, 單位)}}
    """
    result: dict[str, dict[str, tuple[str, str]]] = defaultdict(dict)
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            code = row["FA_RFNBR"].strip()
            prefix = code[:4]
            name = normalize_name(row["FA_CANME"])
            unit = row["單位"].strip()
            # 同前綴內若重名，以第一次出現為準
            result[prefix].setdefault(name, (code, unit))
    return dict(result)


def parse_amount(val) -> float | None:
    """轉 float，支援 '78.36天'、'2.24次' 之類帶單位字串。"""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    m = re.match(r"^[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    return float(m.group()) if m else None


def extract_period_dates(
    df: pd.DataFrame, cols: list[int],
) -> list[str]:
    """從 header 列抽取三期日期字串 (MM/DD/YYYY)。"""
    return [str(df.iloc[0, c]).strip() for c in cols]


def convert_sheet(
    df: pd.DataFrame,
    value_cols: list[int],
    name_map: dict[str, tuple[str, str]],
) -> dict[str, dict]:
    """轉換單一工作表為 {代碼: row_dict}。"""
    result: dict[str, dict] = {}
    for i in range(1, len(df)):
        raw = df.iloc[i, 0]
        if pd.isna(raw):
            continue
        name = normalize_name(raw)
        if name not in name_map:
            continue
        code, unit = name_map[name]
        values = [parse_amount(df.iloc[i, c]) for c in value_cols]
        row: dict = {"FA_CANME": name, "單位": unit}
        for label, v in zip(_PERIOD_LABELS, values):
            row[label] = v
        result[code] = row
    return result


def build_report(
    xlsx_path: str,
    tag_map: dict[str, dict[str, tuple[str, str]]],
) -> dict:
    """讀取全部工作表，組成 Report JSON。"""
    report: dict = {}
    period_dates: list[str] = []
    for sheet, (prefix, value_cols) in _SHEET_SPEC.items():
        df = pd.read_excel(xlsx_path, sheet_name=sheet, header=None)
        if not period_dates:
            period_dates = extract_period_dates(df, value_cols)
        name_map = tag_map.get(prefix, {})
        report.update(convert_sheet(df, value_cols, name_map))

    sorted_report = dict(sorted(report.items()))
    sorted_report["_period_dates"] = period_dates
    return sorted_report


def main() -> None:
    """CLI 入口：將單一公司 Excel 財報轉為 Report JSON。

    參數：
        argv[1]：Excel 檔路徑（必填，檔名格式 ``公司名_單一|合併.xlsx``）。
        argv[2]：``tag_table.csv`` 路徑（選填，預設使用內建路徑）。
        argv[3]：輸出資料夾（選填，預設目前目錄）。

    輸出檔名為 ``{公司名稱}_{單一|合併}.json``，內含每個會計代碼的
    ``FA_CANME``、``單位``、三期金額（``Current/Period_2/Period_3``）
    及 ``_period_dates`` metadata。
    """
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    xlsx_path = sys.argv[1]
    tag_path = sys.argv[2] if len(sys.argv) >= 3 else r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\V6\data\tag_table.csv"
    output_dir = sys.argv[3] if len(sys.argv) >= 4 else "."

    company, type_label = parse_filename(xlsx_path)
    tag_map = load_tag_table(tag_path)
    report = build_report(xlsx_path, tag_map)

    os.makedirs(output_dir, exist_ok=True)
    filename = f"{company}_{type_label}.json"
    output_path = os.path.join(output_dir, filename)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=4)

    code_count = len(report) - 1  # 扣掉 _period_dates
    print(
        f"✓ {filename} — {code_count} codes, "
        f"期別: {report['_period_dates']}"
    )


if __name__ == "__main__":
    main()