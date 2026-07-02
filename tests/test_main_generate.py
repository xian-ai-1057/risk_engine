"""scripts/main.py --generate（串接模型生成段落）測試。

驗證：
  - ``_call_llm`` 組出正確的 OpenAI 相容 payload 並解析回應為 4-1~4-5 dict
  - ``--generate`` 時 ``_run`` 會把 narrative_sections / risk_sections 塞進輸出
  - 不帶 ``--generate`` 時輸出結構與原本一致（無新欄位）
  - 缺 LLM 環境變數 → CONFIG_ERROR / exit 2

全程不打真 API：``_call_llm`` 以 monkeypatch 換成罐頭；單元測試則
monkeypatch ``urllib.request.urlopen``。
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

# 動態載入 scripts/main.py（不是套件成員）
_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))
main_mod = importlib.import_module("main")

_SECTIONS = {k: f"{k} 段落" for k in ("4-1", "4-2", "4-3", "4-4", "4-5")}


# ── 共用 fixture ─────────────────────────────────────

@pytest.fixture
def make_argv(monkeypatch):
    def _set(*flags: str) -> None:
        monkeypatch.setattr(sys, "argv", ["main.py", *flags])
    return _set


def _setup_base_dir(tmp_path: Path, monkeypatch) -> None:
    """在 tmp_path 佈置 main.py 需要的同層檔案並把 base_dir 指過去。"""
    (tmp_path / "指標.xlsx").write_bytes(b"dummy")
    (tmp_path / "risk_user_prompt.txt").write_text("RISK", encoding="utf-8")
    (tmp_path / "narrative_user_prompt.txt").write_text(
        "NARRATIVE", encoding="utf-8",
    )
    prompt_dir = tmp_path / "inputs" / "prompt"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / main_mod._NARRATIVE_SYS_PROMPT).write_text(
        "敘事系統", encoding="utf-8",
    )
    (prompt_dir / main_mod._RISK_SYS_PROMPT).write_text(
        "風險系統", encoding="utf-8",
    )
    monkeypatch.setattr("main.get_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(
        "main.xlsx_convert",
        lambda path: ({"批發業": []}, {"批發業": {}}, {}),
    )
    monkeypatch.setattr(
        "main.convert_html_files_to_dict",
        lambda files, tag_map=None: {"_period_dates": []},
    )
    monkeypatch.setattr(
        "main.run_pipeline",
        lambda **kwargs: {
            "narrative_prompt": "N-PROMPT",
            "risk_prompt": "R-PROMPT",
            "grouped_report": {},
            "risk_report": {},
        },
    )


# ── 1. _call_llm 單元測試（monkeypatch urlopen）──────

class _FakeResp:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        return self._body


class TestCallLlm:
    def test_payload_and_parsing(self, monkeypatch):
        captured: dict = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["auth"] = req.headers.get("Authorization")
            captured["body"] = json.loads(req.data.decode("utf-8"))
            resp = {
                "choices": [
                    {"message": {"content": json.dumps(_SECTIONS)}},
                ],
            }
            return _FakeResp(json.dumps(resp).encode("utf-8"))

        monkeypatch.setattr(
            "urllib.request.urlopen", fake_urlopen,
        )

        out = main_mod._call_llm(
            "https://api.example.com/v1/",
            "sk-xyz",
            "gpt-4o",
            "SYS",
            "USER",
        )

        assert out == _SECTIONS
        # URL 去掉尾斜線後補 /chat/completions
        assert captured["url"] == "https://api.example.com/v1/chat/completions"
        assert captured["auth"] == "Bearer sk-xyz"
        body = captured["body"]
        assert body["model"] == "gpt-4o"
        assert body["messages"][0] == {"role": "system", "content": "SYS"}
        assert body["messages"][1] == {"role": "user", "content": "USER"}
        # 帶結構化輸出 schema，產出 4-1~4-5
        schema = body["response_format"]["json_schema"]["schema"]
        assert schema["required"] == ["4-1", "4-2", "4-3", "4-4", "4-5"]
        assert schema["additionalProperties"] is False


# ── 2. --generate：輸出含 narrative/risk sections ────

class TestGenerateFlag:
    def test_generate_attaches_sections(
        self, tmp_path, monkeypatch, make_argv,
    ):
        _setup_base_dir(tmp_path, monkeypatch)
        monkeypatch.setenv("LLM_BASE_URL", "https://x/v1")
        monkeypatch.setenv("LLM_API_KEY", "sk-1")
        monkeypatch.setenv("LLM_MODEL", "m")

        calls: list = []

        def fake_call(base_url, api_key, model, sys_p, user_p, **kw):
            calls.append((sys_p, user_p))
            return dict(_SECTIONS)

        monkeypatch.setattr("main._call_llm", fake_call)

        out_path = tmp_path / "out.json"
        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "批發業",
            "--generate",
            "-o", str(out_path),
        )
        main_mod.main()

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert data["narrative_sections"] == _SECTIONS
        assert data["risk_sections"] == _SECTIONS
        # 兩次呼叫：敘事(sys=敘事系統, user=N-PROMPT) 與 風險
        assert ("敘事系統", "N-PROMPT") in calls
        assert ("風險系統", "R-PROMPT") in calls

    def test_no_generate_has_no_sections(
        self, tmp_path, monkeypatch, make_argv,
    ):
        _setup_base_dir(tmp_path, monkeypatch)

        def boom(*a, **k):  # 不應被呼叫
            raise AssertionError("未帶 --generate 不該呼叫模型")

        monkeypatch.setattr("main._call_llm", boom)

        out_path = tmp_path / "out.json"
        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "批發業",
            "-o", str(out_path),
        )
        main_mod.main()

        data = json.loads(out_path.read_text(encoding="utf-8"))
        assert "narrative_sections" not in data
        assert "risk_sections" not in data


# ── 3. 缺 LLM 環境變數 → CONFIG_ERROR / exit 2 ──────

class TestMissingLlmEnv:
    def test_missing_env_returns_config_error(
        self, tmp_path, monkeypatch, make_argv, capsys,
    ):
        _setup_base_dir(tmp_path, monkeypatch)
        for var in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
            monkeypatch.delenv(var, raising=False)

        make_argv(
            "a.html", "b.html", "c.html", "d.html",
            "--industry", "批發業",
            "--generate",
            "--stdout",
        )

        with pytest.raises(SystemExit) as exc:
            main_mod.main()

        assert exc.value.code == 2
        line = capsys.readouterr().out.strip().splitlines()[-1]
        payload = json.loads(line)
        assert payload["error_code"] == "CONFIG_ERROR"
