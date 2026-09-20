"""The Textual application shell.

M0 is the frame only: a focused search box, a footer of bindings, and a clean exit.
The search palette itself arrives in M1 (docs/07-roadmap.md).
"""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Input, Static

from prompt_cache.paths import db_path


class PromptCacheApp(App[None]):
    """Search-first, keyboard-first. Everything starts from the box at the top."""

    CSS_PATH = "app.tcss"
    TITLE = "prompt-cache"

    # Textual's own command palette binds ctrl+p, which docs/04-ui.md reserves for pin. This
    # app is already search-first, so a second palette would only confuse things.
    ENABLE_COMMAND_PALETTE = False

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "quit", priority=True),
        Binding("escape", "clear_search", "clear"),
    ]

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self.connection = connection

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            yield Input(placeholder="Search prompts…", id="search")
            yield Static(
                "Nothing here yet.\n\n"
                "Prompts, search and fill arrive in M1 and M2.\n"
                f"Database: {db_path()}",
                id="results",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search", Input).focus()

    def action_clear_search(self) -> None:
        """Esc empties the search box and returns focus to it."""
        search = self.query_one("#search", Input)
        search.value = ""
        search.focus()
