# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包 spec：risk_analysis.exe

設計要點：
  * 入口：scripts/main.py
  * 採 onefile 模式（單一 exe），避免上游部署需處理多檔
  * 不打包業務資料（指標 xlsx / 兩個 prompt）—設計上要求這些檔放在
    exe 同層，方便不重新打包就更新規則或 prompt
  * 需要 openpyxl 來讀指標 xlsx（utils.xlsx_to_indicators），
    指標規則、敘事會科、科目代碼對照表（tag_table）皆整合在 xlsx 內。
    pandas/numpy 已從主流程移除（為了壓 exe 體積，原本 ~33MB → ~10MB），
    excludes 內顯式排除避免被 hook 拉進來

部署目錄結構（exe 同層）：
  risk_analysis.exe
  indicators_config.xlsx     ← 指標規則 + 敘事會科 + tag_table 三 sheet
  risk_user_prompt.txt
  narrative_user_prompt.txt

打包指令（在 repo root 執行）：
  pyinstaller build/risk_analysis.spec --distpath outputs/dist

產出：outputs/dist/risk_analysis(.exe)
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
        "utils.convert_indicators",
        "utils.html_to_json",
        "utils.narrative",
        "utils.simple_convert",
        "utils.xlsx_to_indicators",
        # xlsx 解析改用純 openpyxl（不再經過 pandas）
        "openpyxl",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 主流程不用，避免被巨大依賴拖累 exe 體積。
        # pandas/numpy 完全排除：xlsx_to_indicators 改純 openpyxl 後不再需要。
        "pandas",
        "numpy",
        "docx",
        "matplotlib",
        "scipy",
        "tkinter",
        # 補強：其他常見 PyInstaller 誤抓的重型依賴
        "PIL",
        "pytest",
        "IPython",
        "jupyter",
        # 這支 util 是 standalone CLI、會 import pandas，
        # 主流程不會經過它；排除以免被 graph analyzer 拉進來。
        "utils.xlsx_to_report_json",
        # Web 介面（web/ 套件與其相依）只供 risk-web 使用，
        # scripts/main.py 不會 import；顯式排除確保 web stack
        # 永遠不會被冷凍進 EXE。
        "web",
        "fastapi",
        "starlette",
        "uvicorn",
        "python_multipart",
        "anyio",
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
