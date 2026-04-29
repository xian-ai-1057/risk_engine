"""將 data/html 中的財報 HTML 檔案組合為 JSON。

解析 4 個 HTML 檔案（Big5 編碼）中的財務資料表，
產出與 risk_engine/loader.py 相容的 JSON 格式。

Usage:
    python -m utils.html_to_json --input data/html --output data/report.json
"""
import argparse
import csv
import json
import logging
import os
import re
import sys

logger = logging.getLogger(__name__)


# ── 數值解析 ────────────────────────────────────────

def parse_value(text: str) -> tuple[float | None, str]:
    """將 HTML 表格中的文字轉為數值，並偵測單位。

    支援格式：
        "1,594,651"  → (1594651.0, "")
        "(966,404)"  → (-966404.0, "")
        "47.66%"     → (47.66, "%")
        "85.44天"    → (85.44, "天")
        "0.64倍"     → (0.64, "倍")
        "&nbsp;" / 空白 → (None, "")
    """
    # 去除 HTML 實體與空白
    text = text.replace("&nbsp;", "").replace("\xa0", "").strip()
    if not text:
        return None, ""

    # 括號表示負數
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    # 偵測並去除單位後綴
    unit = ""
    for suffix in ("%", "天", "倍", "次"):
        if text.endswith(suffix):
            unit = suffix
            text = text[: -len(suffix)]
            break

    # 去除千位逗號
    text = text.replace(",", "")

    text = text.strip()
    if not text:
        return None, unit

    try:
        val = float(text)
    except ValueError:
        return None, unit

    return (-val if negative else val), unit


# ── HTML 表格解析 ────────────────────────────────────

# 匹配日期格式 MM/DD/YYYY
_DATE_RE = re.compile(r'\d{2}/\d{2}/\d{4}')

# 匹配含 TIB 代碼的 <td> 標籤
_CODE_RE = re.compile(
    r'<td[^>]*\btitle="(TIB[A-D]\d+)"[^>]*>',
    re.IGNORECASE,
)

# 匹配 <tr> 區塊
_TR_RE = re.compile(
    r'<tr[^>]*>(.*?)</tr>',
    re.IGNORECASE | re.DOTALL,
)

# 匹配 <td> 中的內容
_TD_CONTENT_RE = re.compile(
    r'<td[^>]*>(.*?)</td>',
    re.IGNORECASE | re.DOTALL,
)


def _strip_tags(html: str) -> str:
    """移除 HTML 標籤與 HTML 實體，只保留文字。"""
    text = re.sub(r'<[^>]+>', '', html)
    text = text.replace("&nbsp;", " ").replace("\xa0", " ")
    text = text.replace("&amp;", "&").replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    return text.strip()


def extract_period_dates(html: str) -> list[str]:
    """從 HTML 表格的 header row 提取期間日期。

    掃描每個 <tr>，找到第一個含有日期（MM/DD/YYYY）
    的 header row，提取所有日期並回傳。順序與表格欄位
    一致（Current, Period_2, Period_3）。

    Args:
        html: HTML 原始字串。

    Returns:
        日期字串列表，如 ["09/30/2024", "12/31/2023", "12/31/2022"]。
        找不到時回傳空列表。
    """
    for tr_match in _TR_RE.finditer(html):
        tr_content = tr_match.group(1)
        dates = _DATE_RE.findall(tr_content)
        if dates:
            return dates
    return []


# ── 科目名稱與單位 ─────────────────────────────────

def _load_tag_table(path: str) -> dict[str, str]:
    """讀取科目代碼對照表，回傳 {代碼: 中文名稱}。"""
    tag_map: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = row["FA_RFNBR"].strip()
                name = row["FA_CANME"].strip()
                tag_map[code] = name
    except FileNotFoundError:
        logger.error("科目對照表不存在: %s", path)
        raise
    except KeyError as e:
        logger.error(
            "科目對照表缺少必要欄位 %s: %s", e, path,
        )
        raise
    except OSError as e:
        logger.error(
            "讀取科目對照表失敗: %s — %s", path, e,
        )
        raise
    return tag_map


def _get_unit(code: str, detected_unit: str = "") -> str:
    """依代碼前綴決定單位，TIBB 則使用從 HTML 偵測到的單位。"""
    prefix = code[:4].upper()
    if prefix in ("TIBA", "TIBC", "TIBD"):
        return "仟元"
    return detected_unit


def parse_html_table(
    html: str,
    value_indices: list[int] | None = None,
) -> dict[str, dict[str, float | None]]:
    """解析含 TIB 代碼的 HTML 表格。

    Args:
        html: HTML 原始字串。
        value_indices: 要擷取的數值欄索引（從 0 起算）。
            若為 None，取前 3 欄。
            例如檔案 1 需設為 [0, 2, 4] 只取金額欄。

    Returns:
        {代碼: {Current, Period_2, Period_3}, ...}
    """
    result: dict[str, dict[str, float | None]] = {}

    for tr_match in _TR_RE.finditer(html):
        tr_content = tr_match.group(1)

        # 找這個 <tr> 中是否有 TIB 代碼
        code_match = _CODE_RE.search(tr_match.group(0))
        if not code_match:
            continue

        code = code_match.group(1)

        # 取得所有 <td> 內容
        tds = _TD_CONTENT_RE.findall(tr_content)
        if not tds:
            continue

        # 第一個 td 是代碼/名稱欄，後面的是數值欄
        value_tds = tds[1:]  # 跳過名稱欄

        if value_indices is not None:
            # 依指定索引取值
            parsed = []
            for idx in value_indices:
                if idx < len(value_tds):
                    parsed.append(
                        parse_value(_strip_tags(value_tds[idx]))
                    )
                else:
                    parsed.append((None, ""))
        else:
            # 取前 3 欄
            parsed = [
                parse_value(_strip_tags(td))
                for td in value_tds[:3]
            ]

        # 確保有 3 個值
        while len(parsed) < 3:
            parsed.append((None, ""))

        values = [p[0] for p in parsed]
        # 取第一個偵測到的非空單位
        detected_unit = next(
            (p[1] for p in parsed if p[1]), ""
        )

        result[code] = {
            "Current": values[0],
            "Period_2": values[1],
            "Period_3": values[2],
            "_unit": detected_unit,
        }

    return result


# ── 備註擷取 ────────────────────────────────────────

def _extract_notes_file2(html: str) -> list[str]:
    """從財務比率 HTML 擷取會計師查核資訊。"""
    notes: list[str] = []

    # 找最後一個 <tr> 區塊中 rowspan 的大段文字
    # 該區塊包含 (自結報告)、(會計師查核) 等資訊
    pattern = re.compile(
        r"rowspan[^>]*>(.*?)</td>",
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        text = _strip_tags(m.group(1))
        # 以換行分割並清理
        for line in text.split("\n"):
            line = line.strip()
            if line:
                notes.append(line)

    return notes


def _extract_notes_file4(html: str) -> list[str]:
    """從淨值調節表 HTML 擷取備註。"""
    notes: list[str] = []

    # 備註在資料表之後的獨立 <table> 中
    # 特徵：含有 "備註" 或跟在 TIBD 資料之後
    # 找所有 <td> 中含有大段文字的區塊
    # 比對特徵：在最後一個 TIB 代碼之後出現的表格文字
    last_tib = html.rfind('title="TIBD')
    if last_tib < 0:
        return notes

    tail = html[last_tib:]
    # 找 </table> 之後的內容
    table_end = tail.find("</table>")
    if table_end < 0:
        return notes

    after_table = tail[table_end:]

    # 從後續表格中擷取文字
    for td_match in _TD_CONTENT_RE.finditer(after_table):
        text = _strip_tags(td_match.group(1))
        text = text.strip()
        if text:
            notes.append(text)

    return notes


# ── 主流程 ──────────────────────────────────────────

_FILE_CONFIG = [
    {
        "filename": "財報_1財務概況.html",
        "value_indices": [0, 2, 4],  # 6 欄中取金額欄
    },
    {
        "filename": "財報_2財務比率.html",
        "value_indices": None,  # 3 欄直接取
        "notes_section": "財務比率分析",
    },
    {
        "filename": "財報_3現金流量.html",
        "value_indices": None,
    },
    {
        "filename": "財報_4淨值調節.html",
        "value_indices": None,
        "notes_section": "淨值調節表",
    },
]


def _read_html(path: str) -> str:
    """以 Big5 編碼讀取 HTML 檔案。"""
    # 嘗試 Big5，失敗則用 utf-8
    for enc in ("big5", "cp950", "utf-8"):
        try:
            with open(path, encoding=enc, errors="strict") as f:
                return f.read()
        except (UnicodeDecodeError, LookupError):
            continue

    # 最後用 big5 + replace 容錯
    with open(path, encoding="big5", errors="replace") as f:
        return f.read()


def convert_html_files_to_dict(
    html_paths: list[str],
    tag_table_path: str | None = None,
) -> dict:
    """將 4 個 HTML 財報轉為 dict（純記憶體，不寫檔案）。

    接收明確的 4 個檔案路徑，與 _FILE_CONFIG 逐一配對解析。
    適用於 EXE 入口或需要並行呼叫的場景，避免暫存檔衝突。

    Args:
        html_paths: 4 個 HTML 檔案路徑，順序須對應
            _FILE_CONFIG（財務概況、財務比率、現金流量、淨值調節）。
        tag_table_path: 科目代碼對照表 CSV 路徑（選填）。

    Returns:
        與 risk_engine/loader.py 相容的 dict 結構。

    Raises:
        FileNotFoundError: 任一 HTML 檔案不存在。
        ValueError: html_paths 長度不為 4。
    """
    if len(html_paths) != len(_FILE_CONFIG):
        raise ValueError(
            f"須提供 {len(_FILE_CONFIG)} 個 HTML 檔案，"
            f"實際收到 {len(html_paths)} 個"
        )

    # 載入科目名稱對照
    tag_map: dict[str, str] = {}
    if tag_table_path and os.path.isfile(tag_table_path):
        tag_map = _load_tag_table(tag_table_path)

    result: dict = {}
    skipped: dict[str, list[str]] = {}
    period_dates: list[str] = []

    for filepath, cfg in zip(html_paths, _FILE_CONFIG):
        if not os.path.isfile(filepath):
            raise FileNotFoundError(
                f"HTML 檔案不存在: {filepath}"
            )

        logger.info("解析 HTML: %s", filepath)
        html = _read_html(filepath)

        # 從第一個 HTML 提取期間日期
        if not period_dates:
            period_dates = extract_period_dates(html)

        # 解析表格數據
        data = parse_html_table(
            html,
            value_indices=cfg.get("value_indices"),
        )
        result.update(data)

        # 擷取備註
        section = cfg.get("notes_section")
        if section == "財務比率分析":
            notes = _extract_notes_file2(html)
            if notes:
                skipped[section] = notes
        elif section == "淨值調節表":
            notes = _extract_notes_file4(html)
            if notes:
                skipped[section] = notes

    # 附加 FA_CANME 與單位
    for code, row in result.items():
        row["FA_CANME"] = tag_map.get(code, "")
        detected = row.pop("_unit", "")
        row["單位"] = _get_unit(code, detected)

    result["skipped"] = skipped
    result["_period_dates"] = period_dates

    logger.info(
        "HTML 轉換完成: %d 筆代碼, 期間: %s",
        len(result) - 2, period_dates,
    )
    return result


def convert_html_to_json(
    html_dir: str,
    output_path: str,
    tag_table_path: str | None = None,
) -> dict:
    """將 HTML 資料夾中的財報轉為 JSON。

    Args:
        html_dir: HTML 檔案所在資料夾路徑。
        output_path: 輸出 JSON 檔案路徑。
        tag_table_path: 科目代碼對照表 CSV 路徑（選填）。

    Returns:
        轉換後的完整 dict。
    """
    # 載入科目名稱對照
    tag_map: dict[str, str] = {}
    if tag_table_path and os.path.isfile(tag_table_path):
        tag_map = _load_tag_table(tag_table_path)

    result: dict = {}
    skipped: dict[str, list[str]] = {}
    period_dates: list[str] = []

    for cfg in _FILE_CONFIG:
        filepath = os.path.join(html_dir, cfg["filename"])
        if not os.path.isfile(filepath):
            print(
                f"警告: 檔案不存在，跳過: {filepath}",
                file=sys.stderr,
            )
            continue

        html = _read_html(filepath)

        # 從第一個 HTML 提取期間日期
        if not period_dates:
            period_dates = extract_period_dates(html)

        # 解析表格數據
        data = parse_html_table(
            html,
            value_indices=cfg.get("value_indices"),
        )
        result.update(data)

        # 擷取備註
        section = cfg.get("notes_section")
        if section == "財務比率分析":
            notes = _extract_notes_file2(html)
            if notes:
                skipped[section] = notes
        elif section == "淨值調節表":
            notes = _extract_notes_file4(html)
            if notes:
                skipped[section] = notes

    # 附加 FA_CANME 與單位
    for code, row in result.items():
        row["FA_CANME"] = tag_map.get(code, "")
        detected = row.pop("_unit", "")
        row["單位"] = _get_unit(code, detected)

    result["skipped"] = skipped
    result["_period_dates"] = period_dates

    # 寫入 JSON
    try:
        os.makedirs(
            os.path.dirname(output_path) or ".",
            exist_ok=True,
        )
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
    except PermissionError:
        logger.error(
            "無權限寫入輸出檔案: %s", output_path,
        )
        raise
    except OSError as e:
        logger.error(
            "寫入輸出檔案失敗: %s — %s", output_path, e,
        )
        raise

    print(f"轉換完成: {len(result) - 1} 筆代碼 → {output_path}")
    return result


# ── CLI ─────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="將財報 HTML 檔案組合為 JSON",
    )
    parser.add_argument(
        "--input", "-i",
        default="data/html",
        help="HTML 資料夾路徑（預設: data/html）",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/report.json",
        help="輸出 JSON 路徑（預設: data/report.json）",
    )
    parser.add_argument(
        "--tag-table", "-t",
        default="tag_table.csv",
        help="科目代碼對照表 CSV（預設: tag_table.csv）",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.input):
        print(
            f"錯誤: 資料夾不存在: {args.input}",
            file=sys.stderr,
        )
        sys.exit(1)

    convert_html_to_json(args.input, args.output, args.tag_table)


if __name__ == "__main__":
    main()
