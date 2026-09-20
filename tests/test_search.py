from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from prompt_cache.store import prompts as store
from prompt_cache.store import search
from prompt_cache.store.db import database

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
def conn(tmp_path: Path):
    with database(tmp_path / "s.db") as connection:
        yield connection


def titles(results) -> list[str]:
    return [hit.prompt.title for hit in results.flat()]


def group_names(results) -> list[str]:
    return [name for name, _ in results.groups]


@pytest.fixture
def sample(conn):
    made = {
        "comment": store.create(conn, "LinkedIn comment\nWrite a comment on the post. #social"),
        "reply": store.create(conn, "LinkedIn reply to reply\nRespond to their reply."),
        "email": store.create(conn, "Email reply\nAnswer the thread politely."),
        "proposal": store.create(conn, "Generic proposal\nPitch for the brief below."),
    }
    return made


class TestFindingThings:
    def test_exact_word_in_title(self, conn, sample):
        assert titles(search.search(conn, "proposal", now=NOW)) == ["Generic proposal"]

    def test_prefix_across_two_tokens(self, conn, sample):
        """'lin com' should reach 'LinkedIn comment'."""
        assert titles(search.search(conn, "lin com", now=NOW))[0] == "LinkedIn comment"

    def test_typo_tolerant(self, conn, sample):
        """The fuzzy pass is what makes abbreviations work at all."""
        assert "LinkedIn reply to reply" in titles(search.search(conn, "lnkd reply", now=NOW))

    def test_matches_body_not_just_title(self, conn, sample):
        assert titles(search.search(conn, "politely", now=NOW)) == ["Email reply"]

    def test_matches_tags(self, conn, sample):
        assert "LinkedIn comment" in titles(search.search(conn, "social", now=NOW))

    def test_no_match_offers_to_create(self, conn, sample):
        results = search.search(conn, "zzzz nothing matches", now=NOW)
        assert results.is_empty
        assert results.create_label == "zzzz nothing matches"

    def test_a_match_does_not_offer_to_create(self, conn, sample):
        assert search.search(conn, "proposal", now=NOW).create_label is None

    def test_deleted_prompts_are_not_found(self, conn, sample):
        store.soft_delete(conn, sample["proposal"].id)
        assert titles(search.search(conn, "proposal", now=NOW)) == []

    @pytest.mark.parametrize("query", ['"', "*", "AND", "NEAR(", "a OR", "^", "()"])
    def test_fts_syntax_in_a_query_does_not_crash(self, conn, sample, query):
        """Users type punctuation; FTS5 treats much of it as syntax."""
        search.search(conn, query, now=NOW)


class TestRanking:
    def test_pinned_outranks_an_equal_match(self, conn):
        store.create(conn, "Report draft")
        pinned = store.create(conn, "Report summary")
        store.toggle_pin(conn, pinned.id)
        ranked = titles(search.search(conn, "report", now=NOW))
        assert ranked[0] == "Report summary"
        assert "Report draft" in ranked

    def test_frequently_used_outranks_unused(self, conn):
        store.create(conn, "Report alpha")
        used = store.create(conn, "Report beta")
        for _ in range(10):
            store.mark_used(conn, used.id)
        assert titles(search.search(conn, "report", now=NOW))[0] == "Report beta"

    def test_frecency_decays_with_age(self, conn):
        prompt = store.create(conn, "Aged")
        store.mark_used(conn, prompt.id)
        fresh = store.get(conn, prompt.id)

        recent_score = search.frecency(fresh, now=fresh.last_used_at)
        old_score = search.frecency(fresh, now=fresh.last_used_at + timedelta(days=90))
        assert old_score < recent_score

    def test_never_used_has_no_frecency(self, conn):
        assert search.frecency(store.create(conn, "Unused"), now=NOW) == 0.0

    def test_results_respect_the_limit(self, conn):
        for index in range(20):
            store.create(conn, f"Report number {index}")
        assert len(search.search(conn, "report", limit=5, now=NOW).flat()) == 5


class TestBrowsing:
    def test_empty_query_groups_pinned_recent_most_used(self, conn, sample):
        store.toggle_pin(conn, sample["email"].id)
        for _ in range(5):
            store.mark_used(conn, sample["proposal"].id)

        results = search.search(conn, "", now=NOW)
        assert "Pinned" in group_names(results)
        assert "Recent" in group_names(results)
        assert titles(results)[0] == "Email reply", "pinned comes first"

    def test_whitespace_only_query_browses(self, conn, sample):
        assert group_names(search.search(conn, "   ", now=NOW)) == group_names(
            search.search(conn, "", now=NOW)
        )

    def test_empty_database_browses_to_nothing(self, conn):
        results = search.search(conn, "", now=NOW)
        assert results.groups == []
        assert results.create_label is None

    def test_a_prompt_appears_once_across_groups(self, conn, sample):
        for _ in range(5):
            store.mark_used(conn, sample["proposal"].id)
        flat = [hit.prompt.id for hit in search.search(conn, "", now=NOW).flat()]
        assert len(flat) == len(set(flat))


class TestPerformance:
    def test_stays_responsive_at_a_thousand_prompts(self, conn):
        """The roadmap's M1 bar: search must not degrade at realistic scale."""
        import time

        for index in range(1000):
            store.create(conn, f"Prompt number {index}\nSome body text for number {index}")

        start = time.perf_counter()
        results = search.search(conn, "number 500", now=NOW)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert results.flat(), "expected matches"
        assert elapsed_ms < 500, f"search took {elapsed_ms:.0f}ms at 1000 prompts"
