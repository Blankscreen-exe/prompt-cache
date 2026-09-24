"""F5, the reply-to-a-reply flow, driven end to end.

This is the whole reason M4 exists: the second prompt in a thread should cost one paste,
not a rebuild. The test that matters is `test_the_follow_up_fills_itself`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, TextArea

from prompt_cache import clipboard
from prompt_cache.store import conversations as conversation_store
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database
from prompt_cache.ui.app import PromptCacheApp
from prompt_cache.ui.screens.conversation import ConversationScreen
from prompt_cache.ui.screens.fill import FillScreen
from prompt_cache.ui.screens.picker import PromptPicker

COMMENT = "Comment template\nPOST:\n{{post: clipboard}}\n\nANGLE: {{angle: short | long}}\n"
REPLY = (
    "Reply template\n"
    "POST:\n{{post}}\n\n"
    "MY COMMENT: {{my_comment: optional}}\n\n"
    "THEIR REPLY:\n{{their_reply: clipboard}}\n"
)


@pytest.fixture
def clip(monkeypatch):
    """A fake OS clipboard the app both reads and writes."""
    state = {"text": ""}
    monkeypatch.setattr(clipboard, "write_text", lambda t: state.update(text=t))
    monkeypatch.setattr(clipboard, "read_text", lambda: state["text"])
    monkeypatch.setattr(clipboard, "read_text_or_empty", lambda: state["text"])
    return state


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "threads.db"


def drive(db_file: Path, scenario, seed=None):
    async def go():
        with database(db_file) as conn:
            if seed is not None:
                seed(conn)
            app = PromptCacheApp(conn)
            async with app.run_test(size=(100, 44)) as pilot:
                await pilot.pause()
                await scenario(app, pilot, conn)

    asyncio.run(go())


def seed_templates(conn):
    prompt_store.create(conn, COMMENT)
    prompt_store.create(conn, REPLY)


class TestFillsBecomeThreads:
    def test_a_fill_starts_a_thread_named_after_its_content(self, db_file, clip):
        clip["text"] = "Excited to share that our team shipped onboarding improvements"

        async def scenario(app, pilot, conn):
            await pilot.press(*"comment temp")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            threads = conversation_store.list_live(conn)
            assert len(threads) == 1
            assert threads[0].label.startswith("Excited to share")
            assert threads[0].values["post"].startswith("Excited to share")

        drive(db_file, scenario, seed=seed_templates)

    def test_threads_show_up_when_browsing(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            conversation_store.create(conn, {"post": "A thread about something"})

        async def scenario(app, pilot, conn):
            listing = app.screen.query_one("#results", OptionList)
            ids = [listing.get_option_at_index(i).id for i in range(listing.option_count)]
            assert any(i and i.startswith("__thread__") for i in ids)

        drive(db_file, scenario, seed=seed)

    def test_a_thread_is_findable_by_its_content(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            conversation_store.create(conn, {"post": "zebra crossing statistics"})

        async def scenario(app, pilot, conn):
            await pilot.press(*"zebra")
            await pilot.pause()
            listing = app.screen.query_one("#results", OptionList)
            ids = [listing.get_option_at_index(i).id for i in range(listing.option_count)]
            assert any(i and i.startswith("__thread__") for i in ids)

        drive(db_file, scenario, seed=seed)

    def test_enter_on_a_thread_opens_it(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            conversation_store.create(conn, {"post": "zebra crossing statistics"})

        async def scenario(app, pilot, conn):
            await pilot.press(*"zebra")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ConversationScreen)

        drive(db_file, scenario, seed=seed)


class TestTheFollowUpFlow:
    def test_the_follow_up_fills_itself(self, db_file, clip):
        """F5: only the new reply is pasted. The post and my comment come from the thread.

        This is the flow the whole product is for.
        """
        clip["text"] = "The original post about onboarding"

        async def scenario(app, pilot, conn):
            # 1. Comment on the post.
            await pilot.press(*"comment temp")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            thread = conversation_store.list_live(conn)[0]

            # 2. Save the comment actually posted.
            conversation_store.set_value(conn, thread.id, "my_comment", "What I said back")

            # 3. Their reply arrives on the clipboard.
            clip["text"] = "Their new reply to me"

            # 4. Open the thread and continue with the reply template.
            await pilot.press("escape")
            await pilot.pause()
            await pilot.press(*"onboarding")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, ConversationScreen)

            await pilot.press("ctrl+n")
            await pilot.pause()
            assert isinstance(app.screen, PromptPicker)
            await pilot.press(*"reply")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, FillScreen)

            # The point: two of three fields were filled without a paste.
            values = app.screen.current_values()
            assert values["post"] == "The original post about onboarding"
            assert values["my_comment"] == "What I said back"
            assert values["their_reply"] == "Their new reply to me"

            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "The original post about onboarding" in clip["text"]
            assert "What I said back" in clip["text"]
            assert "Their new reply to me" in clip["text"]
            assert conversation_store.get(conn, thread.id).fill_count == 2

        drive(db_file, scenario, seed=seed_templates)

    def test_continuing_keeps_everything_in_one_thread(self, db_file, clip):
        clip["text"] = "A post to comment on"

        async def scenario(app, pilot, conn):
            await pilot.press(*"comment temp")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            thread = conversation_store.list_live(conn)[0]
            reply = prompt_store.get_by_name(conn, "reply-template")

            app.push_screen(FillScreen(reply.id, conversation_id=thread.id))
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert len(conversation_store.list_live(conn)) == 1, "no second thread"
            assert conversation_store.get(conn, thread.id).fill_count == 2

        drive(db_file, scenario, seed=seed_templates)

    def test_a_fresh_fill_starts_a_separate_thread(self, db_file, clip):
        clip["text"] = "First post"

        async def scenario(app, pilot, conn):
            for text in ("First post", "A completely different second post"):
                clip["text"] = text
                await pilot.press(*"comment temp")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                await pilot.press("ctrl+enter")
                await pilot.pause()
                app.screen.query_one("#search", Input).value = ""
                await pilot.pause()

            assert len(conversation_store.list_live(conn)) == 2

        drive(db_file, scenario, seed=seed_templates)


class TestThreadScreen:
    def _thread(self, conn):
        return conversation_store.create(conn, {"post": "A post", "my_comment": "My comment"})

    def test_values_are_listed(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            self._thread(conn)

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()

            listing = app.screen.query_one("#thread-values", OptionList)
            ids = [listing.get_option_at_index(i).id for i in range(listing.option_count)]
            assert ids == ["my_comment", "post"]

        drive(db_file, scenario, seed=seed)

    def test_ctrl_s_saves_the_clipboard_into_a_named_value(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            self._thread(conn)

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()

            clip["text"] = "what I actually posted"
            app.screen.query_one("#thread-value-name", Input).value = "their_reply"
            await pilot.pause()
            await pilot.press("ctrl+s")
            await pilot.pause()

            assert conversation_store.get(conn, thread.id).values["their_reply"] == (
                "what I actually posted"
            )

        drive(db_file, scenario, seed=seed)

    def test_ctrl_s_with_no_name_updates_the_selected_value(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            self._thread(conn)

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()

            clip["text"] = "replacement text"
            await pilot.press("ctrl+s")
            await pilot.pause()

            # my_comment sorts first, so it is the highlighted row.
            assert conversation_store.get(conn, thread.id).values["my_comment"] == (
                "replacement text"
            )

        drive(db_file, scenario, seed=seed)

    def test_a_value_can_be_removed(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            self._thread(conn)

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()
            await pilot.press("ctrl+d")
            await pilot.pause()

            assert "my_comment" not in conversation_store.get(conn, thread.id).values

        drive(db_file, scenario, seed=seed)

    def test_the_history_shows_what_was_sent(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            template = prompt_store.get_by_name(conn, "comment-template")
            conversation_store.add_fill(
                conn, prompt_id=template.id, values={"post": "P"}, output="THE ASSEMBLED TEXT"
            )

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()

            history = str(app.screen.query_one("#thread-fills").content)
            assert "THE ASSEMBLED TEXT" in history
            assert "Comment template" in history

        drive(db_file, scenario, seed=seed)

    def test_ctrl_r_copies_the_last_output_again(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            template = prompt_store.get_by_name(conn, "comment-template")
            conversation_store.add_fill(
                conn, prompt_id=template.id, values={}, output="EARLIER OUTPUT"
            )

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()
            await pilot.press("ctrl+r")
            await pilot.pause()

            assert clip["text"] == "EARLIER OUTPUT"

        drive(db_file, scenario, seed=seed)

    def test_escape_returns_to_search(self, db_file, clip):
        def seed(conn):
            seed_templates(conn)
            self._thread(conn)

        async def scenario(app, pilot, conn):
            thread = conversation_store.list_live(conn)[0]
            app.push_screen(ConversationScreen(thread.id))
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert not isinstance(app.screen, ConversationScreen)
            assert app.screen.query_one("#search", TextArea | Input) is not None

        drive(db_file, scenario, seed=seed)
