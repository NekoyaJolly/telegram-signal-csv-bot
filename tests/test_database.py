from __future__ import annotations

import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from scripts.reset_db import build_reset_targets, delete_existing_paths, list_reset_paths
from src.config import AppConfig
from src.database import (
    DatabaseSchemaError,
    connect,
    init_db,
    save_parsed_signal,
    save_raw_message,
    save_rejected_message,
    update_copy_error,
    update_copy_success,
)
from src.models import ParsedSignalData, RawMessageInput


def test_raw_message_can_be_saved(tmp_path: Path) -> None:
    connection = _connection(tmp_path)

    result = save_raw_message(connection, _raw_message())

    assert result.inserted is True
    assert result.raw_message_id == 1


def test_duplicate_raw_message_is_not_saved_twice(tmp_path: Path) -> None:
    connection = _connection(tmp_path)

    first = save_raw_message(connection, _raw_message())
    second = save_raw_message(connection, _raw_message())
    count = connection.execute("SELECT COUNT(*) AS count FROM raw_messages").fetchone()["count"]

    assert first.raw_message_id == second.raw_message_id
    assert second.inserted is False
    assert count == 1


def test_parsed_signal_can_be_saved(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    raw_id = save_raw_message(connection, _raw_message()).raw_message_id

    parsed_id = save_parsed_signal(connection, raw_id, _parsed_signal())
    row = connection.execute(
        "SELECT side, entry_type, entry1, entry2, entry3, entry4, entry5 FROM parsed_signals WHERE id = ?",
        (parsed_id,),
    ).fetchone()

    assert row["side"] == "SELL"
    assert row["entry_type"] == "range"
    assert row["entry1"] == "4563"
    assert row["entry2"] == "4568"
    assert row["entry3"] is None
    assert row["entry4"] is None
    assert row["entry5"] is None


def test_rejected_message_can_be_saved(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    raw_id = save_raw_message(connection, _raw_message()).raw_message_id

    rejected_id = save_rejected_message(connection, raw_id, "Entry 行がありません")
    row = connection.execute("SELECT reason FROM rejected_messages WHERE id = ?", (rejected_id,)).fetchone()

    assert row["reason"] == "Entry 行がありません"


def test_copy_success_can_be_saved(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    raw_id = save_raw_message(connection, _raw_message()).raw_message_id

    update_copy_success(connection, raw_id)
    row = connection.execute("SELECT copied_to_log_channel, copy_error FROM raw_messages WHERE id = ?", (raw_id,)).fetchone()

    assert row["copied_to_log_channel"] == 1
    assert row["copy_error"] is None


def test_copy_error_can_be_saved(tmp_path: Path) -> None:
    connection = _connection(tmp_path)
    raw_id = save_raw_message(connection, _raw_message()).raw_message_id

    update_copy_error(connection, raw_id, "Forbidden")
    row = connection.execute("SELECT copied_to_log_channel, copy_error FROM raw_messages WHERE id = ?", (raw_id,)).fetchone()

    assert row["copied_to_log_channel"] == 0
    assert row["copy_error"] == "Forbidden"


def test_init_db_creates_entry_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"

    init_db(db_path)
    connection = connect(db_path)
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(parsed_signals)").fetchall()}

    assert {"entry1", "entry2", "entry3", "entry4", "entry5"}.issubset(columns)


def test_old_parsed_signals_schema_raises_clear_error(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"
    connection = sqlite3.connect(db_path)
    connection.execute(
        """
        CREATE TABLE parsed_signals (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          raw_message_id INTEGER NOT NULL,
          side TEXT NOT NULL,
          symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          entry_type TEXT NOT NULL,
          entry_min TEXT NOT NULL,
          entry_max TEXT NOT NULL,
          entry_raw TEXT NOT NULL,
          tp1 TEXT,
          tp2 TEXT,
          tp3 TEXT,
          tp4 TEXT,
          tp5 TEXT,
          sl TEXT NOT NULL,
          signal_time TEXT NOT NULL,
          signal_time_utc TEXT NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(DatabaseSchemaError) as error:
        init_db(db_path)

    assert "entry1" in str(error.value)
    assert "python -m scripts.reset_db" in str(error.value)


def test_reset_db_targets_are_built_from_config_paths(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"
    config = AppConfig(
        telegram_bot_token="",
        telegram_log_chat_id=None,
        signal_timezone=ZoneInfo("Asia/Tokyo"),
        sqlite_db_path=db_path,
        csv_output_path=tmp_path / "trade_signals.csv",
        rejected_csv_output_path=tmp_path / "rejected_signals.csv",
        log_dir=tmp_path / "logs",
    )

    targets = list_reset_paths(build_reset_targets(config))

    assert targets == [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        tmp_path / "trade_signals.csv",
        tmp_path / "rejected_signals.csv",
    ]


def test_reset_db_deletes_only_local_data_and_keeps_env(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"
    target_paths = [
        db_path,
        Path(f"{db_path}-wal"),
        Path(f"{db_path}-shm"),
        tmp_path / "trade_signals.csv",
        tmp_path / "rejected_signals.csv",
    ]
    env_path = tmp_path / ".env"
    for target_path in target_paths:
        target_path.write_text("delete me", encoding="utf-8")
    env_path.write_text("TELEGRAM_BOT_TOKEN=secret", encoding="utf-8")

    deleted_count = delete_existing_paths(target_paths)

    assert deleted_count == 5
    assert all(not target_path.exists() for target_path in target_paths)
    assert env_path.read_text(encoding="utf-8") == "TELEGRAM_BOT_TOKEN=secret"


def _connection(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "signals.sqlite3"
    init_db(db_path)
    return connect(db_path)


def _raw_message() -> RawMessageInput:
    return RawMessageInput(
        source="telegram",
        telegram_chat_id="123",
        telegram_message_id="456",
        received_at="2026-03-22T10:28:00Z",
        raw_text="SELL XAUUSD 1m",
        raw_update_json='{"ok": true}',
    )


def _parsed_signal() -> ParsedSignalData:
    return ParsedSignalData(
        side="SELL",
        symbol="XAUUSD",
        timeframe="1m",
        entry_type="range",
        entry_min="4563",
        entry_max="4568",
        entry_raw="4563 - 4568",
        entry1="4563",
        entry2="4568",
        entry3=None,
        entry4=None,
        entry5=None,
        tp1="4559",
        tp2="4551",
        tp3="4533",
        tp4=None,
        tp5=None,
        sl="4571",
        signal_time="2026-03-22T19:28:00+09:00",
        signal_time_utc="2026-03-22T10:28:00Z",
    )
