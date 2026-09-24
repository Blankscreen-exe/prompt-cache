"""M5 through the UI: history, the first-run offer, and settings."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, TextArea

from prompt_cache import clipboard
from prompt_cache.packs import examples as example_pack
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database
from prompt_cache.ui.app import PromptCacheApp
from prompt_cache.ui.screens.history import HistoryScreen
from prompt_cache.ui.screens.settings import SettingsScreen


@pytest.fixture(autouse=True)
def stub_clipboard(monkeypatch):
    monkeypatch.setattr(clipboard, "write_text", lambda _t: None)
    monkeypatch.setattr(clipboard, "read_text_or_empty", lambda: "")


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "m5ui.db"


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


def visible_ids(app) -> list[str]:
    listing = app.screen.query_one("#results", OptionList)
    return [
        listing.get_option_at_index(i).id
        for i in range(listing.option_count)
        if not listing.get_option_at_index(i).disabled
    ]


class TestFirstRun:
    def test_an_empty_database_offers_the_examples(self, db_file):
        async def scenario(app, pilot, conn):
            assert "__examples__" in visible_ids(app)

        drive(db_file, scenario)

    def test_accepting_installs_them_and_stops_offering(self, db_file):
        async def scenario(app, pilot, conn):
            await pilot.press("enter")
            await pilot.pause()

            names = {p.name for p in prompt_store.list_live(conn)}
            assert "social-comment" in names
            assert "social-voice" in names
            assert "__examples__" not in visible_ids(app), "offered once, not forever"

        drive(db_file, scenario)

    def test_a_database_with_prompts_is_never_offered_them(self, db_file):
        def seed(conn):
            prompt_store.create(conn, "Mine\nalready here")

        async def scenario(app, pilot, conn):
            assert "__examples__" not in visible_ids(app)

        drive(db_file, scenario, seed=seed)

    def test_the_examples_are_a_working_template_set(self, db_file):
        """They must actually resolve, not just import."""

        def seed(conn):
            example_pack.install_examples(conn)

        async def scenario(app, pilot, conn):
            from prompt_cache.core.render import render

            comment = prompt_store.get_by_name(conn, "social-comment")
            blocks = prompt_store.bodies_by_name(conn)
            result = render(comment.body, {"post": "A post", "persona": "@about-me"}, blocks)

            assert result.missing_blocks == (), "every example include must exist"
            assert not [w for w in result.warnings if "cycle" in w.message.lower()]
            assert "A post" in result.text

        drive(db_file, scenario, seed=seed)


class TestHistoryScreen:
    def seed_edited(self, conn):
        prompt = prompt_store.create(conn, "Draft\nthe original wording")
        prompt_store.update_body(conn, prompt.id, "Draft\ncompletely rewritten")
        return prompt

    def test_ctrl_h_opens_history_from_the_editor(self, db_file):
        async def scenario(app, pilot, conn):
            await pilot.press(*"draft")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            await pilot.press("ctrl+h")
            await pilot.pause()

            assert isinstance(app.screen, HistoryScreen)

        drive(db_file, scenario, seed=self.seed_edited)

    def test_the_diff_shows_what_changed(self, db_file):
        async def scenario(app, pilot, conn):
            prompt = prompt_store.list_live(conn)[0]
            app.push_screen(HistoryScreen(prompt.id))
            await pilot.pause()

            diff = str(app.screen.query_one("#history-diff-text").content)
            assert "the original wording" in diff
            assert "completely rewritten" in diff

        drive(db_file, scenario, seed=self.seed_edited)

    def test_restoring_brings_the_old_text_back_into_the_editor(self, db_file):
        async def scenario(app, pilot, conn):
            await pilot.press(*"draft")
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            await pilot.press("ctrl+h")
            await pilot.pause()
            await pilot.press("ctrl+r")
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()

            assert "the original wording" in app.screen.query_one("#editor-body", TextArea).text

        drive(db_file, scenario, seed=self.seed_edited)

    def test_a_prompt_with_no_history_says_so(self, db_file):
        def seed(conn):
            prompt_store.create(conn, "Fresh\nnever edited")

        async def scenario(app, pilot, conn):
            prompt = prompt_store.list_live(conn)[0]
            app.push_screen(HistoryScreen(prompt.id))
            await pilot.pause()

            assert "No history yet" in str(app.screen.query_one("#history-list").options[0].prompt)

        drive(db_file, scenario, seed=seed)


class TestSettingsScreen:
    def seed_one(self, conn):
        prompt_store.create(conn, "Exportable\nsome body")

    def test_it_opens_and_shows_the_database_path(self, db_file):
        async def scenario(app, pilot, conn):
            app.push_screen(SettingsScreen())
            await pilot.pause()

            title = str(app.screen.query_one("#settings-title").content)
            assert "prompt-cache.db" in title

        drive(db_file, scenario, seed=self.seed_one)

    def test_exporting_a_pack_writes_it(self, db_file, tmp_path):
        async def scenario(app, pilot, conn):
            app.push_screen(SettingsScreen())
            await pilot.pause()

            target = tmp_path / "exported"
            app.screen.query_one("#settings-path", Input).value = str(target)
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()

            assert (target / "pack.json").is_file()
            assert (target / "prompts" / "exportable.md").is_file()
            assert "Exported 1 prompts" in str(app.screen.query_one("#settings-status").content)

        drive(db_file, scenario, seed=self.seed_one)

    def test_a_full_backup_writes_a_json_file(self, db_file, tmp_path):
        async def scenario(app, pilot, conn):
            app.push_screen(SettingsScreen())
            await pilot.pause()

            target = tmp_path / "backup.json"
            app.screen.query_one("#settings-path", Input).value = str(target)
            await pilot.pause()
            await pilot.press("ctrl+b")
            await pilot.pause()

            assert target.is_file()
            assert "Exportable" in target.read_text(encoding="utf-8")

        drive(db_file, scenario, seed=self.seed_one)

    def test_importing_a_bad_path_reports_instead_of_crashing(self, db_file, tmp_path):
        async def scenario(app, pilot, conn):
            app.push_screen(SettingsScreen())
            await pilot.pause()

            app.screen.query_one("#settings-path", Input).value = str(tmp_path / "nope")
            await pilot.pause()
            await pilot.press("ctrl+i")
            await pilot.pause()

            assert app.is_running
            assert "pack" in str(app.screen.query_one("#settings-status").content).lower()

        drive(db_file, scenario, seed=self.seed_one)

    def test_a_pack_round_trips_through_the_ui(self, db_file, tmp_path):
        async def scenario(app, pilot, conn):
            app.push_screen(SettingsScreen())
            await pilot.pause()

            target = tmp_path / "rt"
            app.screen.query_one("#settings-path", Input).value = str(target)
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            await pilot.press("ctrl+i")
            await pilot.pause()

            names = sorted(p.name for p in prompt_store.list_live(conn))
            assert names == ["exportable", "exportable-2"], "re-import keeps both"

        drive(db_file, scenario, seed=self.seed_one)
