"""The prompt editor.

No save button and no dialogs (D4): the body autosaves as you type, the first line
becomes the title, and `#tags` are picked up. Esc goes back.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Static, TextArea

from prompt_cache import clipboard
from prompt_cache.store import prompts as prompt_store

# Long enough that typing does not thrash the database, short enough that Esc never
# races the save.
AUTOSAVE_DELAY = 0.4


class EditorScreen(Screen[None]):
    """Edit one prompt. Everything is derived from the body."""

    # escape is priority because TextArea would otherwise consume it. Deleting a
    # prompt deliberately lives on the search screen, not here: ctrl+d is
    # "delete character" inside a TextArea and must stay that way.
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "back", priority=True),
        Binding("ctrl+s", "save_now", "save", priority=True),
        Binding("ctrl+r", "copy_raw", "copy raw", priority=True),
    ]

    def __init__(self, prompt_id: str) -> None:
        super().__init__()
        self.prompt_id = prompt_id
        self._timer = None
        self._dirty = False

    def compose(self) -> ComposeResult:
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        body = prompt.body if prompt else ""
        with Vertical(id="editor-main"):
            yield Static(id="editor-meta")
            yield TextArea(body, id="editor-body", soft_wrap=True, tab_behavior="indent")
        yield Footer()

    def on_mount(self) -> None:
        area = self.query_one("#editor-body", TextArea)
        area.focus()
        area.cursor_location = area.document.end
        self._refresh_meta()

    # ------------------------------------------------------------------ saving

    @on(TextArea.Changed, "#editor-body")
    def _on_changed(self) -> None:
        self._dirty = True
        if self._timer is not None:
            self._timer.stop()
        self._timer = self.set_timer(AUTOSAVE_DELAY, self._save)

    def _save(self) -> None:
        if not self._dirty:
            return
        body = self.query_one("#editor-body", TextArea).text
        try:
            prompt_store.update_body(self.app.connection, self.prompt_id, body)
        except KeyError:
            # The prompt was deleted from under us; nothing to save into.
            self._dirty = False
            return
        self._dirty = False
        self._refresh_meta()

    def _refresh_meta(self) -> None:
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        if prompt is None:
            return
        line = Text(no_wrap=True, overflow="ellipsis")
        line.append(prompt.title or "Untitled", style="bold")
        line.append(f"   {prompt.name}", style="dim")
        if prompt.tags:
            line.append("   " + " ".join(f"#{tag}" for tag in prompt.tags), style="cyan")
        line.append("   saved", style="dim italic")
        self.query_one("#editor-meta", Static).update(line)

    # ---------------------------------------------------------------- actions

    def action_save_now(self) -> None:
        self._save()
        self.notify("Saved", timeout=1)

    def action_close(self) -> None:
        """Esc: flush the pending autosave before leaving, so nothing is lost."""
        if self._timer is not None:
            self._timer.stop()
        self._save()
        self._discard_if_empty()
        self.dismiss(None)

    def _discard_if_empty(self) -> None:
        """A prompt created and left blank is noise; drop it rather than keep it.

        This keeps Ctrl+N followed by Esc from littering the list.
        """
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        if prompt is not None and not prompt.body.strip() and prompt.use_count == 0:
            prompt_store.purge(self.app.connection, self.prompt_id)

    def action_copy_raw(self) -> None:
        self._save()
        prompt = prompt_store.get(self.app.connection, self.prompt_id)
        if prompt is None:
            return
        try:
            clipboard.write_text(prompt.body)
        except clipboard.ClipboardUnavailable as exc:
            self.notify(str(exc), severity="error", timeout=8)
            return
        prompt_store.mark_used(self.app.connection, prompt.id)
        self.notify("Copied", timeout=2)
