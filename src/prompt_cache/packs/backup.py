"""Full backup: one JSON file with everything.

Unlike a pack, a backup **does** include conversations and fills. It is for the owner's
own safekeeping, never for sharing — see the module docstring in `packs/__init__.py`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

BACKUP_VERSION = 1

# Every table worth restoring. FTS tables are rebuilt from these, never dumped.
TABLES = (
    "prompts",
    "prompt_versions",
    "prompt_tags",
    "conversations",
    "fills",
    "settings",
)


@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _rows(conn: sqlite3.Connection, table: str) -> list[dict]:
    return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]


def dump_backup(conn: sqlite3.Connection, destination: Path | str) -> BackupResult:
    """Write everything to a single JSON file."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    data = {table: _rows(conn, table) for table in TABLES}
    payload = {
        "backup_version": BACKUP_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "data": data,
    }
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return BackupResult(path=destination, counts={table: len(rows) for table, rows in data.items()})


def load_backup(conn: sqlite3.Connection, source: Path | str) -> dict[str, int]:
    """Replace everything with the contents of a backup file.

    Destructive by design — this is a restore, not a merge. The caller is responsible
    for confirming with the user first.
    """
    source = Path(source)
    payload = json.loads(source.read_text(encoding="utf-8"))
    data = payload.get("data", {})

    counts: dict[str, int] = {}
    conn.execute("BEGIN")
    try:
        for table in reversed(TABLES):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM prompts_fts")
        conn.execute("DELETE FROM conversations_fts")

        for table in TABLES:
            rows = data.get(table, [])
            counts[table] = len(rows)
            for row in rows:
                columns = ", ".join(row)
                placeholders = ", ".join("?" for _ in row)
                conn.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
                    tuple(row.values()),
                )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    _rebuild_indexes(conn)
    return counts


def _rebuild_indexes(conn: sqlite3.Connection) -> None:
    """Rebuild both FTS tables from the restored rows, so search works immediately."""
    from prompt_cache.store import conversations as conversation_store
    from prompt_cache.store import prompts as prompt_store

    for prompt in prompt_store.list_live(conn):
        prompt_store.reindex(conn, prompt)
    for conversation in conversation_store.list_live(conn):
        conversation_store.reindex(conn, conversation)
