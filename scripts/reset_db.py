from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from src.config import AppConfig, load_config


@dataclass(frozen=True)
class ResetTargets:
    """ローカル検証データの削除対象パス。"""

    sqlite_db_path: Path
    sqlite_wal_path: Path
    sqlite_shm_path: Path
    csv_output_path: Path
    rejected_csv_output_path: Path


def main() -> None:
    """ローカル検証用のSQLite DBとCSVだけを削除する。"""

    args = parse_args()
    config = load_config(require_bot_token=False)
    targets = build_reset_targets(config)
    target_paths = list_reset_paths(targets)
    print_targets(target_paths)

    if not args.yes and not confirm_reset():
        print("削除を中止しました。")
        return

    deleted_count = delete_existing_paths(target_paths)
    print(f"削除が完了しました。削除数: {deleted_count}")
    print("次に `python -m scripts.init_db` を実行してください。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ローカル検証用のSQLite DBとCSVを削除します")
    parser.add_argument("--yes", action="store_true", help="確認なしで削除します")
    return parser.parse_args()


def build_reset_targets(config: AppConfig) -> ResetTargets:
    """設定値から削除対象パスを作る。"""

    sqlite_db_path = config.sqlite_db_path
    return ResetTargets(
        sqlite_db_path=sqlite_db_path,
        sqlite_wal_path=Path(f"{sqlite_db_path}-wal"),
        sqlite_shm_path=Path(f"{sqlite_db_path}-shm"),
        csv_output_path=config.csv_output_path,
        rejected_csv_output_path=config.rejected_csv_output_path,
    )


def list_reset_paths(targets: ResetTargets) -> list[Path]:
    """表示順を固定して削除対象パスを返す。"""

    return [
        targets.sqlite_db_path,
        targets.sqlite_wal_path,
        targets.sqlite_shm_path,
        targets.csv_output_path,
        targets.rejected_csv_output_path,
    ]


def print_targets(target_paths: list[Path]) -> None:
    print("以下のローカル検証データを削除します。")
    for target_path in target_paths:
        print(f"- {target_path}")


def confirm_reset() -> bool:
    answer = input("続行しますか？ [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def delete_existing_paths(target_paths: list[Path]) -> int:
    """存在する削除対象だけを削除する。.envやBot Tokenには触らない。"""

    deleted_count = 0
    for target_path in target_paths:
        if target_path.exists():
            target_path.unlink()
            deleted_count += 1
    return deleted_count


if __name__ == "__main__":
    main()
