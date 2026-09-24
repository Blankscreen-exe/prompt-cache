"""End-to-end flows driven through Textual's pilot.

These are the M1 acceptance criteria as tests: writing a prompt is typing plus Enter with
no dialogs, and retrieving one is a couple of keystrokes.

The clipboard is stubbed throughout — a test suite must never clobber the real one.
"""

from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, TextArea

from prompt_cache import clipboard
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database
from prompt_cache.ui.app import PromptCacheApp
from prompt_cache.ui.screens.editor import EditorScreen
from prompt_cache.ui.screens.trash import TrashScreen


@pytest.fixture
def copied(monkeypatch) -> list[str]:
    """Captures whatever the app puts on the clipboard."""
    captured: list[str] = []
    monkeypatch.setattr(clipboard, "write_text", captured.append)
    return captured


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "ui.db"


def drive(db_file: Path, scenario, seed=None):
    """Run `scenario(app, pilot, conn)` against a fresh app."""

    async def go():
        with database(db_file) as conn:
            if seed is not None:
                seed(conn)
            app = PromptCacheApp(conn)
            async with app.run_test(size=(100, 30)) as pilot:
                await pilot.pause()
                await scenario(app, pilot, conn)

    asyncio.run(go())


def results_of(app) -> OptionList:
    return app.screen.query_one("#results", OptionList)


def visible_ids(app) -> list[str]:
    listing = results_of(app)
    return [
        listing.get_option_at_index(i).id
        for i in range(listing.option_count)
        if not listing.get_option_at_index(i).disabled
    ]


class TestWritingAPrompt:
    def test_typing_then_enter_creates_a_prompt_with_no_dialog(self, db_file, copied):
        """The M1 bar: writing a new prompt is typing plus Enter."""

        async def scenario(app, pilot, conn):
            await pilot.press(*"Daily standup")
            await pilot.press("enter")
            await pilot.pause()

            assert isinstance(app.screen, EditorScreen), "Enter should open the editor"
            assert app.screen.query_one("#editor-body", TextArea).text == "Daily standup"

            prompts = prompt_store.list_live(conn)
            assert len(prompts) == 1
            assert prompts[0].title == "Daily standup"
            assert prompts[0].name == "daily-standup"

        drive(db_file, scenario)

    def test_editing_autosaves_and_updates_the_title(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"Seed")
            await pilot.press("enter")
            await pilot.pause()

            area = app.screen.query_one("#editor-body", TextArea)
            area.text = "Renamed title\n\nSome body with #atag"
            await pilot.pause()
            app.screen.action_save_now()
            await pilot.pause()

            saved = prompt_store.list_live(conn)[0]
            assert saved.title == "Renamed title"
            assert saved.tags == ("atag",)

        drive(db_file, scenario)

    def test_escape_from_an_untouched_new_prompt_leaves_no_litter(self, db_file, copied):
        """Ctrl+N then Esc should not leave an empty prompt behind."""

        async def scenario(app, pilot, conn):
            await pilot.press("ctrl+n")
            await pilot.pause()
            assert isinstance(app.screen, EditorScreen)

            await pilot.press("escape")
            await pilot.pause()
            assert prompt_store.list_live(conn) == []

        drive(db_file, scenario)


def seed_three(conn):
    prompt_store.create(conn, "LinkedIn comment\nWrite a comment. #social")
    prompt_store.create(conn, "Email reply\nAnswer the thread.")
    prompt_store.create(conn, "Generic proposal\nPitch the brief.")


class TestFindingAndCopying:
    def test_search_then_enter_copies_the_body(self, db_file, copied):
        """The other M1 bar: retrieve and copy in a couple of keystrokes."""

        async def scenario(app, pilot, conn):
            await pilot.press(*"propo")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert copied == ["Generic proposal\nPitch the brief."]
            assert prompt_store.get_by_name(conn, "generic-proposal").use_count == 1

        drive(db_file, scenario, seed=seed_three)

    def test_results_narrow_as_you_type(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.pause()
            assert len(visible_ids(app)) == 3, "empty query browses everything"

            await pilot.press(*"email")
            await pilot.pause()
            assert len(visible_ids(app)) == 1

        drive(db_file, scenario, seed=seed_three)

    def test_no_match_offers_to_create_from_what_was_typed(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"nothing like this")
            await pilot.pause()
            assert visible_ids(app) == ["__create__"]

            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, EditorScreen)
            assert prompt_store.list_live(conn)[0].title == "nothing like this"

        drive(db_file, scenario, seed=seed_three)

    def test_escape_clears_the_query(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"email")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert app.screen.query_one("#search", Input).value == ""
            assert len(visible_ids(app)) == 3

        drive(db_file, scenario, seed=seed_three)

    def test_arrow_keys_move_the_selection_without_leaving_the_search_box(self, db_file, copied):
        async def scenario(app, pilot, conn):
            search_box = app.screen.query_one("#search", Input)
            first = results_of(app).highlighted

            await pilot.press("down")
            await pilot.pause()

            assert results_of(app).highlighted != first
            assert app.focused is search_box, "typing must stay possible while navigating"

        drive(db_file, scenario, seed=seed_three)

    def test_a_clipboard_failure_warns_instead_of_crashing(self, db_file, monkeypatch):
        def boom(_text):
            raise clipboard.ClipboardUnavailable("no backend here")

        monkeypatch.setattr(clipboard, "write_text", boom)

        async def scenario(app, pilot, conn):
            await pilot.press(*"propo")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert app.is_running, "the app must survive a broken clipboard"
            assert prompt_store.get_by_name(conn, "generic-proposal").use_count == 0

        drive(db_file, scenario, seed=seed_three)


class TestPinning:
    def test_pin_floats_a_prompt_to_the_top(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"proposal")
            await pilot.pause()
            await pilot.press("ctrl+p")
            await pilot.pause()

            assert prompt_store.get_by_name(conn, "generic-proposal").pinned

            app.screen.query_one("#search", Input).value = ""
            await pilot.pause()
            top = prompt_store.get(conn, visible_ids(app)[0])
            assert top.name == "generic-proposal"

        drive(db_file, scenario, seed=seed_three)


class TestDeleteAndRestore:
    def test_delete_then_restore_through_the_trash_screen(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"email")
            await pilot.pause()
            await pilot.press("ctrl+d")
            await pilot.pause()

            assert len(prompt_store.list_live(conn)) == 2
            assert len(prompt_store.list_trash(conn)) == 1

            await pilot.press("ctrl+t")
            await pilot.pause()
            assert isinstance(app.screen, TrashScreen)

            await pilot.press("enter")
            await pilot.pause()
            assert len(prompt_store.list_live(conn)) == 3
            assert prompt_store.list_trash(conn) == []

            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, TrashScreen)

        drive(db_file, scenario, seed=seed_three)

    def test_deleted_prompts_leave_the_search_results(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"email")
            await pilot.pause()
            await pilot.press("ctrl+d")
            await pilot.pause()
            assert visible_ids(app) == ["__create__"], "only the create row should remain"

        drive(db_file, scenario, seed=seed_three)


class TestBindingsAreNotShadowed:
    """Textual's Input and TextArea bind ctrl+e and ctrl+d themselves.

    A screen binding on the same key silently does nothing unless it is declared
    `priority`. That bug shipped once already — this class is the guard.
    """

    def test_ctrl_e_opens_the_editor(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"email")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()

            assert isinstance(app.screen, EditorScreen)
            assert "Email reply" in app.screen.query_one("#editor-body", TextArea).text

        drive(db_file, scenario, seed=seed_three)

    def test_editing_then_escaping_returns_to_search_with_changes_saved(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"email")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()

            app.screen.query_one("#editor-body", TextArea).text = "Edited title\nnew body"
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert app.screen.query_one("#search", Input) is not None, "back on search"
            assert prompt_store.get_by_name(conn, "email-reply").title == "Edited title"

        drive(db_file, scenario, seed=seed_three)

    def test_every_screen_binding_survives_the_focused_widget(self, db_file, copied):
        """Any screen key also bound by the focused widget must be `priority`."""
        from textual.widgets import Input as TextualInput

        widget_keys: set[str] = set()
        for binding in TextualInput.BINDINGS:
            widget_keys.update(str(getattr(binding, "key", "")).split(","))

        async def scenario(app, pilot, conn):
            shadowed = [
                binding.key
                for binding in app.screen.BINDINGS
                if binding.key in widget_keys and not binding.priority
            ]
            assert not shadowed, f"shadowed by the focused Input: {shadowed}"

        drive(db_file, scenario, seed=seed_three)


class TestFrameworkAttributeCollisions:
    """Textual's MessagePump owns several private attribute names.

    Shadowing one from a Screen subclass does not error — it silently breaks the
    widget. `_closing` cost an afternoon: setting it told Textual the message pump was
    shutting down, and the whole app hung with no traceback.
    """

    RESERVED = ("_closing", "_running", "_pending_message", "_message_queue", "_parent")

    def test_our_screens_do_not_shadow_message_pump_internals(self):
        from textual.message_pump import MessagePump

        from prompt_cache.ui.screens.conversation import ConversationScreen
        from prompt_cache.ui.screens.editor import EditorScreen
        from prompt_cache.ui.screens.fill import FillScreen
        from prompt_cache.ui.screens.history import HistoryScreen
        from prompt_cache.ui.screens.picker import PromptPicker
        from prompt_cache.ui.screens.search import SearchScreen
        from prompt_cache.ui.screens.settings import SettingsScreen
        from prompt_cache.ui.screens.trash import TrashScreen

        owned = set(MessagePump.__init__.__code__.co_names)
        screens = (
            SearchScreen,
            EditorScreen,
            FillScreen,
            ConversationScreen,
            HistoryScreen,
            SettingsScreen,
            TrashScreen,
            PromptPicker,
        )

        clashes = []
        for screen in screens:
            source = inspect.getsource(screen)
            for name in self.RESERVED:
                if f"self.{name} =" in source and name in owned:
                    clashes.append(f"{screen.__name__}.{name}")
        assert not clashes, f"these shadow Textual internals: {clashes}"
