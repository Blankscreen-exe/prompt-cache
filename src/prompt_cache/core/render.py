"""Assembling a filled template into the text that lands on the clipboard.

Two rules do the interesting work:

- **An empty `optional` blank takes its whole line with it**, so a labelled section
  disappears cleanly instead of leaving a dangling "MY COMMENT:".
- Removing a line can strand blank lines, so runs of them collapse to one — but only
  when something was actually removed, otherwise the author's own spacing is preserved
  exactly.

Pure: no I/O, no database, no Textual. Resolving `{{@includes}}` is M3; until then an
include renders as nothing and says so.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from prompt_cache.core.parser import (
    Blank,
    BlankRef,
    IncludeRef,
    Literal,
    Template,
    TemplateWarning,
    parse,
)

# Marks a line for removal. A private-use codepoint, so it cannot collide with
# anything a user pastes in.
LINE_KILL = ""


class ValueSource(StrEnum):
    """Where a pre-filled value came from, for the badge next to each field."""

    CONVERSATION = "from conversation"
    CLIPBOARD = "from clipboard"
    DEFAULT = "default"
    EMPTY = ""


@dataclass(frozen=True, slots=True)
class Rendered:
    """The finished text, plus what the caller should know about it."""

    text: str
    missing: tuple[str, ...] = ()
    warnings: tuple[TemplateWarning, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not self.missing


@dataclass(slots=True)
class Prefill:
    """Starting values for a fill form, and where each one came from."""

    values: dict[str, str] = field(default_factory=dict)
    sources: dict[str, ValueSource] = field(default_factory=dict)


def initial_values(
    template: Template,
    *,
    clipboard_text: str | None = None,
    conversation: Mapping[str, str] | None = None,
) -> Prefill:
    """Pre-fill every blank, first match wins.

    The order is fixed by docs/02-concepts.md: a value the conversation already knows,
    then the clipboard for `clipboard` blanks, then an explicit default, then the first
    option of a choice, then empty.
    """
    prefill = Prefill()
    for blank in template.blanks:
        existing = (conversation or {}).get(blank.name)
        if existing:
            prefill.values[blank.name] = existing
            prefill.sources[blank.name] = ValueSource.CONVERSATION
            continue

        if blank.from_clipboard and clipboard_text:
            prefill.values[blank.name] = clipboard_text
            prefill.sources[blank.name] = ValueSource.CLIPBOARD
            continue

        default = blank.default_value
        prefill.values[blank.name] = default
        prefill.sources[blank.name] = ValueSource.DEFAULT if default else ValueSource.EMPTY
    return prefill


def _value_for(blank: Blank, values: Mapping[str, str]) -> tuple[str, bool]:
    """The text a blank contributes, and whether it should remove its line."""
    raw = values.get(blank.name, "")
    text = raw if raw is not None else ""

    if blank.is_choice:
        option = blank.option_for(text)
        if option is not None and option.is_none:
            return "", True
        if option is not None and option.is_block:
            # Blocks are resolved in M3; until then they contribute nothing.
            return "", False
        return text, False

    if not text.strip() and blank.optional:
        return "", True
    return text, False


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        if not line.strip() and result and not result[-1].strip():
            continue
        result.append(line)
    return result


def render(
    template: Template | str,
    values: Mapping[str, str] | None = None,
) -> Rendered:
    """Assemble the output. Never raises; unknown values are simply empty."""
    if isinstance(template, str):
        template = parse(template)
    values = values or {}

    warnings = list(template.warnings)
    missing: list[str] = []
    killed_any = False
    pieces: list[str] = []

    for token in template.tokens:
        if isinstance(token, Literal):
            pieces.append(token.text)
        elif isinstance(token, BlankRef):
            blank = template.blank(token.name)
            if blank is None:  # pragma: no cover - parser guarantees this
                continue
            text, kill_line = _value_for(blank, values)
            if kill_line:
                killed_any = True
                pieces.append(LINE_KILL)
            else:
                pieces.append(text)
                if not text.strip() and not blank.optional and blank.name not in missing:
                    missing.append(blank.name)
        elif isinstance(token, IncludeRef):
            warnings.append(
                TemplateWarning(
                    f"Include '@{token.block}' is not resolved yet (arrives in M3).",
                    "{{@" + token.block + "}}",
                )
            )

    text = "".join(pieces)

    if killed_any:
        kept = [line for line in text.split("\n") if LINE_KILL not in line]
        text = "\n".join(_collapse_blank_runs(kept))

    return Rendered(text=text, missing=tuple(missing), warnings=tuple(warnings))
