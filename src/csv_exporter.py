from __future__ import annotations

import csv
import sqlite3
from collections import Counter
from pathlib import Path

from src.database import (
    fetch_parsed_signal_export_rows,
    fetch_rejected_export_rows,
    record_export_log,
)


TRADE_SIGNAL_COLUMNS = [
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

REJECTED_SIGNAL_COLUMNS = [
    "signal_id",
    "source",
    "telegram_chat_id",
    "telegram_message_id",
    "received_at",
    "reason",
    "raw_text",
]


def append_parsed_signal_row(connection: sqlite3.Connection, output_path: Path, raw_message_id: int) -> None:
    """受信ごとに、その raw message に属する parsed_signals 全行を CSV へ追記する。

    1 メッセージに複数シグナルが含まれる場合、ブロック順に複数行を追記する。
    """

    rows = connection.execute(
        """
        SELECT
          parsed.id AS parsed_id,
          parsed.block_index AS block_index,
          raw.source,
          raw.telegram_chat_id,
          raw.telegram_message_id,
          parsed.side,
          parsed.symbol,
          parsed.timeframe,
          parsed.entry_type,
          parsed.entry_min,
          parsed.entry_max,
          parsed.entry_raw,
          parsed.entry1,
          parsed.entry2,
          parsed.entry3,
          parsed.entry4,
          parsed.entry5,
          parsed.tp1,
          parsed.tp2,
          parsed.tp3,
          parsed.tp4,
          parsed.tp5,
          parsed.sl,
          parsed.signal_time,
          parsed.signal_time_utc,
          raw.received_at,
          raw.raw_text
        FROM parsed_signals AS parsed
        JOIN raw_messages AS raw ON raw.id = parsed.raw_message_id
        WHERE raw.id = ?
        ORDER BY parsed.block_index
        """,
        (raw_message_id,),
    ).fetchall()
    if not rows:
        raise RuntimeError("CSV 追記対象の parsed_signals が見つかりません")
    # block_count は同一メッセージ内の保存済みシグナル数。複数のときだけ signal_id に block_index を付与する
    block_count = len(rows)
    for row in rows:
        _append_row(output_path, TRADE_SIGNAL_COLUMNS, _trade_row_to_dict(row, block_count))


def append_rejected_signal_row(connection: sqlite3.Connection, output_path: Path, raw_message_id: int) -> None:
    """受信ごとに、その raw message に属する rejected_messages 全行を CSV へ追記する。"""

    rows = connection.execute(
        """
        SELECT
          rejected.block_index AS block_index,
          raw.source,
          raw.telegram_chat_id,
          raw.telegram_message_id,
          raw.received_at,
          rejected.reason,
          raw.raw_text
        FROM rejected_messages AS rejected
        JOIN raw_messages AS raw ON raw.id = rejected.raw_message_id
        WHERE raw.id = ?
        ORDER BY rejected.block_index
        """,
        (raw_message_id,),
    ).fetchall()
    if not rows:
        raise RuntimeError("CSV 追記対象の rejected_messages が見つかりません")
    block_count = len(rows)
    for row in rows:
        _append_row(output_path, REJECTED_SIGNAL_COLUMNS, _rejected_row_to_dict(row, block_count))


def regenerate_trade_signals_csv(connection: sqlite3.Connection, output_path: Path) -> int:
    """SQLite の parsed_signals から trade_signals.csv を全再生成する。"""

    fetched = fetch_parsed_signal_export_rows(connection)
    block_counts = Counter(row["raw_message_id"] for row in fetched)
    rows = [_trade_row_to_dict(row, block_counts[row["raw_message_id"]]) for row in fetched]
    _write_rows(output_path, TRADE_SIGNAL_COLUMNS, rows)
    record_export_log(connection, "trade_signals", output_path, len(rows))
    return len(rows)


def regenerate_rejected_signals_csv(connection: sqlite3.Connection, output_path: Path) -> int:
    """SQLite の rejected_messages から rejected_signals.csv を全再生成する。"""

    fetched = fetch_rejected_export_rows(connection)
    block_counts = Counter(row["raw_message_id"] for row in fetched)
    rows = [_rejected_row_to_dict(row, block_counts[row["raw_message_id"]]) for row in fetched]
    _write_rows(output_path, REJECTED_SIGNAL_COLUMNS, rows)
    record_export_log(connection, "rejected_signals", output_path, len(rows))
    return len(rows)


def _append_row(output_path: Path, columns: list[str], row: dict[str, str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    should_write_header = not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open("a", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        if should_write_header:
            writer.writeheader()
        writer.writerow(row)


def _write_rows(output_path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _build_signal_id(chat_id: str, message_id: str, block_index: object, block_count: int) -> str:
    """CSV 用の signal_id を組み立てる。

    1 メッセージ 1 シグナルなら従来どおり `{chat}_{message}`。複数シグナルが含まれる場合のみ
    末尾に block_index (1始まり) を付与して `{chat}_{message}_{n}` とし、行の一意性を保つ。
    """

    base = f"{chat_id}_{message_id}"
    if block_count <= 1:
        return base
    return f"{base}_{_cell_to_text(block_index)}"


def _trade_row_to_dict(row: sqlite3.Row, block_count: int) -> dict[str, str]:
    chat_id = _cell_to_text(row["telegram_chat_id"])
    message_id = _cell_to_text(row["telegram_message_id"])
    return {
        "signal_id": _build_signal_id(chat_id, message_id, row["block_index"], block_count),
        "source": _cell_to_text(row["source"]),
        "telegram_chat_id": chat_id,
        "telegram_message_id": message_id,
        "side": _cell_to_text(row["side"]),
        "symbol": _cell_to_text(row["symbol"]),
        "timeframe": _cell_to_text(row["timeframe"]),
        "entry_type": _cell_to_text(row["entry_type"]),
        "entry_min": _cell_to_text(row["entry_min"]),
        "entry_max": _cell_to_text(row["entry_max"]),
        "entry_raw": _cell_to_text(row["entry_raw"]),
        "entry1": _cell_to_text(row["entry1"]),
        "entry2": _cell_to_text(row["entry2"]),
        "entry3": _cell_to_text(row["entry3"]),
        "entry4": _cell_to_text(row["entry4"]),
        "entry5": _cell_to_text(row["entry5"]),
        "tp1": _cell_to_text(row["tp1"]),
        "tp2": _cell_to_text(row["tp2"]),
        "tp3": _cell_to_text(row["tp3"]),
        "tp4": _cell_to_text(row["tp4"]),
        "tp5": _cell_to_text(row["tp5"]),
        "sl": _cell_to_text(row["sl"]),
        "signal_time": _cell_to_text(row["signal_time"]),
        "signal_time_utc": _cell_to_text(row["signal_time_utc"]),
        "received_at": _cell_to_text(row["received_at"]),
        "raw_text": _normalize_raw_text(_cell_to_text(row["raw_text"])),
    }


def _rejected_row_to_dict(row: sqlite3.Row, block_count: int) -> dict[str, str]:
    chat_id = _cell_to_text(row["telegram_chat_id"])
    message_id = _cell_to_text(row["telegram_message_id"])
    return {
        "signal_id": _build_signal_id(chat_id, message_id, row["block_index"], block_count),
        "source": _cell_to_text(row["source"]),
        "telegram_chat_id": chat_id,
        "telegram_message_id": message_id,
        "received_at": _cell_to_text(row["received_at"]),
        "reason": _cell_to_text(row["reason"]),
        "raw_text": _normalize_raw_text(_cell_to_text(row["raw_text"])),
    }


def _cell_to_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _normalize_raw_text(raw_text: str) -> str:
    return raw_text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
