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

def _stub_xlsx(tmp_path: Path) -> Path:
    """建立一個空的 dummy xlsx，僅用於通過 `_resolve_paths` 的存在性檢查。

    內容無關緊要 —— 我們會 monkeypatch ``main.xlsx_convert``，
    所以實際上不會真的呼叫 pandas 讀取它。
    """
    p = tmp_path / "指標.xlsx"
    p.write_bytes(b"dummy")
    return p


class TestMissingFile:
    def test_html_not_found_returns_missing_file(
        self,
        tmp_path: Path,
        monkeypatch,
        make_argv,
        capture_stdout,
    ):
        # 在 tmp_path 建立必要的同層設定檔，避免提前因設定缺失而失敗
        _stub_xlsx(tmp_path)
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
        # xlsx 在 HTML 之前載入；mock 掉 xlsx_convert 才能跑到 HTML 解析步驟
        monkeypatch.setattr(
            "main.xlsx_convert",
            lambda path: ({"批發業": []}, {"批發業": {}}, {}),
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

    def test_missing_xlsx_returns_missing_file(
        self,
        tmp_path: Path,
        monkeypatch,
        make_argv,
        capture_stdout,
    ):
        # 故意不建立 xlsx；prompt 都備齊
        (tmp_path / "risk_user_prompt.txt").write_text(
            "RISK", encoding="utf-8",
        )
        (tmp_path / "narrative_user_prompt.txt").write_text(
            "NARRATIVE", encoding="utf-8",
        )
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )

        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "批發業", "--stdout",
        )

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

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
        _stub_xlsx(tmp_path)
        (tmp_path / "risk_user_prompt.txt").write_text(
            "RISK", encoding="utf-8",
        )
        (tmp_path / "narrative_user_prompt.txt").write_text(
            "NARRATIVE", encoding="utf-8",
        )

        # mock convert_html_files_to_dict 使其不真的去讀檔
        monkeypatch.setattr(
            "main.convert_html_files_to_dict",
            lambda files, tag_map=None: {
                "_period_dates": [],
            },
        )
        # mock xlsx_convert 直接回固定 config（避免依賴 pandas/openpyxl）
        monkeypatch.setattr(
            "main.xlsx_convert",
            lambda path: ({"批發業": []}, {"批發業": {}}, {}),
        )
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )

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


# ── 6. 預設 output 路徑落在 base_dir/outputs/ ───────

class TestDefaultOutputPath:
    def test_default_path_under_base_dir(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )
        path = main_mod._default_output_path("trace-001")
        assert path.startswith(
            str(tmp_path / "outputs") + os.sep,
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


# ── 7. tag_table 來源：xlsx sheet 優先、CSV fallback ──

class TestTagTableSource:
    """確認 _run 走的是 xlsx 內 tag_table sheet → 不再讀 CSV；
    sheet 缺席時才 fallback 到 tag_table.csv。"""

    def _stub_prompts(self, tmp_path: Path) -> None:
        _stub_xlsx(tmp_path)
        (tmp_path / "risk_user_prompt.txt").write_text(
            "RISK", encoding="utf-8",
        )
        (tmp_path / "narrative_user_prompt.txt").write_text(
            "NARRATIVE", encoding="utf-8",
        )

    def _patch_pipeline(self, monkeypatch):
        """繞過真正的 ReportPipeline，回傳 stub 結果。"""
        monkeypatch.setattr(
            "main.run_pipeline",
            lambda **kwargs: {
                "narrative_prompt": "N",
                "risk_prompt": "R",
                "grouped_report": {},
                "risk_report": {},
            },
        )

    def test_xlsx_tag_map_used_when_present(
        self, tmp_path, monkeypatch, make_argv,
    ):
        self._stub_prompts(tmp_path)
        # 即使有 tag_table.csv 也不該被讀（xlsx 是唯一來源）
        (tmp_path / "tag_table.csv").write_text(
            "FA_RFNBR,FA_CANME\nTIBA001,CSV版本\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )
        monkeypatch.setattr(
            "main.xlsx_convert",
            lambda path: (
                {"批發業": []},
                {"批發業": {}},
                {"TIBA001": "XLSX版本"},
            ),
        )

        captured: dict = {}

        def fake_convert(html_paths, tag_map=None):
            captured["tag_map"] = tag_map
            return {"_period_dates": []}

        monkeypatch.setattr(
            "main.convert_html_files_to_dict", fake_convert,
        )
        self._patch_pipeline(monkeypatch)

        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "批發業",
            "-o", str(tmp_path / "out.json"),
        )
        main_mod.main()

        assert captured["tag_map"] == {"TIBA001": "XLSX版本"}

    def test_empty_tag_map_when_xlsx_lacks_sheet(
        self, tmp_path, monkeypatch, make_argv,
    ):
        """xlsx 沒有 tag_table sheet → tag_map 為空 dict，
        流程仍跑完，且不會去讀任何 CSV。"""
        self._stub_prompts(tmp_path)
        # 故意放一份 tag_table.csv —— 不應該被讀
        (tmp_path / "tag_table.csv").write_text(
            "FA_RFNBR,FA_CANME\nTIBA001,不該出現\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "main.get_base_dir", lambda: str(tmp_path),
        )
        monkeypatch.setattr(
            "main.xlsx_convert",
            lambda path: ({"批發業": []}, {"批發業": {}}, {}),
        )

        captured: dict = {}

        def fake_convert(html_paths, tag_map=None):
            captured["tag_map"] = tag_map
            return {"_period_dates": []}

        monkeypatch.setattr(
            "main.convert_html_files_to_dict", fake_convert,
        )
        self._patch_pipeline(monkeypatch)

        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "批發業",
            "-o", str(tmp_path / "out.json"),
        )
        main_mod.main()

        assert captured["tag_map"] == {}


# ── 8. 版本化檔名探測 _discover_versioned ──────────

class TestDiscoverVersioned:
    """確認 ``{base}_V{ver}.{ext}`` 版本化檔名自動辨識。"""

    def test_picks_highest_version(self, tmp_path):
        (tmp_path / "risk_user_prompt_V1_1_0.txt").write_text(
            "old", encoding="utf-8",
        )
        (tmp_path / "risk_user_prompt_V1_2_0.txt").write_text(
            "new", encoding="utf-8",
        )

        picked = main_mod._discover_versioned(
            str(tmp_path), "risk_user_prompt", ".txt",
        )

        assert picked == str(
            tmp_path / "risk_user_prompt_V1_2_0.txt",
        )

    def test_fallback_to_unversioned(self, tmp_path):
        (tmp_path / "risk_user_prompt.txt").write_text(
            "plain", encoding="utf-8",
        )

        picked = main_mod._discover_versioned(
            str(tmp_path), "risk_user_prompt", ".txt",
        )

        assert picked == str(tmp_path / "risk_user_prompt.txt")

    def test_prefers_versioned_over_unversioned(self, tmp_path):
        (tmp_path / "risk_user_prompt.txt").write_text(
            "plain", encoding="utf-8",
        )
        (tmp_path / "risk_user_prompt_V1_0_0.txt").write_text(
            "versioned", encoding="utf-8",
        )

        picked = main_mod._discover_versioned(
            str(tmp_path), "risk_user_prompt", ".txt",
        )

        assert picked == str(
            tmp_path / "risk_user_prompt_V1_0_0.txt",
        )

    def test_mixed_segment_lengths(self, tmp_path):
        (tmp_path / "risk_user_prompt_V1.txt").write_text(
            "short", encoding="utf-8",
        )
        (tmp_path / "risk_user_prompt_V1_0_1.txt").write_text(
            "long", encoding="utf-8",
        )

        picked = main_mod._discover_versioned(
            str(tmp_path), "risk_user_prompt", ".txt",
        )

        assert picked == str(
            tmp_path / "risk_user_prompt_V1_0_1.txt",
        )

    def test_ignores_invalid_suffix(self, tmp_path):
        # 非版本化後綴：不應被選為版本化檔
        (tmp_path / "risk_user_prompt_draft.txt").write_text(
            "draft", encoding="utf-8",
        )

        picked = main_mod._discover_versioned(
            str(tmp_path), "risk_user_prompt", ".txt",
        )

        assert picked is None

    def test_returns_none_when_absent(self, tmp_path):
        picked = main_mod._discover_versioned(
            str(tmp_path), "risk_user_prompt", ".txt",
        )
        assert picked is None

    def test_resolve_paths_uses_versioned_xlsx(
        self, tmp_path, monkeypatch,
    ):
        """``_resolve_paths`` 對 xlsx 也走版本化探測。"""
        (tmp_path / "indicators_config_V2_0_0.xlsx").write_bytes(b"d")
        (tmp_path / "risk_user_prompt_V1_1_1.txt").write_text(
            "R", encoding="utf-8",
        )
        (tmp_path / "narrative_user_prompt_V1_1_1.txt").write_text(
            "N", encoding="utf-8",
        )

        paths = main_mod._resolve_paths(str(tmp_path))

        assert paths["xlsx"] == str(
            tmp_path / "indicators_config_V2_0_0.xlsx",
        )
        assert paths["risk_user_prompt"] == str(
            tmp_path / "risk_user_prompt_V1_1_1.txt",
        )
        assert paths["narrative_user_prompt"] == str(
            tmp_path / "narrative_user_prompt_V1_1_1.txt",
        )

    def test_resolve_paths_missing_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            main_mod._resolve_paths(str(tmp_path))
