from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config import AppConfig
from src.csv_exporter import regenerate_rejected_signals_csv, regenerate_trade_signals_csv
from src.database import (
    connect,
    init_db,
    reprocess_unprocessed_messages,
    save_parsed_signal,
    save_raw_message,
    save_rejected_message,
)
from src.main import regenerate_csv_after_reprocess
from src.models import ParsedSignalData, RawMessageInput
from scripts.process_sample_message import process_manual_message


EXPECTED_TRADE_COLUMNS = [
    "signal_id",
    "source",
    "telegram_chat_id",
    "telegram_message_id",
    "side",
    "symbol",
    "timeframe",
    "entry_type",
    "entry_min",
    "entry_max",
    "entry_raw",
    "entry1",
    "entry2",
    "entry3",
    "entry4",
    "entry5",
    "tp1",
    "tp2",
    "tp3",
    "tp4",
    "tp5",
    "sl",
    "signal_time",
    "signal_time_utc",
    "received_at",
    "raw_text",
]


def test_trade_signals_csv_can_be_generated(tmp_path: Path) -> None:
    connection = _seed_parsed_signal(tmp_path)
    output_path = tmp_path / "trade_signals.csv"

    count = regenerate_trade_signals_csv(connection, output_path)
    rows = _read_csv(output_path)

    assert count == 1
    assert rows[0]["signal_id"] == "123_456"
    assert rows[0]["side"] == "SELL"
    assert list(rows[0].keys()) == EXPECTED_TRADE_COLUMNS


def test_rejected_signals_csv_can_be_generated(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    raw_id = save_raw_message(connection, _raw_message()).raw_message_id
    save_rejected_message(connection, raw_id, "Entry 行がありません")
    output_path = tmp_path / "rejected_signals.csv"

    count = regenerate_rejected_signals_csv(connection, output_path)
    rows = _read_csv(output_path)

    assert count == 1
    assert rows[0]["reason"] == "Entry 行がありません"


def test_raw_text_newlines_are_written_as_backslash_n(tmp_path: Path) -> None:
    connection = _seed_parsed_signal(tmp_path)
    output_path = tmp_path / "trade_signals.csv"

    regenerate_trade_signals_csv(connection, output_path)
    rows = _read_csv(output_path)

    assert rows[0]["raw_text"] == "SELL XAUUSD 1m\\nEntry | 4563 - 4568"


def test_entry_columns_are_exported(tmp_path: Path) -> None:
    connection = _seed_parsed_signal(tmp_path)
    output_path = tmp_path / "trade_signals.csv"

    regenerate_trade_signals_csv(connection, output_path)
    rows = _read_csv(output_path)

    assert rows[0]["entry_type"] == "range"
    assert rows[0]["entry_min"] == "4563"
    assert rows[0]["entry_max"] == "4568"
    assert rows[0]["entry_raw"] == "4563 - 4568"
    assert rows[0]["entry1"] == "4563"
    assert rows[0]["entry2"] == "4568"
    assert rows[0]["entry3"] == ""
    assert rows[0]["entry4"] == ""
    assert rows[0]["entry5"] == ""


def test_csv_is_written_with_utf8_bom(tmp_path: Path) -> None:
    connection = _seed_parsed_signal(tmp_path)
    output_path = tmp_path / "trade_signals.csv"

    regenerate_trade_signals_csv(connection, output_path)

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")


def test_csv_is_regenerated_after_startup_reprocess(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    save_raw_message(connection, _raw_message(raw_text=_valid_raw_text(), message_id="456"))
    save_raw_message(connection, _raw_message(raw_text="SELL XAUUSD 1m", message_id="457"))
    config = AppConfig(
        telegram_bot_token="",
        telegram_log_chat_id=None,
        signal_timezone=ZoneInfo("Asia/Tokyo"),
        sqlite_db_path=db_path,
        csv_output_path=tmp_path / "trade_signals.csv",
        rejected_csv_output_path=tmp_path / "rejected_signals.csv",
        log_dir=tmp_path / "logs",
    )

    parsed_count, rejected_count = reprocess_unprocessed_messages(connection, config.signal_timezone)
    regenerate_csv_after_reprocess(connection, config, parsed_count, rejected_count)

    trade_rows = _read_csv(config.csv_output_path)
    rejected_rows = _read_csv(config.rejected_csv_output_path)
    assert parsed_count == 1
    assert rejected_count == 1
    assert trade_rows[0]["signal_id"] == "123_456"
    assert rejected_rows[0]["signal_id"] == "123_457"


def test_process_sample_message_rejects_six_entry_points(tmp_path: Path) -> None:
    db_path = tmp_path / "signals.sqlite3"
    init_db(db_path)
    config = AppConfig(
        telegram_bot_token="",
        telegram_log_chat_id=None,
        signal_timezone=ZoneInfo("Asia/Tokyo"),
        sqlite_db_path=db_path,
        csv_output_path=tmp_path / "trade_signals.csv",
        rejected_csv_output_path=tmp_path / "rejected_signals.csv",
        log_dir=tmp_path / "logs",
    )

    result = process_manual_message(
        config=config,
        raw_text=_six_entry_raw_text(),
        telegram_message_id="manual-six-entry",
    )
    connection = connect(db_path)
    parsed_count = connection.execute("SELECT COUNT(*) AS count FROM parsed_signals").fetchone()["count"]
    rejected_row = connection.execute("SELECT reason FROM rejected_messages").fetchone()
    rejected_rows = _read_csv(config.rejected_csv_output_path)

    assert result.status == "rejected"
    assert parsed_count == 0
    assert rejected_row["reason"] == "Entry は最大5点までです"
    assert rejected_rows[0]["signal_id"] == "manual_manual-six-entry"


def _seed_parsed_signal(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "signals.sqlite3"
    init_db(db_path)
    connection = connect(db_path)
    raw_id = save_raw_message(connection, _raw_message()).raw_message_id
    save_parsed_signal(connection, raw_id, _parsed_signal())
    return connection


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _raw_message(
    raw_text: str = "SELL XAUUSD 1m\nEntry | 4563 - 4568", message_id: str = "456"
) -> RawMessageInput:
    return RawMessageInput(
        source="telegram",
        telegram_chat_id="123",
        telegram_message_id=message_id,
        received_at="2026-03-22T10:28:00Z",
        raw_text=raw_text,
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


def _valid_raw_text() -> str:
    return """SELL XAUUSD 1m

Entry | 4563 - 4568

TP | 4559 - 4551 - 4533
SL | 4571

2026-03-22-19:28
"""


def _six_entry_raw_text() -> str:
    return """SELL XAUUSD 1m

Entry | 4563 - 4568 - 4570 - 4575 - 4580 - 4590

TP | 4559 - 4551 - 4533
SL | 4571

2026-03-22-19:28
"""
