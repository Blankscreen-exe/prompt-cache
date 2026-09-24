"""A thread: what it knows, what has been sent, and what to send next.

The values panel is the point. Once a thread knows `post` and `my_comment`, continuing it
with a reply template fills those in by name, and the only thing left to supply is the
new reply — which comes from the clipboard.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from prompt_cache import clipboard
from prompt_cache.store import conversations as conversation_store

PREVIEW_CHARS = 70


class ConversationScreen(Screen[None]):
    """One thread, its values and its fill history."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "back", priority=True),
        Binding("ctrl+n", "continue_with", "continue with…", priority=True),
        Binding("ctrl+s", "set_from_clipboard", "value from clipboard", priority=True),
        Binding("ctrl+r", "copy_last", "copy last output", priority=True),
        Binding("ctrl+d", "delete_value", "delete value", priority=True),
    ]

    def __init__(self, conversation_id: str) -> None:
        super().__init__()
        self.conversation_id = conversation_id

    def compose(self) -> ComposeResult:
        with Vertical(id="thread-main"):
            yield Static(id="thread-title")
            yield Static(Text("values", style="dim"), classes="section-label")
            yield OptionList(id="thread-values")
            yield Input(
                placeholder="new value name… (ctrl+s saves the clipboard into it)",
                id="thread-value-name",
            )
            yield Static(Text("history", style="dim"), classes="section-label")
            with VerticalScroll(id="thread-history"):
                yield Static(id="thread-fills")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_all()
        self.query_one("#thread-values", OptionList).focus()

    # ------------------------------------------------------------------ render

    def refresh_all(self) -> None:
        thread = conversation_store.get(self.app.connection, self.conversation_id)
        if thread is None:
            self.dismiss(None)
            return

        title = Text(no_wrap=True, overflow="ellipsis")
        title.append(thread.label, style="bold")
        plural = "s" if thread.fill_count != 1 else ""
        title.append(f"   {thread.fill_count} fill{plural}", style="dim")
        if thread.templates:
            title.append("   " + " · ".join(thread.templates), style="dim italic")
        self.query_one("#thread-title", Static).update(title)

        values = self.query_one("#thread-values", OptionList)
        values.clear_options()
        if not thread.values:
            values.add_option(Option(Text("No values yet", style="dim italic"), disabled=True))
        else:
            for name in sorted(thread.values):
                row = Text(no_wrap=True, overflow="ellipsis")
                row.append(f"{name}", style="bold cyan")
                preview = " ".join(thread.values[name].split())[:PREVIEW_CHARS]
                row.append(f"   {preview}", style="dim")
                values.add_option(Option(row, id=name))
            values.highlighted = 0

        fills = conversation_store.fills_for(self.app.connection, self.conversation_id)
        history = Text()
        if not fills:
            history.append("Nothing sent yet.", style="dim italic")
        for fill in fills:
            history.append(f"{fill.prompt_title}", style="bold")
            if fill.created_at:
                history.append(f"   {fill.created_at:%Y-%m-%d %H:%M}", style="dim")
            history.append("\n")
            excerpt = " ".join(fill.output.split())[:160]
            history.append(f"  {excerpt}\n\n", style="dim")
        self.query_one("#thread-fills", Static).update(history)

    def _selected_value_name(self) -> str | None:
        values = self.query_one("#thread-values", OptionList)
        index = values.highlighted
        if index is None:
            return None
        return values.get_option_at_index(index).id

    # ---------------------------------------------------------------- actions

    @on(Input.Submitted, "#thread-value-name")
    def _on_name_submitted(self) -> None:
        self.action_set_from_clipboard()

    def action_set_from_clipboard(self) -> None:
        """Save the clipboard into a value — the typed name, else the selected one.

        This is how the comment you actually posted gets back into the thread, so the
        next follow-up already knows it.
        """
        name_input = self.query_one("#thread-value-name", Input)
        name = name_input.value.strip() or self._selected_value_name()
        if not name:
            self.notify("Type a value name first", severity="warning", timeout=3)
            return

        try:
            text = clipboard.read_text()
        except clipboard.ClipboardUnavailable as exc:
            self.notify(str(exc), severity="error", timeout=8)
            return
        if not text.strip():
            self.notify("Clipboard is empty", severity="warning", timeout=3)
            return

        conversation_store.set_value(self.app.connection, self.conversation_id, name, text)
        name_input.value = ""
        self.notify(f"Saved to {name}", timeout=2)
        self.refresh_all()

    def action_delete_value(self) -> None:
        name = self._selected_value_name()
        if not name:
            return
        conversation_store.remove_value(self.app.connection, self.conversation_id, name)
        self.notify(f"Removed {name}", timeout=2)
        self.refresh_all()

    def action_continue_with(self) -> None:
        """Pick the next template; its blanks pre-fill from this thread by name."""
        from prompt_cache.ui.screens.fill import FillScreen
        from prompt_cache.ui.screens.picker import PromptPicker

        def chosen(prompt) -> None:
            if prompt is None:
                return
            self.app.push_screen(
                FillScreen(prompt.id, conversation_id=self.conversation_id),
                lambda _: self.refresh_all(),
            )

        self.app.push_screen(PromptPicker(title="Continue with…", templates_first=True), chosen)

    def action_copy_last(self) -> None:
        fills = conversation_store.fills_for(self.app.connection, self.conversation_id)
        if not fills:
            self.notify("Nothing to copy yet", severity="warning", timeout=3)
            return
        try:
            clipboard.write_text(fills[0].output)
        except clipboard.ClipboardUnavailable as exc:
            self.notify(str(exc), severity="error", timeout=8)
            return
        self.notify("Copied last output", timeout=2)

    def action_close(self) -> None:
        self.dismiss(None)
