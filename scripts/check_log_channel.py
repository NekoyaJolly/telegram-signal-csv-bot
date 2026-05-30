from __future__ import annotations

import asyncio
import os
import re

from dotenv import load_dotenv
from telegram import Bot
from telegram.error import BadRequest, Forbidden, TelegramError

from src.config import ConfigError, load_config


CHAT_ID_PATTERN = re.compile(r"^-?\d+$")


def main() -> None:
    """Telegramログチャンネルの参照と投稿権限を確認する。"""

    try:
        asyncio.run(check_log_channel())
    except ConfigError as error:
        raise SystemExit(f"設定エラー: {error}") from error


async def check_log_channel() -> None:
    """Bot Tokenを表示せずにログチャンネル疎通を確認する。"""

    load_dotenv(override=True)
    raw_chat_id = os.getenv("TELEGRAM_LOG_CHAT_ID", "")
    config = load_config(require_bot_token=True)
    if config.telegram_log_chat_id is None:
        raise SystemExit("TELEGRAM_LOG_CHAT_ID が空です。.env にログチャンネルIDを設定してください。")

    print_chat_id_diagnostics(raw_chat_id, config.telegram_log_chat_id)
    bot = Bot(token=config.telegram_bot_token)
    try:
        chat = await bot.get_chat(config.telegram_log_chat_id)
        print("get_chat に成功しました。")
        print(f"chat.id={chat.id}")
        print(f"chat.type={chat.type}")
        print(f"chat.title={chat.title or ''}")
        await bot.send_message(config.telegram_log_chat_id, "log channel test")
        print("send_message に成功しました。ログチャンネルへの投稿権限があります。")
    except BadRequest as error:
        print(f"Telegram API が BadRequest を返しました: {error}")
        print_chat_not_found_help()
        raise SystemExit(1) from error
    except Forbidden as error:
        print(f"Telegram API が Forbidden を返しました: {error}")
        print_chat_not_found_help()
        raise SystemExit(1) from error
    except TelegramError as error:
        print(f"Telegram API エラーです: {error}")
        raise SystemExit(1) from error


def print_chat_id_diagnostics(raw_chat_id: str, chat_id: str) -> None:
    """chat_id の形式だけを表示し、Bot Tokenは出さない。"""

    print("TELEGRAM_LOG_CHAT_ID を確認します。")
    if raw_chat_id != raw_chat_id.strip():
        print("警告: TELEGRAM_LOG_CHAT_ID の前後に空白があります。.env を修正してください。")
    if not CHAT_ID_PATTERN.match(chat_id):
        print("警告: TELEGRAM_LOG_CHAT_ID に数値以外の文字が含まれています。")
    elif not chat_id.startswith("-100"):
        print("注意: チャンネルIDの場合は -100 で始まることが多いです。グループIDでないか確認してください。")
    print(f"chat_id={chat_id}")


def print_chat_not_found_help() -> None:
    print("Chat not found / Forbidden の主な原因:")
    print("- chat_id が間違っている")
    print("- チャンネルIDの -100 が抜けている")
    print("- Botがログチャンネルまたはグループに追加されていない")
    print("- Botに投稿権限がない")
    print("本体保存テストだけ行う場合は .env の TELEGRAM_LOG_CHAT_ID= を空にしてください。")


if __name__ == "__main__":
    main()
