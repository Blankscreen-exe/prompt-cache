"""Clipboard wrapper tests.

The pyperclip layer is mocked so these run in CI and on a headless box. Whether a real
clipboard works on a given machine is a manual check — see `test_round_trip_on_this_machine`,
which skips when no backend is present.
"""

from __future__ import annotations

import pyperclip
import pytest

from prompt_cache import clipboard


class TestBomHandling:
    def test_leading_bom_is_stripped(self, monkeypatch):
        """Text through a PowerShell pipe can arrive with a BOM; it must not reach a prompt."""
        monkeypatch.setattr(pyperclip, "paste", lambda: "﻿hello")
        assert clipboard.read_text() == "hello"

    def test_only_one_bom_is_removed(self, monkeypatch):
        monkeypatch.setattr(pyperclip, "paste", lambda: "﻿﻿hello")
        assert clipboard.read_text() == "﻿hello"

    def test_a_bom_elsewhere_is_left_alone(self, monkeypatch):
        monkeypatch.setattr(pyperclip, "paste", lambda: "a﻿b")
        assert clipboard.read_text() == "a﻿b"

    def test_no_bom_is_untouched(self, monkeypatch):
        monkeypatch.setattr(pyperclip, "paste", lambda: "plain text")
        assert clipboard.read_text() == "plain text"


class TestTextIsNotMangled:
    @pytest.mark.parametrize(
        "text",
        [
            "line one\nline two\n\nline four",
            "emoji ☕ and accents café",
            "  leading and trailing spaces  ",
            "tabs\there",
            "",
        ],
    )
    def test_round_trip_preserves_text(self, monkeypatch, text):
        captured: list[str] = []
        monkeypatch.setattr(pyperclip, "copy", captured.append)
        monkeypatch.setattr(pyperclip, "paste", lambda: captured[-1])

        clipboard.write_text(text)
        assert clipboard.read_text() == text

    def test_none_from_backend_becomes_empty_string(self, monkeypatch):
        monkeypatch.setattr(pyperclip, "paste", lambda: None)
        assert clipboard.read_text() == ""


class TestFailureHandling:
    @pytest.fixture
    def broken(self, monkeypatch):
        def boom(*args, **kwargs):
            raise pyperclip.PyperclipException("no backend")

        monkeypatch.setattr(pyperclip, "paste", boom)
        monkeypatch.setattr(pyperclip, "copy", boom)

    def test_read_raises_with_an_actionable_message(self, broken):
        with pytest.raises(clipboard.ClipboardUnavailable) as excinfo:
            clipboard.read_text()
        assert "wl-clipboard" in str(excinfo.value)
        assert "xclip" in str(excinfo.value)

    def test_write_raises_with_an_actionable_message(self, broken):
        with pytest.raises(clipboard.ClipboardUnavailable):
            clipboard.write_text("anything")

    def test_read_or_empty_degrades_instead_of_raising(self, broken):
        assert clipboard.read_text_or_empty() == ""

    def test_is_available_is_false_and_never_raises(self, broken):
        assert clipboard.is_available() is False

    def test_is_available_survives_an_unexpected_error(self, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("something odd")

        monkeypatch.setattr(pyperclip, "paste", boom)
        assert clipboard.is_available() is False


@pytest.mark.skipif(not clipboard.is_available(), reason="no clipboard backend on this machine")
def test_round_trip_on_this_machine():
    """A genuine OS round trip. Skips where no backend exists."""
    original = clipboard.read_text_or_empty()
    try:
        sample = "prompt-cache clipboard check\nsecond line ☕"
        clipboard.write_text(sample)
        assert clipboard.read_text() == sample
    finally:
        clipboard.write_text(original)
