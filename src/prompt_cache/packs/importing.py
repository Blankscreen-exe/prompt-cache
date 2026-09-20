"""Reading a template pack.

Importing is previewed before it happens, because a pack can collide with prompts that
already exist and the user should decide rather than discover.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from prompt_cache.packs.exporting import MANIFEST_NAME, PROMPTS_DIR
from prompt_cache.store import prompts as prompt_store


class PackError(RuntimeError):
    """The folder is not a readable pack, with a message worth showing."""


class OnCollision(StrEnum):
    """What to do about a prompt whose slug already exists."""

    KEEP_BOTH = "keep both"
    SKIP = "skip"
    OVERWRITE = "overwrite"


@dataclass(frozen=True, slots=True)
class PackEntry:
    name: str
    title: str
    body: str
    tags: tuple[str, ...] = ()
    pinned: bool = False
    title_is_custom: bool = False
    collides: bool = False


@dataclass(slots=True)
class PackPreview:
    """What an import would bring in, and what it would collide with."""

    name: str
    entries: list[PackEntry] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def collisions(self) -> list[PackEntry]:
        return [entry for entry in self.entries if entry.collides]


@dataclass(frozen=True, slots=True)
class ImportResult:
    imported: int = 0
    skipped: int = 0
    overwritten: int = 0
    renamed: tuple[tuple[str, str], ...] = ()


def preview_pack(conn: sqlite3.Connection, source: Path | str) -> PackPreview:
    """Read a pack and report what importing it would do. Never writes."""
    source = Path(source)
    manifest_path = source / MANIFEST_NAME
    if not manifest_path.is_file():
        raise PackError(f"No {MANIFEST_NAME} in {source} — is that a pack folder?")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackError(f"{MANIFEST_NAME} is not valid JSON: {exc}") from exc

    preview = PackPreview(name=str(manifest.get("name") or source.name))
    existing = set(prompt_store.bodies_by_name(conn))

    for raw in manifest.get("prompts", []):
        name = str(raw.get("name") or "").strip()
        if not name:
            preview.problems.append("An entry has no name; skipped.")
            continue

        relative = str(raw.get("file") or f"{PROMPTS_DIR}/{name}.md")
        body_path = source / relative
        if not body_path.is_file():
            preview.problems.append(f"{name}: missing file {relative}")
            continue

        preview.entries.append(
            PackEntry(
                name=name,
                title=str(raw.get("title") or name),
                body=body_path.read_text(encoding="utf-8"),
                tags=tuple(raw.get("tags") or ()),
                pinned=bool(raw.get("pinned")),
                title_is_custom=bool(raw.get("title_is_custom")),
                collides=name in existing,
            )
        )

    if not preview.entries and not preview.problems:
        preview.problems.append("The pack contains no prompts.")
    return preview


def import_pack(
    conn: sqlite3.Connection,
    source: Path | str,
    *,
    on_collision: OnCollision = OnCollision.KEEP_BOTH,
    only: list[str] | None = None,
) -> ImportResult:
    """Bring a pack in, deciding collisions by `on_collision`."""
    preview = preview_pack(conn, source)
    wanted = set(only) if only is not None else None

    imported = skipped = overwritten = 0
    renamed: list[tuple[str, str]] = []

    for entry in preview.entries:
        if wanted is not None and entry.name not in wanted:
            continue

        if entry.collides:
            if on_collision is OnCollision.SKIP:
                skipped += 1
                continue
            if on_collision is OnCollision.OVERWRITE:
                current = prompt_store.get_by_name(conn, entry.name)
                if current is not None:
                    # force_version so the replaced text stays recoverable.
                    prompt_store.update_body(conn, current.id, entry.body, force_version=True)
                    overwritten += 1
                    continue

        created = prompt_store.create(
            conn,
            entry.body,
            title=entry.title if entry.title_is_custom else None,
        )
        if created.name != entry.name:
            renamed.append((entry.name, created.name))
        if entry.pinned and not created.pinned:
            prompt_store.toggle_pin(conn, created.id)
        imported += 1

    return ImportResult(
        imported=imported,
        skipped=skipped,
        overwritten=overwritten,
        renamed=tuple(renamed),
    )
