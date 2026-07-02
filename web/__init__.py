"""風險分析Demo — Web UI for the 財報風險判斷引擎.

A thin FastAPI layer that drives the real risk-judgment engine
(``risk_engine.api.run_report``) from a browser: upload the 4 財報 HTML
files, pick a 產業別, and view the computed risk results — with an optional
LLM toggle to also generate the narrative sections.

This package is intentionally isolated from ``risk_engine`` / ``utils`` /
``scripts`` and is **never** bundled into the PyInstaller EXE (see
``build/risk_analysis.spec`` excludes). It is an optional dependency group:
``pip install -e ".[web]"``.

Importing this package bootstraps ``sys.path`` so ``risk_engine``, ``utils``
and ``scripts`` resolve even without an editable install — the app can be run
straight from a checkout with ``python -m web``.

It also loads a repo-root ``.env`` (if present) so ``RISK_WEB_HOST`` /
``RISK_WEB_PORT`` / ``RISK_WEB_RELOAD`` / ``RISK_WEB_RESOURCE_DIR`` can be set
once instead of exported per-shell — see ``.env.example``. Real shell
environment variables always take priority over ``.env``.
"""
import os
import sys

from dotenv import load_dotenv

# ── sys.path bootstrap ──────────────────────────────────────────────
# web/ lives at the repo root, alongside src/ and scripts/. Add both the
# repo root (so ``scripts`` is importable) and src/ (so ``risk_engine`` /
# ``utils`` resolve) without requiring ``pip install -e .``.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO_ROOT, "src")
for _p in (_SRC, _REPO_ROOT):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

# ── .env bootstrap ───────────────────────────────────────────────────
# Runs once, on first import of the ``web`` package — covers every launch
# path (``python -m web``, ``risk-web``, ``uvicorn web.app:app``, tests).
load_dotenv(os.path.join(_REPO_ROOT, ".env"))

__all__ = ["_REPO_ROOT"]
