"""Deriving a title, a slug and tags from a prompt body.

Pure: no I/O. Slugification is delegated to `python-slugify` rather than hand-rolled.
"""

from __future__ import annotations

import re

from slugify import slugify

MAX_TITLE_LENGTH = 120
FALLBACK_TITLE = "Untitled"
FALLBACK_SLUG = "untitled"

# A fenced code block, ``` or ~~~, with anything up to the matching fence.
_FENCE = re.compile(r"^(?P<fence>```+|~~~+).*?^(?P=fence)", re.MULTILINE | re.DOTALL)

# An inline #tag. Requires a letter first, so "#1" and a markdown "# Heading"
# (which has a space) are both excluded. Not preceded by a word character or
# another '#', so "a#b" and "##" do not match.
_TAG = re.compile(r"(?<![\w#])#([A-Za-z][\w-]*)")

# A markdown ATX heading, with optional closing hashes: "## Title ##".
# Matched rather than stripped, so a title that merely starts with a #tag survives.
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*$")


def title_from_body(body: str) -> str:
    """The first non-empty line, with leading markdown hashes stripped.

    Returns ``Untitled`` for a body that is empty or only whitespace.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        heading = _HEADING.match(stripped)
        if heading:
            stripped = heading.group(1).strip()
        elif set(stripped) <= {"#", " "}:
            # A line of nothing but hashes is decoration, not a title.
            continue
        if not stripped:
            continue
        return stripped[:MAX_TITLE_LENGTH]
    return FALLBACK_TITLE


def make_slug(title: str) -> str:
    """A URL-ish identifier used by ``{{@name}}`` includes."""
    return slugify(title, max_length=80) or FALLBACK_SLUG


def strip_code_blocks(body: str) -> str:
    """Body with fenced code blocks removed, so their contents are not scanned."""
    return _FENCE.sub("", body)


def extract_tags(body: str) -> tuple[str, ...]:
    """Inline ``#tags``, lowercased, de-duplicated, in order of appearance.

    Fenced code blocks are ignored so a shell comment or a CSS colour is not a tag.
    """
    seen: dict[str, None] = {}
    for match in _TAG.finditer(strip_code_blocks(body)):
        seen.setdefault(match.group(1).lower(), None)
    return tuple(seen)
