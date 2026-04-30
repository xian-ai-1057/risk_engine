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

from risk_engine.paths import get_base_dir


_DEFAULT_FMT = (
    "%(asctime)s [%(levelname)s]"
    " %(name)s - %(message)s"
)
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 標記由 setup_logging 加進 root logger 的 handlers，
# 重複呼叫時只移除自己加過的，不動到外部 handler。
_OWN_HANDLER_ATTR = "_risk_engine_owned"


def setup_logging(
    log_file: str | None = None,
    level: int = logging.INFO,
    request_id: str = "",
) -> None:
    """設定 root logger：console + 檔案。

    冪等：重複呼叫時只清除前次由本函數加入的 handler，
    不會清除外部（如 pytest caplog）已掛上的 handler。

    Args:
        log_file: log 檔路徑。未指定時預設寫入
            程式所在目錄的 log/ 子目錄。
        level: log 層級，預設 INFO。
        request_id: 本次執行的唯一識別碼，
            用於 log 檔名以區分並行呼叫。
    """
    root = logging.getLogger()

    # 只移除自己上次加過的 handler，保留外部 handler
    for h in list(root.handlers):
        if getattr(h, _OWN_HANDLER_ATTR, False):
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass

    if log_file is None:
        log_dir = os.path.join(get_base_dir(), "log")
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
    setattr(console, _OWN_HANDLER_ATTR, True)

    # File handler
    file_handler = logging.FileHandler(
        log_file, encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    setattr(file_handler, _OWN_HANDLER_ATTR, True)

    root.setLevel(level)
    root.addHandler(console)
    root.addHandler(file_handler)
