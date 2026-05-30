from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.models import ParsedSignalData, RawMessageInput, RawMessageRecord, RawMessageSaveResult
from src.parser import SignalParseError, parse_signal


REQUIRED_PARSED_SIGNAL_COLUMNS = {
    "id",
    "raw_message_id",
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
    "created_at",
}


class DatabaseSchemaError(Exception):
    """既存SQLite DBのスキーマが現在のコードと一致しない場合の例外。"""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS raw_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT NOT NULL,
  telegram_chat_id TEXT NOT NULL,
  telegram_message_id TEXT NOT NULL,
  received_at TEXT NOT NULL,
  raw_text TEXT NOT NULL,
  raw_update_json TEXT,
  copied_to_log_channel INTEGER NOT NULL DEFAULT 0,
  copy_error TEXT,
  created_at TEXT NOT NULL,
  UNIQUE (telegram_chat_id, telegram_message_id)
);

CREATE TABLE IF NOT EXISTS parsed_signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_message_id INTEGER NOT NULL,
  side TEXT NOT NULL,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  entry_type TEXT NOT NULL,
  entry_min TEXT NOT NULL,
  entry_max TEXT NOT NULL,
  entry_raw TEXT NOT NULL,
  entry1 TEXT,
  entry2 TEXT,
  entry3 TEXT,
  entry4 TEXT,
  entry5 TEXT,
  tp1 TEXT,
  tp2 TEXT,
  tp3 TEXT,
  tp4 TEXT,
  tp5 TEXT,
  sl TEXT NOT NULL,
  signal_time TEXT NOT NULL,
  signal_time_utc TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (raw_message_id) REFERENCES raw_messages(id),
  UNIQUE (raw_message_id)
);

CREATE TABLE IF NOT EXISTS rejected_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_message_id INTEGER NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (raw_message_id) REFERENCES raw_messages(id),
  UNIQUE (raw_message_id)
);

CREATE TABLE IF NOT EXISTS export_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  export_type TEXT NOT NULL,
  output_path TEXT NOT NULL,
  exported_rows INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """SQLite 接続を作成し、アプリ共通の PRAGMA を必ず適用する。"""

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL;")
    connection.execute("PRAGMA busy_timeout=5000;")
    connection.execute("PRAGMA foreign_keys=ON;")
    return connection


def init_db(db_path: Path) -> None:
    """必要なテーブルを安全に作成する。"""

    with connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        validate_schema(connection, db_path)
        connection.commit()


def validate_schema(connection: sqlite3.Connection, db_path: Path) -> None:
    """古いSQLiteスキーマを早期検出し、復旧手順が分かるエラーにする。"""

    rows = connection.execute("PRAGMA table_info(parsed_signals)").fetchall()
    existing_columns = {str(row["name"]) for row in rows}
    missing_columns = sorted(REQUIRED_PARSED_SIGNAL_COLUMNS - existing_columns)
    if missing_columns:
        missing_text = ", ".join(missing_columns)
        raise DatabaseSchemaError(
            "SQLite DB の parsed_signals テーブルが古いスキーマです。"
            f"不足カラム: {missing_text}。"
            f"対象DB: {db_path}。"
            "初期開発段階のため、必要なデータを退避したうえで "
            "`python -m scripts.reset_db` と `python -m scripts.init_db` を実行してください。"
        )


def utc_now_iso() -> str:
    """SQLite に保存する UTC 現在時刻を ISO 8601 で返す。"""

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def save_raw_message(connection: sqlite3.Connection, message: RawMessageInput) -> RawMessageSaveResult:
    """raw_messages へ保存し、重複時は既存 id を返す。"""

    created_at = utc_now_iso()
    cursor = connection.execute(
        """
        INSERT OR IGNORE INTO raw_messages (
          source, telegram_chat_id, telegram_message_id, received_at, raw_text, raw_update_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message.source,
            message.telegram_chat_id,
            message.telegram_message_id,
            message.received_at,
            message.raw_text,
            message.raw_update_json,
            created_at,
        ),
    )
    inserted = cursor.rowcount == 1
    row = connection.execute(
        """
        SELECT id FROM raw_messages
        WHERE telegram_chat_id = ? AND telegram_message_id = ?
        """,
        (message.telegram_chat_id, message.telegram_message_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("raw_messages の保存結果を取得できませんでした")
    connection.commit()
    return RawMessageSaveResult(raw_message_id=int(row["id"]), inserted=inserted)


def update_copy_success(connection: sqlite3.Connection, raw_message_id: int) -> None:
    """copyMessage 成功状態を raw_messages に反映する。"""

    connection.execute(
        """
        UPDATE raw_messages
        SET copied_to_log_channel = 1, copy_error = NULL
        WHERE id = ?
        """,
        (raw_message_id,),
    )
    connection.commit()


def update_copy_error(connection: sqlite3.Connection, raw_message_id: int, copy_error: str) -> None:
    """copyMessage 失敗理由を保存して後続処理を継続可能にする。"""

    connection.execute(
        """
        UPDATE raw_messages
        SET copied_to_log_channel = 0, copy_error = ?
        WHERE id = ?
        """,
        (copy_error, raw_message_id),
    )
    connection.commit()


def save_parsed_signal(
    connection: sqlite3.Connection, raw_message_id: int, signal: ParsedSignalData
) -> int:
    """parsed_signals へ正規化済みシグナルを保存する。"""

    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT OR IGNORE INTO parsed_signals (
          raw_message_id, side, symbol, timeframe, entry_type, entry_min, entry_max, entry_raw,
          entry1, entry2, entry3, entry4, entry5,
          tp1, tp2, tp3, tp4, tp5, sl, signal_time, signal_time_utc, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_message_id,
            signal.side,
            signal.symbol,
            signal.timeframe,
            signal.entry_type,
            signal.entry_min,
            signal.entry_max,
            signal.entry_raw,
            signal.entry1,
            signal.entry2,
            signal.entry3,
            signal.entry4,
            signal.entry5,
            signal.tp1,
            signal.tp2,
            signal.tp3,
            signal.tp4,
            signal.tp5,
            signal.sl,
            signal.signal_time,
            signal.signal_time_utc,
            created_at,
        ),
    )
    row = connection.execute(
        "SELECT id FROM parsed_signals WHERE raw_message_id = ?", (raw_message_id,)
    ).fetchone()
    if row is None:
        raise RuntimeError("parsed_signals の保存結果を取得できませんでした")
    connection.commit()
    return int(row["id"])


def save_rejected_message(connection: sqlite3.Connection, raw_message_id: int, reason: str) -> int:
    """rejected_messages へパース失敗理由を保存する。"""

    created_at = utc_now_iso()
    connection.execute(
        """
        INSERT OR IGNORE INTO rejected_messages (raw_message_id, reason, created_at)
        VALUES (?, ?, ?)
        """,
        (raw_message_id, reason, created_at),
    )
    row = connection.execute(
        "SELECT id FROM rejected_messages WHERE raw_message_id = ?", (raw_message_id,)
    ).fetchone()
    if row is None:
        raise RuntimeError("rejected_messages の保存結果を取得できませんでした")
    connection.commit()
    return int(row["id"])


def has_processed_result(connection: sqlite3.Connection, raw_message_id: int) -> bool:
    """raw message が成功または失敗として処理済みか確認する。"""

    row = connection.execute(
        """
        SELECT 1 FROM parsed_signals WHERE raw_message_id = ?
        UNION
        SELECT 1 FROM rejected_messages WHERE raw_message_id = ?
        LIMIT 1
        """,
        (raw_message_id, raw_message_id),
    ).fetchone()
    return row is not None


def fetch_unprocessed_raw_messages(connection: sqlite3.Connection) -> list[RawMessageRecord]:
    """raw のみ保存済みで、成功・失敗の処理結果がないメッセージを返す。"""

    rows = connection.execute(
        """
        SELECT raw.id, raw.source, raw.telegram_chat_id, raw.telegram_message_id, raw.received_at, raw.raw_text
        FROM raw_messages AS raw
        LEFT JOIN parsed_signals AS parsed ON parsed.raw_message_id = raw.id
        LEFT JOIN rejected_messages AS rejected ON rejected.raw_message_id = raw.id
        WHERE parsed.id IS NULL AND rejected.id IS NULL
        ORDER BY raw.id
        """
    ).fetchall()
    return [
        RawMessageRecord(
            id=int(row["id"]),
            source=str(row["source"]),
            telegram_chat_id=str(row["telegram_chat_id"]),
            telegram_message_id=str(row["telegram_message_id"]),
            received_at=str(row["received_at"]),
            raw_text=str(row["raw_text"]),
        )
        for row in rows
    ]


def reprocess_unprocessed_messages(connection: sqlite3.Connection, signal_timezone: ZoneInfo) -> tuple[int, int]:
    """raw のみ残ったメッセージを再パースし、成功数と失敗数を返す。"""

    parsed_count = 0
    rejected_count = 0
    for raw_message in fetch_unprocessed_raw_messages(connection):
        try:
            signal = parse_signal(raw_message.raw_text, signal_timezone)
            save_parsed_signal(connection, raw_message.id, signal)
            parsed_count += 1
        except SignalParseError as error:
            save_rejected_message(connection, raw_message.id, str(error))
            rejected_count += 1
    return parsed_count, rejected_count


def fetch_parsed_signal_export_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """trade_signals.csv の生成に必要な結合済み行を取得する。"""

    return connection.execute(
        """
        SELECT
          parsed.id AS parsed_id,
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
        ORDER BY parsed.id
        """
    ).fetchall()


def fetch_rejected_export_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """rejected_signals.csv の生成に必要な結合済み行を取得する。"""

    return connection.execute(
        """
        SELECT
          raw.source,
          raw.telegram_chat_id,
          raw.telegram_message_id,
          raw.received_at,
          rejected.reason,
          raw.raw_text
        FROM rejected_messages AS rejected
        JOIN raw_messages AS raw ON raw.id = rejected.raw_message_id
        ORDER BY rejected.id
        """
    ).fetchall()


def record_export_log(
    connection: sqlite3.Connection, export_type: str, output_path: Path, exported_rows: int
) -> None:
    """CSV 全再生成の履歴を export_logs に保存する。"""

    connection.execute(
        """
        INSERT INTO export_logs (export_type, output_path, exported_rows, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (export_type, str(output_path), exported_rows, utc_now_iso()),
    )
    connection.commit()
