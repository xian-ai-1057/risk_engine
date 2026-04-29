"""loader 模組單元測試。"""
import json
import os
import tempfile

import pytest

from risk_engine.loader import _to_float, load_config, load_report


# ── _to_float ─────────────────────────────────────────

class TestToFloat:
    def test_none(self):
        assert _to_float(None) is None

    def test_int(self):
        assert _to_float(42) == 42.0

    def test_float(self):
        assert _to_float(3.14) == 3.14

    def test_string_number(self):
        assert _to_float("58.72") == 58.72

    def test_empty_string(self):
        assert _to_float("") is None

    def test_whitespace_string(self):
        assert _to_float("  ") is None

    def test_invalid_string(self):
        assert _to_float("abc") is None

    def test_negative(self):
        assert _to_float("-10.5") == -10.5


# ── load_report (JSON) ───────────────────────────────

class TestLoadReportJson:
    def test_load_valid_json(self, tmp_path):
        data = {
            "TIBB011": {
                "FA_CANME": "應收帳款週轉天數",
                "單位": "天",
                "Current": 58.72,
                "Period_2": 47.9,
                "Period_3": 73.53,
            },
        }
        path = tmp_path / "report.json"
        path.write_text(json.dumps(data), encoding="utf-8")

        report = load_report(str(path))
        assert "TIBB011" in report
        assert report["TIBB011"]["Current"] == 58.72
        assert report["TIBB011"]["Period_2"] == 47.9

    def test_file_not_found(self):
        with pytest.raises(Exception, match="不存在"):
            load_report("/nonexistent/report.json")

    def test_invalid_json(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json", encoding="utf-8")
        with pytest.raises(Exception, match="格式錯誤"):
            load_report(str(path))


# ── load_report (CSV) ────────────────────────────────

class TestLoadReportCsv:
    def test_load_valid_csv(self, tmp_path):
        csv_content = (
            "FA_RFNBR,FA_CANME,單位,Current,Period_2,Period_3\n"
            "TIBB011,應收帳款週轉天數,天,58.72,47.9,73.53\n"
        )
        path = tmp_path / "report.csv"
        path.write_text(csv_content, encoding="utf-8-sig")

        report = load_report(str(path))
        assert "TIBB011" in report
        assert report["TIBB011"]["Current"] == 58.72

    def test_missing_key_column(self, tmp_path):
        csv_content = "COL_A,COL_B\n1,2\n"
        path = tmp_path / "bad.csv"
        path.write_text(csv_content, encoding="utf-8-sig")
        with pytest.raises(Exception):
            load_report(str(path))


# ── load_config ───────────────────────────────────────

class TestLoadConfig:
    def test_load_valid_config(self, tmp_path):
        config = {
            "批發業": [
                {
                    "tag_id": "T001",
                    "compare_type": "absolute",
                    "operator": ">",
                    "threshold": 150,
                },
            ],
        }
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(config, ensure_ascii=False),
            encoding="utf-8",
        )

        rules = load_config(str(path), "批發業")
        assert len(rules) == 1
        assert rules[0]["tag_id"] == "T001"

    def test_industry_not_found(self, tmp_path):
        config = {"批發業": []}
        path = tmp_path / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")

        with pytest.raises(Exception, match="不存在"):
            load_config(str(path), "零售業")

    def test_config_file_not_found(self):
        with pytest.raises(Exception, match="不存在"):
            load_config("/nonexistent/config.json", "批發業")

    def test_invalid_json_config(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{bad", encoding="utf-8")
        with pytest.raises(Exception, match="格式錯誤"):
            load_config(str(path), "批發業")
