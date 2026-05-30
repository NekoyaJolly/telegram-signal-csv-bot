from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from src.config import AppConfig, load_config
from src.csv_exporter import append_parsed_signal_row, append_rejected_signal_row
from src.database import (
    connect,
    init_db,
    save_parsed_signal,
    save_raw_message,
    save_rejected_message,
    utc_now_iso,
)
from src.models import RawMessageInput
from src.parser import SignalParseError, parse_signal


@dataclass(frozen=True)
class ManualProcessResult:
    """手動投入メッセージの処理結果。"""

    raw_message_id: int
    status: str
    detail: str


def main() -> None:
    """標準入力または引数の本文をTelegramなしでDB/CSVへ処理する。"""

    args = parse_args()
    raw_text = read_raw_text(args.message)
    if not raw_text.strip():
        raise SystemExit("処理する本文が空です。標準入力または引数で本文を渡してください。")

    config = load_config(require_bot_token=False)
    init_db(config.sqlite_db_path)
    result = process_manual_message(
        config=config,
        raw_text=raw_text,
        telegram_message_id=args.message_id,
    )
    print(f"{result.status}: raw_message_id={result.raw_message_id} {result.detail}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="サンプル本文をTelegramなしでDB/CSVへ処理します")
    parser.add_argument("message", nargs="?", help="処理する本文。省略時は標準入力から読み込みます")
    parser.add_argument(
        "--message-id",
        default=f"manual-{utc_now_iso()}",
        help="manual投入用のtelegram_message_id相当の値です",
    )
    return parser.parse_args()


def read_raw_text(message: str | None) -> str:
    if message is not None:
        return message
    return sys.stdin.read()


def process_manual_message(
    config: AppConfig,
    raw_text: str,
    telegram_message_id: str,
) -> ManualProcessResult:
    """Telegram APIへ接続せず、本文をraw保存からCSV出力まで通す。"""

    with connect(config.sqlite_db_path) as connection:
        raw_result = save_raw_message(
            connection,
            RawMessageInput(
                source="manual",
                telegram_chat_id="manual",
                telegram_message_id=telegram_message_id,
                received_at=utc_now_iso(),
                raw_text=raw_text,
                raw_update_json=None,
            ),
        )
        try:
            signal = parse_signal(raw_text, config.signal_timezone)
        except SignalParseError as error:
            save_rejected_message(connection, raw_result.raw_message_id, str(error))
            append_rejected_signal_row(
                connection,
                config.rejected_csv_output_path,
                raw_result.raw_message_id,
            )
            return ManualProcessResult(
                raw_message_id=raw_result.raw_message_id,
                status="rejected",
                detail=str(error),
            )

        save_parsed_signal(connection, raw_result.raw_message_id, signal)
        append_parsed_signal_row(connection, config.csv_output_path, raw_result.raw_message_id)
        return ManualProcessResult(
            raw_message_id=raw_result.raw_message_id,
            status="parsed",
            detail=signal.entry_type,
        )


if __name__ == "__main__":
    main()
