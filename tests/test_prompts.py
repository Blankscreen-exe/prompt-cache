from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from prompt_cache.store import prompts as store
from prompt_cache.store.db import database


@pytest.fixture
def conn(tmp_path: Path):
    with database(tmp_path / "p.db") as connection:
        yield connection


def _fts_ids(conn: sqlite3.Connection, term: str) -> set[str]:
    rows = conn.execute(
        "SELECT prompt_id FROM prompts_fts WHERE prompts_fts MATCH ?", (term,)
    ).fetchall()
    return {row["prompt_id"] for row in rows}


class TestCreate:
    def test_derives_title_slug_and_tags(self, conn):
        prompt = store.create(conn, "LinkedIn comment\n\nWrite one. #social")
        assert prompt.title == "LinkedIn comment"
        assert prompt.name == "linkedin-comment"
        assert prompt.tags == ("social",)
        assert prompt.use_count == 0
        assert not prompt.pinned
        assert not prompt.is_deleted

    def test_ids_are_unique_and_sortable(self, conn):
        first = store.create(conn, "One")
        second = store.create(conn, "Two")
        assert first.id != second.id
        assert first.id < second.id  # ULIDs sort by creation time

    def test_explicit_title_is_marked_custom(self, conn):
        prompt = store.create(conn, "body text", title="My Own Title")
        assert prompt.title == "My Own Title"
        assert prompt.title_is_custom

    def test_duplicate_titles_get_distinct_slugs(self, conn):
        a = store.create(conn, "Same title")
        b = store.create(conn, "Same title")
        c = store.create(conn, "Same title")
        assert [a.name, b.name, c.name] == ["same-title", "same-title-2", "same-title-3"]

    def test_is_indexed_for_search(self, conn):
        prompt = store.create(conn, "Findable thing\nwith body words")
        assert _fts_ids(conn, "findable") == {prompt.id}
        assert _fts_ids(conn, "body") == {prompt.id}

    def test_empty_body_is_allowed(self, conn):
        prompt = store.create(conn, "")
        assert prompt.title == "Untitled"
        assert prompt.name == "untitled"


class TestUpdate:
    def test_title_follows_the_first_line(self, conn):
        prompt = store.create(conn, "Old title\nbody")
        updated = store.update_body(conn, prompt.id, "New title\nbody")
        assert updated.title == "New title"

    def test_custom_title_survives_body_edits(self, conn):
        prompt = store.create(conn, "body", title="Fixed")
        updated = store.update_body(conn, prompt.id, "Totally different first line")
        assert updated.title == "Fixed"

    def test_slug_does_not_change_on_edit(self, conn):
        """Includes point at the slug, so typing must never rename a prompt."""
        prompt = store.create(conn, "Original title\nbody")
        updated = store.update_body(conn, prompt.id, "Completely new title\nbody")
        assert updated.name == prompt.name == "original-title"

    def test_tags_are_recomputed(self, conn):
        prompt = store.create(conn, "Title #one")
        updated = store.update_body(conn, prompt.id, "Title #two #three")
        assert updated.tags == ("two", "three")
        rows = conn.execute(
            "SELECT tag FROM prompt_tags WHERE prompt_id = ?", (prompt.id,)
        ).fetchall()
        assert {row["tag"] for row in rows} == {"two", "three"}

    def test_search_index_follows_the_edit(self, conn):
        prompt = store.create(conn, "Before\noldword")
        store.update_body(conn, prompt.id, "After\nnewword")
        assert _fts_ids(conn, "oldword") == set()
        assert _fts_ids(conn, "newword") == {prompt.id}

    def test_unknown_id_raises(self, conn):
        with pytest.raises(KeyError):
            store.update_body(conn, "nope", "body")


class TestRename:
    def test_changes_slug_and_keeps_it_unique(self, conn):
        store.create(conn, "Taken name")
        prompt = store.create(conn, "Other")
        renamed = store.rename(conn, prompt.id, "Taken name")
        assert renamed.name == "taken-name-2"

    def test_renaming_to_its_own_name_is_stable(self, conn):
        prompt = store.create(conn, "Stable")
        assert store.rename(conn, prompt.id, "Stable").name == "stable"


class TestPinAndUsage:
    def test_toggle_pin(self, conn):
        prompt = store.create(conn, "Pin me")
        assert store.toggle_pin(conn, prompt.id).pinned is True
        assert store.toggle_pin(conn, prompt.id).pinned is False

    def test_mark_used_increments_and_timestamps(self, conn):
        prompt = store.create(conn, "Use me")
        assert prompt.last_used_at is None
        store.mark_used(conn, prompt.id)
        store.mark_used(conn, prompt.id)
        reloaded = store.get(conn, prompt.id)
        assert reloaded.use_count == 2
        assert reloaded.last_used_at is not None


class TestSoftDelete:
    def test_delete_then_restore(self, conn):
        prompt = store.create(conn, "Temporary")
        store.soft_delete(conn, prompt.id)

        assert store.get(conn, prompt.id).is_deleted
        assert store.list_live(conn) == []
        assert [p.id for p in store.list_trash(conn)] == [prompt.id]
        assert _fts_ids(conn, "temporary") == set(), "deleted prompts must leave the index"

        restored = store.restore(conn, prompt.id)
        assert not restored.is_deleted
        assert [p.id for p in store.list_live(conn)] == [prompt.id]
        assert _fts_ids(conn, "temporary") == {prompt.id}

    def test_a_deleted_prompt_keeps_its_slug_reserved(self, conn):
        """Trash is recoverable, so a deleted prompt must not surrender its name.

        Otherwise a new prompt could take it and restore would silently rename the
        original, breaking any {{@include}} pointing at it.
        """
        original = store.create(conn, "Contested")
        store.soft_delete(conn, original.id)

        newcomer = store.create(conn, "Contested")
        assert newcomer.name == "contested-2", "the deleted prompt still holds 'contested'"

        restored = store.restore(conn, original.id)
        assert restored.name == "contested", "restore returns the original name intact"

    def test_get_by_name_ignores_deleted(self, conn):
        prompt = store.create(conn, "Hidden")
        store.soft_delete(conn, prompt.id)
        assert store.get_by_name(conn, "hidden") is None

    def test_purge_is_permanent(self, conn):
        prompt = store.create(conn, "Gone")
        store.soft_delete(conn, prompt.id)
        store.purge(conn, prompt.id)
        assert store.get(conn, prompt.id) is None
        assert store.list_trash(conn) == []


class TestListing:
    def test_live_is_newest_first(self, conn):
        a = store.create(conn, "First")
        b = store.create(conn, "Second")
        assert [p.id for p in store.list_live(conn)] == [b.id, a.id]

    def test_count_live_excludes_trash(self, conn):
        a = store.create(conn, "A")
        store.create(conn, "B")
        store.soft_delete(conn, a.id)
        assert store.count_live(conn) == 1


class TestSummary:
    def test_summary_skips_the_title_line(self, conn):
        prompt = store.create(conn, "Title line\nfirst body line\nsecond body line")
        assert prompt.summary == "first body line second body line"

    def test_summary_of_a_one_line_prompt_is_empty(self, conn):
        assert store.create(conn, "Only a title").summary == ""
