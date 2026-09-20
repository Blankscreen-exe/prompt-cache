"""Search and ranking for the palette.

Two match sources, blended:

- **FTS5** over title, body, name and tags — finds words anywhere in the text.
- **rapidfuzz** over titles and slugs — finds what the user *meant*, so "lnkd rep"
  reaches "LinkedIn reply to reply" even though no prefix matches.

Whatever matched is then weighted by **frecency** (how often and how recently the prompt
is used) and a pin bonus, because in practice the right answer is usually something you
reached for last week.
"""

from __future__ import annotations

import math
import re
import sqlite3
from datetime import UTC, datetime

from rapidfuzz import fuzz, process

from prompt_cache.core.models import Prompt, SearchHit, SearchResults
from prompt_cache.store import prompts as prompt_store

# Scoring weights. Match quality dominates; frecency breaks ties and surfaces habits.
FRECENCY_WEIGHT = 25.0
PINNED_BONUS = 40.0
RECENCY_HALF_LIFE_DAYS = 30.0

# Below this, a fuzzy match is noise rather than a result.
MIN_FUZZY_SCORE = 55.0

DEFAULT_LIMIT = 50

# FTS5 treats plenty of punctuation as syntax; strip it rather than escaping.
_FTS_UNSAFE = re.compile(r"[^\w\s]")


def _fts_query(query: str) -> str:
    """Turn user input into a safe FTS5 prefix query.

    Every token becomes a prefix term, so "lin com" matches "LinkedIn comment".
    """
    tokens = _FTS_UNSAFE.sub(" ", query).split()
    return " ".join(f'"{token}"*' for token in tokens)


def frecency(prompt: Prompt, *, now: datetime | None = None) -> float:
    """How habitual this prompt is, roughly 0 upward.

    Frequency is logarithmic so a prompt used 200 times does not bury everything else;
    recency decays with a 30-day half-life.
    """
    if prompt.use_count == 0 or prompt.last_used_at is None:
        return 0.0
    now = now or datetime.now(UTC)
    last_used = prompt.last_used_at
    if last_used.tzinfo is None:
        last_used = last_used.replace(tzinfo=UTC)
    days = max((now - last_used).total_seconds() / 86400.0, 0.0)
    recency = 0.5 ** (days / RECENCY_HALF_LIFE_DAYS)
    return math.log1p(prompt.use_count) * (0.4 + 0.6 * recency)


def _fts_matches(conn: sqlite3.Connection, query: str) -> dict[str, float]:
    """Prompt id -> normalised FTS score in roughly 0 to 100."""
    fts = _fts_query(query)
    if not fts:
        return {}
    try:
        rows = conn.execute(
            "SELECT prompt_id, bm25(prompts_fts, 10.0, 1.0, 5.0, 3.0) AS rank"
            " FROM prompts_fts WHERE prompts_fts MATCH ? ORDER BY rank",
            (fts,),
        ).fetchall()
    except sqlite3.OperationalError:
        # A query FTS5 cannot parse should degrade to fuzzy-only, not break the palette.
        return {}

    scores: dict[str, float] = {}
    for row in rows:
        # bm25 returns negative numbers, better matches being more negative.
        scores[row["prompt_id"]] = min(100.0, -float(row["rank"]) * 10.0)
    return scores


def _fuzzy_matches(candidates: list[Prompt], query: str) -> dict[str, float]:
    """Prompt id → best fuzzy score across title and slug."""
    if not candidates:
        return {}
    haystack = {prompt.id: f"{prompt.title} {prompt.name}" for prompt in candidates}
    matches = process.extract(
        query,
        haystack,
        scorer=fuzz.WRatio,
        limit=None,
        score_cutoff=MIN_FUZZY_SCORE,
    )
    return {prompt_id: float(score) for _, score, prompt_id in matches}


def _browse(prompts: list[Prompt], now: datetime) -> SearchResults:
    """What an empty query shows: pinned, then recent, then most used."""
    pinned = sorted(
        (p for p in prompts if p.pinned),
        key=lambda p: p.last_used_at or p.updated_at or now,
        reverse=True,
    )
    rest = [p for p in prompts if not p.pinned]
    recent = sorted(rest, key=lambda p: p.updated_at or now, reverse=True)[:10]
    recent_ids = {p.id for p in recent}
    most_used = [
        p
        for p in sorted(rest, key=lambda p: p.use_count, reverse=True)
        if p.use_count > 0 and p.id not in recent_ids
    ][:10]

    def to_hits(items: list[Prompt]) -> list[SearchHit]:
        return [
            SearchHit(
                prompt=p,
                score=frecency(p, now=now),
                frecency_score=frecency(p, now=now),
                matched_on="browse",
            )
            for p in items
        ]

    groups: list[tuple[str, list[SearchHit]]] = []
    if pinned:
        groups.append(("Pinned", to_hits(pinned)))
    if recent:
        groups.append(("Recent", to_hits(recent)))
    if most_used:
        groups.append(("Most used", to_hits(most_used)))
    return SearchResults(groups=groups)


def search(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    now: datetime | None = None,
) -> SearchResults:
    """Rank live prompts against `query`.

    An empty query browses instead of searching. A query that matches nothing returns
    `create_label` so the palette can offer to create a prompt from what was typed.
    """
    now = now or datetime.now(UTC)
    live = prompt_store.list_live(conn)
    query = query.strip()

    if not query:
        return _browse(live, now)

    by_id = {prompt.id: prompt for prompt in live}
    fts_scores = _fts_matches(conn, query)
    fuzzy_scores = _fuzzy_matches(live, query)

    hits: list[SearchHit] = []
    for prompt_id in set(fts_scores) | set(fuzzy_scores):
        prompt = by_id.get(prompt_id)
        if prompt is None:
            continue
        fts_score = fts_scores.get(prompt_id, 0.0)
        fuzzy_score = fuzzy_scores.get(prompt_id, 0.0)
        match_score = max(fts_score, fuzzy_score)
        freq = frecency(prompt, now=now)
        pin_bonus = PINNED_BONUS if prompt.pinned else 0.0
        hits.append(
            SearchHit(
                prompt=prompt,
                score=match_score + FRECENCY_WEIGHT * freq + pin_bonus,
                match_score=match_score,
                frecency_score=freq,
                pinned_bonus=pin_bonus,
                matched_on="title" if fuzzy_score >= fts_score else "text",
            )
        )

    hits.sort(key=lambda hit: (-hit.score, hit.prompt.title.lower()))
    hits = hits[:limit]

    results = SearchResults(groups=[("Prompts", hits)] if hits else [])
    if not hits:
        results.create_label = query
    return results
