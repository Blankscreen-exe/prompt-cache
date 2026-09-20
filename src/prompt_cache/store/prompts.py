"""Prompt persistence: create, autosave, pin, usage, soft delete, restore.

Titles, slugs and tags are all derived from the body by `core.slug` — the user never
names anything (D4). The FTS index is kept in step here, on every write.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime

from ulid import ULID

from prompt_cache.core.models import Prompt
from prompt_cache.core.slug import extract_tags, make_slug, title_from_body


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def new_id() -> str:
    """A ULID: lexicographically sortable by creation time."""
    return str(ULID())


def _row_to_prompt(row: sqlite3.Row, tags: tuple[str, ...] = ()) -> Prompt:
    return Prompt(
        id=row["id"],
        name=row["name"],
        title=row["title"],
        body=row["body"],
        title_is_custom=bool(row["title_is_custom"]),
        pinned=bool(row["pinned"]),
        use_count=row["use_count"],
        last_used_at=_parse(row["last_used_at"]),
        created_at=_parse(row["created_at"]),
        updated_at=_parse(row["updated_at"]),
        deleted_at=_parse(row["deleted_at"]),
        tags=tags,
    )


def _tags_for(conn: sqlite3.Connection, prompt_id: str) -> tuple[str, ...]:
    rows = conn.execute(
        "SELECT tag FROM prompt_tags WHERE prompt_id = ? ORDER BY rowid", (prompt_id,)
    )
    return tuple(row["tag"] for row in rows)


def unique_name(conn: sqlite3.Connection, base: str, *, exclude_id: str | None = None) -> str:
    """`base`, or `base-2`, `base-3`… until it is free.

    Soft-deleted prompts keep their name, so a restored prompt can still collide; this
    is the single place that decides.
    """
    candidate = base
    suffix = 1
    while True:
        row = conn.execute(
            "SELECT id FROM prompts WHERE name = ? AND (? IS NULL OR id != ?)",
            (candidate, exclude_id, exclude_id),
        ).fetchone()
        if row is None:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def _sync_derived(conn: sqlite3.Connection, prompt: Prompt) -> None:
    """Rewrite the tag rows and the FTS entry for one prompt."""
    conn.execute("DELETE FROM prompt_tags WHERE prompt_id = ?", (prompt.id,))
    conn.executemany(
        "INSERT OR IGNORE INTO prompt_tags (prompt_id, tag) VALUES (?, ?)",
        [(prompt.id, tag) for tag in prompt.tags],
    )
    conn.execute("DELETE FROM prompts_fts WHERE prompt_id = ?", (prompt.id,))
    if not prompt.is_deleted:
        conn.execute(
            "INSERT INTO prompts_fts (prompt_id, title, body, name, tags) VALUES (?, ?, ?, ?, ?)",
            (prompt.id, prompt.title, prompt.body, prompt.name, " ".join(prompt.tags)),
        )


def create(conn: sqlite3.Connection, body: str, *, title: str | None = None) -> Prompt:
    """Save a new prompt. Title and slug come from the body unless `title` is given."""
    now = _now()
    resolved_title = title if title is not None else title_from_body(body)
    prompt = Prompt(
        id=new_id(),
        name=unique_name(conn, make_slug(resolved_title)),
        title=resolved_title,
        body=body,
        title_is_custom=title is not None,
        created_at=_parse(now),
        updated_at=_parse(now),
        tags=extract_tags(body),
    )
    conn.execute(
        "INSERT INTO prompts (id, name, title, title_is_custom, body, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            prompt.id,
            prompt.name,
            prompt.title,
            int(prompt.title_is_custom),
            prompt.body,
            now,
            now,
        ),
    )
    _sync_derived(conn, prompt)
    return prompt


def get(conn: sqlite3.Connection, prompt_id: str) -> Prompt | None:
    row = conn.execute("SELECT * FROM prompts WHERE id = ?", (prompt_id,)).fetchone()
    return _row_to_prompt(row, _tags_for(conn, prompt_id)) if row else None


def get_by_name(conn: sqlite3.Connection, name: str) -> Prompt | None:
    row = conn.execute(
        "SELECT * FROM prompts WHERE name = ? AND deleted_at IS NULL", (name,)
    ).fetchone()
    return _row_to_prompt(row, _tags_for(conn, row["id"])) if row else None


def update_body(conn: sqlite3.Connection, prompt_id: str, body: str) -> Prompt:
    """Autosave. The title follows the first line unless the user overrode it.

    The slug is deliberately *not* regenerated: includes (`{{@name}}`) point at it, so
    renaming is an explicit action, never a side effect of typing.
    """
    existing = get(conn, prompt_id)
    if existing is None:
        raise KeyError(prompt_id)

    title = existing.title if existing.title_is_custom else title_from_body(body)
    now = _now()
    conn.execute(
        "UPDATE prompts SET body = ?, title = ?, updated_at = ? WHERE id = ?",
        (body, title, now, prompt_id),
    )
    updated = get(conn, prompt_id)
    assert updated is not None
    updated = replace(updated, tags=extract_tags(body))
    _sync_derived(conn, updated)
    return updated


def set_title(conn: sqlite3.Connection, prompt_id: str, title: str) -> Prompt:
    """Override the derived title. Marks it custom so the body stops driving it."""
    conn.execute(
        "UPDATE prompts SET title = ?, title_is_custom = 1, updated_at = ? WHERE id = ?",
        (title, _now(), prompt_id),
    )
    prompt = get(conn, prompt_id)
    if prompt is None:
        raise KeyError(prompt_id)
    _sync_derived(conn, prompt)
    return prompt


def rename(conn: sqlite3.Connection, prompt_id: str, name: str) -> Prompt:
    """Change the slug that includes point at, keeping it unique."""
    resolved = unique_name(conn, make_slug(name), exclude_id=prompt_id)
    conn.execute(
        "UPDATE prompts SET name = ?, updated_at = ? WHERE id = ?",
        (resolved, _now(), prompt_id),
    )
    prompt = get(conn, prompt_id)
    if prompt is None:
        raise KeyError(prompt_id)
    _sync_derived(conn, prompt)
    return prompt


def toggle_pin(conn: sqlite3.Connection, prompt_id: str) -> Prompt:
    conn.execute(
        "UPDATE prompts SET pinned = 1 - pinned, updated_at = ? WHERE id = ?",
        (_now(), prompt_id),
    )
    prompt = get(conn, prompt_id)
    if prompt is None:
        raise KeyError(prompt_id)
    return prompt


def mark_used(conn: sqlite3.Connection, prompt_id: str) -> None:
    """Record a copy or a fill. Feeds frecency ranking."""
    conn.execute(
        "UPDATE prompts SET use_count = use_count + 1, last_used_at = ? WHERE id = ?",
        (_now(), prompt_id),
    )


def soft_delete(conn: sqlite3.Connection, prompt_id: str) -> None:
    """Move to trash. Recoverable; drops out of search immediately."""
    conn.execute("UPDATE prompts SET deleted_at = ? WHERE id = ?", (_now(), prompt_id))
    conn.execute("DELETE FROM prompts_fts WHERE prompt_id = ?", (prompt_id,))


def restore(conn: sqlite3.Connection, prompt_id: str) -> Prompt:
    """Bring a prompt back from trash, re-resolving its name if it was taken."""
    existing = get(conn, prompt_id)
    if existing is None:
        raise KeyError(prompt_id)
    name = unique_name(conn, existing.name, exclude_id=prompt_id)
    conn.execute(
        "UPDATE prompts SET deleted_at = NULL, name = ?, updated_at = ? WHERE id = ?",
        (name, _now(), prompt_id),
    )
    prompt = get(conn, prompt_id)
    assert prompt is not None
    _sync_derived(conn, prompt)
    return prompt


def purge(conn: sqlite3.Connection, prompt_id: str) -> None:
    """Delete for real. Only ever called from the trash view."""
    conn.execute("DELETE FROM prompts WHERE id = ?", (prompt_id,))
    conn.execute("DELETE FROM prompts_fts WHERE prompt_id = ?", (prompt_id,))


def _list(conn: sqlite3.Connection, where: str, params: tuple = ()) -> list[Prompt]:
    rows = conn.execute(f"SELECT * FROM prompts WHERE {where}", params).fetchall()
    return [_row_to_prompt(row, _tags_for(conn, row["id"])) for row in rows]


def list_live(conn: sqlite3.Connection) -> list[Prompt]:
    """Every prompt not in the trash, newest first."""
    return _list(conn, "deleted_at IS NULL ORDER BY updated_at DESC")


def list_trash(conn: sqlite3.Connection) -> list[Prompt]:
    return _list(conn, "deleted_at IS NOT NULL ORDER BY deleted_at DESC")


def count_live(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) FROM prompts WHERE deleted_at IS NULL").fetchone()[0]
