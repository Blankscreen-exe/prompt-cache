"""Parsing the template grammar.

The whole language is in docs/02-concepts.md. This module turns a prompt body into a
token stream plus the list of blanks it declares, and it **never raises on bad input**:
anything it cannot make sense of degrades to something usable and records a warning, so
a half-typed template in the editor is still a working template.

Pure: no I/O, no database, no Textual.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import StrEnum

CLIPBOARD = "clipboard"
OPTIONAL = "optional"
NONE_OPTION = "none"
FLAGS = frozenset({CLIPBOARD, OPTIONAL})

# Either an escaped "\{{", or a {{...}} group. Non-greedy so the nearest }} wins.
_TOKEN = re.compile(r"\\\{\{|\{\{(.*?)\}\}", re.DOTALL)

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

# An unmatched "{{" left in literal text, which is almost always a typo.
_STRAY_OPEN = re.compile(r"\{\{")


class BlankKind(StrEnum):
    TEXT = "text"
    CHOICE = "choice"
    BLOCK_CHOICE = "block_choice"


@dataclass(frozen=True, slots=True)
class Choice:
    """One option of a choice blank."""

    label: str
    block: str | None = None
    is_none: bool = False

    @property
    def is_block(self) -> bool:
        return self.block is not None


@dataclass(frozen=True, slots=True)
class Blank:
    """A declared placeholder. One per name, however many times it appears."""

    name: str  # canonical, lowercase
    display_name: str  # as first written, for labels
    kind: BlankKind = BlankKind.TEXT
    options: tuple[Choice, ...] = ()
    default: str | None = None
    from_clipboard: bool = False
    optional: bool = False
    source: str = ""  # the raw {{...}} it came from

    @property
    def is_choice(self) -> bool:
        return self.kind in (BlankKind.CHOICE, BlankKind.BLOCK_CHOICE)

    @property
    def default_value(self) -> str:
        """The value to start with when nothing else supplies one."""
        if self.default is not None:
            return self.default
        if self.options:
            return self.options[0].label
        return ""

    def option_for(self, label: str) -> Choice | None:
        for option in self.options:
            if option.label == label:
                return option
        return None


@dataclass(frozen=True, slots=True)
class TemplateWarning:
    """Something the author probably did not mean. Shown, never raised."""

    message: str
    source: str = ""


@dataclass(frozen=True, slots=True)
class Literal:
    text: str


@dataclass(frozen=True, slots=True)
class BlankRef:
    name: str


@dataclass(frozen=True, slots=True)
class IncludeRef:
    block: str


Token = Literal | BlankRef | IncludeRef


@dataclass(frozen=True, slots=True)
class Template:
    """A parsed prompt body."""

    tokens: tuple[Token, ...] = ()
    blanks: tuple[Blank, ...] = ()
    includes: tuple[str, ...] = ()
    warnings: tuple[TemplateWarning, ...] = ()

    @property
    def has_blanks(self) -> bool:
        return bool(self.blanks)

    @property
    def is_template(self) -> bool:
        """Whether filling it needs a form at all."""
        return bool(self.blanks or self.includes)

    def blank(self, name: str) -> Blank | None:
        canonical = name.lower()
        for blank in self.blanks:
            if blank.name == canonical:
                return blank
        return None


def _split_options(choice_src: str, warnings: list[TemplateWarning], source: str):
    """Split a choice list, pulling off a trailing ``= default``.

    The ``=`` is only special in the final option, so ``{{x: a=b | c}}`` keeps ``a=b``
    as an option rather than reading it as a default.
    """
    raw = choice_src.split("|")
    default: str | None = None

    if raw and "=" in raw[-1]:
        option_text, _, default_text = raw[-1].rpartition("=")
        raw[-1] = option_text
        default = default_text.strip()

    labels = []
    for item in raw:
        label = item.strip()
        if not label:
            warnings.append(TemplateWarning("Empty option in the choice list.", source))
            continue
        labels.append(label)
    return labels, default


def _build_choices(
    labels: list[str], warnings: list[TemplateWarning], source: str
) -> tuple[tuple[Choice, ...], BlankKind]:
    has_block = any(label.startswith("@") for label in labels)
    options: list[Choice] = []

    for label in labels:
        if label.startswith("@"):
            block = label[1:].strip()
            if not _NAME.match(block):
                warnings.append(TemplateWarning(f"'{label}' is not a valid block name.", source))
                continue
            options.append(Choice(label=f"@{block}", block=block))
        elif has_block and label.lower() == NONE_OPTION:
            options.append(Choice(label=label, is_none=True))
        else:
            if has_block:
                warnings.append(
                    TemplateWarning(
                        f"'{label}' mixes plain text into a list of blocks;"
                        " it will insert its own text, not a block.",
                        source,
                    )
                )
            options.append(Choice(label=label))

    kind = BlankKind.BLOCK_CHOICE if has_block else BlankKind.CHOICE
    return tuple(options), kind


def _parse_spec(
    name: str, display: str, spec: str, warnings: list[TemplateWarning], source: str
) -> Blank:
    """Read everything after the colon.

    Comma-separated parts; any part that is exactly ``clipboard`` or ``optional`` is a
    flag, and whatever is left — rejoined with its original spacing — is the choice
    list. That is what lets an option contain a comma: ``{{t: short, punchy | long}}``.
    """
    flags: set[str] = set()
    remainder: list[str] = []
    for part in spec.split(","):
        if part.strip().lower() in FLAGS:
            flags.add(part.strip().lower())
        else:
            remainder.append(part)

    choice_src = ",".join(remainder).strip()
    from_clipboard = CLIPBOARD in flags
    optional = OPTIONAL in flags

    if not choice_src:
        if not flags and spec.strip():
            warnings.append(TemplateWarning("Empty modifier; treated as plain text.", source))
        return Blank(
            name=name,
            display_name=display,
            kind=BlankKind.TEXT,
            from_clipboard=from_clipboard,
            optional=optional,
            source=source,
        )

    labels, default = _split_options(choice_src, warnings, source)
    if not labels:
        return Blank(
            name=name,
            display_name=display,
            kind=BlankKind.TEXT,
            from_clipboard=from_clipboard,
            optional=optional,
            source=source,
        )

    options, kind = _build_choices(labels, warnings, source)
    if not options:
        return Blank(
            name=name,
            display_name=display,
            kind=BlankKind.TEXT,
            from_clipboard=from_clipboard,
            optional=optional,
            source=source,
        )

    if default is not None and all(option.label != default for option in options):
        warnings.append(
            TemplateWarning(
                f"Default '{default}' is not one of the options; using '{options[0].label}'.",
                source,
            )
        )
        default = None

    if from_clipboard:
        warnings.append(TemplateWarning("'clipboard' has no effect on a choice; ignored.", source))
        from_clipboard = False

    return Blank(
        name=name,
        display_name=display,
        kind=kind,
        options=options,
        default=default,
        from_clipboard=False,
        optional=optional,
        source=source,
    )


def _parse_one(inner: str, warnings: list[TemplateWarning]) -> Token | None:
    """Turn the text inside one ``{{ }}`` into a token, or None if it is not valid."""
    source = "{{" + inner + "}}"
    body = inner.strip()

    if not body:
        warnings.append(TemplateWarning("Empty {{ }}; left as text.", source))
        return None

    if body.startswith("@"):
        block = body[1:].strip()
        if not _NAME.match(block):
            warnings.append(TemplateWarning(f"'{block}' is not a valid block name.", source))
            return None
        return IncludeRef(block=block)

    name_part, sep, spec = body.partition(":")
    display = name_part.strip()
    if not _NAME.match(display):
        warnings.append(
            TemplateWarning(
                f"'{display}' is not a valid blank name"
                " (letters, digits, _ and -, starting with a letter).",
                source,
            )
        )
        return None

    canonical = display.lower()
    if sep:
        blank = _parse_spec(canonical, display, spec, warnings, source)
    else:
        blank = Blank(name=canonical, display_name=display, source=source)
    return blank


def _merge(existing: Blank, incoming: Blank, warnings: list[TemplateWarning]) -> Blank:
    """One input, repeated in the output — so a repeated name keeps its first declaration."""
    incoming_declares = (
        incoming.kind is not BlankKind.TEXT
        or incoming.from_clipboard
        or incoming.optional
        or incoming.default is not None
    )
    existing_declares = (
        existing.kind is not BlankKind.TEXT
        or existing.from_clipboard
        or existing.optional
        or existing.default is not None
    )
    if incoming_declares and existing_declares and incoming != existing:
        warnings.append(
            TemplateWarning(
                f"'{incoming.display_name}' is declared twice with different modifiers;"
                f" using the first ({existing.source}).",
                incoming.source,
            )
        )
    chosen = existing if existing_declares else incoming
    # The label the user sees comes from the first spelling, whichever declaration wins.
    return replace(chosen, display_name=existing.display_name)


def parse(body: str) -> Template:
    """Parse a prompt body. Never raises."""
    tokens: list[Token] = []
    blanks: dict[str, Blank] = {}
    includes: list[str] = []
    warnings: list[TemplateWarning] = []

    position = 0
    for match in _TOKEN.finditer(body):
        literal = body[position : match.start()]
        if literal:
            tokens.append(Literal(literal))
        position = match.end()

        if match.group(0) == "\\{{":
            tokens.append(Literal("{{"))
            continue

        token = _parse_one(match.group(1), warnings)
        if token is None:
            # Not valid: keep the original text so nothing silently disappears.
            tokens.append(Literal(match.group(0)))
            continue

        if isinstance(token, IncludeRef):
            tokens.append(token)
            if token.block not in includes:
                includes.append(token.block)
            continue

        existing = blanks.get(token.name)
        blanks[token.name] = _merge(existing, token, warnings) if existing else token
        tokens.append(BlankRef(token.name))

    trailing = body[position:]
    if trailing:
        tokens.append(Literal(trailing))

    for token in tokens:
        if isinstance(token, Literal) and _STRAY_OPEN.search(token.text):
            warnings.append(TemplateWarning("Unclosed '{{' — did you mean to close it with '}}'?"))
            break

    return Template(
        tokens=tuple(tokens),
        blanks=tuple(blanks.values()),
        includes=tuple(includes),
        warnings=tuple(warnings),
    )
