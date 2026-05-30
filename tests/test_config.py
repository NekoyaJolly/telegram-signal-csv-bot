from __future__ import annotations

from pathlib import Path

import pytest

from src.config import load_config


def test_load_config_prefers_env_file_over_empty_process_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_LOG_CHAT_ID", "")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TELEGRAM_BOT_TOKEN=",
                "TELEGRAM_LOG_CHAT_ID=-5020668206",
                "SIGNAL_TIMEZONE=Asia/Tokyo",
                "SQLITE_DB_PATH=./data/signals.sqlite3",
                "CSV_OUTPUT_PATH=./output/trade_signals.csv",
                "REJECTED_CSV_OUTPUT_PATH=./output/rejected_signals.csv",
                "LOG_DIR=./logs",
            ]
        ),
        encoding="utf-8",
    )

    config = load_config(require_bot_token=False)

    assert config.telegram_log_chat_id == "-5020668206"
