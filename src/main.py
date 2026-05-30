from __future__ import annotations

import logging
import sqlite3

from src.config import AppConfig, load_config
from src.csv_exporter import regenerate_rejected_signals_csv, regenerate_trade_signals_csv
from src.database import connect, init_db, reprocess_unprocessed_messages
from src.logging_config import setup_logging
from src.telegram_bot import build_application


logger = logging.getLogger(__name__)


def main() -> None:
    """Telegram polling を起動するアプリケーションエントリーポイント。"""

    config = load_config(require_bot_token=True)
    setup_logging(config.log_dir)
    logger.info("アプリ起動")
    logger.info("Telegramログチャンネル設定 enabled=%s", config.telegram_log_chat_id is not None)
    init_db(config.sqlite_db_path)
    logger.info("DB初期化 path=%s", config.sqlite_db_path)

    connection = connect(config.sqlite_db_path)
    parsed_count, rejected_count = reprocess_unprocessed_messages(connection, config.signal_timezone)
    regenerate_csv_after_reprocess(connection, config, parsed_count, rejected_count)

    application = build_application(config, connection)
    logger.info("Telegram polling起動")
    application.run_polling(allowed_updates=None)


def regenerate_csv_after_reprocess(
    connection: sqlite3.Connection, config: AppConfig, parsed_count: int, rejected_count: int
) -> None:
    """未処理raw再処理でDBが更新された場合、CSVをSQLite正本から復旧する。"""

    if parsed_count == 0 and rejected_count == 0:
        return

    logger.info("未処理raw再処理 parsed=%s rejected=%s", parsed_count, rejected_count)
    trade_rows = regenerate_trade_signals_csv(connection, config.csv_output_path)
    rejected_rows = regenerate_rejected_signals_csv(connection, config.rejected_csv_output_path)
    logger.info(
        "未処理raw再処理後にCSVを全再生成した trade_rows=%s rejected_rows=%s",
        trade_rows,
        rejected_rows,
    )


if __name__ == "__main__":
    main()
