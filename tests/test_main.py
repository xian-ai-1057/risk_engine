"""scripts/main.py EXE 入口契約測試。

聚焦驗證：
  - ``--stdout`` 模式錯誤 JSON 結構（含 ``error_code``、``request_id``）
  - exit code 與 ERROR_CODES 對應正確
  - 成功輸出含 ``schema_version``

不在這裡跑完整 happy path（留給 e2e 測試）；
只用 monkeypatch + 受控錯誤注入驗證錯誤合約。
"""
import importlib
import io
import json
import os
import sys
from pathlib import Path

import pytest

from risk_engine import types


# 動態載入 scripts/main.py（不是套件成員）
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
main_mod = importlib.import_module("main")


# ── 共用 fixture ─────────────────────────────────────

@pytest.fixture
def capture_stdout(capsys):
    """從 capsys 取得 stdout JSON 並 parse。"""
    def _read() -> dict:
        captured = capsys.readouterr()
        # 過濾空行
        line = captured.out.strip().splitlines()[-1]
        return json.loads(line)
    return _read


@pytest.fixture
def make_argv(monkeypatch):
    """設定 sys.argv（供 main() 使用）。"""
    def _set(*flags: str) -> None:
        monkeypatch.setattr(
            sys, "argv", ["main.py", *flags],
        )
    return _set


# ── 1. INVALID_ARGS：stdin JSON 解析失敗 ───────────

class TestStdinInvalidJson:
    def test_stdin_bad_json_returns_invalid_args(
        self, monkeypatch, make_argv, capture_stdout,
    ):
        make_argv("--stdin", "--stdout")
        monkeypatch.setattr(
            sys, "stdin", io.StringIO("{not json"),
        )

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 1
        payload = capture_stdout()
        assert payload["error_code"] == "INVALID_ARGS"
        assert "request_id" in payload
        assert payload["error_code"] in types.ERROR_CODES


# ── 2. INVALID_ARGS：CLI 缺 4 個 HTML / industry ──

class TestCliMissingArgs:
    def test_missing_html_files_with_stdout(
        self, make_argv, capture_stdout,
    ):
        make_argv("--industry", "批發業", "--stdout")

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 1
        payload = capture_stdout()
        assert payload["error_code"] == "INVALID_ARGS"

    def test_missing_industry_with_stdout(
        self, make_argv, capture_stdout,
    ):
        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--stdout",
        )

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 1
        payload = capture_stdout()
        assert payload["error_code"] == "INVALID_ARGS"


# ── 3. MISSING_FILE：HTML 檔不存在 ───────────────

class TestMissingFile:
    def test_html_not_found_returns_missing_file(
        self,
        tmp_path: Path,
        monkeypatch,
        make_argv,
        capture_stdout,
    ):
        # 在 tmp_path 建立必要的同層設定檔，避免提前因設定缺失而失敗
        (tmp_path / "indicators_config.json").write_text(
            json.dumps({"批發業": []}),
            encoding="utf-8",
        )
        (tmp_path / "risk_user_prompt.txt").write_text(
            "RISK", encoding="utf-8",
        )
        (tmp_path / "narrative_user_prompt.txt").write_text(
            "NARRATIVE", encoding="utf-8",
        )

        # 把 base_dir 指向 tmp_path
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )

        # 4 個不存在的 HTML 路徑
        bogus = [
            str(tmp_path / f"nope_{i}.html")
            for i in range(4)
        ]
        make_argv(
            *bogus, "--industry", "批發業", "--stdout",
        )

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        # html_to_json 找不到檔會丟 FileNotFoundError
        # → MISSING_FILE / exit 2
        assert exc.value.code == 2
        payload = capture_stdout()
        assert payload["error_code"] == "MISSING_FILE"


# ── 4. CONFIG_ERROR：industry 不在設定檔 ─────────

class TestConfigError:
    def test_unknown_industry(
        self,
        tmp_path: Path,
        monkeypatch,
        make_argv,
        capture_stdout,
    ):
        (tmp_path / "indicators_config.json").write_text(
            json.dumps({"批發業": []}),
            encoding="utf-8",
        )
        (tmp_path / "risk_user_prompt.txt").write_text(
            "RISK", encoding="utf-8",
        )
        (tmp_path / "narrative_user_prompt.txt").write_text(
            "NARRATIVE", encoding="utf-8",
        )

        # mock convert_html_files_to_dict 使其不真的去讀檔
        monkeypatch.setattr(
            "main.convert_html_files_to_dict",
            lambda files, tag_table_path=None: {
                "_period_dates": [],
            },
        )
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )

        # 4 個 dummy HTML 路徑（mock 後不會真的開檔）
        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "不存在的產業",
            "--stdout",
        )

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 2
        payload = capture_stdout()
        assert payload["error_code"] == "CONFIG_ERROR"


# ── 5. ERROR_CODES 涵蓋性 ────────────────────────

class TestErrorCodesContract:
    def test_all_codes_in_canonical_set(self):
        """確保新增的 error_code 都在 ERROR_CODES 中。"""
        assert set(types.ERROR_CODES) == {
            "INVALID_ARGS",
            "MISSING_FILE",
            "CONFIG_ERROR",
            "PROCESSING_ERROR",
        }


# ── 6. 預設 output 路徑落在 base_dir/output/ ────────

class TestDefaultOutputPath:
    def test_default_path_under_base_dir(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )
        path = main_mod._default_output_path("trace-001")
        assert path.startswith(
            str(tmp_path / "output") + os.sep,
        ), path
        assert "trace-001" in path
        assert path.endswith(".json")

    def test_concurrent_request_ids_distinct(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )
        p1 = main_mod._default_output_path("r1")
        p2 = main_mod._default_output_path("r2")
        assert p1 != p2
        assert "r1" in p1 and "r2" in p2
