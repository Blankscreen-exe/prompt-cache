"""Resolving includes and assembling a filled template.

Three rules do the interesting work:

- **Includes are spliced in recursively.** `{{@name}}` pulls another prompt's body in at
  fill time, and blanks inside that body become blanks of the template being filled.
- **Cycles are reported, never followed.** A includes B includes A names the whole chain
  and renders nothing, rather than recursing until the stack gives out.
- **An empty `optional` blank takes its whole line with it**, so a labelled section
  disappears instead of leaving a dangling "MY COMMENT:". Removing a line can strand
  blank lines, so runs of them collapse — but only when something was actually removed,
  otherwise the author's own spacing is preserved exactly.

Pure: no I/O, no database, no Textual. Block bodies arrive as a plain mapping, so the
store decides where they come from and this module stays testable on its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from prompt_cache.core.parser import (
    Blank,
    BlankKind,
    BlankRef,
    IncludeRef,
    Literal,
    Template,
    TemplateWarning,
    parse,
)

# Deep enough for any sane nesting, shallow enough to stop runaway structures early.
MAX_INCLUDE_DEPTH = 10

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
class BlockChoiceRef:
    """A `{{persona: @a | @b}}` blank, with each option already expanded.

    Which branch is emitted depends on the value at render time, so all of them are
    resolved up front — including their own includes and blanks.
    """

    name: str
    branches: tuple[tuple[str, tuple[object, ...]], ...] = ()

    def branch(self, label: str) -> tuple[object, ...] | None:
        for option_label, tokens in self.branches:
            if option_label == label:
                return tokens
        return None


@dataclass(frozen=True, slots=True)
class ResolvedTemplate:
    """A template with every include spliced in and every blank collected."""

    tokens: tuple[object, ...] = ()
    blanks: tuple[Blank, ...] = ()
    warnings: tuple[TemplateWarning, ...] = ()
    used_blocks: tuple[str, ...] = ()
    missing_blocks: tuple[str, ...] = ()

    @property
    def has_blanks(self) -> bool:
        return bool(self.blanks)

    def blank(self, name: str) -> Blank | None:
        canonical = name.lower()
        for blank in self.blanks:
            if blank.name == canonical:
                return blank
        return None


def resolve(template: Template | str, blocks: Mapping[str, str] | None = None) -> ResolvedTemplate:
    """Splice in every include, collecting blanks and reporting what went wrong.

    `blocks` maps a block's slug to its body. A name that is not in it is reported as a
    missing include and contributes nothing.
    """
    if isinstance(template, str):
        template = parse(template)
    blocks = blocks or {}

    warnings = list(template.warnings)
    blanks: dict[str, Blank] = {blank.name: blank for blank in template.blanks}
    used: list[str] = []
    missing: list[str] = []

    def expand_include(name: str, stack: tuple[str, ...]) -> list[object]:
        if name in stack:
            chain = " -> ".join([*stack, name])
            warnings.append(TemplateWarning(f"Include cycle: {chain}", "{{@" + name + "}}"))
            return []
        if len(stack) >= MAX_INCLUDE_DEPTH:
            warnings.append(
                TemplateWarning(
                    f"Includes nested more than {MAX_INCLUDE_DEPTH} deep at '@{name}'.",
                    "{{@" + name + "}}",
                )
            )
            return []

        body = blocks.get(name)
        if body is None:
            if name not in missing:
                missing.append(name)
                warnings.append(
                    TemplateWarning(f"Include '@{name}' does not exist.", "{{@" + name + "}}")
                )
            return []

        if name not in used:
            used.append(name)

        sub = parse(body)
        warnings.extend(sub.warnings)
        for blank in sub.blanks:
            # The outer template's declaration wins, matching the repeated-name rule.
            blanks.setdefault(blank.name, blank)
        return expand(sub, (*stack, name))

    def expand(source: Template, stack: tuple[str, ...]) -> list[object]:
        out: list[object] = []
        for token in source.tokens:
            if isinstance(token, Literal):
                out.append(token)
            elif isinstance(token, IncludeRef):
                out.extend(expand_include(token.block, stack))
            elif isinstance(token, BlankRef):
                blank = blanks.get(token.name)
                if blank is not None and blank.kind is BlankKind.BLOCK_CHOICE:
                    branches = tuple(
                        (
                            option.label,
                            tuple(expand_include(option.block, stack)) if option.block else (),
                        )
                        for option in blank.options
                    )
                    out.append(BlockChoiceRef(name=blank.name, branches=branches))
                else:
                    out.append(token)
        return out

    tokens = expand(template, ())
    return ResolvedTemplate(
        tokens=tuple(tokens),
        blanks=tuple(blanks.values()),
        warnings=tuple(warnings),
        used_blocks=tuple(used),
        missing_blocks=tuple(missing),
    )


@dataclass(frozen=True, slots=True)
class Rendered:
    """The finished text, plus what the caller should know about it."""

    text: str
    missing: tuple[str, ...] = ()
    warnings: tuple[TemplateWarning, ...] = ()
    missing_blocks: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        return not self.missing and not self.missing_blocks


@dataclass(slots=True)
class Prefill:
    """Starting values for a fill form, and where each one came from."""

    values: dict[str, str] = field(default_factory=dict)
    sources: dict[str, ValueSource] = field(default_factory=dict)


def initial_values(
    template: Template | ResolvedTemplate,
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


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    result: list[str] = []
    for line in lines:
        if not line.strip() and result and not result[-1].strip():
            continue
        result.append(line)
    return result


def render(
    template: Template | ResolvedTemplate | str,
    values: Mapping[str, str] | None = None,
    blocks: Mapping[str, str] | None = None,
) -> Rendered:
    """Assemble the output. Never raises; unknown values are simply empty."""
    resolved = template if isinstance(template, ResolvedTemplate) else resolve(template, blocks)
    values = values or {}

    missing: list[str] = []
    killed_any = False

    def emit(tokens: tuple[object, ...]) -> list[str]:
        nonlocal killed_any
        pieces: list[str] = []
        for token in tokens:
            if isinstance(token, Literal):
                pieces.append(token.text)
            elif isinstance(token, BlockChoiceRef):
                chosen = values.get(token.name, "")
                branch = token.branch(chosen)
                blank = resolved.blank(token.name)
                option = blank.option_for(chosen) if blank else None
                if option is not None and option.is_none:
                    killed_any = True
                    pieces.append(LINE_KILL)
                elif branch:
                    pieces.extend(emit(branch))
                elif option is not None and not option.is_block:
                    # A plain-text option mixed into a block list inserts its own text.
                    pieces.append(option.label)
                else:
                    killed_any = True
                    pieces.append(LINE_KILL)
            elif isinstance(token, BlankRef):
                blank = resolved.blank(token.name)
                if blank is None:  # pragma: no cover - resolve guarantees this
                    continue
                text = values.get(blank.name, "") or ""
                if not text.strip() and blank.optional:
                    killed_any = True
                    pieces.append(LINE_KILL)
                    continue
                pieces.append(text)
                if not text.strip() and not blank.optional and blank.name not in missing:
                    missing.append(blank.name)
        return pieces

    text = "".join(emit(resolved.tokens))

    if killed_any:
        kept = [line for line in text.split("\n") if LINE_KILL not in line]
        text = "\n".join(_collapse_blank_runs(kept))

    return Rendered(
        text=text,
        missing=tuple(missing),
        warnings=resolved.warnings,
        missing_blocks=resolved.missing_blocks,
    )
