from __future__ import annotations

import pytest

from scripts.check_log_channel import print_chat_id_diagnostics


def test_chat_id_diagnostics_warns_for_non_channel_like_id(capsys: pytest.CaptureFixture[str]) -> None:
    print_chat_id_diagnostics("-5020668206", "-5020668206")

    output = capsys.readouterr().out
    assert "chat_id=-5020668206" in output
    assert "-100" in output


def test_chat_id_diagnostics_warns_for_non_numeric_id(capsys: pytest.CaptureFixture[str]) -> None:
    print_chat_id_diagnostics("abc", "abc")

    output = capsys.readouterr().out
    assert "数値以外" in output
