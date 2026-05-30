from __future__ import annotations

from src.config import load_config
from src.csv_exporter import regenerate_rejected_signals_csv, regenerate_trade_signals_csv
from src.database import connect, init_db


def main() -> None:
    """SQLite から CSV を全再生成する。"""

    config = load_config(require_bot_token=False)
    init_db(config.sqlite_db_path)
    with connect(config.sqlite_db_path) as connection:
        trade_count = regenerate_trade_signals_csv(connection, config.csv_output_path)
        rejected_count = regenerate_rejected_signals_csv(connection, config.rejected_csv_output_path)
    print(f"trade_signals.csv を再生成しました: {trade_count} 行")
    print(f"rejected_signals.csv を再生成しました: {rejected_count} 行")


if __name__ == "__main__":
    main()
