"""Diffing two versions of a prompt.

`difflib` is stdlib and does this properly; there is no reason to hand-roll it.

Pure: no I/O.
"""

from __future__ import annotations

import difflib


def unified(old: str, new: str, *, old_label: str = "before", new_label: str = "after") -> str:
    """A unified diff, or an empty string when the two are identical."""
    lines = list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=old_label,
            tofile=new_label,
            lineterm="",
            n=3,
        )
    )
    if not lines:
        return ""
    return "\n".join(line.rstrip("\n") for line in lines)


def summarise(old: str, new: str) -> tuple[int, int]:
    """(lines added, lines removed) between two bodies."""
    added = removed = 0
    for line in difflib.ndiff(old.splitlines(), new.splitlines()):
        if line.startswith("+ "):
            added += 1
        elif line.startswith("- "):
            removed += 1
    return added, removed
