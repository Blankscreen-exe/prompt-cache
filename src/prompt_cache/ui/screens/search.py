"""The search palette — the home screen and the fast path.

Type, and results narrow as you go. Enter copies. Nothing matching offers to create a
prompt from whatever was typed, so writing and finding are the same motion (F2, F3).
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList
from textual.widgets.option_list import Option

from prompt_cache import clipboard
from prompt_cache.core.models import Prompt
from prompt_cache.core.parser import parse
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store import search as search_store

CREATE_ID = "__create__"
HEADER_PREFIX = "__header__"


def _row(prompt: Prompt) -> Text:
    """One result line. Built as rich Text so user titles cannot inject markup."""
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append("★ " if prompt.pinned else "  ", style="bold yellow" if prompt.pinned else "")
    text.append(prompt.title, style="bold")

    details: list[str] = []
    template = parse(prompt.body)
    if template.blanks:
        count = len(template.blanks)
        details.append(f"template · {count} blank{'s' if count != 1 else ''}")
    if prompt.tags:
        details.append(" ".join(f"#{tag}" for tag in prompt.tags))
    if prompt.use_count:
        details.append(f"{prompt.use_count}x")
    if details:
        text.append("   " + " · ".join(details), style="dim")

    if prompt.summary:
        text.append("\n    " + prompt.summary[:80], style="dim italic")
    return text


class SearchScreen(Screen):
    """Search box on top, ranked results beneath, bindings in the footer."""

    # `priority=True` throughout: the search box is an Input, and Input binds ctrl+e
    # (end) and ctrl+d (delete_right), which would otherwise swallow edit and delete.
    # In a palette the screen action is always what the user meant.
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "clear", "clear", priority=True),
        Binding("ctrl+n", "new_prompt", "new", priority=True),
        Binding("ctrl+e", "edit", "edit", priority=True),
        Binding("ctrl+p", "pin", "pin", priority=True),
        Binding("ctrl+t", "trash", "trash", priority=True),
        Binding("ctrl+d", "delete", "delete", priority=True),
        Binding("down", "cursor_down", "", show=False),
        Binding("up", "cursor_up", "", show=False),
        Binding("pagedown", "page_down", "", show=False),
        Binding("pageup", "page_up", "", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="main"):
            yield Input(placeholder="Search prompts…   (type to create a new one)", id="search")
            yield OptionList(id="results")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_results()
        self.query_one("#search", Input).focus()

    # ------------------------------------------------------------------ results

    @property
    def _results(self) -> OptionList:
        return self.query_one("#results", OptionList)

    @property
    def _query(self) -> str:
        return self.query_one("#search", Input).value

    def refresh_results(self) -> None:
        """Re-run the search and rebuild the list, keeping the first row selected."""
        results = search_store.search(self.app.connection, self._query)
        options: list[Option] = []

        multiple_groups = len(results.groups) > 1
        for group_name, hits in results.groups:
            if multiple_groups:
                options.append(
                    Option(
                        Text(group_name.upper(), style="dim bold"),
                        id=f"{HEADER_PREFIX}{group_name}",
                        disabled=True,
                    )
                )
            options.extend(Option(_row(hit.prompt), id=hit.prompt.id) for hit in hits)

        if results.create_label:
            label = Text(no_wrap=True, overflow="ellipsis")
            label.append("+ ", style="bold green")
            label.append("Create prompt: ")
            label.append(results.create_label, style="bold")
            options.append(Option(label, id=CREATE_ID))

        self._results.clear_options()
        if options:
            self._results.add_options(options)
            self._highlight_first_selectable()

    def _highlight_first_selectable(self) -> None:
        for index in range(self._results.option_count):
            if not self._results.get_option_at_index(index).disabled:
                self._results.highlighted = index
                return

    def _selected_prompt(self) -> Prompt | None:
        """The prompt under the cursor, or None if there isn't one."""
        index = self._results.highlighted
        if index is None:
            return None
        option = self._results.get_option_at_index(index)
        if option.id in (None, CREATE_ID) or option.id.startswith(HEADER_PREFIX):
            return None
        return prompt_store.get(self.app.connection, option.id)

    # ------------------------------------------------------------------ events

    @on(Input.Changed, "#search")
    def _on_query_changed(self) -> None:
        self.refresh_results()

    @on(Input.Submitted, "#search")
    def _on_submit(self) -> None:
        self.action_activate()

    @on(OptionList.OptionSelected, "#results")
    def _on_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.action_activate()

    # ---------------------------------------------------------------- actions

    def action_activate(self) -> None:
        """Enter: copy the selected prompt, or create one from the typed text."""
        index = self._results.highlighted
        if index is None:
            if self._query.strip():
                self.action_new_prompt(self._query)
            return

        option = self._results.get_option_at_index(index)
        if option.id == CREATE_ID:
            self.action_new_prompt(self._query)
            return

        prompt = self._selected_prompt()
        if prompt is None:
            return
        self._use(prompt)

    def _use(self, prompt: Prompt) -> None:
        """Enter: a template opens its fill form, a plain prompt copies straight out."""
        if parse(prompt.body).is_template:
            from prompt_cache.ui.screens.fill import FillScreen

            self.app.push_screen(FillScreen(prompt.id), lambda _: self._after_edit())
            return
        self._copy(prompt)

    def _copy(self, prompt: Prompt) -> None:
        try:
            clipboard.write_text(prompt.body)
        except clipboard.ClipboardUnavailable as exc:
            self.notify(str(exc), severity="error", timeout=8)
            return
        prompt_store.mark_used(self.app.connection, prompt.id)
        self.notify(f"Copied · {prompt.title}", timeout=2)
        self.refresh_results()

    def action_new_prompt(self, seed: str = "") -> None:
        from prompt_cache.ui.screens.editor import EditorScreen

        prompt = prompt_store.create(self.app.connection, seed)
        self.app.push_screen(EditorScreen(prompt.id), lambda _: self._after_edit())

    def action_edit(self) -> None:
        from prompt_cache.ui.screens.editor import EditorScreen

        prompt = self._selected_prompt()
        if prompt is None:
            return
        self.app.push_screen(EditorScreen(prompt.id), lambda _: self._after_edit())

    def _after_edit(self) -> None:
        self.refresh_results()
        self.query_one("#search", Input).focus()

    def action_pin(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            return
        updated = prompt_store.toggle_pin(self.app.connection, prompt.id)
        self.notify(f"{'Pinned' if updated.pinned else 'Unpinned'} · {updated.title}", timeout=2)
        self.refresh_results()

    def action_delete(self) -> None:
        prompt = self._selected_prompt()
        if prompt is None:
            return
        prompt_store.soft_delete(self.app.connection, prompt.id)
        self.notify(f"Deleted · {prompt.title}  (ctrl+t to restore)", timeout=4)
        self.refresh_results()

    def action_trash(self) -> None:
        from prompt_cache.ui.screens.trash import TrashScreen

        self.app.push_screen(TrashScreen(), lambda _: self._after_edit())

    def action_clear(self) -> None:
        search = self.query_one("#search", Input)
        search.value = ""
        search.focus()

    # Arrow keys move the result cursor while focus stays in the search box, so
    # typing and navigating never need a focus change.
    def action_cursor_down(self) -> None:
        self._results.action_cursor_down()

    def action_cursor_up(self) -> None:
        self._results.action_cursor_up()

    def action_page_down(self) -> None:
        self._results.action_page_down()

    def action_page_up(self) -> None:
        self._results.action_page_up()
