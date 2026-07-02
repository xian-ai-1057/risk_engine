"""Bridge between the FastAPI layer and the risk-judgment engine.

Responsibilities kept out of the route handlers:
  - resolve server-side resource paths (指標 xlsx + 兩份 user prompt 模板),
    reusing the versioned-file discovery already implemented for the EXE
    (``scripts.main._resolve_paths`` → ``_discover_versioned``);
  - list available 產業別 from the active xlsx (cached by file mtime);
  - persist uploaded HTML to a per-request temp dir and run the real engine
    (``risk_engine.api.run_report``), cleaning up afterwards;
  - load the bundled sample output for the零輸入 demo path.

The engine itself is imported and called **in-process** — no subprocess of the
EXE. Core modules are consumed read-only; nothing here mutates them.
"""
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any

# ``web/__init__`` has already put src/ and the repo root on sys.path, so these
# resolve without an editable install.
from risk_engine import types
from risk_engine.api import run_report
from risk_engine.paths import get_base_dir
from scripts.main import _resolve_paths  # reuse versioned-file discovery
from utils.xlsx_to_indicators import convert as xlsx_convert

logger = logging.getLogger(__name__)

# System prompts live in inputs/prompt/ (only needed for the LLM toggle).
_NARRATIVE_SYS_PROMPT = "財報敘事_sys_prompt.txt"
_RISK_SYS_PROMPT = "財報風險_sys_prompt.txt"

# LLM endpoint config is read from the server environment (``.env`` loaded by
# ``web/__init__``), never collected from the browser — the UI has no key
# fields. All three must be set for the generate toggle to work.
_LLM_ENV_VARS = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")


def llm_env_ready() -> bool:
    """True iff all LLM_* env vars are set (so /api/health can flag the UI)."""
    return all(os.environ.get(v, "").strip() for v in _LLM_ENV_VARS)


def _read_llm_env() -> tuple[str, str, str]:
    """Return ``(base_url, api_key, model)`` from env; raise if any missing.

    Raises:
        types.ConfigError: one or more LLM_* vars unset — the route maps this
            to HTTP 400 so the browser shows a clear message.
    """
    values = {v: os.environ.get(v, "").strip() for v in _LLM_ENV_VARS}
    missing = [v for v, val in values.items() if not val]
    if missing:
        raise types.ConfigError(
            "啟用 LLM 生成需在伺服器 .env 設定: " + ", ".join(missing),
        )
    return values["LLM_BASE_URL"], values["LLM_API_KEY"], values["LLM_MODEL"]

# Fixed HTML order the engine expects.
HTML_SLOTS = ("財務概況", "財務比率", "現金流量", "淨值調節")


def _repo_root() -> str:
    """Repo root (frozen-aware, though the web app never runs frozen)."""
    return get_base_dir()


def resource_dir() -> str:
    """Directory holding the指標 xlsx + user-prompt 模板.

    Defaults to ``<repo>/deploy`` (the EXE-style deployment layout); override
    with ``RISK_WEB_RESOURCE_DIR`` to point at another folder.
    """
    return os.environ.get("RISK_WEB_RESOURCE_DIR") or os.path.join(
        _repo_root(), "deploy",
    )


def prompt_dir() -> str:
    """Directory holding the LLM system prompts (inputs/prompt/)."""
    return os.path.join(_repo_root(), "inputs", "prompt")


def sample_path() -> str:
    """Path to the bundled full-output sample used by the零輸入 demo path."""
    return os.path.join(
        _repo_root(), "inputs", "json_sample", "final_results.json",
    )


# ── 產業別 listing (cached by xlsx mtime) ────────────────────────────

_industries_cache: dict[str, tuple[float, list[str]]] = {}


def list_industries() -> list[str]:
    """Return the 產業別 keys from the active指標 xlsx.

    Raises:
        FileNotFoundError: the xlsx / prompt 模板 can't be discovered.
        ValueError / KeyError: the xlsx structure is malformed.
    """
    paths = _resolve_paths(resource_dir())
    xlsx = paths["xlsx"]
    mtime = os.path.getmtime(xlsx)
    cached = _industries_cache.get(xlsx)
    if cached and cached[0] == mtime:
        return cached[1]
    config, _filter, _tag = xlsx_convert(xlsx)
    industries = list(config.keys())
    _industries_cache[xlsx] = (mtime, industries)
    return industries


def load_sample() -> dict[str, Any]:
    """Load the bundled sample engine output (demo mode, no engine run)."""
    with open(sample_path(), encoding="utf-8") as f:
        return json.load(f)


# ── analyze ──────────────────────────────────────────────────────────

@dataclass
class AnalyzeInputs:
    """Everything the /api/analyze route collected from the request.

    ``files`` are ``(filename, raw_bytes)`` in the fixed engine order
    (概況 / 比率 / 現金流量 / 淨值調節). Bytes are written to disk verbatim so
    the engine's own encoding detection (utf-8 / utf-8-sig / big5) still works.
    """

    files: list[tuple[str, bytes]]
    industry: str
    customer_id: str = ""
    report_date: str = ""
    request_id: str = ""
    generate: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


def analyze(inp: AnalyzeInputs) -> dict[str, Any]:
    """Persist uploads, run the engine, and return its result dict.

    When ``inp.generate`` is set the LLM endpoint is read from the server
    environment (``LLM_BASE_URL`` / ``LLM_API_KEY`` / ``LLM_MODEL``, populated
    from ``.env``); it is never taken from the request.

    Raises:
        FileNotFoundError: server-side resource files are missing.
        types.ConfigError / types.ReportLoadError: propagated from the engine
            (bad 產業, missing LLM config, unparseable財報 …) — the route maps
            these to HTTP 400.
    """
    paths = _resolve_paths(resource_dir())
    tmpdir = tempfile.mkdtemp(prefix="risk_web_")
    try:
        html_paths: list[str] = []
        for idx, (name, content) in enumerate(inp.files):
            base = os.path.basename(name) or "upload.html"
            dest = os.path.join(tmpdir, f"{idx}_{base}")
            with open(dest, "wb") as f:  # raw bytes → preserve Big5 財報
                f.write(content)
            html_paths.append(dest)

        kwargs: dict[str, Any] = {
            "html_files": html_paths,
            "industry": inp.industry,
            "xlsx_path": paths["xlsx"],
            "narrative_user_prompt_path": paths["narrative_user_prompt"],
            "risk_user_prompt_path": paths["risk_user_prompt"],
            "customer_id": inp.customer_id,
            "report_date": inp.report_date,
            "request_id": inp.request_id,
        }
        if inp.generate:
            # LLM endpoint comes from server env (.env), not the request.
            base_url, api_key, model = _read_llm_env()
            kwargs.update(
                generate=True,
                narrative_sys_prompt_path=os.path.join(
                    prompt_dir(), _NARRATIVE_SYS_PROMPT,
                ),
                risk_sys_prompt_path=os.path.join(
                    prompt_dir(), _RISK_SYS_PROMPT,
                ),
                llm_base_url=base_url,
                llm_api_key=api_key,
                llm_model=model,
            )
        return run_report(**kwargs)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
