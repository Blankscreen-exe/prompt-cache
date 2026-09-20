"""M3 through the UI: a block edited once changes every template that includes it."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select, TextArea

from prompt_cache import clipboard
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database
from prompt_cache.ui.app import PromptCacheApp
from prompt_cache.ui.screens.editor import EditorScreen
from prompt_cache.ui.screens.picker import PromptPicker


@pytest.fixture
def copied(monkeypatch) -> list[str]:
    captured: list[str] = []
    monkeypatch.setattr(clipboard, "write_text", captured.append)
    monkeypatch.setattr(clipboard, "read_text_or_empty", lambda: "")
    return captured


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "inc.db"


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


def seed_blocks(conn):
    prompt_store.create(conn, "Agency info\nWe build things for people.")
    prompt_store.create(conn, "Me profile\nI build things.")
    prompt_store.create(
        conn,
        "Outreach template\nWrite something.\n\n{{@agency-info}}\n\nEND",
    )


class TestFillingWithIncludes:
    def test_the_block_body_lands_in_the_output(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"outreach")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "We build things for people." in copied[0]
            assert "{{@agency-info}}" not in copied[0]

        drive(db_file, scenario, seed=seed_blocks)

    def test_editing_a_block_changes_every_template_that_includes_it(self, db_file, copied):
        """M3's acceptance criterion, end to end."""

        async def scenario(app, pilot, conn):
            block = prompt_store.get_by_name(conn, "agency-info")
            prompt_store.update_body(conn, block.id, "Agency info\nCompletely new wording.")

            await pilot.press(*"outreach")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "Completely new wording." in copied[0]
            assert "We build things" not in copied[0]

        drive(db_file, scenario, seed=seed_blocks)

    def test_a_missing_include_is_shown_rather_than_silently_dropped(self, db_file, copied):
        def seed(conn):
            prompt_store.create(conn, "Broken\n{{@does-not-exist}}\ntail")

        async def scenario(app, pilot, conn):
            await pilot.press(*"broken")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            preview = str(app.screen.query_one("#preview-text").content)
            assert "does not exist" in preview

        drive(db_file, scenario, seed=seed)

    def test_choice_of_block_switches_what_is_inserted(self, db_file, copied):
        def seed(conn):
            prompt_store.create(conn, "Agency info\nAGENCY TEXT")
            prompt_store.create(conn, "Me profile\nMY TEXT")
            prompt_store.create(conn, "Persona template\n{{persona: @me-profile | @agency-info}}")

        async def scenario(app, pilot, conn):
            await pilot.press(*"persona temp")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            app.screen.query_one("#field-persona", Select).value = "@agency-info"
            await pilot.pause()
            await pilot.press("ctrl+enter")
            await pilot.pause()

            assert "AGENCY TEXT" in copied[0]
            assert "MY TEXT" not in copied[0]

        drive(db_file, scenario, seed=seed)

    def test_a_cycle_does_not_hang_the_app(self, db_file, copied):
        def seed(conn):
            a = prompt_store.create(conn, "Block a\n{{@block-b}}")
            prompt_store.create(conn, "Block b\n{{@block-a}}")
            return a

        async def scenario(app, pilot, conn):
            await pilot.press(*"block a")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            assert app.is_running
            preview = str(app.screen.query_one("#preview-text").content)
            assert "cycle" in preview.lower()

        drive(db_file, scenario, seed=seed)


class TestEditorAwareness:
    def test_the_editor_reports_who_depends_on_a_block(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"agency")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()

            meta = str(app.screen.query_one("#editor-meta").content)
            assert "used by 1 template" in meta

        drive(db_file, scenario, seed=seed_blocks)

    def test_a_missing_include_is_flagged_in_the_editor(self, db_file, copied):
        def seed(conn):
            prompt_store.create(conn, "Broken\n{{@nowhere}}")

        async def scenario(app, pilot, conn):
            await pilot.press(*"broken")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()

            meta = str(app.screen.query_one("#editor-meta").content)
            assert "@nowhere" in meta and "missing" in meta

        drive(db_file, scenario, seed=seed)


class TestBlockPicker:
    def test_ctrl_b_inserts_a_chosen_block(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"outreach")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            assert isinstance(app.screen, EditorScreen)

            await pilot.press("ctrl+b")
            await pilot.pause()
            assert isinstance(app.screen, PromptPicker)

            await pilot.press(*"me-pro")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            body = prompt_store.get_by_name(conn, "outreach-template").body
            assert "{{@me-profile}}" in body

        drive(db_file, scenario, seed=seed_blocks)

    def test_escaping_the_picker_inserts_nothing(self, db_file, copied):
        async def scenario(app, pilot, conn):
            before = prompt_store.get_by_name(conn, "outreach-template").body

            await pilot.press(*"outreach")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert isinstance(app.screen, EditorScreen)
            assert app.screen.query_one("#editor-body", TextArea).text == before

        drive(db_file, scenario, seed=seed_blocks)

    def test_the_picker_does_not_offer_the_prompt_being_edited(self, db_file, copied):
        """Offering it would be a one-click way to build a cycle."""

        async def scenario(app, pilot, conn):
            await pilot.press(*"agency")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()

            listing = app.screen.query_one("#picker-list")
            ids = [listing.get_option_at_index(i).id for i in range(listing.option_count)]
            assert "agency-info" not in ids

        drive(db_file, scenario, seed=seed_blocks)

    def test_the_filter_narrows_the_list(self, db_file, copied):
        async def scenario(app, pilot, conn):
            await pilot.press(*"outreach")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()

            listing = app.screen.query_one("#picker-list")
            assert listing.option_count == 2

            app.screen.query_one("#picker-filter", Input).value = "agency"
            await pilot.pause()
            assert listing.option_count == 1

        drive(db_file, scenario, seed=seed_blocks)
