"""Assembly, the optional-line rule, and pre-fill precedence."""

from __future__ import annotations

from prompt_cache.core.parser import parse
from prompt_cache.core.render import ValueSource, initial_values, render


class TestSubstitution:
    def test_fills_a_blank(self):
        assert render("Hello {{name}}!", {"name": "world"}).text == "Hello world!"

    def test_repeated_blank_is_filled_everywhere(self):
        assert render("{{x}} and {{x}} and {{x}}", {"x": "a"}).text == "a and a and a"

    def test_case_insensitive_lookup(self):
        assert render("{{Name}}", {"name": "v"}).text == "v"

    def test_missing_value_renders_empty_and_is_reported(self):
        result = render("A{{x}}B", {})
        assert result.text == "AB"
        assert result.missing == ("x",)
        assert not result.is_complete

    def test_whitespace_only_value_counts_as_missing(self):
        assert render("{{x}}", {"x": "   "}).missing == ("x",)

    def test_a_filled_template_is_complete(self):
        assert render("{{x}}", {"x": "v"}).is_complete

    def test_escaped_braces_survive(self):
        assert render(r"literal \{{ here", {}).text == "literal {{ here"

    def test_multiline_values_are_inserted_verbatim(self):
        body = "POST:\n{{post}}\nEND"
        assert render(body, {"post": "one\ntwo"}).text == "POST:\none\ntwo\nEND"

    def test_no_values_needed(self):
        assert render("plain text", {}).text == "plain text"


class TestOptionalLineRule:
    def test_empty_optional_removes_its_whole_line(self):
        body = "A\nMY COMMENT: {{c: optional}}\nB"
        assert render(body, {"c": ""}).text == "A\nB"

    def test_filled_optional_keeps_the_line(self):
        body = "A\nMY COMMENT: {{c: optional}}\nB"
        assert render(body, {"c": "hi"}).text == "A\nMY COMMENT: hi\nB"

    def test_whitespace_only_counts_as_empty(self):
        body = "A\nX: {{c: optional}}\nB"
        assert render(body, {"c": "  \t "}).text == "A\nB"

    def test_an_empty_non_optional_blank_keeps_its_line(self):
        """Only `optional` removes lines; a plain empty blank leaves the scaffolding."""
        body = "A\nLABEL: {{c}}\nB"
        assert render(body, {"c": ""}).text == "A\nLABEL: \nB"

    def test_stranded_blank_lines_collapse(self):
        body = "A\n\n{{c: optional}}\n\nB"
        assert render(body, {"c": ""}).text == "A\n\nB"

    def test_author_spacing_is_untouched_when_nothing_is_removed(self):
        body = "A\n\n\n\nB"
        assert render(body, {}).text == body, "no removal means no reformatting"

    def test_several_optionals_on_separate_lines(self):
        body = "keep\n1: {{a: optional}}\n2: {{b: optional}}\nkeep2"
        assert render(body, {"a": "", "b": ""}).text == "keep\nkeep2"

    def test_only_the_empty_one_is_removed(self):
        body = "1: {{a: optional}}\n2: {{b: optional}}"
        assert render(body, {"a": "", "b": "kept"}).text == "2: kept"

    def test_two_blanks_on_one_line_one_empty_removes_the_line(self):
        assert render("{{a: optional}} {{b}}", {"a": "", "b": "x"}).text == ""

    def test_optional_missing_is_not_reported_as_missing(self):
        assert render("{{a: optional}}", {"a": ""}).missing == ()


class TestChoices:
    def test_choice_value_is_inserted(self):
        assert render("{{t: a | b}}", {"t": "b"}).text == "b"

    def test_none_option_removes_its_line(self):
        body = "A\nPROOF: {{p: @x | none}}\nB"
        assert render(body, {"p": "none"}).text == "A\nB"

    def test_a_block_option_contributes_nothing_until_m3(self):
        assert render("{{p: @x | @y}}", {"p": "@x"}).text == ""

    def test_a_value_outside_the_options_is_still_inserted(self):
        """The form constrains choices; the renderer does not second-guess a value."""
        assert render("{{t: a | b}}", {"t": "custom"}).text == "custom"


class TestIncludes:
    def test_include_is_not_resolved_yet_but_warns(self):
        result = render("before {{@block}} after", {})
        assert "block" in result.warnings[-1].message
        assert result.text == "before  after"


class TestWarningsSurvive:
    def test_parse_warnings_reach_the_result(self):
        assert render("{{1bad}}", {}).warnings

    def test_accepts_an_already_parsed_template(self):
        template = parse("{{x}}")
        assert render(template, {"x": "v"}).text == "v"


class TestInitialValues:
    def test_clipboard_fills_a_clipboard_blank(self):
        prefill = initial_values(parse("{{post: clipboard}}"), clipboard_text="pasted")
        assert prefill.values["post"] == "pasted"
        assert prefill.sources["post"] is ValueSource.CLIPBOARD

    def test_clipboard_is_ignored_for_a_plain_blank(self):
        prefill = initial_values(parse("{{post}}"), clipboard_text="pasted")
        assert prefill.values["post"] == ""
        assert prefill.sources["post"] is ValueSource.EMPTY

    def test_choice_starts_on_its_default(self):
        prefill = initial_values(parse("{{t: a | b = b}}"))
        assert prefill.values["t"] == "b"
        assert prefill.sources["t"] is ValueSource.DEFAULT

    def test_choice_without_a_default_starts_on_the_first_option(self):
        assert initial_values(parse("{{t: a | b}}")).values["t"] == "a"

    def test_conversation_beats_clipboard(self):
        """The precedence order in docs/02-concepts.md, top to bottom."""
        prefill = initial_values(
            parse("{{post: clipboard}}"),
            clipboard_text="from clipboard",
            conversation={"post": "from thread"},
        )
        assert prefill.values["post"] == "from thread"
        assert prefill.sources["post"] is ValueSource.CONVERSATION

    def test_conversation_beats_a_choice_default(self):
        prefill = initial_values(parse("{{t: a | b}}"), conversation={"t": "b"})
        assert prefill.values["t"] == "b"

    def test_empty_conversation_value_does_not_win(self):
        prefill = initial_values(
            parse("{{post: clipboard}}"), clipboard_text="cb", conversation={"post": ""}
        )
        assert prefill.values["post"] == "cb"

    def test_empty_clipboard_falls_through(self):
        prefill = initial_values(parse("{{post: clipboard}}"), clipboard_text="")
        assert prefill.values["post"] == ""
        assert prefill.sources["post"] is ValueSource.EMPTY

    def test_every_blank_gets_an_entry(self):
        prefill = initial_values(parse("{{a}} {{b: clipboard}} {{c: x | y}}"))
        assert set(prefill.values) == {"a", "b", "c"}


class TestTheWholeThing:
    def test_a_realistic_template_end_to_end(self):
        body = (
            "Write a comment on the post below. Under 80 words.\n\n"
            "ANGLE: {{angle: counterpoint | experience}}\n\n"
            "POST:\n{{post: clipboard}}\n\n"
            "MY NOTE: {{note: optional}}\n"
        )
        template = parse(body)
        prefill = initial_values(template, clipboard_text="Their post text.")
        result = render(template, prefill.values)

        assert result.is_complete
        assert result.warnings == ()
        # The MY NOTE line goes, and the blank lines it stranded collapse to one —
        # so the output ends cleanly rather than with trailing whitespace.
        assert result.text == (
            "Write a comment on the post below. Under 80 words.\n\n"
            "ANGLE: counterpoint\n\n"
            "POST:\nTheir post text.\n"
        )
        assert "MY NOTE" not in result.text, "the empty optional took its line"
        assert not result.text.endswith("\n\n"), "no trailing blank pile-up"
