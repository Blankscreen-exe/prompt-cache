"""Smoke tests for the Textual shell.

Driven headlessly through Textual's own pilot, so "it opens and quits cleanly" is verified
rather than assumed. ``asyncio.run`` keeps this free of a pytest-asyncio dependency.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input

from prompt_cache.store.db import database
from prompt_cache.ui.app import PromptCacheApp


def run(coro) -> None:
    asyncio.run(coro)


@pytest.fixture
def db_file(tmp_path: Path) -> Path:
    return tmp_path / "app.db"


def test_app_starts_and_exits_cleanly(db_file: Path):
    async def scenario():
        with database(db_file) as connection:
            app = PromptCacheApp(connection)
            async with app.run_test() as pilot:
                await pilot.pause()
            assert app.return_code in (0, None)

    run(scenario())


def test_search_box_has_focus_on_open(db_file: Path):
    async def scenario():
        with database(db_file) as connection:
            app = PromptCacheApp(connection)
            async with app.run_test() as pilot:
                await pilot.pause()
                assert app.focused is app.query_one("#search", Input)

    run(scenario())


def test_typing_lands_in_the_search_box(db_file: Path):
    async def scenario():
        with database(db_file) as connection:
            app = PromptCacheApp(connection)
            async with app.run_test() as pilot:
                await pilot.press("l", "i", "n")
                assert app.query_one("#search", Input).value == "lin"

    run(scenario())


def test_escape_clears_the_search_box(db_file: Path):
    async def scenario():
        with database(db_file) as connection:
            app = PromptCacheApp(connection)
            async with app.run_test() as pilot:
                await pilot.press("l", "i", "n")
                await pilot.press("escape")
                search = app.query_one("#search", Input)
                assert search.value == ""
                assert app.focused is search

    run(scenario())


def test_ctrl_q_quits(db_file: Path):
    async def scenario():
        with database(db_file) as connection:
            app = PromptCacheApp(connection)
            async with app.run_test() as pilot:
                await pilot.press("ctrl+q")
                await pilot.pause()
            assert not app.is_running

    run(scenario())


def test_ctrl_p_is_not_stolen_by_textuals_command_palette(db_file: Path):
    """docs/04-ui.md reserves ctrl+p for pin, so the built-in palette must stay off."""

    async def scenario():
        with database(db_file) as connection:
            app = PromptCacheApp(connection)
            async with app.run_test() as pilot:
                await pilot.press("ctrl+p")
                await pilot.pause()
                assert app.screen is app.screen_stack[0], "a palette screen was pushed"

    run(scenario())
