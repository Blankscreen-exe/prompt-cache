"""The fill flow, driven through the pilot.

M2's acceptance criterion: from "post copied" to "assembled prompt on the clipboard" in
a handful of keystrokes, with the clipboard blank already filled in.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button, Select, TextArea

from prompt_cache import clipboard
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database
from prompt_cache.ui.app import PromptCacheApp
from prompt_cache.ui.screens.fill import FillScreen

TEMPLATE = (
    "Write a comment on the post below. Under 80 words.\n\n"
    "ANGLE: {{angle: counterpoint | experience}}\n\n"
    "POST:\n{{post: clipboard}}\n\n"
    "MY NOTE: {{note: optional}}\n"
)


@pytest.fixture
def copied(monkeypatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(clipboard, "write_text", captured.append)
    return captured


@pytest.fixture
def pasteable(monkeypatch):
    """Whatever the app 'reads' from the clipboard when a form opens."""

    def _set(text: str):
        monkeypatch.setattr(clipboard, "read_text_or_empty", lambda: text)

    _set("")
    return _set


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "fill.db"


def drive(db_file: Path, scenario, seed=None):
    async def go():
        with database(db_file) as conn:
            if seed is not None:
                seed(conn)
            app = PromptCacheApp(conn)
            async with app.run_test(size=(100, 40)) as pilot:
                await pilot.pause()
                await scenario(app, pilot, conn)

    asyncio.run(go())


def seed_template(conn):
    prompt_store.create(conn, TEMPLATE, title="Social comment")


def seed_plain(conn):
    prompt_store.create(conn, "Plain prompt\nno blanks here")


class TestOpeningTheForm:
    def test_enter_on_a_template_opens_the_fill_form(self, db_file, copied, pasteable):
        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, FillScreen)
            assert copied == [], "a template must not copy straight out"

        drive(db_file, scenario, seed=seed_template)

    def test_enter_on_a_plain_prompt_still_copies_directly(self, db_file, copied, pasteable):
        async def scenario(app, pilot, conn):
            await pilot.press(*"plain")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert not isinstance(app.screen, FillScreen)
            assert copied == ["Plain prompt\nno blanks here"]

        drive(db_file, scenario, seed=seed_plain)

    def test_a_field_appears_for_every_blank(self, db_file, copied, pasteable):
        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()

            assert app.screen.query_one("#field-angle", Select) is not None
            assert app.screen.query_one("#field-post", TextArea) is not None
            assert app.screen.query_one("#field-note", TextArea) is not None

        drive(db_file, scenario, seed=seed_template)


class TestClipboardPrefill:
    def test_a_clipboard_blank_is_already_filled(self, db_file, copied, pasteable):
        pasteable("Their post text.")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()

            assert app.screen.current_values()["post"] == "Their post text."

        drive(db_file, scenario, seed=seed_template)

    def test_the_whole_flow_is_open_then_copy(self, db_file, copied, pasteable):
        """The M2 bar: post on the clipboard, then Enter and Ctrl+Enter."""
        pasteable("Their post text.")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert copied == [
                "Write a comment on the post below. Under 80 words.\n\n"
                "ANGLE: counterpoint\n\n"
                "POST:\nTheir post text.\n"
            ]
            assert prompt_store.list_live(conn)[0].use_count == 1

        drive(db_file, scenario, seed=seed_template)

    def test_focus_lands_on_copy_when_nothing_needs_typing(self, db_file, copied, pasteable):
        pasteable("Already here.")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.focused, Button), "one keypress should finish the job"

        drive(db_file, scenario, seed=seed_template)

    def test_focus_lands_on_the_first_gap_when_something_is_missing(
        self, db_file, copied, pasteable
    ):
        pasteable("")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is app.screen.query_one("#field-post", TextArea)

        drive(db_file, scenario, seed=seed_template)


class TestPreviewAndValues:
    def test_typing_updates_the_preview(self, db_file, copied, pasteable):
        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()

            app.screen.query_one("#field-post", TextArea).text = "typed post"
            await pilot.pause()
            preview = app.screen.query_one("#preview-text").content
            assert "typed post" in str(preview)

        drive(db_file, scenario, seed=seed_template)

    def test_an_empty_optional_drops_its_line_from_the_output(self, db_file, copied, pasteable):
        pasteable("post text")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "MY NOTE" not in copied[0]

        drive(db_file, scenario, seed=seed_template)

    def test_a_filled_optional_keeps_its_line(self, db_file, copied, pasteable):
        pasteable("post text")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()

            app.screen.query_one("#field-note", TextArea).text = "a note"
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "MY NOTE: a note" in copied[0]

        drive(db_file, scenario, seed=seed_template)

    def test_choosing_a_different_option_changes_the_output(self, db_file, copied, pasteable):
        pasteable("post text")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()

            app.screen.query_one("#field-angle", Select).value = "experience"
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "ANGLE: experience" in copied[0]

        drive(db_file, scenario, seed=seed_template)


class TestLeavingAndFailing:
    def test_escape_goes_back_without_copying(self, db_file, copied, pasteable):
        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert not isinstance(app.screen, FillScreen)
            assert copied == []

        drive(db_file, scenario, seed=seed_template)

    def test_copying_with_a_gap_warns_but_still_copies(self, db_file, copied, pasteable):
        pasteable("")

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert copied, "the user asked for it; give them what there is"
            assert "POST:" in copied[0]

        drive(db_file, scenario, seed=seed_template)

    def test_a_broken_clipboard_does_not_crash_the_form(self, db_file, monkeypatch, pasteable):
        def boom(_text):
            raise clipboard.ClipboardUnavailable("no backend")

        monkeypatch.setattr(clipboard, "write_text", boom)

        async def scenario(app, pilot, conn):
            await pilot.press(*"social")
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert app.is_running
            assert isinstance(app.screen, FillScreen), "stay put so nothing is lost"

        drive(db_file, scenario, seed=seed_template)
