"""A searchable prompt picker.

Used twice: choosing a block to include from the editor, and choosing the next template
when continuing a thread. Both are "find one prompt, fast", which is what the palette
already does — so this is the same idea in a modal.
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

from prompt_cache.core.models import Prompt
from prompt_cache.core.parser import parse
from prompt_cache.store import prompts as prompt_store


class PromptPicker(ModalScreen[Prompt | None]):
    """Choose a prompt. Dismisses with it, or with None."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel", "cancel", priority=True),
        Binding("down", "cursor_down", "", show=False, priority=True),
        Binding("up", "cursor_up", "", show=False, priority=True),
    ]

    def __init__(
        self,
        *,
        title: str = "Pick a prompt",
        exclude_id: str | None = None,
        templates_first: bool = False,
    ) -> None:
        super().__init__()
        self.picker_title = title
        self.exclude_id = exclude_id
        self.templates_first = templates_first

    def compose(self) -> ComposeResult:
        with Vertical(id="picker"):
            yield Static(Text(self.picker_title, style="bold"), id="picker-title")
            yield Input(placeholder="Filter…", id="picker-filter")
            yield OptionList(id="picker-list")

    def on_mount(self) -> None:
        self.refresh_list()
        self.query_one("#picker-filter", Input).focus()

    @property
    def _list(self) -> OptionList:
        return self.query_one("#picker-list", OptionList)

    def _candidates(self) -> list[Prompt]:
        query = self.query_one("#picker-filter", Input).value.strip().lower()
        items = [
            prompt
            for prompt in prompt_store.list_live(self.app.connection)
            if prompt.id != self.exclude_id
            and (not query or query in prompt.name or query in prompt.title.lower())
        ]
        if self.templates_first:
            # A thread is continued with a template; a plain prompt has nothing to fill.
            items.sort(key=lambda p: (not parse(p.body).is_template, -p.use_count))
        return items

    def refresh_list(self) -> None:
        self._list.clear_options()
        candidates = self._candidates()
        if not candidates:
            self._list.add_option(
                Option(Text("Nothing matches", style="dim italic"), disabled=True)
            )
            return

        for prompt in candidates:
            row = Text(no_wrap=True, overflow="ellipsis")
            row.append(prompt.title, style="bold")
            template = parse(prompt.body)
            if template.blanks:
                count = len(template.blanks)
                row.append(f"   {count} blank{'s' if count != 1 else ''}", style="dim")
            row.append(f"   @{prompt.name}", style="cyan")
            self._list.add_option(Option(row, id=prompt.id))
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
        if not option.id:
            return
        prompt = prompt_store.get(self.app.connection, option.id)
        if prompt is not None:
            self.dismiss(prompt)

    def action_cursor_down(self) -> None:
        self._list.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._list.action_cursor_up()

    def action_cancel(self) -> None:
        self.dismiss(None)
