"""資料載入模組。

負責載入財報 CSV / JSON 與指標設定 JSON，
回傳統一的型別化資料結構。
"""
import csv
import json
import logging
import os
from typing import Any

from risk_engine import types

logger = logging.getLogger(__name__)


# ── 數值轉換 ────────────────────────────────────────

def to_float(val: Any) -> float | None:
    """將任意值轉換為 ``float``。

    供財報載入與外部 CSV/Excel 轉換器共用，統一空值與
    無法解析時的處理規則。

    Args:
        val: 可為 ``None``、``int``、``float``、``str``。

    Returns:
        - 數值（int/float）：直接轉 float。
        - 字串：先 strip，空字串回傳 ``None``，無法 parse 回傳 ``None``。
        - ``None``：回傳 ``None``。
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    val = str(val).strip()
    if not val:
        return None
    try:
        return float(val)
    except ValueError:
        return None


# ── 財報載入 ────────────────────────────────────────

def _build_report_row(
    data: dict[str, Any],
) -> types.ReportRow:
    """從原始 dict 建構正規化的 ReportRow。"""
    return {
        "FA_CANME": data.get("FA_CANME", ""),
        "單位": data.get("單位", ""),
        "Current": to_float(data.get("Current")),
        "Period_2": to_float(data.get("Period_2")),
        "Period_3": to_float(data.get("Period_3")),
    }


def _load_report_csv(path: str) -> types.Report:
    """從 CSV 載入財報，以 FA_RFNBR 為 key。"""
    report: types.Report = {}
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames and "FA_RFNBR" not in reader.fieldnames:
            raise KeyError(
                f"CSV 缺少必要欄位 'FA_RFNBR'，"
                f"現有欄位: {', '.join(reader.fieldnames)}"
            )
        for row in reader:
            code = row["FA_RFNBR"].strip()
            report[code] = _build_report_row(row)
    return report


def _load_report_json(path: str) -> types.Report:
    """從 JSON 載入財報。

    預期格式為 {代碼: {FA_CANME, 單位,
    Current, Period_2, Period_3}, ...}。
    """
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    return {
        code: _build_report_row(data)
        for code, data in raw.items()
    }


def load_report(path: str) -> types.Report:
    """載入財報，自動依副檔名判斷 CSV 或 JSON。

    Args:
        path: 財報檔案路徑（.csv 或 .json）。

    Returns:
        {代碼: ReportRow, ...}

    Raises:
        ReportLoadError: 檔案不存在或格式錯誤。
    """
    logger.info("載入財報: %s", path)

    if not os.path.isfile(path):
        raise types.ReportLoadError(
            f"財報檔案不存在: {path}"
        )

    try:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".json":
            report = _load_report_json(path)
        else:
            report = _load_report_csv(path)
    except (json.JSONDecodeError, KeyError,
            UnicodeDecodeError) as e:
        raise types.ReportLoadError(
            f"財報檔案格式錯誤: {path} — {e}"
        ) from e

    logger.info("財報載入完成，代碼數: %d", len(report))
    return report


# ── 指標設定載入 ────────────────────────────────────

def load_config(
    config_path: str,
    industry: str,
) -> list[dict[str, Any]]:
    """載入指標設定檔並篩選產業。

    Args:
        config_path: JSON 設定檔路徑。
        industry: 產業名稱。

    Returns:
        該產業的規則列表。

    Raises:
        ConfigError: 檔案不存在、格式錯誤或產業不存在。
    """
    logger.info(
        "載入指標設定: %s (產業: %s)",
        config_path, industry,
    )

    if not os.path.isfile(config_path):
        raise types.ConfigError(
            f"指標設定檔不存在: {config_path}"
        )

    try:
        with open(
            config_path, encoding="utf-8",
        ) as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise types.ConfigError(
            f"指標設定檔 JSON 格式錯誤:"
            f" {config_path} — {e}"
        ) from e

    if industry not in config:
        available = ", ".join(config.keys())
        raise types.ConfigError(
            f"產業 '{industry}' 不存在。"
            f" 可用產業: {available}"
        )

    rules = config[industry]
    logger.info("規則載入完成，規則數: %d", len(rules))
    return rules


# ── CSV 讀取（convert_indicators 用） ──────────────

def load_csv(csv_path: str) -> list[dict[str, str]]:
    """讀取 CSV，回傳 list of dict。

    Args:
        csv_path: CSV 檔案路徑。

    Returns:
        每列一個 dict 的列表。
    """
    with open(csv_path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))
