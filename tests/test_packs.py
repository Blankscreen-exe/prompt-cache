"""Packs, backups and version history — the "nothing is ever lost" milestone."""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from prompt_cache.core import diffing
from prompt_cache.packs import dump_backup, export_pack, import_pack, load_backup, preview_pack
from prompt_cache.packs.importing import OnCollision, PackError
from prompt_cache.store import conversations as conversation_store
from prompt_cache.store import prompts as prompt_store
from prompt_cache.store.db import database


@pytest.fixture
def conn(tmp_path: Path):
    with database(tmp_path / "m5.db") as connection:
        yield connection


@pytest.fixture
def other(tmp_path: Path):
    """A second, empty database — the "laptop"."""
    with database(tmp_path / "laptop.db") as connection:
        yield connection


class TestVersions:
    def test_the_first_edit_snapshots_the_original(self, conn):
        prompt = prompt_store.create(conn, "Title\noriginal body")
        prompt_store.update_body(conn, prompt.id, "Title\nchanged body")

        versions = prompt_store.versions_for(conn, prompt.id)
        assert len(versions) == 1
        assert versions[0].body == "Title\noriginal body"

    def test_typing_does_not_create_hundreds_of_versions(self, conn):
        """Debounce: a burst of edits snapshots once, not once per keystroke."""
        prompt = prompt_store.create(conn, "Title\nv0")
        for index in range(50):
            prompt_store.update_body(conn, prompt.id, f"Title\nv{index}")
        assert len(prompt_store.versions_for(conn, prompt.id)) == 1

    def test_an_edit_after_the_interval_snapshots_again(self, conn, monkeypatch):
        prompt = prompt_store.create(conn, "Title\nv0")
        prompt_store.update_body(conn, prompt.id, "Title\nv1")

        # Pretend the existing version is older than the debounce window.
        old = prompt_store.versions_for(conn, prompt.id)[0]
        stale = (old.created_at - timedelta(minutes=5)).isoformat()
        conn.execute("UPDATE prompt_versions SET created_at = ? WHERE id = ?", (stale, old.id))

        prompt_store.update_body(conn, prompt.id, "Title\nv2")
        assert len(prompt_store.versions_for(conn, prompt.id)) == 2

    def test_forcing_always_snapshots(self, conn):
        prompt = prompt_store.create(conn, "Title\nv0")
        prompt_store.update_body(conn, prompt.id, "Title\nv1")
        prompt_store.update_body(conn, prompt.id, "Title\nv2", force_version=True)
        assert len(prompt_store.versions_for(conn, prompt.id)) == 2

    def test_saving_identical_text_does_not_snapshot(self, conn):
        prompt = prompt_store.create(conn, "Title\nsame")
        prompt_store.update_body(conn, prompt.id, "Title\nsame")
        assert prompt_store.versions_for(conn, prompt.id) == []

    def test_restore_brings_an_old_body_back(self, conn):
        prompt = prompt_store.create(conn, "Title\noriginal")
        prompt_store.update_body(conn, prompt.id, "Title\nreplacement")
        version = prompt_store.versions_for(conn, prompt.id)[0]

        restored = prompt_store.restore_version(conn, prompt.id, version.id)
        assert restored.body == "Title\noriginal"

    def test_restore_never_destroys_what_it_replaced(self, conn):
        prompt = prompt_store.create(conn, "Title\noriginal")
        prompt_store.update_body(conn, prompt.id, "Title\nreplacement")
        version = prompt_store.versions_for(conn, prompt.id)[0]

        prompt_store.restore_version(conn, prompt.id, version.id)
        bodies = [v.body for v in prompt_store.versions_for(conn, prompt.id)]
        assert "Title\nreplacement" in bodies, "the replaced text stays recoverable"

    def test_restoring_an_unknown_version_raises(self, conn):
        prompt = prompt_store.create(conn, "Title\nbody")
        with pytest.raises(KeyError):
            prompt_store.restore_version(conn, prompt.id, "nope")

    def test_versions_go_when_the_prompt_is_purged(self, conn):
        prompt = prompt_store.create(conn, "Title\nv0")
        prompt_store.update_body(conn, prompt.id, "Title\nv1")
        prompt_store.purge(conn, prompt.id)
        assert conn.execute("SELECT count(*) FROM prompt_versions").fetchone()[0] == 0


class TestDiffing:
    def test_identical_text_has_no_diff(self):
        assert diffing.unified("same", "same") == ""

    def test_a_change_shows_both_sides(self):
        diff = diffing.unified("one\ntwo", "one\nthree")
        assert "-two" in diff and "+three" in diff

    def test_summarise_counts_lines(self):
        assert diffing.summarise("a\nb", "a\nb\nc") == (1, 0)
        assert diffing.summarise("a\nb\nc", "a") == (0, 2)


class TestPackRoundTrip:
    def test_export_then_import_into_a_fresh_database(self, conn, other, tmp_path):
        """The PC-to-laptop path (D16/D25)."""
        prompt_store.create(conn, "Agency info\nWe do things. #standing")
        template = prompt_store.create(conn, "Outreach\n{{@agency-info}}\n{{post: clipboard}}")
        prompt_store.toggle_pin(conn, template.id)

        result = export_pack(conn, tmp_path / "pack", name="my setup")
        assert result.prompt_count == 2

        imported = import_pack(other, tmp_path / "pack")
        assert imported.imported == 2

        moved = prompt_store.get_by_name(other, "outreach")
        assert moved is not None
        assert "{{@agency-info}}" in moved.body
        assert moved.pinned, "pin state travels with the pack"
        assert prompt_store.get_by_name(other, "agency-info") is not None

    def test_a_pack_is_plain_readable_markdown(self, conn, tmp_path):
        prompt_store.create(conn, "Readable\nthe body text")
        export_pack(conn, tmp_path / "pack")

        body = (tmp_path / "pack" / "prompts" / "readable.md").read_text(encoding="utf-8")
        assert body == "Readable\nthe body text"
        manifest = json.loads((tmp_path / "pack" / "pack.json").read_text(encoding="utf-8"))
        assert manifest["prompts"][0]["name"] == "readable"

    def test_a_pack_never_contains_conversations(self, conn, tmp_path):
        """Threads hold real posts and replies; sharing a pack must not leak them."""
        template = prompt_store.create(conn, "T\n{{post}}")
        conversation_store.add_fill(
            conn, prompt_id=template.id, values={"post": "SECRET POST"}, output="SECRET OUTPUT"
        )
        export_pack(conn, tmp_path / "pack")

        everything = " ".join(
            path.read_text(encoding="utf-8")
            for path in (tmp_path / "pack").rglob("*")
            if path.is_file()
        )
        assert "SECRET" not in everything

    def test_deleted_prompts_are_not_exported(self, conn, tmp_path):
        gone = prompt_store.create(conn, "Gone\nbody")
        prompt_store.create(conn, "Kept\nbody")
        prompt_store.soft_delete(conn, gone.id)
        assert export_pack(conn, tmp_path / "pack").names == ("kept",)

    def test_only_selected_prompts_are_exported(self, conn, tmp_path):
        one = prompt_store.create(conn, "One\nbody")
        prompt_store.create(conn, "Two\nbody")
        assert export_pack(conn, tmp_path / "p", prompt_ids=[one.id]).names == ("one",)


class TestPackImportPreview:
    def test_preview_reports_collisions_without_writing(self, conn, tmp_path):
        prompt_store.create(conn, "Shared\noriginal here")
        export_pack(conn, tmp_path / "pack")
        before = len(prompt_store.list_live(conn))

        preview = preview_pack(conn, tmp_path / "pack")
        assert [e.name for e in preview.collisions] == ["shared"]
        assert len(prompt_store.list_live(conn)) == before, "preview must not write"

    def test_keep_both_renames_rather_than_clobbering(self, conn, tmp_path):
        prompt_store.create(conn, "Shared\noriginal here")
        export_pack(conn, tmp_path / "pack")

        result = import_pack(conn, tmp_path / "pack", on_collision=OnCollision.KEEP_BOTH)
        assert result.imported == 1
        assert result.renamed == (("shared", "shared-2"),)
        assert prompt_store.get_by_name(conn, "shared").body == "Shared\noriginal here"

    def test_skip_leaves_the_existing_prompt_alone(self, conn, tmp_path):
        prompt_store.create(conn, "Shared\noriginal here")
        export_pack(conn, tmp_path / "pack")

        result = import_pack(conn, tmp_path / "pack", on_collision=OnCollision.SKIP)
        assert result.skipped == 1
        assert len(prompt_store.list_live(conn)) == 1

    def test_overwrite_replaces_but_keeps_a_version(self, conn, tmp_path):
        original = prompt_store.create(conn, "Shared\noriginal here")
        export_pack(conn, tmp_path / "pack")
        prompt_store.update_body(conn, original.id, "Shared\nlocally changed")

        result = import_pack(conn, tmp_path / "pack", on_collision=OnCollision.OVERWRITE)
        assert result.overwritten == 1
        assert prompt_store.get(conn, original.id).body == "Shared\noriginal here"
        bodies = [v.body for v in prompt_store.versions_for(conn, original.id)]
        assert "Shared\nlocally changed" in bodies, "the overwritten text stays recoverable"

    def test_only_imports_the_named_prompts(self, conn, other, tmp_path):
        prompt_store.create(conn, "One\nbody")
        prompt_store.create(conn, "Two\nbody")
        export_pack(conn, tmp_path / "pack")

        import_pack(other, tmp_path / "pack", only=["one"])
        assert [p.name for p in prompt_store.list_live(other)] == ["one"]

    def test_a_folder_that_is_not_a_pack_says_so(self, conn, tmp_path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(PackError, match=r"pack\.json"):
            preview_pack(conn, tmp_path / "empty")

    def test_a_broken_manifest_says_so(self, conn, tmp_path):
        (tmp_path / "bad").mkdir()
        (tmp_path / "bad" / "pack.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(PackError, match="valid JSON"):
            preview_pack(conn, tmp_path / "bad")

    def test_a_missing_body_file_is_reported_not_fatal(self, conn, tmp_path):
        prompt_store.create(conn, "One\nbody")
        export_pack(conn, tmp_path / "pack")
        (tmp_path / "pack" / "prompts" / "one.md").unlink()

        preview = preview_pack(conn, tmp_path / "pack")
        assert preview.entries == []
        assert any("missing file" in p for p in preview.problems)


class TestBackup:
    def test_a_backup_round_trips_everything(self, conn, other, tmp_path):
        template = prompt_store.create(conn, "T\n{{post}}")
        prompt_store.update_body(conn, template.id, "T\n{{post}} edited")
        conversation_store.add_fill(conn, prompt_id=template.id, values={"post": "P"}, output="OUT")

        result = dump_backup(conn, tmp_path / "backup.json")
        assert result.counts["prompts"] == 1
        assert result.counts["conversations"] == 1
        assert result.counts["fills"] == 1

        load_backup(other, tmp_path / "backup.json")
        assert len(prompt_store.list_live(other)) == 1
        assert len(conversation_store.list_live(other)) == 1
        assert conversation_store.list_live(other)[0].fill_count == 1

    def test_a_backup_does_include_conversations(self, conn, tmp_path):
        """Unlike a pack. A backup is for the owner, not for sharing."""
        template = prompt_store.create(conn, "T\n{{post}}")
        conversation_store.add_fill(
            conn, prompt_id=template.id, values={"post": "PRIVATE"}, output="PRIVATE OUT"
        )
        dump_backup(conn, tmp_path / "backup.json")
        assert "PRIVATE" in (tmp_path / "backup.json").read_text(encoding="utf-8")

    def test_search_works_again_after_a_restore(self, conn, other, tmp_path):
        """FTS tables are rebuilt rather than dumped, so they must be repopulated."""
        from prompt_cache.store import search

        prompt_store.create(conn, "Findable\nwith distinctive wording")
        dump_backup(conn, tmp_path / "backup.json")
        load_backup(other, tmp_path / "backup.json")

        hits = search.search(other, "distinctive").flat()
        assert [h.prompt.name for h in hits] == ["findable"]

    def test_restoring_replaces_rather_than_merges(self, conn, other, tmp_path):
        prompt_store.create(conn, "From backup\nbody")
        dump_backup(conn, tmp_path / "backup.json")

        prompt_store.create(other, "Pre-existing\nbody")
        load_backup(other, tmp_path / "backup.json")

        assert [p.name for p in prompt_store.list_live(other)] == ["from-backup"]
