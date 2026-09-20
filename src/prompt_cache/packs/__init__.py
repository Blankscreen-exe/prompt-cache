"""Template packs and backups.

A **pack** is a portable set of prompts — templates and the blocks they include —
written as plain Markdown files with a small manifest. It is how a setup moves between
machines (D16/D25) and how one is shared with someone else.

A pack **never contains conversations**. Those hold the text of real posts and replies,
and sharing a pack must not leak them.

A **backup** is different: a single JSON file with everything, conversations included,
meant for the owner's own safekeeping rather than for sharing.
"""

from __future__ import annotations

from prompt_cache.packs.backup import dump_backup, load_backup
from prompt_cache.packs.exporting import export_pack
from prompt_cache.packs.importing import import_pack, preview_pack

__all__ = [
    "dump_backup",
    "export_pack",
    "import_pack",
    "load_backup",
    "preview_pack",
]
