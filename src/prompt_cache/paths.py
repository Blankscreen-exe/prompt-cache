"""Where prompt-cache keeps its data.

Never inside the repository: the repo is public and the database holds personal content.
See docs/05-architecture.md.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DIR_NAME = "prompt-cache"
DB_FILE_NAME = "prompt-cache.db"
DATA_DIR_ENV = "PROMPT_CACHE_DATA"


def data_dir() -> Path:
    """The directory holding the database.

    ``PROMPT_CACHE_DATA`` overrides everything. Otherwise:

    - Windows: ``%APPDATA%\\prompt-cache``
    - everywhere else: ``$XDG_DATA_HOME/prompt-cache`` (default ``~/.local/share/prompt-cache``)
    """
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser()

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / APP_DIR_NAME

    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def db_path() -> Path:
    """Full path to the SQLite database file."""
    return data_dir() / DB_FILE_NAME


def ensure_data_dir() -> Path:
    """Create the data directory if it does not exist, and return it."""
    directory = data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    return directory
