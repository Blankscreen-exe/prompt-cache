"""Conversation and fill persistence.

A conversation is created automatically by the first fill of a template and named from
its own content (D4 — the user never names anything). Its values merge by **blank name**,
which is the entire mechanism behind follow-ups: `post` in one template pre-fills `post`
in the next because the names match.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

from ulid import ULID

from prompt_cache.core.labels import label_from_values
from prompt_cache.core.models import Conversation, Fill


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _loads(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _values_text(values: dict[str, str]) -> str:
    """Everything searchable about a conversation's values, flattened for FTS."""
    return " ".join(f"{name} {value}" for name, value in values.items())


def _sync_fts(conn: sqlite3.Connection, conversation: Conversation) -> None:
    conn.execute("DELETE FROM conversations_fts WHERE conversation_id = ?", (conversation.id,))
    if conversation.deleted_at is None:
        conn.execute(
            "INSERT INTO conversations_fts (conversation_id, label, values_text) VALUES (?, ?, ?)",
            (conversation.id, conversation.label, _values_text(conversation.values)),
        )


def _row_to_conversation(conn: sqlite3.Connection, row: sqlite3.Row) -> Conversation:
    stats = conn.execute(
        "SELECT count(*) AS n FROM fills WHERE conversation_id = ?", (row["id"],)
    ).fetchone()
    templates = conn.execute(
        "SELECT DISTINCT p.title FROM fills f JOIN prompts p ON p.id = f.prompt_id"
        " WHERE f.conversation_id = ? ORDER BY f.created_at",
        (row["id"],),
    ).fetchall()
    return Conversation(
        id=row["id"],
        label=row["label"],
        label_is_custom=bool(row["label_is_custom"]),
        values=_loads(row["values_json"]),
        fill_count=stats["n"],
        templates=tuple(t["title"] for t in templates),
        created_at=_parse(row["created_at"]),
        updated_at=_parse(row["updated_at"]),
        archived_at=_parse(row["archived_at"]),
        deleted_at=_parse(row["deleted_at"]),
    )


def create(
    conn: sqlite3.Connection,
    values: dict[str, str] | None = None,
    *,
    label: str | None = None,
) -> Conversation:
    """Start a thread. The label is derived unless one is given."""
    values = dict(values or {})
    now = _now()
    conversation = Conversation(
        id=str(ULID()),
        label=label if label is not None else label_from_values(values),
        label_is_custom=label is not None,
        values=values,
        created_at=_parse(now),
        updated_at=_parse(now),
    )
    conn.execute(
        "INSERT INTO conversations (id, label, label_is_custom, values_json,"
        " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            conversation.id,
            conversation.label,
            int(conversation.label_is_custom),
            json.dumps(conversation.values),
            now,
            now,
        ),
    )
    _sync_fts(conn, conversation)
    return conversation


def get(conn: sqlite3.Connection, conversation_id: str) -> Conversation | None:
    row = conn.execute("SELECT * FROM conversations WHERE id = ?", (conversation_id,)).fetchone()
    return _row_to_conversation(conn, row) if row else None


def merge_values(
    conn: sqlite3.Connection, conversation_id: str, values: dict[str, str]
) -> Conversation:
    """Fold new values in by name. Later values win; empty ones never overwrite.

    An empty value is treated as "nothing to say", not as "erase what you knew" — a
    follow-up template with a blank field must not wipe the thread's memory of it.
    """
    conversation = get(conn, conversation_id)
    if conversation is None:
        raise KeyError(conversation_id)

    merged = dict(conversation.values)
    for name, value in values.items():
        if value and value.strip():
            merged[name] = value

    label = conversation.label
    if not conversation.label_is_custom:
        label = label_from_values(merged)

    conn.execute(
        "UPDATE conversations SET values_json = ?, label = ?, updated_at = ? WHERE id = ?",
        (json.dumps(merged), label, _now(), conversation_id),
    )
    updated = get(conn, conversation_id)
    assert updated is not None
    _sync_fts(conn, updated)
    return updated


def set_value(
    conn: sqlite3.Connection, conversation_id: str, name: str, value: str
) -> Conversation:
    """Set one value directly, e.g. saving the comment actually posted."""
    return merge_values(conn, conversation_id, {name.strip().lower(): value})


def remove_value(conn: sqlite3.Connection, conversation_id: str, name: str) -> Conversation:
    """Forget one value. Useful when a stale field keeps pre-filling a follow-up."""
    conversation = get(conn, conversation_id)
    if conversation is None:
        raise KeyError(conversation_id)
    remaining = {k: v for k, v in conversation.values.items() if k != name}
    conn.execute(
        "UPDATE conversations SET values_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(remaining), _now(), conversation_id),
    )
    updated = get(conn, conversation_id)
    assert updated is not None
    _sync_fts(conn, updated)
    return updated


def set_label(conn: sqlite3.Connection, conversation_id: str, label: str) -> Conversation:
    conn.execute(
        "UPDATE conversations SET label = ?, label_is_custom = 1, updated_at = ? WHERE id = ?",
        (label, _now(), conversation_id),
    )
    conversation = get(conn, conversation_id)
    if conversation is None:
        raise KeyError(conversation_id)
    _sync_fts(conn, conversation)
    return conversation


def add_fill(
    conn: sqlite3.Connection,
    *,
    prompt_id: str,
    values: dict[str, str],
    output: str,
    conversation_id: str | None = None,
    prompt_version_id: str | None = None,
) -> Fill:
    """Record one use of a template, starting a thread if there is not one yet.

    `output` is the fully assembled text, so editing a block later never rewrites what
    was actually sent.
    """
    if conversation_id is None:
        conversation_id = create(conn, values).id
    else:
        merge_values(conn, conversation_id, values)

    now = _now()
    fill_id = str(ULID())
    conn.execute(
        "INSERT INTO fills (id, conversation_id, prompt_id, prompt_version_id,"
        " values_json, output, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (fill_id, conversation_id, prompt_id, prompt_version_id, json.dumps(values), output, now),
    )
    conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, conversation_id))
    return Fill(
        id=fill_id,
        conversation_id=conversation_id,
        prompt_id=prompt_id,
        prompt_version_id=prompt_version_id,
        values=dict(values),
        output=output,
        created_at=_parse(now),
    )


def fills_for(conn: sqlite3.Connection, conversation_id: str) -> list[Fill]:
    """Every fill in a thread, newest first."""
    rows = conn.execute(
        "SELECT f.*, p.title AS prompt_title FROM fills f"
        " LEFT JOIN prompts p ON p.id = f.prompt_id"
        " WHERE f.conversation_id = ? ORDER BY f.created_at DESC",
        (conversation_id,),
    ).fetchall()
    return [
        Fill(
            id=row["id"],
            conversation_id=row["conversation_id"],
            prompt_id=row["prompt_id"],
            prompt_version_id=row["prompt_version_id"],
            values=_loads(row["values_json"]),
            output=row["output"],
            prompt_title=row["prompt_title"] or "(deleted prompt)",
            created_at=_parse(row["created_at"]),
        )
        for row in rows
    ]


def _list(conn: sqlite3.Connection, where: str, params: tuple = ()) -> list[Conversation]:
    rows = conn.execute(f"SELECT * FROM conversations WHERE {where}", params).fetchall()
    return [_row_to_conversation(conn, row) for row in rows]


def list_live(conn: sqlite3.Connection) -> list[Conversation]:
    """Threads that are neither archived nor deleted, most recent first."""
    return _list(conn, "deleted_at IS NULL AND archived_at IS NULL ORDER BY updated_at DESC")


def list_archived(conn: sqlite3.Connection) -> list[Conversation]:
    return _list(conn, "deleted_at IS NULL AND archived_at IS NOT NULL ORDER BY updated_at DESC")


def archive(conn: sqlite3.Connection, conversation_id: str) -> None:
    """Hide a thread from Recent without losing it. Nothing expires on its own (D18)."""
    conn.execute("UPDATE conversations SET archived_at = ? WHERE id = ?", (_now(), conversation_id))


def unarchive(conn: sqlite3.Connection, conversation_id: str) -> None:
    conn.execute("UPDATE conversations SET archived_at = NULL WHERE id = ?", (conversation_id,))


def soft_delete(conn: sqlite3.Connection, conversation_id: str) -> None:
    conn.execute("UPDATE conversations SET deleted_at = ? WHERE id = ?", (_now(), conversation_id))
    conn.execute("DELETE FROM conversations_fts WHERE conversation_id = ?", (conversation_id,))


def restore(conn: sqlite3.Connection, conversation_id: str) -> Conversation:
    conn.execute("UPDATE conversations SET deleted_at = NULL WHERE id = ?", (conversation_id,))
    conversation = get(conn, conversation_id)
    if conversation is None:
        raise KeyError(conversation_id)
    _sync_fts(conn, conversation)
    return conversation
