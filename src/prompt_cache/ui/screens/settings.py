"""Settings: where the data lives, how to move it, and what every key does."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from prompt_cache import __version__
from prompt_cache.packs import dump_backup, export_pack, import_pack, preview_pack
from prompt_cache.packs.importing import OnCollision, PackError
from prompt_cache.paths import DATA_DIR_ENV, db_path

BINDING_REFERENCE = [
    ("Search", "type to filter · ⏎ use · ^e edit · ^p pin · ^d delete · ^t trash · ^n new"),
    ("Editor", "autosaves · ^b include a block · ^h history · ^r copy raw · esc back"),
    ("Fill form", "tab between fields · ^⏎ copy · ^e edit the template · esc back"),
    ("Thread", "^n continue with… · ^s value from clipboard · ^r copy last · ^d drop value"),
    ("History", "↑↓ pick a version · ^r restore it · esc back"),
    ("Anywhere", "esc goes back one level · ^q quits"),
]


class SettingsScreen(Screen[None]):
    """Data location, packs, backup, and the full key reference."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close", "back", priority=True),
        Binding("ctrl+e", "export_pack", "export pack", priority=True),
        Binding("ctrl+i", "import_pack", "import pack", priority=True),
        Binding("ctrl+b", "backup", "full backup", priority=True),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-main"):
            yield Static(id="settings-title")
            yield Input(
                placeholder="folder or file path for export / import / backup…",
                id="settings-path",
            )
            yield Static(id="settings-status")
            with VerticalScroll(id="settings-body"):
                yield Static(id="settings-reference")
        yield Footer()

    def on_mount(self) -> None:
        title = Text()
        title.append("prompt-cache ", style="bold")
        title.append(f"v{__version__}\n", style="dim")
        title.append("database  ", style="dim")
        title.append(f"{db_path()}\n")
        title.append(f"override with ${DATA_DIR_ENV}", style="dim italic")
        self.query_one("#settings-title", Static).update(title)

        reference = Text()
        reference.append(
            "A pack holds prompts and blocks — never threads, so it is safe to share.\n"
            "A backup holds everything, including threads. Keep it to yourself.\n\n",
            style="dim",
        )
        for screen, keys in BINDING_REFERENCE:
            reference.append(f"{screen}\n", style="bold")
            reference.append(f"  {keys}\n\n", style="dim")
        self.query_one("#settings-reference", Static).update(reference)

        self.query_one("#settings-path", Input).focus()

    # ------------------------------------------------------------------ helpers

    def _path(self) -> Path | None:
        raw = self.query_one("#settings-path", Input).value.strip().strip('"')
        if not raw:
            self.notify("Type a path first", severity="warning", timeout=3)
            return None
        return Path(raw).expanduser()

    def _status(self, text: str, style: str = "") -> None:
        self.query_one("#settings-status", Static).update(Text(text, style=style))

    # ------------------------------------------------------------------ actions

    def action_export_pack(self) -> None:
        target = self._path()
        if target is None:
            return
        try:
            result = export_pack(self.app.connection, target)
        except OSError as exc:
            self._status(f"Could not write there: {exc}", "bold red")
            return
        self._status(f"Exported {result.prompt_count} prompts to {result.path}", "green")
        self.notify("Pack exported", timeout=3)

    def action_import_pack(self) -> None:
        source = self._path()
        if source is None:
            return
        try:
            preview = preview_pack(self.app.connection, source)
        except (PackError, OSError) as exc:
            self._status(str(exc), "bold red")
            return

        collisions = len(preview.collisions)
        result = import_pack(self.app.connection, source, on_collision=OnCollision.KEEP_BOTH)
        message = f"Imported {result.imported} prompts from “{preview.name}”"
        if collisions:
            message += f" · {collisions} renamed to avoid clashing with existing ones"
        if preview.problems:
            message += f" · {len(preview.problems)} skipped"
        self._status(message, "green")
        self.notify("Pack imported", timeout=3)

    def action_backup(self) -> None:
        target = self._path()
        if target is None:
            return
        if target.is_dir():
            target = target / "prompt-cache-backup.json"
        try:
            result = dump_backup(self.app.connection, target)
        except OSError as exc:
            self._status(f"Could not write there: {exc}", "bold red")
            return
        self._status(f"Backed up {result.total} rows to {result.path}", "green")
        self.notify("Backup written", timeout=3)

    @on(Input.Submitted, "#settings-path")
    def _on_submit(self) -> None:
        self._status("Choose: ^e export pack · ^i import pack · ^b full backup", "dim")

    def action_close(self) -> None:
        self.dismiss(None)
