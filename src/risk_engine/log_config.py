"""統一 logging 設定模組。

提供 setup_logging() 供 CLI 入口呼叫，
同時輸出至 console 與 log 檔案。

EXE 打包時 log 檔預設寫入 EXE 同層 log/ 子目錄，
以時間戳 + request_id 命名確保並行安全。
"""
import logging
import os
import sys
from datetime import datetime


_DEFAULT_FMT = (
    "%(asctime)s [%(levelname)s]"
    " %(name)s - %(message)s"
)
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _get_base_dir() -> str:
    """取得程式所在目錄（相容 EXE 打包）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.getcwd()


def setup_logging(
    log_file: str | None = None,
    level: int = logging.INFO,
    request_id: str = "",
) -> None:
    """設定 root logger：console + 檔案。

    Args:
        log_file: log 檔路徑。未指定時預設寫入
            程式所在目錄的 log/ 子目錄。
        level: log 層級，預設 INFO。
        request_id: 本次執行的唯一識別碼，
            用於 log 檔名以區分並行呼叫。
    """
    root = logging.getLogger()

    # 防止重複加入 handler
    if root.handlers:
        root.handlers.clear()

    if log_file is None:
        log_dir = os.path.join(_get_base_dir(), "log")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{request_id}" if request_id else ""
        log_file = os.path.join(
            log_dir, f"{ts}{suffix}.log",
        )

    formatter = logging.Formatter(
        _DEFAULT_FMT, datefmt=_DEFAULT_DATEFMT,
    )

    # Console handler
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    console.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(
        log_file, encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)
