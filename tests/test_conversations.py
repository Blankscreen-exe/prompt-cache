"""Conversations: auto-naming, value merging by blank name, and fill history."""

from __future__ import annotations

from pathlib import Path

import pytest

from prompt_cache.core.labels import label_from_values
from prompt_cache.store import conversations as store
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database


@pytest.fixture
def conn(tmp_path: Path):
    with database(tmp_path / "c.db") as connection:
        yield connection


@pytest.fixture
def template(conn):
    return prompt_store.create(conn, "Comment\n{{post}} {{my_comment}}")


class TestLabelling:
    def test_label_comes_from_the_longest_value(self):
        values = {"tone": "brief", "post": "Excited to share that our team just shipped a thing"}
        assert label_from_values(values).startswith("Excited to share")

    def test_label_is_truncated_to_a_few_words(self):
        label = label_from_values({"post": " ".join(f"word{i}" for i in range(50))})
        assert label.endswith("…")
        assert len(label.split()) <= 9

    def test_whitespace_is_normalised(self):
        assert label_from_values({"post": "  a\n\n  b  "}) == "a b"

    def test_no_values_falls_back(self):
        assert label_from_values({}) == "Untitled thread"

    def test_only_empty_values_falls_back(self):
        assert label_from_values({"a": "", "b": "   "}) == "Untitled thread"

    def test_ties_are_broken_deterministically(self):
        values = {"b": "same length", "a": "same length"}
        assert label_from_values(values) == label_from_values(dict(reversed(values.items())))


class TestCreating:
    def test_a_conversation_names_itself(self, conn):
        thread = store.create(conn, {"post": "A post about onboarding flows"})
        assert thread.label == "A post about onboarding flows"
        assert not thread.label_is_custom

    def test_an_explicit_label_is_marked_custom(self, conn):
        assert store.create(conn, {}, label="Mine").label_is_custom

    def test_a_custom_label_survives_new_values(self, conn):
        thread = store.create(conn, {"post": "old"}, label="Mine")
        updated = store.merge_values(conn, thread.id, {"post": "something much longer now"})
        assert updated.label == "Mine"

    def test_a_derived_label_follows_the_content(self, conn):
        thread = store.create(conn, {"post": "short"})
        updated = store.merge_values(conn, thread.id, {"post": "a considerably longer post now"})
        assert updated.label == "a considerably longer post now"


class TestMergingValues:
    def test_values_merge_by_name(self, conn):
        thread = store.create(conn, {"post": "P"})
        updated = store.merge_values(conn, thread.id, {"my_comment": "C"})
        assert updated.values == {"post": "P", "my_comment": "C"}

    def test_later_values_overwrite(self, conn):
        thread = store.create(conn, {"post": "first"})
        assert store.merge_values(conn, thread.id, {"post": "second"}).values["post"] == "second"

    def test_an_empty_value_never_erases_what_is_known(self, conn):
        """A follow-up with a blank field must not wipe the thread's memory."""
        thread = store.create(conn, {"post": "keep me"})
        updated = store.merge_values(conn, thread.id, {"post": "", "other": "  "})
        assert updated.values["post"] == "keep me"
        assert "other" not in updated.values

    def test_set_value_lowercases_the_name(self, conn):
        thread = store.create(conn, {})
        assert "my_comment" in store.set_value(conn, thread.id, "MY_COMMENT", "x").values

    def test_merging_into_a_missing_conversation_raises(self, conn):
        with pytest.raises(KeyError):
            store.merge_values(conn, "nope", {"a": "b"})


class TestFills:
    def test_the_first_fill_starts_a_thread(self, conn, template):
        fill = store.add_fill(conn, prompt_id=template.id, values={"post": "A post"}, output="OUT")
        thread = store.get(conn, fill.conversation_id)
        assert thread.fill_count == 1
        assert thread.values == {"post": "A post"}

    def test_a_second_fill_joins_the_same_thread(self, conn, template):
        first = store.add_fill(conn, prompt_id=template.id, values={"post": "P"}, output="1")
        store.add_fill(
            conn,
            prompt_id=template.id,
            values={"their_reply": "R"},
            output="2",
            conversation_id=first.conversation_id,
        )
        thread = store.get(conn, first.conversation_id)
        assert thread.fill_count == 2
        assert set(thread.values) == {"post", "their_reply"}

    def test_fills_come_back_newest_first_with_their_template(self, conn, template):
        first = store.add_fill(conn, prompt_id=template.id, values={}, output="one")
        store.add_fill(
            conn,
            prompt_id=template.id,
            values={},
            output="two",
            conversation_id=first.conversation_id,
        )
        fills = store.fills_for(conn, first.conversation_id)
        assert [f.output for f in fills] == ["two", "one"]
        assert fills[0].prompt_title == "Comment"

    def test_the_assembled_output_is_frozen_at_fill_time(self, conn, template):
        """Editing a block later must not rewrite what was actually sent."""
        fill = store.add_fill(conn, prompt_id=template.id, values={"post": "P"}, output="ASSEMBLED")
        prompt_store.update_body(conn, template.id, "Comment\ncompletely different")
        assert store.fills_for(conn, fill.conversation_id)[0].output == "ASSEMBLED"

    def test_a_deleted_prompt_leaves_its_fills_readable(self, conn, template):
        fill = store.add_fill(conn, prompt_id=template.id, values={}, output="O")
        prompt_store.soft_delete(conn, template.id)
        assert store.fills_for(conn, fill.conversation_id)[0].output == "O"

    def test_templates_used_are_listed_on_the_thread(self, conn, template):
        other = prompt_store.create(conn, "Reply\n{{their_reply}}")
        fill = store.add_fill(conn, prompt_id=template.id, values={}, output="a")
        store.add_fill(
            conn,
            prompt_id=other.id,
            values={},
            output="b",
            conversation_id=fill.conversation_id,
        )
        assert set(store.get(conn, fill.conversation_id).templates) == {"Comment", "Reply"}


class TestListingAndLifecycle:
    def test_live_threads_are_most_recent_first(self, conn, template):
        a = store.create(conn, {"post": "first"})
        b = store.create(conn, {"post": "second"})
        assert [c.id for c in store.list_live(conn)] == [b.id, a.id]

    def test_archive_hides_from_live_without_losing_it(self, conn):
        thread = store.create(conn, {"post": "P"})
        store.archive(conn, thread.id)
        assert store.list_live(conn) == []
        assert [c.id for c in store.list_archived(conn)] == [thread.id]
        assert store.get(conn, thread.id).is_archived

        store.unarchive(conn, thread.id)
        assert [c.id for c in store.list_live(conn)] == [thread.id]

    def test_soft_delete_and_restore(self, conn):
        thread = store.create(conn, {"post": "P"})
        store.soft_delete(conn, thread.id)
        assert store.list_live(conn) == []
        assert store.restore(conn, thread.id).deleted_at is None
        assert [c.id for c in store.list_live(conn)] == [thread.id]

    def test_deleting_a_thread_takes_its_fills(self, conn, template):
        fill = store.add_fill(conn, prompt_id=template.id, values={}, output="O")
        conn.execute("DELETE FROM conversations WHERE id = ?", (fill.conversation_id,))
        assert conn.execute("SELECT count(*) FROM fills").fetchone()[0] == 0


class TestSearchable:
    def test_a_thread_is_findable_by_its_values(self, conn, template):
        from prompt_cache.store import search

        store.add_fill(
            conn,
            prompt_id=template.id,
            values={"post": "Excited about onboarding flows"},
            output="O",
        )
        hits = search.search(conn, "onboarding").flat()
        assert any(h.is_conversation for h in hits)

    def test_a_deleted_thread_is_not_findable(self, conn, template):
        from prompt_cache.store import search

        fill = store.add_fill(
            conn, prompt_id=template.id, values={"post": "findme zzz"}, output="O"
        )
        store.soft_delete(conn, fill.conversation_id)
        assert not any(h.is_conversation for h in search.search(conn, "findme").flat())

    def test_threads_appear_when_browsing(self, conn, template):
        from prompt_cache.store import search

        store.add_fill(conn, prompt_id=template.id, values={"post": "P"}, output="O")
        groups = [name for name, _ in search.search(conn, "").groups]
        assert "Threads" in groups
