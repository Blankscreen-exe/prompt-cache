from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from prompt_cache.store import db

EXPECTED_TABLES = {
    "prompts",
    "prompt_versions",
    "prompt_tags",
    "conversations",
    "fills",
    "settings",
    "prompts_fts",
    "conversations_fts",
}


@pytest.fixture
def conn(tmp_path: Path):
    connection = db.open_database(tmp_path / "test.db")
    yield connection
    connection.close()


def _tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
    return {row["name"] for row in rows}


def test_fts5_is_available(conn: sqlite3.Connection):
    db.check_fts5(conn)


def test_migration_creates_every_table(conn: sqlite3.Connection):
    assert _tables(conn) >= EXPECTED_TABLES


def test_schema_version_is_set(conn: sqlite3.Connection):
    assert db.schema_version(conn) == len(db._migration_files())


def test_migrate_is_idempotent(tmp_path: Path):
    path = tmp_path / "twice.db"
    first = db.open_database(path)
    version = db.schema_version(first)
    first.close()

    second = db.open_database(path)
    assert db.schema_version(second) == version
    assert _tables(second) >= EXPECTED_TABLES
    second.close()


def test_pragmas_are_applied(conn: sqlite3.Connection):
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_connect_creates_missing_parent_directories(tmp_path: Path):
    path = tmp_path / "deep" / "nested" / "pc.db"
    connection = db.open_database(path)
    connection.close()
    assert path.exists()


def test_foreign_keys_are_enforced(conn: sqlite3.Connection):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO prompt_versions (id, prompt_id, title, body, created_at)"
            " VALUES ('v1', 'does-not-exist', 't', 'b', '2026-01-01T00:00:00Z')"
        )


def test_prompt_name_is_unique(conn: sqlite3.Connection):
    row = ("{id}", "same-slug", "Title", "Body", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    insert = (
        "INSERT INTO prompts (id, name, title, body, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?)"
    )
    conn.execute(insert, ("a", *row[1:]))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, ("b", *row[1:]))


def test_full_text_search_actually_matches(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO prompts_fts (prompt_id, title, body, name, tags) VALUES (?, ?, ?, ?, ?)",
        (
            "p1",
            "LinkedIn comment",
            "Write a comment on the post below",
            "linkedin-comment",
            "social",
        ),
    )
    rows = conn.execute(
        "SELECT prompt_id FROM prompts_fts WHERE prompts_fts MATCH ?", ("comment",)
    ).fetchall()
    assert [row["prompt_id"] for row in rows] == ["p1"]


def test_prefix_search_works(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO prompts_fts (prompt_id, title, body, name, tags) VALUES (?, ?, ?, ?, ?)",
        ("p1", "LinkedIn comment", "body", "linkedin-comment", ""),
    )
    rows = conn.execute(
        "SELECT prompt_id FROM prompts_fts WHERE prompts_fts MATCH ?", ("link*",)
    ).fetchall()
    assert len(rows) == 1


def test_deleting_a_prompt_cascades_to_versions(conn: sqlite3.Connection):
    conn.execute(
        "INSERT INTO prompts (id, name, title, body, created_at, updated_at)"
        " VALUES ('p1', 'slug', 'T', 'B', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO prompt_versions (id, prompt_id, title, body, created_at)"
        " VALUES ('v1', 'p1', 'T', 'B', '2026-01-01T00:00:00Z')"
    )
    conn.execute("DELETE FROM prompts WHERE id = 'p1'")
    assert conn.execute("SELECT count(*) FROM prompt_versions").fetchone()[0] == 0


def test_migrations_are_numbered_without_gaps():
    files = db._migration_files()
    assert files, "expected at least one migration"
    assert [int(p.name.split("_", 1)[0]) for p in files] == list(range(1, len(files) + 1))
