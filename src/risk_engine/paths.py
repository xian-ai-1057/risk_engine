"""路徑解析模組。

集中提供 frozen-aware 的 base directory 解析，
供 log_config、scripts/main.py 等共用，避免重複實作。
"""
import os
import sys


def get_base_dir() -> str:
    """取得程式所在目錄。

    PyInstaller 打包後（``sys.frozen``）回傳 EXE 所在目錄；
    一般執行時回傳此模組所在的 repo root（``src/`` 的上一層）。

    Returns:
        程式或 EXE 所在目錄的絕對路徑。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # 此檔位於 src/risk_engine/paths.py，repo root 為其上兩層
    return os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)),
        ),
    )
