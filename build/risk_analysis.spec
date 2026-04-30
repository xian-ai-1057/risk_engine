# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包 spec：risk_analysis.exe

設計要點：
  * 入口：scripts/main.py
  * 採 onefile 模式（單一 exe），避免上游部署需處理多檔
  * 不打包業務資料（indicators_config.json / 兩個 prompt /
    tag_table.csv）— 設計上要求這些檔放在 exe 同層，方便不重新
    打包就更新規則或 prompt
  * 只用到標準函式庫 + 自家原始碼，不需 hiddenimports

打包指令（在 repo root 執行）：
  pyinstaller build/risk_analysis.spec

產出：dist/risk_analysis(.exe)
"""
import os
import sys
from pathlib import Path

# spec 檔執行時 cwd 不一定是 repo root；用 SPECPATH 推導
_REPO_ROOT = Path(SPECPATH).resolve().parent
_SRC = str(_REPO_ROOT / "src")
_SCRIPTS = str(_REPO_ROOT / "scripts")

# 把 src/ 與 scripts/ 加進 PyInstaller 的 module 搜尋路徑
sys.path.insert(0, _SRC)
sys.path.insert(0, _SCRIPTS)


block_cipher = None


a = Analysis(
    [str(_REPO_ROOT / "scripts" / "main.py")],
    pathex=[_SRC, _SCRIPTS],
    binaries=[],
    datas=[],
    # 動態 import 的子模組需要明列；目前都是靜態 import，留空即可
    hiddenimports=[
        "risk_engine",
        "risk_engine.checker",
        "risk_engine.formula",
        "risk_engine.loader",
        "risk_engine.log_config",
        "risk_engine.paths",
        "risk_engine.pipeline",
        "risk_engine.post_rules",
        "risk_engine.report",
        "risk_engine.threshold",
        "risk_engine.types",
        "utils.combine_prompt",
        "utils.html_to_json",
        "utils.narrative",
        "utils.simple_convert",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 主流程不用，避免被巨大依賴拖累 exe 體積
        "pandas",
        "numpy",
        "docx",
        "openpyxl",
        "matplotlib",
        "scipy",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(
    a.pure, a.zipped_data, cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="risk_analysis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
