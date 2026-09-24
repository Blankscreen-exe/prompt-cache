"""The fill form.

One field per blank, a live preview underneath, and Ctrl+Enter to put the finished
prompt on the clipboard. Values that came from somewhere carry a badge saying where, so
it is obvious at a glance what was pre-filled and what still needs typing.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Select, Static, TextArea

from prompt_cache import clipboard
from prompt_cache.core.parser import Blank, parse
from prompt_cache.core.render import ValueSource, initial_values, render, resolve
from prompt_cache.store import conversations as conversation_store
from prompt_cache.store import prompts as prompt_store

FIELD_PREFIX = "field-"


def _field_id(blank: Blank) -> str:
    return f"{FIELD_PREFIX}{blank.name}"


class FillScreen(Screen[None]):
    """Fill a template's blanks and copy the result."""

    # Ctrl+Enter confirms because plain Enter must insert a newline in a TextArea.
    # Both are priority: TextArea and Select bind several of these themselves.
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "back", priority=True),
        Binding("ctrl+enter", "copy", "copy prompt", priority=True),
        Binding("ctrl+j", "copy", "copy prompt", show=False, priority=True),
        Binding("ctrl+e", "edit_template", "edit template", priority=True),
    ]

    def __init__(self, prompt_id: str, conversation_id: str | None = None) -> None:
        super().__init__()
        self.prompt_id = prompt_id
        # Set when continuing an existing thread; otherwise the first fill starts one.
        self.conversation_id = conversation_id
        # Both are filled in compose(), once the app (and its connection) is reachable.
        self.template = resolve(parse(""))
        self.sources: dict[str, ValueSource] = {}

    def compose(self) -> ComposeResult:
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        body = prompt.body if prompt else ""
        # Blocks are every other live prompt, so a block's own blanks join this form.
        blocks = prompt_store.bodies_by_name(self.app.connection)
        self.template = resolve(parse(body), blocks)

        thread = (
            conversation_store.get(self.app.connection, self.conversation_id)
            if self.conversation_id
            else None
        )
        prefill = initial_values(
            self.template,
            clipboard_text=clipboard.read_text_or_empty(),
            conversation=thread.values if thread else None,
        )
        self.sources = prefill.sources

        title = Text(no_wrap=True, overflow="ellipsis")
        title.append(prompt.title if prompt else "Untitled", style="bold")
        title.append(
            f"   {'continuing: ' + thread.label if thread else 'new thread'}",
            style="dim italic",
        )
        blank_count = len(self.template.blanks)
        title.append(f"   {blank_count} blank{'s' if blank_count != 1 else ''}", style="dim")
        if self.template.used_blocks:
            title.append("   " + " ".join(f"@{b}" for b in self.template.used_blocks), style="cyan")
        if self.template.missing_blocks:
            title.append(
                "   missing: " + " ".join(f"@{b}" for b in self.template.missing_blocks),
                style="bold yellow",
            )

        with Vertical(id="fill-main"):
            yield Static(title, id="fill-title")
            with VerticalScroll(id="fill-fields"):
                for blank in self.template.blanks:
                    yield Static(self._label_for(blank), classes="field-label")
                    yield self._widget_for(blank, prefill.values.get(blank.name, ""))
            yield Static(Text("preview", style="dim"), id="preview-label")
            with VerticalScroll(id="fill-preview"):
                yield Static(id="preview-text")
            yield Button("Copy prompt", id="copy-button", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.update_preview()
        self._focus_first_gap()

    # ------------------------------------------------------------------ fields

    def _label_for(self, blank: Blank) -> Text:
        label = Text()
        label.append(blank.display_name.upper(), style="bold")
        source = self.sources.get(blank.name, ValueSource.EMPTY)
        if source.value:
            label.append(f"   {source.value}", style="dim italic")
        if blank.optional:
            label.append("   optional", style="dim")
        return label

    def _widget_for(self, blank: Blank, value: str):
        if blank.is_choice:
            options = [(option.label, option.label) for option in blank.options]
            allowed = {option.label for option in blank.options}
            return Select(
                options,
                value=value if value in allowed else Select.BLANK,
                id=_field_id(blank),
                allow_blank=True,
            )
        return TextArea(value, id=_field_id(blank), soft_wrap=True)

    def current_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for blank in self.template.blanks:
            widget = self.query_one(f"#{_field_id(blank)}")
            if isinstance(widget, Select):
                raw = widget.value
                values[blank.name] = "" if raw is Select.BLANK else str(raw)
            else:
                values[blank.name] = widget.text
        return values

    def _focus_first_gap(self) -> None:
        """Focus the first field still needing input, else the copy button.

        When everything is pre-filled, the whole flow is one keypress.
        """
        values = self.current_values()
        for blank in self.template.blanks:
            if blank.optional:
                continue
            if not values.get(blank.name, "").strip():
                self.query_one(f"#{_field_id(blank)}").focus()
                return
        self.query_one("#copy-button", Button).focus()

    # ----------------------------------------------------------------- preview

    def update_preview(self) -> None:
        result = render(self.template, self.current_values())

        preview = Text()
        preview.append(result.text or "(empty)", style="" if result.text else "dim italic")
        if result.missing:
            preview.append("\n\nstill empty: ", style="dim")
            preview.append(", ".join(result.missing), style="yellow")
        for warning in result.warnings:
            preview.append(f"\n! {warning.message}", style="yellow")
        self.query_one("#preview-text", Static).update(preview)

    @on(TextArea.Changed)
    def _on_text_changed(self) -> None:
        self.update_preview()

    @on(Select.Changed)
    def _on_select_changed(self, event: Select.Changed) -> None:
        # A value the user picked is no longer "from" anywhere.
        name = (event.select.id or "")[len(FIELD_PREFIX) :]
        self.sources.pop(name, None)
        self.update_preview()

    @on(Button.Pressed, "#copy-button")
    def _on_copy_button(self) -> None:
        self.action_copy()

    # ----------------------------------------------------------------- actions

    def action_copy(self) -> None:
        result = render(self.template, self.current_values())
        try:
            clipboard.write_text(result.text)
        except clipboard.ClipboardUnavailable as exc:
            self.notify(str(exc), severity="error", timeout=8)
            return

        prompt_store.mark_used(self.app.connection, self.prompt_id)
        fill = conversation_store.add_fill(
            self.app.connection,
            prompt_id=self.prompt_id,
            values=self.current_values(),
            output=result.text,
            conversation_id=self.conversation_id,
        )
        self.conversation_id = fill.conversation_id

        if result.missing:
            self.notify(
                f"Copied, but {', '.join(result.missing)} was left empty",
                severity="warning",
                timeout=4,
            )
        else:
            self.notify("Copied · saved to thread", timeout=2)
        self.dismiss(None)

    def action_edit_template(self) -> None:
        from prompt_cache.ui.screens.editor import EditorScreen

        self.app.push_screen(EditorScreen(self.prompt_id), lambda _: self.dismiss(None))

    def action_close(self) -> None:
        self.dismiss(None)
