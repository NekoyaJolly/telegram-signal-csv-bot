from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from src.csv_exporter import regenerate_rejected_signals_csv, regenerate_trade_signals_csv
from src.database import connect, init_db, save_parsed_signal, save_raw_message, save_rejected_message
from src.models import ParsedSignalData, RawMessageInput


def test_trade_signals_csv_can_be_generated(tmp_path: Path) -> None:
    connection = _seed_parsed_signal(tmp_path)
    output_path = tmp_path / "trade_signals.csv"

    count = regenerate_trade_signals_csv(connection, output_path)
    rows = _read_csv(output_path)

    assert count == 1
    assert rows[0]["signal_id"] == "123_456"
    assert rows[0]["side"] == "SELL"


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


def test_csv_is_written_with_utf8_bom(tmp_path: Path) -> None:
    connection = _seed_parsed_signal(tmp_path)
    output_path = tmp_path / "trade_signals.csv"

    regenerate_trade_signals_csv(connection, output_path)

    assert output_path.read_bytes().startswith(b"\xef\xbb\xbf")


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


def _raw_message() -> RawMessageInput:
    return RawMessageInput(
        source="telegram",
        telegram_chat_id="123",
        telegram_message_id="456",
        received_at="2026-03-22T10:28:00Z",
        raw_text="SELL XAUUSD 1m\nEntry | 4563 - 4568",
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
        tp1="4559",
        tp2="4551",
        tp3="4533",
        tp4=None,
        tp5=None,
        sl="4571",
        signal_time="2026-03-22T19:28:00+09:00",
        signal_time_utc="2026-03-22T10:28:00Z",
    )
