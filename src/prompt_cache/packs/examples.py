"""The example pack that ships with prompt-cache.

Deliberately generic (D28). It gives a new install a working *shape* — a voice block, a
persona pair, a comment template that pulls from the clipboard, and a follow-up that
reuses its values — without handing anyone someone else's actual wording.

The repo is public, so nothing here may be real business content.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from prompt_cache.packs.importing import ImportResult, OnCollision, import_pack

EXAMPLES_DIR = Path(__file__).parent / "examples"
SETTING_KEY = "examples_offered"


def examples_path() -> Path:
    return EXAMPLES_DIR


def has_been_offered(conn: sqlite3.Connection) -> bool:
    """Whether the first-run offer has already been made, accepted or not."""
    row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (SETTING_KEY,)).fetchone()
    return row is not None


def mark_offered(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
        (SETTING_KEY, "true"),
    )


def should_offer(conn: sqlite3.Connection) -> bool:
    """Offer only on a genuinely empty database, and only once."""
    if has_been_offered(conn):
        return False
    count = conn.execute("SELECT count(*) FROM prompts").fetchone()[0]
    return count == 0


def install_examples(conn: sqlite3.Connection) -> ImportResult:
    """Import the example pack, keeping anything already present."""
    result = import_pack(conn, EXAMPLES_DIR, on_collision=OnCollision.KEEP_BOTH)
    mark_offered(conn)
    return result
