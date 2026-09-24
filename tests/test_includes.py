"""Include resolution: nesting, cycles, depth, and blanks inside blocks."""

from __future__ import annotations

from typing import ClassVar

import pytest

from prompt_cache.core.render import MAX_INCLUDE_DEPTH, render, resolve


def blank_names(resolved) -> list[str]:
    return [b.name for b in resolved.blanks]


class TestStaticIncludes:
    def test_inserts_the_block_body(self):
        out = render("A {{@b}} C", {}, {"b": "BODY"})
        assert out.text == "A BODY C"

    def test_the_same_block_twice(self):
        assert render("{{@b}}|{{@b}}", {}, {"b": "X"}).text == "X|X"

    def test_missing_block_is_reported_and_empty(self):
        out = render("A{{@nope}}B", {}, {})
        assert out.text == "AB"
        assert out.missing_blocks == ("nope",)
        assert not out.is_complete

    def test_used_blocks_are_listed(self):
        resolved = resolve("{{@a}} {{@b}}", {"a": "A", "b": "B"})
        assert resolved.used_blocks == ("a", "b")

    def test_a_deleted_block_simply_goes_missing(self):
        """`blocks` only ever contains live prompts, so this is the deleted case."""
        assert resolve("{{@gone}}", {}).missing_blocks == ("gone",)


class TestNesting:
    def test_nested_includes_resolve(self):
        blocks = {"outer": "1 {{@inner}} 3", "inner": "2"}
        assert render("{{@outer}}", {}, blocks).text == "1 2 3"

    def test_three_deep(self):
        blocks = {"a": "A{{@b}}", "b": "B{{@c}}", "c": "C"}
        assert render("{{@a}}", {}, blocks).text == "ABC"

    def test_depth_is_capped(self):
        """A chain longer than the cap stops and says so, rather than recursing away."""
        depth = MAX_INCLUDE_DEPTH + 5
        blocks = {f"b{i}": f"{i}{{{{@b{i + 1}}}}}" for i in range(depth)}
        blocks[f"b{depth}"] = "END"
        out = render("{{@b0}}", {}, blocks)
        assert any("nested more than" in w.message for w in out.warnings)
        assert "END" not in out.text

    def test_a_diamond_is_not_a_cycle(self):
        """Two paths to the same block are fine; only a loop is a problem."""
        blocks = {
            "top": "{{@left}}{{@right}}",
            "left": "[{{@shared}}]",
            "right": "({{@shared}})",
            "shared": "S",
        }
        out = render("{{@top}}", {}, blocks)
        assert out.text == "[S](S)"
        assert out.warnings == ()


class TestCycles:
    def test_direct_self_reference(self):
        out = render("{{@a}}", {}, {"a": "loop {{@a}}"})
        assert any("cycle" in w.message.lower() for w in out.warnings)
        assert out.text == "loop "

    def test_two_step_cycle_names_the_chain(self):
        blocks = {"a": "A{{@b}}", "b": "B{{@a}}"}
        out = render("{{@a}}", {}, blocks)
        cycle = next(w for w in out.warnings if "cycle" in w.message.lower())
        assert "a -> b -> a" in cycle.message

    def test_a_cycle_does_not_lose_the_rest_of_the_output(self):
        blocks = {"a": "start {{@b}} end", "b": "{{@a}}"}
        out = render("{{@a}}", {}, blocks)
        assert "start" in out.text and "end" in out.text

    def test_a_long_cycle_is_caught(self):
        blocks = {"a": "{{@b}}", "b": "{{@c}}", "c": "{{@a}}"}
        assert any("cycle" in w.message.lower() for w in render("{{@a}}", {}, blocks).warnings)

    @pytest.mark.parametrize(
        "blocks",
        [
            {"a": "{{@a}}"},
            {"a": "{{@b}}", "b": "{{@a}}"},
            {"a": "{{@b}}{{@c}}", "b": "{{@a}}", "c": "{{@a}}"},
        ],
    )
    def test_cycles_never_hang_or_raise(self, blocks):
        render("{{@a}}", {}, blocks)


class TestBlanksInsideBlocks:
    def test_a_blocks_blanks_become_the_templates_blanks(self):
        resolved = resolve("{{@sig}}", {"sig": "Regards, {{me}}"})
        assert blank_names(resolved) == ["me"]

    def test_and_they_can_be_filled(self):
        out = render("{{@sig}}", {"me": "Sam"}, {"sig": "Regards, {{me}}"})
        assert out.text == "Regards, Sam"

    def test_the_outer_declaration_wins_on_a_name_clash(self):
        blocks = {"b": "{{tone}}"}
        resolved = resolve("{{tone: a | b}} {{@b}}", blocks)
        assert resolved.blank("tone").is_choice, "the outer declaration is kept"

    def test_a_blank_shared_between_template_and_block_fills_once(self):
        out = render("{{name}} / {{@b}}", {"name": "X"}, {"b": "again {{name}}"})
        assert out.text == "X / again X"

    def test_optional_inside_a_block_still_removes_its_line(self):
        blocks = {"b": "KEEP\nNOTE: {{n: optional}}\nKEEP2"}
        assert render("{{@b}}", {"n": ""}, blocks).text == "KEEP\nKEEP2"


class TestChoiceOfBlock:
    BLOCKS: ClassVar[dict[str, str]] = {
        "me-profile": "I am me.",
        "agency-info": "We are the agency.",
    }

    def test_the_chosen_block_is_inserted(self):
        body = "{{persona: @me-profile | @agency-info}}"
        out = render(body, {"persona": "@agency-info"}, self.BLOCKS)
        assert out.text == "We are the agency."

    def test_switching_the_choice_switches_the_block(self):
        body = "{{persona: @me-profile | @agency-info}}"
        assert render(body, {"persona": "@me-profile"}, self.BLOCKS).text == "I am me."

    def test_the_default_option_is_used_when_no_value_is_given(self):
        body = "X {{persona: @me-profile | @agency-info}}"
        from prompt_cache.core.render import initial_values

        resolved = resolve(body, self.BLOCKS)
        values = initial_values(resolved).values
        assert render(resolved, values).text == "X I am me."

    def test_none_removes_its_line(self):
        body = "A\nPROOF: {{p: @me-profile | none}}\nB"
        assert render(body, {"p": "none"}, self.BLOCKS).text == "A\nB"

    def test_one_template_serves_both_personas(self):
        """The whole point of choice-of-block: no duplicated templates (D21)."""
        body = "Write as:\n{{persona: @me-profile | @agency-info}}\nEnd"
        as_me = render(body, {"persona": "@me-profile"}, self.BLOCKS).text
        as_agency = render(body, {"persona": "@agency-info"}, self.BLOCKS).text
        assert as_me == "Write as:\nI am me.\nEnd"
        assert as_agency == "Write as:\nWe are the agency.\nEnd"

    def test_a_missing_chosen_block_is_reported(self):
        out = render("{{p: @gone | @me-profile}}", {"p": "@gone"}, self.BLOCKS)
        assert "gone" in out.missing_blocks

    def test_blanks_inside_a_chosen_block_are_collected(self):
        blocks = {"a": "A {{x}}", "b": "B"}
        resolved = resolve("{{p: @a | @b}}", blocks)
        assert "x" in blank_names(resolved)

    def test_a_cycle_through_a_choice_is_caught(self):
        blocks = {"a": "{{p: @a | none}}"}
        out = render("{{@a}}", {"p": "@a"}, blocks)
        assert any("cycle" in w.message.lower() for w in out.warnings)


class TestUsedBy:
    def test_counts_direct_includes_and_choice_options(self, tmp_path):
        from prompt_cache.store import prompts as store
        from prompt_cache.store.db import database

        with database(tmp_path / "u.db") as conn:
            block = store.create(conn, "Agency info\nWe do things.")
            store.create(conn, "T1\n{{@agency-info}}")
            store.create(conn, "T2\n{{persona: @agency-info | none}}")
            store.create(conn, "T3\nno reference here")

            users = store.used_by(conn, block.name, exclude_id=block.id)
            assert sorted(p.title for p in users) == ["T1", "T2"]

    def test_an_escaped_reference_does_not_count(self, tmp_path):
        from prompt_cache.store import prompts as store
        from prompt_cache.store.db import database

        with database(tmp_path / "u2.db") as conn:
            block = store.create(conn, "Agency info\nbody")
            store.create(conn, "Docs\nWrite \\{{@agency-info}} to include it.")
            assert store.used_by(conn, block.name, exclude_id=block.id) == []
