from __future__ import annotations

import pytest
from zoneinfo import ZoneInfo

from src.parser import SignalParseError, parse_signal, parse_signal_blocks, split_signal_blocks


TOKYO = ZoneInfo("Asia/Tokyo")


# 実際に届く「複数シグナル連結」入力 (時刻行の直後に空行なしで次の B/S ヘッダーが続く)
MULTI_SIGNAL_RAW_TEXT = (
    "SELL XAUUSD 5m\n\nEntry | 4505 - 4510\n\nTP | 4500 - 4495 - 4485\nSL | 4515\n\n2026-06-02-23:00\n"
    "BUY XAUUSD 5m\n\nEntry | 4461 - 4456\n\nTP | 4466 - 4471 - 4481\nSL | 4451\n\n2026-06-03-14:25\n"
    "SELL XAUUSD 5m\n\nEntry | 4466 - 4471\n\nTP | 4461 - 4456 - 4446\nSL | 4476\n\n2026-06-03-14:45"
)


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
    assert signal.entry1 == "4563"
    assert signal.entry2 == "4568"
    assert signal.entry3 is None


def test_entry_reversed_range_is_saved_as_min_max() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4568 - 4563"), TOKYO)

    assert signal.entry_min == "4563"
    assert signal.entry_max == "4568"
    assert signal.entry_raw == "4568 - 4563"
    assert signal.entry1 == "4568"
    assert signal.entry2 == "4563"


def test_single_entry_is_parsed() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4533"), TOKYO)

    assert signal.entry_type == "single"
    assert signal.entry_min == "4533"
    assert signal.entry_max == "4533"
    assert signal.entry_raw == "4533"
    assert signal.entry1 == "4533"
    assert signal.entry2 is None


def test_range_entry_type_is_range() -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry="4563 - 4568"), TOKYO)

    assert signal.entry_type == "range"


@pytest.mark.parametrize(
    ("entry", "expected_type", "expected_min", "expected_max", "expected_entries"),
    [
        ("4563 - 4568 - 4570", "multi", "4563", "4570", ["4563", "4568", "4570", None, None]),
        ("4563 - 4568 - 4570 - 4575", "multi", "4563", "4575", ["4563", "4568", "4570", "4575", None]),
        ("4563 - 4568 - 4570 - 4575 - 4580", "multi", "4563", "4580", ["4563", "4568", "4570", "4575", "4580"]),
        ("4570 - 4563 - 4580 - 4568", "multi", "4563", "4580", ["4570", "4563", "4580", "4568", None]),
    ],
)
def test_multi_entry_is_parsed(
    entry: str,
    expected_type: str,
    expected_min: str,
    expected_max: str,
    expected_entries: list[str | None],
) -> None:
    signal = parse_signal(_message("SELL XAUUSD 1m", entry=entry), TOKYO)

    assert signal.entry_type == expected_type
    assert signal.entry_min == expected_min
    assert signal.entry_max == expected_max
    assert signal.entry_raw == entry
    assert [signal.entry1, signal.entry2, signal.entry3, signal.entry4, signal.entry5] == expected_entries


@pytest.mark.parametrize("entry", ["4563 - 4568 - 4570 - 4575 - 4580 - 4590", "abc"])
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


def test_single_message_is_one_block() -> None:
    blocks = split_signal_blocks(_message("SELL XAUUSD 1m"))

    assert len(blocks) == 1


def test_multiple_signals_are_split_into_blocks() -> None:
    blocks = split_signal_blocks(MULTI_SIGNAL_RAW_TEXT)

    assert len(blocks) == 3
    assert blocks[0].startswith("SELL XAUUSD 5m")
    assert blocks[1].startswith("BUY XAUUSD 5m")
    assert blocks[2].startswith("SELL XAUUSD 5m")


def test_parse_signal_blocks_returns_each_signal_in_order() -> None:
    results = parse_signal_blocks(MULTI_SIGNAL_RAW_TEXT, TOKYO)

    assert [result.block_index for result in results] == [1, 2, 3]
    assert all(result.signal is not None and result.error is None for result in results)
    signals = [result.signal for result in results]
    assert [signal.side for signal in signals if signal is not None] == ["SELL", "BUY", "SELL"]
    assert [signal.signal_time for signal in signals if signal is not None] == [
        "2026-06-02T23:00:00+09:00",
        "2026-06-03T14:25:00+09:00",
        "2026-06-03T14:45:00+09:00",
    ]


def test_parse_signal_blocks_separates_failed_block() -> None:
    # 2ブロック目の SL 行を欠落させ、ブロック単位で成功/失敗が切り分けられることを確認する
    raw_text = (
        "SELL XAUUSD 5m\n\nEntry | 4505 - 4510\n\nTP | 4500 - 4495 - 4485\nSL | 4515\n\n2026-06-02-23:00\n"
        "BUY XAUUSD 5m\n\nEntry | 4461 - 4456\n\nTP | 4466 - 4471 - 4481\n\n2026-06-03-14:25"
    )

    results = parse_signal_blocks(raw_text, TOKYO)

    assert len(results) == 2
    assert results[0].signal is not None and results[0].error is None
    assert results[1].signal is None and results[1].error == "SL 行がありません"


def test_parse_signal_blocks_wraps_single_invalid_message_as_one_rejected_block() -> None:
    results = parse_signal_blocks("SELL XAUUSD 1m", TOKYO)

    assert len(results) == 1
    assert results[0].signal is None
    assert results[0].error is not None


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
