"""Version history: what a prompt used to be, and how to get it back.

Restoring never destroys anything — the text being replaced is snapshotted first, so
you can always undo an undo.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from prompt_cache.core import diffing
from prompt_cache.store import prompts as prompt_store

DIFF_STYLES = {"+": "green", "-": "red", "@": "cyan"}


class HistoryScreen(Screen[None]):
    """Past versions of one prompt, diffed against what it says now."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "back", priority=True),
        Binding("ctrl+r", "restore", "restore this version", priority=True),
        Binding("down", "cursor_down", "", show=False, priority=True),
        Binding("up", "cursor_up", "", show=False, priority=True),
    ]

    def __init__(self, prompt_id: str) -> None:
        super().__init__()
        self.prompt_id = prompt_id

    def compose(self) -> ComposeResult:
        with Vertical(id="history-main"):
            yield Static(id="history-title")
            yield OptionList(id="history-list")
            yield Static(Text("changes since this version", style="dim"), classes="section-label")
            with VerticalScroll(id="history-diff"):
                yield Static(id="history-diff-text")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all()
        self.query_one("#history-list", OptionList).focus()

    @property
    def _list(self) -> OptionList:
        return self.query_one("#history-list", OptionList)

    def refresh_all(self) -> None:
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        if prompt is None:
            self.dismiss(None)
            return

        versions = prompt_store.versions_for(self.app.connection, self.prompt_id)

        title = Text(no_wrap=True, overflow="ellipsis")
        title.append(prompt.title, style="bold")
        count = len(versions)
        title.append(f"   {count} earlier version{'s' if count != 1 else ''}", style="dim")
        self.query_one("#history-title", Static).update(title)

        self._list.clear_options()
        if not versions:
            self._list.add_option(
                Option(
                    Text(
                        "No history yet — edit this prompt and it will appear here",
                        style="dim italic",
                    ),
                    disabled=True,
                )
            )
            self._show_diff(None)
            return

        for version in versions:
            added, removed = diffing.summarise(version.body, prompt.body)
            row = Text(no_wrap=True, overflow="ellipsis")
            if version.created_at:
                row.append(f"{version.created_at:%Y-%m-%d %H:%M}", style="bold")
            row.append(f"   +{added}", style="green")
            row.append(f" -{removed}", style="red")
            if version.title != prompt.title:
                row.append(f"   titled “{version.title}”", style="dim")
            self._list.add_option(Option(row, id=version.id))
        self._list.highlighted = 0
        self._show_diff(versions[0].id)

    def _show_diff(self, version_id: str | None) -> None:
        target = self.query_one("#history-diff-text", Static)
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        if prompt is None or version_id is None:
            target.update(Text("Nothing to compare.", style="dim italic"))
            return

        version = next(
            (
                candidate
                for candidate in prompt_store.versions_for(self.app.connection, self.prompt_id)
                if candidate.id == version_id
            ),
            None,
        )
        if version is None:
            target.update(Text("Nothing to compare.", style="dim italic"))
            return

        diff = diffing.unified(version.body, prompt.body, old_label="then", new_label="now")
        if not diff:
            target.update(Text("Identical to the current text.", style="dim italic"))
            return

        rendered = Text()
        for line in diff.splitlines():
            rendered.append(line + "\n", style=DIFF_STYLES.get(line[:1], ""))
        target.update(rendered)

    @on(OptionList.OptionHighlighted, "#history-list")
    def _on_highlight(self, event: OptionList.OptionHighlighted) -> None:
        self._show_diff(event.option.id)

    def _selected_version(self) -> str | None:
        index = self._list.highlighted
        if index is None:
            return None
        return self._list.get_option_at_index(index).id

    def action_restore(self) -> None:
        version_id = self._selected_version()
        if version_id is None:
            return
        prompt_store.restore_version(self.app.connection, self.prompt_id, version_id)
        self.notify("Restored · the replaced text is still in history", timeout=4)
        self.refresh_all()

    def action_cursor_down(self) -> None:
        self._list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._list.action_cursor_up()

    def action_close(self) -> None:
        self.dismiss(None)
