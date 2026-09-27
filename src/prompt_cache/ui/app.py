"""The Textual application shell.

Owns the database connection and installs the search palette as the home screen.
"""

from __future__ import annotations

import sqlite3
from typing import ClassVar

from textual import events
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

    async def on_event(self, event: events.Event) -> None:
        # Textual clears focus on AppBlur and only restores it on AppFocus, or early for a
        # Key or MouseDown. A terminal's "paste N KB?" confirmation blurs the app, and
        # Windows Terminal then sends the paste *before* the focus-in, so the Paste found
        # nothing focused and was silently dropped. Treat Paste like a keypress: it is proof
        # the user is back, so restore focus first and let it reach the widget.
        if isinstance(event, events.Paste) and not event.is_forwarded and not self.app_focus:
            self.app_focus = True
        await super().on_event(event)
