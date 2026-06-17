from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

from telegram import Message, Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from src.config import AppConfig
from src.csv_exporter import append_parsed_signal_row, append_rejected_signal_row
from src.database import (
    has_processed_result,
    save_parsed_signal,
    save_raw_message,
    save_rejected_message,
    update_copy_error,
    update_copy_success,
)
from src.models import RawMessageInput, SignalBlockResult
from src.parser import parse_signal_blocks


logger = logging.getLogger(__name__)


def build_application(config: AppConfig, connection: sqlite3.Connection) -> Application:
    """Telegram polling アプリケーションを組み立てる。"""

    application = ApplicationBuilder().token(config.telegram_bot_token).build()
    application.bot_data["config"] = config
    application.bot_data["connection"] = connection
    application.add_handler(CommandHandler("start", _handle_start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text_message))
    return application


async def _handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message is not None:
        await update.effective_message.reply_text("Telegram Signal CSV Bot は起動しています。")


async def _handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if message is None or message.text is None:
        return

    config = _get_config(context)
    connection = _get_connection(context)
    raw_input = _build_raw_message_input(update, message)
    save_result = save_raw_message(connection, raw_input)
    logger.info("Telegram受信 chat_id=%s message_id=%s", raw_input.telegram_chat_id, raw_input.telegram_message_id)

    if not save_result.inserted and has_processed_result(connection, save_result.raw_message_id):
        await message.reply_text("このメッセージは処理済みです。")
        return

    await _copy_to_log_channel(config, context, message, save_result.raw_message_id)
    await _parse_store_and_export(config, connection, message, save_result.raw_message_id, raw_input.raw_text)


async def _copy_to_log_channel(
    config: AppConfig, context: ContextTypes.DEFAULT_TYPE, message: Message, raw_message_id: int
) -> None:
    if config.telegram_log_chat_id is None:
        logger.info("copyMessageスキップ raw_message_id=%s reason=TELEGRAM_LOG_CHAT_ID未設定", raw_message_id)
        return
    try:
        await context.bot.copy_message(
            chat_id=config.telegram_log_chat_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )
        update_copy_success(_get_connection(context), raw_message_id)
        logger.info("copyMessage成功 raw_message_id=%s", raw_message_id)
    except Exception as error:
        copy_error = str(error)
        update_copy_error(_get_connection(context), raw_message_id, copy_error)
        logger.exception("copyMessage失敗 raw_message_id=%s", raw_message_id)


async def _parse_store_and_export(
    config: AppConfig,
    connection: sqlite3.Connection,
    message: Message,
    raw_message_id: int,
    raw_text: str,
) -> None:
    # 1メッセージに複数シグナルが連結されることがあるため、ブロック単位で成功/失敗を切り分けて保存する
    results = parse_signal_blocks(raw_text, config.signal_timezone)
    parsed_results = [result for result in results if result.signal is not None]
    rejected_results = [result for result in results if result.signal is None]

    for result in results:
        if result.signal is not None:
            save_parsed_signal(connection, raw_message_id, result.block_index, result.signal)
        elif result.error is not None:
            save_rejected_message(connection, raw_message_id, result.block_index, result.error)
    logger.info(
        "パース完了 raw_message_id=%s parsed=%s rejected=%s",
        raw_message_id,
        len(parsed_results),
        len(rejected_results),
    )

    if parsed_results:
        try:
            append_parsed_signal_row(connection, config.csv_output_path, raw_message_id)
            logger.info("CSV出力成功 raw_message_id=%s path=%s", raw_message_id, config.csv_output_path)
        except Exception:
            logger.exception("CSV出力失敗 raw_message_id=%s", raw_message_id)
    if rejected_results:
        try:
            append_rejected_signal_row(connection, config.rejected_csv_output_path, raw_message_id)
            logger.info("rejected CSV出力成功 raw_message_id=%s", raw_message_id)
        except Exception:
            logger.exception("rejected CSV出力失敗 raw_message_id=%s", raw_message_id)

    await message.reply_text(_build_reply_text(parsed_results, rejected_results))


def _build_reply_text(
    parsed_results: list[SignalBlockResult], rejected_results: list[SignalBlockResult]
) -> str:
    """成功/失敗ブロック数に応じて、利用者向けの返信文面を組み立てる。"""

    parsed_count = len(parsed_results)
    rejected_count = len(rejected_results)
    if parsed_count and not rejected_count:
        if parsed_count == 1:
            return "シグナルを保存しました。"
        return f"シグナルを{parsed_count}件保存しました。"
    if rejected_count and not parsed_count:
        if rejected_count == 1:
            return f"シグナルを rejected として保存しました: {rejected_results[0].error}"
        return f"{rejected_count}件すべてを rejected として保存しました。"
    reasons = "; ".join(sorted({result.error for result in rejected_results if result.error}))
    return f"シグナルを{parsed_count}件保存し、{rejected_count}件を rejected として保存しました: {reasons}"


def _build_raw_message_input(update: Update, message: Message) -> RawMessageInput:
    received_at = _message_time_to_iso(message)
    return RawMessageInput(
        source="telegram",
        telegram_chat_id=str(message.chat_id),
        telegram_message_id=str(message.message_id),
        received_at=received_at,
        raw_text=message.text or "",
        raw_update_json=update.to_json(),
    )


def _message_time_to_iso(message: Message) -> str:
    if message.date is None:
        return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return message.date.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _get_config(context: ContextTypes.DEFAULT_TYPE) -> AppConfig:
    config = context.application.bot_data["config"]
    if not isinstance(config, AppConfig):
        raise RuntimeError("AppConfig が初期化されていません")
    return config


def _get_connection(context: ContextTypes.DEFAULT_TYPE) -> sqlite3.Connection:
    connection = context.application.bot_data["connection"]
    if not isinstance(connection, sqlite3.Connection):
        raise RuntimeError("SQLite connection が初期化されていません")
    return connection
