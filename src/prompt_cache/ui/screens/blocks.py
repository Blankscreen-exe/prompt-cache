"""Pick a block to include.

The roadmap asked for autocomplete on `{{@` in the editor. A searchable picker does the
same job better in a terminal: no popup chasing the cursor, no guessing when to trigger,
and it doubles as a way to see what blocks exist at all.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from prompt_cache.store import prompts as prompt_store


class BlockPicker(ModalScreen[str | None]):
    """Choose a prompt to include. Dismisses with its slug, or None."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "cancel", priority=True),
        Binding("down", "cursor_down", "", show=False, priority=True),
        Binding("up", "cursor_up", "", show=False, priority=True),
    ]

    def __init__(self, exclude_id: str | None = None) -> None:
        super().__init__()
        self.exclude_id = exclude_id

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static(Text("Include a block", style="bold"), id="picker-title")
            yield Input(placeholder="Filter blocks…", id="picker-filter")
            yield OptionList(id="picker-list")

    def on_mount(self) -> None:
        self.refresh_list()
        self.query_one("#picker-filter", Input).focus()

    @property
    def _list(self) -> OptionList:
        return self.query_one("#picker-list", OptionList)

    def refresh_list(self) -> None:
        query = self.query_one("#picker-filter", Input).value.strip().lower()
        self._list.clear_options()

        candidates = [
            prompt
            for prompt in prompt_store.list_live(self.app.connection)
            if prompt.id != self.exclude_id
            and (not query or query in prompt.name or query in prompt.title.lower())
        ]
        if not candidates:
            self._list.add_option(
                Option(Text("No blocks match", style="dim italic"), disabled=True)
            )
            return

        for prompt in candidates:
            row = Text(no_wrap=True, overflow="ellipsis")
            row.append(f"@{prompt.name}", style="bold cyan")
            row.append(f"   {prompt.title}", style="dim")
            self._list.add_option(Option(row, id=prompt.name))
        self._list.highlighted = 0

    @on(Input.Changed, "#picker-filter")
    def _on_filter(self) -> None:
        self.refresh_list()

    @on(Input.Submitted, "#picker-filter")
    def _on_submit(self) -> None:
        self._choose()

    @on(OptionList.OptionSelected, "#picker-list")
    def _on_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._choose()

    def _choose(self) -> None:
        index = self._list.highlighted
        if index is None:
            return
        option = self._list.get_option_at_index(index)
        if option.id:
            self.dismiss(option.id)

    def action_cursor_down(self) -> None:
        self._list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._list.action_cursor_up()

    def action_cancel(self) -> None:
        self.dismiss(None)
