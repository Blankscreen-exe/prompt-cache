"""The Textual application shell.

Owns the database connection and installs the search palette as the home screen.
"""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from textual.app import App
from textual.binding import Binding
from textual.screen import Screen

from prompt_cache.ui.screens.search import SearchScreen


class PromptCacheApp(App[None]):
    """Search-first, keyboard-first. Everything starts from the box at the top."""

    CSS_PATH = "app.tcss"
    TITLE = "prompt-cache"

    # Textual's own command palette binds ctrl+p, which docs/04-ui.md reserves for pin. This
    # app is already search-first, so a second palette would only confuse things.
    ENABLE_COMMAND_PALETTE = False

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+q", "quit", "quit", priority=True),
    ]

    def __init__(self, connection: sqlite3.Connection) -> None:
        super().__init__()
        self.connection = connection

    def get_default_screen(self) -> Screen:
        return SearchScreen()
