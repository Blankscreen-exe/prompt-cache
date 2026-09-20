"""Trash: soft-deleted prompts, restorable until purged (F9)."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from prompt_cache.store import prompts as prompt_store


class TrashScreen(Screen[None]):
    """Restore or permanently remove deleted prompts."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "back", priority=True),
        Binding("enter", "restore", "restore", show=True),
        Binding("ctrl+x", "purge", "delete forever"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            yield Static(Text("Trash", style="bold"), id="trash-title")
            yield OptionList(id="trash-list")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_list()
        self.query_one("#trash-list", OptionList).focus()

    def refresh_list(self) -> None:
        listing = self.query_one("#trash-list", OptionList)
        listing.clear_options()
        deleted = prompt_store.list_trash(self.app.connection)
        if not deleted:
            listing.add_option(Option(Text("Trash is empty", style="dim italic"), disabled=True))
            return
        for prompt in deleted:
            row = Text(no_wrap=True, overflow="ellipsis")
            row.append(prompt.title, style="bold")
            if prompt.deleted_at:
                row.append(f"   deleted {prompt.deleted_at:%Y-%m-%d %H:%M}", style="dim")
            listing.add_option(Option(row, id=prompt.id))
        # Without this the list opens with nothing selected and enter is a no-op.
        listing.highlighted = 0

    def _selected_id(self) -> str | None:
        listing = self.query_one("#trash-list", OptionList)
        index = listing.highlighted
        if index is None:
            return None
        return listing.get_option_at_index(index).id

    @on(OptionList.OptionSelected, "#trash-list")
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.action_restore()

    def action_restore(self) -> None:
        prompt_id = self._selected_id()
        if prompt_id is None:
            return
        restored = prompt_store.restore(self.app.connection, prompt_id)
        self.notify(f"Restored · {restored.title}", timeout=2)
        self.refresh_list()

    def action_purge(self) -> None:
        prompt_id = self._selected_id()
        if prompt_id is None:
            return
        prompt = prompt_store.get(self.app.connection, prompt_id)
        prompt_store.purge(self.app.connection, prompt_id)
        title = prompt.title if prompt else "prompt"
        self.notify(f"Permanently deleted · {title}", severity="warning", timeout=3)
        self.refresh_list()

    def action_close(self) -> None:
        self.dismiss(None)
