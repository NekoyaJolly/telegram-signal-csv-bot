from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from src.models import ParsedSignalData


class SignalParseError(Exception):
    """トレードシグナル本文を仕様どおりに解釈できない場合の例外。"""


HEADER_PATTERN = re.compile(r"^(?P<side>buy|sell)\s+(?P<symbol>[A-Za-z0-9._-]+)\s+(?P<timeframe>[A-Za-z0-9]+)$", re.IGNORECASE)
PRICE_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")
DATETIME_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}:\d{2}$")


def parse_signal(raw_text: str, signal_timezone: ZoneInfo) -> ParsedSignalData:
    """Telegram 本文を正規化済みシグナルへ変換する。"""

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        raise SignalParseError("本文が空です")

    header = _parse_header(lines[0])
    entry_raw = _extract_pipe_value(lines, "Entry")
    entry_type, entry_min, entry_max = _parse_entry(entry_raw)
    take_profits = _parse_take_profits(_extract_pipe_value(lines, "TP"))
    sl = _parse_single_price(_extract_pipe_value(lines, "SL"), "SL")
    signal_time, signal_time_utc = _parse_signal_time(lines, signal_timezone)

    padded_take_profits = take_profits + [None] * (5 - len(take_profits))
    return ParsedSignalData(
        side=header["side"],
        symbol=header["symbol"],
        timeframe=header["timeframe"],
        entry_type=entry_type,
        entry_min=entry_min,
        entry_max=entry_max,
        entry_raw=entry_raw,
        tp1=padded_take_profits[0],
        tp2=padded_take_profits[1],
        tp3=padded_take_profits[2],
        tp4=padded_take_profits[3],
        tp5=padded_take_profits[4],
        sl=sl,
        signal_time=signal_time,
        signal_time_utc=signal_time_utc,
    )


def _parse_header(line: str) -> dict[str, str]:
    match = HEADER_PATTERN.match(line)
    if match is None:
        raise SignalParseError("1行目の形式が不正です")
    return {
        "side": match.group("side").upper(),
        "symbol": match.group("symbol").upper(),
        "timeframe": match.group("timeframe"),
    }


def _extract_pipe_value(lines: list[str], label: str) -> str:
    pattern = re.compile(rf"^{re.escape(label)}\s*\|\s*(?P<value>.*)$", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line)
        if match is not None:
            value = match.group("value").strip()
            if not value:
                raise SignalParseError(f"{label} が空です")
            return value
    raise SignalParseError(f"{label} 行がありません")


def _split_price_list(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*-\s*", value) if part.strip()]
    if not parts:
        raise SignalParseError("価格が空です")
    return parts


def _parse_entry(value: str) -> tuple[str, str, str]:
    parts = _split_price_list(value)
    if len(parts) == 1:
        price = _parse_single_price(parts[0], "Entry")
        return "single", price, price
    if len(parts) == 2:
        first = _parse_price_decimal(parts[0], "Entry")
        second = _parse_price_decimal(parts[1], "Entry")
        if first <= second:
            return "range", str(first), str(second)
        return "range", str(second), str(first)
    raise SignalParseError("Entry は単独価格または2点レンジのみ許可されています")


def _parse_take_profits(value: str) -> list[str]:
    parts = _split_price_list(value)
    if len(parts) > 5:
        raise SignalParseError("TP は最大5個までです")
    return [_parse_single_price(part, "TP") for part in parts]


def _parse_single_price(value: str, label: str) -> str:
    return str(_parse_price_decimal(value, label))


def _parse_price_decimal(value: str, label: str) -> Decimal:
    if not PRICE_PATTERN.match(value):
        raise SignalParseError(f"{label} の価格形式が不正です")
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise SignalParseError(f"{label} の価格形式が不正です") from error


def _parse_signal_time(lines: list[str], signal_timezone: ZoneInfo) -> tuple[str, str]:
    datetime_line = next((line for line in reversed(lines) if DATETIME_PATTERN.match(line)), None)
    if datetime_line is None:
        raise SignalParseError("日時行の形式が不正です")

    try:
        local_time = datetime.strptime(datetime_line, "%Y-%m-%d-%H:%M").replace(tzinfo=signal_timezone)
    except ValueError as error:
        raise SignalParseError("日時行の形式が不正です") from error

    utc_time = local_time.astimezone(timezone.utc)
    return (
        local_time.isoformat(timespec="seconds"),
        utc_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )
