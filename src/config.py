from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


@dataclass(frozen=True)
class AppConfig:
    """環境変数から読み込んだアプリケーション設定。"""

    telegram_bot_token: str
    telegram_log_chat_id: str | None
    signal_timezone: ZoneInfo
    sqlite_db_path: Path
    csv_output_path: Path
    rejected_csv_output_path: Path
    log_dir: Path


class ConfigError(Exception):
    """環境変数や設定値が不正な場合に送出する例外。"""


def load_config(require_bot_token: bool) -> AppConfig:
    """`.env` と環境変数からアプリ設定を読み込む。"""

    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if require_bot_token and not token:
        raise ConfigError("TELEGRAM_BOT_TOKEN が設定されていません")

    timezone_name = os.getenv("SIGNAL_TIMEZONE", "Asia/Tokyo").strip() or "Asia/Tokyo"
    try:
        signal_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ConfigError(f"SIGNAL_TIMEZONE が不正です: {timezone_name}") from error

    log_chat_id = os.getenv("TELEGRAM_LOG_CHAT_ID", "").strip() or None

    return AppConfig(
        telegram_bot_token=token,
        telegram_log_chat_id=log_chat_id,
        signal_timezone=signal_timezone,
        sqlite_db_path=Path(os.getenv("SQLITE_DB_PATH", "./data/signals.sqlite3")),
        csv_output_path=Path(os.getenv("CSV_OUTPUT_PATH", "./output/trade_signals.csv")),
        rejected_csv_output_path=Path(
            os.getenv("REJECTED_CSV_OUTPUT_PATH", "./output/rejected_signals.csv")
        ),
        log_dir=Path(os.getenv("LOG_DIR", "./logs")),
    )
