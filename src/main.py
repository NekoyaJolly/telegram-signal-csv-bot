from __future__ import annotations

import logging

from src.config import load_config
from src.database import connect, init_db, reprocess_unprocessed_messages
from src.logging_config import setup_logging
from src.telegram_bot import build_application


logger = logging.getLogger(__name__)


def main() -> None:
    """Telegram polling を起動するアプリケーションエントリーポイント。"""

    config = load_config(require_bot_token=True)
    setup_logging(config.log_dir)
    logger.info("アプリ起動")
    init_db(config.sqlite_db_path)
    logger.info("DB初期化 path=%s", config.sqlite_db_path)

    connection = connect(config.sqlite_db_path)
    parsed_count, rejected_count = reprocess_unprocessed_messages(connection, config.signal_timezone)
    if parsed_count or rejected_count:
        logger.info("未処理raw再処理 parsed=%s rejected=%s", parsed_count, rejected_count)

    application = build_application(config, connection)
    logger.info("Telegram polling起動")
    application.run_polling(allowed_updates=None)


if __name__ == "__main__":
    main()
