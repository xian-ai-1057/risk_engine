"""log_config 單元測試。

驗證冪等性與「不清除外部 handler」這兩個併發/library 安全要點。
"""
import logging
import os

import pytest

from risk_engine import log_config


def _own_handlers(root: logging.Logger) -> list:
    return [
        h for h in root.handlers
        if getattr(h, log_config._OWN_HANDLER_ATTR, False)
    ]


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """每個測試都還原 root logger 狀態。"""
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    yield
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass
    for h in saved_handlers:
        root.addHandler(h)
    root.setLevel(saved_level)


class TestSetupLoggingIdempotent:
    def test_repeated_calls_do_not_duplicate_own_handlers(
        self, tmp_path,
    ):
        log_file = tmp_path / "a.log"
        log_config.setup_logging(log_file=str(log_file))
        first = len(_own_handlers(logging.getLogger()))

        log_config.setup_logging(
            log_file=str(tmp_path / "b.log"),
        )
        second = len(_own_handlers(logging.getLogger()))

        assert first == second == 2  # console + file

    def test_external_handler_is_preserved(
        self, tmp_path,
    ):
        root = logging.getLogger()
        external = logging.NullHandler()
        root.addHandler(external)

        log_config.setup_logging(
            log_file=str(tmp_path / "c.log"),
        )

        assert external in root.handlers
        # 並且只多了 2 個自家 handler
        assert len(_own_handlers(root)) == 2

        # 再次呼叫 setup_logging，外部 handler 仍存在
        log_config.setup_logging(
            log_file=str(tmp_path / "d.log"),
        )
        assert external in root.handlers


class TestSetupLoggingDefaultPath:
    def test_default_log_dir_under_base_dir(
        self, tmp_path, monkeypatch,
    ):
        monkeypatch.setattr(
            "risk_engine.log_config.get_base_dir",
            lambda: str(tmp_path),
        )

        log_config.setup_logging(request_id="r1")

        log_dir = tmp_path / "log"
        assert log_dir.is_dir()
        # 至少一個含 r1 的 log 檔
        files = list(log_dir.glob("*r1*.log"))
        assert files, "expected r1-tagged log file"
