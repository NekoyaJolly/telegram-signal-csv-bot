from __future__ import annotations

from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters

from src.config import load_config


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """受信した chat_id を表示する補助ハンドラー。"""

    if update.effective_chat is None:
        return
    print(f"chat_id={update.effective_chat.id}")
    if update.effective_message is not None:
        await update.effective_message.reply_text(f"chat_id: {update.effective_chat.id}")


def main() -> None:
    """Telegram Bot が受け取った chat_id を標準出力へ表示する。"""

    config = load_config(require_bot_token=True)
    application = ApplicationBuilder().token(config.telegram_bot_token).build()
    application.add_handler(MessageHandler(filters.ALL, handle_message))
    print("chat_id を確認したいチャットで、このBotにメッセージを送ってください。Ctrl+Cで終了します。")
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
