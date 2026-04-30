"""從 50家測試案例.csv 提取指定公司，轉換為專案 Report JSON 格式。

用法:
    python -m utils.csv_to_report_json

輸出:
    data/report/json/{統一編號}_{公司名稱}_{單一|合併}.json
"""
import csv
import json
import os
from collections import defaultdict
from datetime import datetime

from risk_engine.loader import to_float

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
COMPANY_LIST = os.path.join(BASE_DIR, "data", "report", "測試案例名單.csv")
SOURCE_CSV = os.path.join(BASE_DIR, "data", "report", "50家測試案例.csv")
TAG_TABLE = os.path.join(BASE_DIR, "data", "tag_table.csv")
OUTPUT_DIR = os.path.join(BASE_DIR, "data", "report", "json")


def _normalize_id(raw_id: str) -> str:
    """移除前導零以便比對統一編號。"""
    stripped = raw_id.strip().lstrip("0")
    return stripped or raw_id.strip()


def _parse_date(date_str: str) -> datetime:
    """解析 MM/DD/YYYY 格式日期。"""
    return datetime.strptime(date_str.strip(), "%m/%d/%Y")


def load_target_companies(path: str) -> dict[str, str]:
    """載入目標公司清單。

    Returns:
        {normalized_id: original_id}
    """
    result = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            original = row["統一編號"].strip()
            result[_normalize_id(original)] = original
    return result


def load_tag_units(path: str) -> dict[str, str]:
    """載入 tag_table，回傳 {FA_RFNBR: 單位}。"""
    result = {}
    # 嘗試 utf-8-sig，失敗再試 big5
    for enc in ("utf-8-sig", "big5"):
        try:
            with open(path, encoding=enc) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row["FA_RFNBR"].strip()
                    result[code] = row["單位"].strip()
            return result
        except (UnicodeDecodeError, KeyError):
            result.clear()
    raise RuntimeError(f"無法讀取 tag_table: {path}")


# ── 型別別名 ────────────────────────────────────────
# AcctData: {會計代碼: {"會科科目": str, "金額": str}}
# CompanyData: {(type_code, date_str, report_type): AcctData}

def load_source_data(
    path: str,
    target_nids: set[str],
) -> tuple[dict[str, dict], dict[str, str]]:
    """載入 50家 CSV，只保留目標公司。

    Returns:
        (data, company_names)
        data: {normalized_id: CompanyData}
        company_names: {normalized_id: 公司名稱}
    """
    data: dict[str, dict] = defaultdict(lambda: defaultdict(dict))
    company_names: dict[str, str] = {}

    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            nid = _normalize_id(row["公司統編"])
            if nid not in target_nids:
                continue

            company_names[nid] = row["公司名稱"].strip()
            type_code = row["單一/合併"].strip()
            date_str = row["財報年月"].strip()
            report_type = row["報表性質"].strip()
            acct_code = row["會計代碼"].strip()
            acct_name = row["會科科目"].strip()
            amount = row["金額(千元)"].strip()

            key = (type_code, date_str, report_type)
            data[nid][key][acct_code] = {
                "會科科目": acct_name,
                "金額": amount,
            }

    return dict(data), company_names


def select_periods(
    period_keys: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    """從 (type_code, date_str, report_type) 中選取最多 3 期。

    規則:
      - 最新日期: 優先取報表性質=3，無則取現有
      - 舊期間: 只取報表性質=1

    Returns:
        [(date_str, report_type), ...] 從新到舊，最多 3 筆
    """
    date_groups: dict[str, list[str]] = defaultdict(list)
    for _, date_str, report_type in period_keys:
        date_groups[date_str].append(report_type)

    sorted_dates = sorted(
        date_groups.keys(),
        key=lambda d: _parse_date(d),
        reverse=True,
    )

    selected: list[tuple[str, str]] = []
    for i, date_str in enumerate(sorted_dates):
        rtypes = date_groups[date_str]
        if i == 0:
            # 最新期: 優先 3，無則取第一個
            rtype = "3" if "3" in rtypes else rtypes[0]
            selected.append((date_str, rtype))
        else:
            # 舊期: 只取 1
            if "1" in rtypes:
                selected.append((date_str, "1"))

        if len(selected) == 3:
            break

    return selected


def build_report_json(
    company_data: dict,
    type_code: str,
    periods: list[tuple[str, str]],
    tag_units: dict[str, str],
) -> dict:
    """建構 Report JSON。

    Args:
        company_data: CompanyData for one company
        type_code: "1" (單一) or "2" (合併)
        periods: [(date_str, report_type), ...] 從新到舊
        tag_units: {FA_RFNBR: 單位}

    Returns:
        {代碼: {FA_CANME, 單位, Current, Period_2, Period_3}}
    """
    period_labels = ["Current", "Period_2", "Period_3"]

    # 收集每期的會計資料
    all_codes: set[str] = set()
    period_data: dict[str, dict] = {}

    for idx, (date_str, report_type) in enumerate(periods):
        key = (type_code, date_str, report_type)
        acct_data = company_data.get(key, {})
        label = period_labels[idx]
        period_data[label] = acct_data
        all_codes.update(acct_data.keys())

    # 建構 JSON
    report = {}
    for code in sorted(all_codes):
        unit = tag_units.get(code, "")

        # FA_CANME 從任一期的會科科目取得
        fa_canme = ""
        for label in period_labels:
            if code in period_data.get(label, {}):
                fa_canme = period_data[label][code]["會科科目"]
                break

        row: dict = {"FA_CANME": fa_canme, "單位": unit}
        for label in period_labels:
            if label in period_data and code in period_data[label]:
                row[label] = to_float(period_data[label][code]["金額"])
            else:
                row[label] = None

        report[code] = row

    # metadata: 各期日期 (MM/DD/YYYY)
    report["_period_dates"] = [d for d, _ in periods]

    return report


def main():
    """批次轉換：自 50 家測試案例 CSV 抽取目標公司，輸出 Report JSON。

    流程：
        1. 讀取 ``測試案例名單.csv`` 取得目標公司統一編號。
        2. 讀取 ``tag_table.csv`` 取得各會計代碼的單位。
        3. 讀取 ``50家測試案例.csv`` 過濾出目標公司資料。
        4. 對每家公司、每個 ``單一/合併`` 類型分別挑選最多 3 期，
           輸出至 ``data/report/json/{統編}_{公司名稱}_{類型}.json``。
    """
    # 1. 載入目標公司
    targets = load_target_companies(COMPANY_LIST)
    target_nids = set(targets.keys())
    print(f"目標公司: {len(targets)} 家")

    # 2. 載入 tag_table
    tag_units = load_tag_units(TAG_TABLE)
    print(f"tag_table 載入: {len(tag_units)} 筆")

    # 3. 載入來源資料
    data, company_names = load_source_data(SOURCE_CSV, target_nids)
    found = set(data.keys())
    missing = target_nids - found
    print(f"找到: {len(found)} 家, 缺少: {len(missing)} 家")
    for nid in sorted(missing):
        print(f"  [WARN] 未找到: {targets[nid]}")

    # 4. 確保輸出目錄
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 5. 逐家轉換
    type_map = {"1": "單一", "2": "合併"}
    file_count = 0

    for nid in sorted(found):
        original_id = targets[nid]
        name = company_names[nid]

        # 按 單一/合併 分組
        type_groups: dict[str, list] = defaultdict(list)
        for key_tuple in data[nid]:
            type_code = key_tuple[0]
            type_groups[type_code].append(key_tuple)

        for type_code in sorted(type_groups.keys()):
            periods = select_periods(type_groups[type_code])
            type_label = type_map.get(type_code, type_code)

            if len(periods) < 3:
                print(
                    f"  [WARN] {name} ({type_label}): "
                    f"只有 {len(periods)} 期"
                )

            report = build_report_json(
                data[nid], type_code, periods, tag_units,
            )

            filename = f"{original_id}_{name}_{type_label}.json"
            filepath = os.path.join(OUTPUT_DIR, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=4)

            period_info = " / ".join(
                f"{d}(性質{r})" for d, r in periods
            )
            print(
                f"  ✓ {filename} — "
                f"{len(report)} codes, {len(periods)} 期 "
                f"[{period_info}]"
            )
            file_count += 1

    print(f"\n完成! 共產生 {file_count} 個 JSON 檔案 → {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
