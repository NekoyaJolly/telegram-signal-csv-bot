from __future__ import annotations

from src.config import load_config
from src.database import init_db


def main() -> None:
    """SQLite DB を初期化する。"""

    config = load_config(require_bot_token=False)
    init_db(config.sqlite_db_path)
    print(f"SQLite DB を初期化しました: {config.sqlite_db_path}")


if __name__ == "__main__":
    main()
