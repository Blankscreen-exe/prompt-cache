"""Domain types. Pure data — no I/O, no database, no Textual."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Prompt:
    """A piece of text the user saved.

    There is no separate "template" type: a template is simply a prompt whose body
    contains blanks. `is_template` is derived, never stored.
    """

    id: str
    name: str
    title: str
    body: str
    title_is_custom: bool = False
    pinned: bool = False
    use_count: int = 0
    last_used_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    deleted_at: datetime | None = None
    tags: tuple[str, ...] = ()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def summary(self) -> str:
        """The body after the title line, collapsed to one line for list rows."""
        lines = self.body.splitlines()
        rest = " ".join(line.strip() for line in lines[1:] if line.strip())
        return rest[:200]


@dataclass(frozen=True, slots=True)
class Conversation:
    """A thread of fills — one post and its replies (D27).

    `values` is the merged map of blank values the thread knows, which is what makes a
    follow-up template fill itself.
    """

    id: str
    label: str
    values: dict[str, str] = field(default_factory=dict)
    label_is_custom: bool = False
    fill_count: int = 0
    templates: tuple[str, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None
    deleted_at: datetime | None = None

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    @property
    def summary(self) -> str:
        """The value names this thread carries, for a list row."""
        return ", ".join(sorted(self.values))


@dataclass(frozen=True, slots=True)
class Fill:
    """One use of a template, with everything needed to reproduce it."""

    id: str
    conversation_id: str
    prompt_id: str
    values: dict[str, str] = field(default_factory=dict)
    output: str = ""
    prompt_version_id: str | None = None
    prompt_title: str = ""
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SearchHit:
    """A prompt or a conversation, plus why it ranked where it did.

    The score breakdown is kept so ranking stays debuggable and testable rather than
    being an opaque number.
    """

    prompt: Prompt | None = None
    conversation: Conversation | None = None
    score: float = 0.0
    match_score: float = 0.0
    frecency_score: float = 0.0
    pinned_bonus: float = 0.0
    matched_on: str = ""

    @property
    def is_conversation(self) -> bool:
        return self.conversation is not None

    @property
    def id(self) -> str:
        item = self.conversation or self.prompt
        return item.id if item else ""

    @property
    def title(self) -> str:
        if self.conversation is not None:
            return self.conversation.label
        return self.prompt.title if self.prompt else ""


@dataclass(slots=True)
class SearchResults:
    """What the palette renders.

    `groups` preserves display order. When a query matches nothing, `create_label`
    carries the text the user typed so the UI can offer to create a prompt from it.
    """

    groups: list[tuple[str, list[SearchHit]]] = field(default_factory=list)
    create_label: str | None = None

    @property
    def is_empty(self) -> bool:
        return all(not hits for _, hits in self.groups)

    def flat(self) -> list[SearchHit]:
        return [hit for _, hits in self.groups for hit in hits]
