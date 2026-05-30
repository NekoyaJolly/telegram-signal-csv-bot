from __future__ import annotations

import pytest
from zoneinfo import ZoneInfo

from src.parser import SignalParseError, parse_signal


TOKYO = ZoneInfo("Asia/Tokyo")


def test_sell_xauusd_signal_is_parsed() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m"), TOKYO)

    assert signal.side == "SELL"
    assert signal.symbol == "XAUUSD"
    assert signal.timeframe == "1m"


def test_buy_usdjpy_signal_is_parsed() -> None:
    signal = parse_signal(
        """BUY USDJPY 5m

Entry | 157.120 - 157.300

TP | 157.500 - 157.800 - 158.200
SL | 156.900

2026-03-22-21:15
""",
        TOKYO,
    )

    assert signal.side == "BUY"
    assert signal.symbol == "USDJPY"
    assert signal.timeframe == "5m"


def test_entry_range_is_parsed() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4563 - 4568"), TOKYO)

    assert signal.entry_type == "range"
    assert signal.entry_min == "4563"
    assert signal.entry_max == "4568"
    assert signal.entry_raw == "4563 - 4568"


def test_entry_reversed_range_is_saved_as_min_max() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4568 - 4563"), TOKYO)

    assert signal.entry_min == "4563"
    assert signal.entry_max == "4568"
    assert signal.entry_raw == "4568 - 4563"


def test_single_entry_is_parsed() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4533"), TOKYO)

    assert signal.entry_type == "single"
    assert signal.entry_min == "4533"
    assert signal.entry_max == "4533"
    assert signal.entry_raw == "4533"


def test_range_entry_type_is_range() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4563 - 4568"), TOKYO)

    assert signal.entry_type == "range"


@pytest.mark.parametrize("entry", ["4563 - 4568 - 4570", "abc"])
def test_invalid_entry_raises_error(entry: str) -> None:
    with pytest.raises(SignalParseError):
        parse_signal(_message("SELL XAUUSD 1m", entry=entry), TOKYO)


def test_one_take_profit_is_valid() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", take_profit="4559"), TOKYO)

    assert signal.tp1 == "4559"
    assert signal.tp2 is None


def test_five_take_profits_are_valid() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", take_profit="4559 - 4551 - 4533 - 4520 - 4510"), TOKYO)

    assert signal.tp1 == "4559"
    assert signal.tp5 == "4510"


def test_six_take_profits_raise_error() -> None:
    with pytest.raises(SignalParseError):
        parse_signal(_message("SELL XAUUSD 1m", take_profit="1 - 2 - 3 - 4 - 5 - 6"), TOKYO)


def test_missing_entry_line_raises_error() -> None:
    with pytest.raises(SignalParseError):
        parse_signal(
            """SELL XAUUSD 1m

TP | 4559 - 4551 - 4533
SL | 4571

2026-03-22-19:28
""",
            TOKYO,
        )


def test_missing_sl_line_raises_error() -> None:
    with pytest.raises(SignalParseError):
        parse_signal(
            """SELL XAUUSD 1m

Entry | 4563 - 4568

TP | 4559 - 4551 - 4533

2026-03-22-19:28
""",
            TOKYO,
        )


def test_invalid_datetime_raises_error() -> None:
    with pytest.raises(SignalParseError):
        parse_signal(
            """SELL XAUUSD 1m

Entry | 4563 - 4568

TP | 4559 - 4551 - 4533
SL | 4571

2026/03/22 19:28
""",
            TOKYO,
        )


def test_signal_time_utc_is_converted() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m"), TOKYO)

    assert signal.signal_time == "2026-03-22T19:28:00+09:00"
    assert signal.signal_time_utc == "2026-03-22T10:28:00Z"


def _message(
    header: str,
    entry: str = "4563 - 4568",
    take_profit: str = "4559 - 4551 - 4533",
    stop_loss: str = "4571",
) -> str:
    return f"""{header}

Entry | {entry}

TP | {take_profit}
SL | {stop_loss}

2026-03-22-19:28
"""
