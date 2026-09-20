"""SQLite connection and migrations.

Migrations are numbered ``.sql`` files applied in order, tracked with ``PRAGMA user_version``.
No ORM, no migration framework — see docs/05-architecture.md.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from prompt_cache.paths import db_path, ensure_data_dir

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Fts5Unavailable(RuntimeError):
    """The bundled SQLite was built without FTS5, which prompt-cache needs for search."""


def _migration_files() -> list[Path]:
    """Every migration, ordered by its numeric prefix."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"), key=lambda p: int(p.name.split("_", 1)[0]))
    for index, path in enumerate(files, start=1):
        number = int(path.name.split("_", 1)[0])
        if number != index:
            raise RuntimeError(f"migrations must be numbered without gaps; found {path.name}")
    return files


def check_fts5(connection: sqlite3.Connection) -> None:
    """Fail early and clearly if this Python's SQLite cannot do full-text search."""
    try:
        with closing(connection.cursor()) as cursor:
            cursor.execute("CREATE VIRTUAL TABLE temp.__fts5_probe USING fts5(x)")
            cursor.execute("DROP TABLE temp.__fts5_probe")
    except sqlite3.OperationalError as exc:  # pragma: no cover - platform dependent
        raise Fts5Unavailable(
            "This Python's SQLite was built without FTS5, which prompt-cache needs for search. "
            "Install Python via uv (`uv python install 3.11`) and run prompt-cache with that."
        ) from exc


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open the database, applying pragmas. Creates the data directory if needed."""
    if path is None:
        ensure_data_dir()
        path = db_path()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(path, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    """The number of migrations applied so far."""
    with closing(connection.cursor()) as cursor:
        return int(cursor.execute("PRAGMA user_version").fetchone()[0])


def migrate(connection: sqlite3.Connection) -> int:
    """Apply any migrations this database has not seen. Returns the resulting version.

    Safe to call on every start: already-applied migrations are skipped.
    """
    check_fts5(connection)

    current = schema_version(connection)
    files = _migration_files()

    for number, path in enumerate(files, start=1):
        if number <= current:
            continue
        sql = path.read_text(encoding="utf-8")
        # PRAGMA user_version does not accept a bound parameter.
        connection.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")

    return schema_version(connection)


def open_database(path: Path | None = None) -> sqlite3.Connection:
    """Connect and bring the schema up to date. The normal way in."""
    connection = connect(path)
    migrate(connection)
    return connection


@contextmanager
def database(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """``open_database`` as a context manager, closing the connection on the way out."""
    connection = open_database(path)
    try:
        yield connection
    finally:
        connection.close()
