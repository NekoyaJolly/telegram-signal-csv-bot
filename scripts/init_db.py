from __future__ import annotations

import sys

from src.config import load_config
from src.database import DatabaseSchemaError, init_db


def main() -> None:
    """SQLite DB を初期化する。"""

    config = load_config(require_bot_token=False)
    try:
        init_db(config.sqlite_db_path)
    except DatabaseSchemaError as error:
        print(f"SQLite DB のスキーマ確認に失敗しました: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    print(f"SQLite DB を初期化しました: {config.sqlite_db_path}")


if __name__ == "__main__":
    main()
