"""Naming a conversation without asking the user to (D4).

The label comes from whichever value carries the most content — usually the thing that
was pasted in, which is exactly what makes a thread recognisable later.

Pure: no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping

LABEL_WORDS = 8
MAX_LABEL_LENGTH = 90
FALLBACK_LABEL = "Untitled thread"


def label_from_values(values: Mapping[str, str]) -> str:
    """A short label derived from the longest value.

    Ties break on the blank name, so the same fill always produces the same label
    rather than depending on dict ordering.
    """
    candidates = [
        (name, " ".join(text.split()))
        for name, text in sorted(values.items())
        if text and text.strip()
    ]
    if not candidates:
        return FALLBACK_LABEL

    _, longest = max(candidates, key=lambda item: (len(item[1]), item[0]))
    words = longest.split()
    label = " ".join(words[:LABEL_WORDS])
    if len(words) > LABEL_WORDS:
        label += "…"
    return label[:MAX_LABEL_LENGTH] or FALLBACK_LABEL
