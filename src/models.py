from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawMessageInput:
    """Telegram から受け取った生メッセージを保存するための入力モデル。"""

    source: str
    telegram_chat_id: str
    telegram_message_id: str
    received_at: str
    raw_text: str
    raw_update_json: str | None


@dataclass(frozen=True)
class RawMessageSaveResult:
    """raw_messages 保存結果と重複判定を表すモデル。"""

    raw_message_id: int
    inserted: bool


@dataclass(frozen=True)
class ParsedSignalData:
    """パース済みトレードシグナルの正規化モデル。"""

    side: str
    symbol: str
    timeframe: str
    entry_type: str
    entry_min: str
    entry_max: str
    entry_raw: str
    entry1: str | None
    entry2: str | None
    entry3: str | None
    entry4: str | None
    entry5: str | None
    tp1: str | None
    tp2: str | None
    tp3: str | None
    tp4: str | None
    tp5: str | None
    sl: str
    signal_time: str
    signal_time_utc: str


@dataclass(frozen=True)
class RawMessageRecord:
    """未処理 raw message の再処理に使う読み取りモデル。"""

    id: int
    source: str
    telegram_chat_id: str
    telegram_message_id: str
    received_at: str
    raw_text: str
