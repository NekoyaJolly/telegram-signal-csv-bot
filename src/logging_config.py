from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


TOKEN_URL_PATTERN = re.compile(r"(https://api\.telegram\.org/bot)[^/\s]+")


class TelegramTokenRedactionFilter(logging.Filter):
    """Telegram Bot Token がログメッセージへ混入した場合に伏せる。"""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted_message = TOKEN_URL_PATTERN.sub(r"\1<redacted>", message)
        if redacted_message != message:
            record.msg = redacted_message
            record.args = ()
        return True


def setup_logging(log_dir: Path) -> None:
    """秘密情報を含めず、ファイルと標準出力へアプリログを出す。"""

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TelegramTokenRedactionFilter())

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(TelegramTokenRedactionFilter())

    logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler], force=True)
    configure_external_log_levels()


def configure_external_log_levels() -> None:
    """外部HTTP系ログはToken露出を避けるためWARNING以上に抑える。"""

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.WARNING)
