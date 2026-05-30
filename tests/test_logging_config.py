from __future__ import annotations

import logging
from pathlib import Path

from src.logging_config import TelegramTokenRedactionFilter, setup_logging


def test_telegram_token_is_redacted_from_httpx_log_message() -> None:
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: POST %s",
        args=("https://api.telegram.org/bot123456:SECRET/copyMessage",),
        exc_info=None,
    )

    assert TelegramTokenRedactionFilter().filter(record) is True
    message = record.getMessage()

    assert "123456:SECRET" not in message
    assert "https://api.telegram.org/bot<redacted>/copyMessage" in message


def test_external_http_loggers_are_warning_or_higher(tmp_path: Path) -> None:
    setup_logging(tmp_path)

    assert logging.getLogger().level == logging.INFO
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("telegram").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("telegram.ext").getEffectiveLevel() >= logging.WARNING
