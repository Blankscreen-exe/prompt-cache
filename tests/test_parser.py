"""The template grammar, form by form, plus the awkward cases.

The parser must never raise: bad input degrades and warns. Every test here that feeds it
nonsense asserts on the degradation, not on an exception.
"""

from __future__ import annotations

import pytest

from prompt_cache.core.parser import (
    BlankKind,
    BlankRef,
    IncludeRef,
    Literal,
    parse,
)


def literals(template) -> str:
    return "".join(t.text for t in template.tokens if isinstance(t, Literal))


def names(template) -> list[str]:
    return [b.name for b in template.blanks]


class TestPlainText:
    def test_no_blanks(self):
        template = parse("Just some text.")
        assert template.blanks == ()
        assert not template.is_template
        assert literals(template) == "Just some text."

    def test_empty_body(self):
        assert parse("").tokens == ()


class TestTextBlanks:
    def test_simple_blank(self):
        blank = parse("Post: {{post}}").blanks[0]
        assert blank.name == "post"
        assert blank.kind is BlankKind.TEXT
        assert not blank.from_clipboard
        assert not blank.optional

    def test_clipboard_modifier(self):
        assert parse("{{post: clipboard}}").blanks[0].from_clipboard

    def test_optional_modifier(self):
        assert parse("{{note: optional}}").blanks[0].optional

    def test_modifiers_combine_with_a_comma(self):
        blank = parse("{{note: clipboard, optional}}").blanks[0]
        assert blank.from_clipboard and blank.optional

    def test_modifier_order_does_not_matter(self):
        blank = parse("{{note: optional , clipboard}}").blanks[0]
        assert blank.from_clipboard and blank.optional

    def test_modifiers_are_case_insensitive(self):
        assert parse("{{note: CLIPBOARD}}").blanks[0].from_clipboard


class TestChoices:
    def test_options_and_implicit_default(self):
        blank = parse("{{tone: professional | friendly | witty}}").blanks[0]
        assert blank.kind is BlankKind.CHOICE
        assert [o.label for o in blank.options] == ["professional", "friendly", "witty"]
        assert blank.default_value == "professional", "first option is the default"

    def test_explicit_default(self):
        blank = parse("{{tone: professional | friendly = friendly}}").blanks[0]
        assert blank.default_value == "friendly"

    def test_default_not_among_options_warns_and_falls_back(self):
        template = parse("{{tone: a | b = zzz}}")
        assert template.blanks[0].default_value == "a"
        assert any("zzz" in w.message for w in template.warnings)

    def test_an_option_may_contain_a_comma(self):
        """The comma splits modifiers, but only where it is not inside a choice list."""
        blank = parse("{{tone: short, punchy | long}}").blanks[0]
        assert [o.label for o in blank.options] == ["short, punchy", "long"]

    def test_equals_inside_a_non_final_option_is_not_a_default(self):
        blank = parse("{{x: a=b | c}}").blanks[0]
        assert [o.label for o in blank.options] == ["a=b", "c"]
        assert blank.default is None

    def test_empty_options_are_dropped_with_a_warning(self):
        template = parse("{{x: a || b}}")
        assert [o.label for o in template.blanks[0].options] == ["a", "b"]
        assert any("Empty option" in w.message for w in template.warnings)

    def test_clipboard_on_a_choice_is_ignored_with_a_warning(self):
        template = parse("{{x: clipboard, a | b}}")
        assert not template.blanks[0].from_clipboard
        assert any("no effect" in w.message for w in template.warnings)

    def test_a_single_option_is_still_a_choice(self):
        assert parse("{{x: only}}").blanks[0].kind is BlankKind.CHOICE


class TestChoiceOfBlock:
    def test_block_options(self):
        blank = parse("{{persona: @me-profile | @agency-info}}").blanks[0]
        assert blank.kind is BlankKind.BLOCK_CHOICE
        assert [o.block for o in blank.options] == ["me-profile", "agency-info"]
        assert blank.default_value == "@me-profile"

    def test_none_is_an_opt_out_inside_a_block_list(self):
        blank = parse("{{proof: @a | @b | none}}").blanks[0]
        assert blank.options[-1].is_none
        assert not blank.options[-1].is_block

    def test_none_is_ordinary_text_outside_a_block_list(self):
        blank = parse("{{x: none | something}}").blanks[0]
        assert blank.kind is BlankKind.CHOICE
        assert not blank.options[0].is_none

    def test_mixing_text_into_a_block_list_warns(self):
        template = parse("{{x: @a | plain text}}")
        assert any("mixes plain text" in w.message for w in template.warnings)
        assert template.blanks[0].kind is BlankKind.BLOCK_CHOICE

    def test_invalid_block_name_warns(self):
        template = parse("{{x: @1bad | @good}}")
        assert [o.block for o in template.blanks[0].options] == ["good"]
        assert any("not a valid block name" in w.message for w in template.warnings)


class TestIncludes:
    def test_static_include(self):
        template = parse("Intro\n{{@agency-info}}\nOutro")
        assert template.includes == ("agency-info",)
        assert any(isinstance(t, IncludeRef) for t in template.tokens)

    def test_repeated_include_listed_once(self):
        assert parse("{{@a}} {{@a}}").includes == ("a",)

    def test_include_makes_it_a_template_even_without_blanks(self):
        assert parse("{{@a}}").is_template

    def test_invalid_include_name_is_kept_as_text(self):
        template = parse("{{@ }}")
        assert template.includes == ()
        assert "{{@ }}" in literals(template)


class TestNames:
    def test_names_are_case_insensitive_and_share_one_blank(self):
        template = parse("{{Post}} and {{post}} and {{POST}}")
        assert names(template) == ["post"]
        assert sum(isinstance(t, BlankRef) for t in template.tokens) == 3

    def test_display_name_keeps_the_first_spelling(self):
        assert parse("{{Post}} {{post}}").blanks[0].display_name == "Post"

    def test_blanks_are_ordered_by_first_appearance(self):
        assert names(parse("{{b}} {{a}} {{b}} {{c}}")) == ["b", "a", "c"]

    @pytest.mark.parametrize("name", ["1abc", "-abc", "_abc", "a b", "a.b", ""])
    def test_invalid_names_are_left_as_text_with_a_warning(self, name):
        template = parse("x {{" + name + "}} y")
        assert template.blanks == ()
        assert template.warnings

    @pytest.mark.parametrize("name", ["a", "post", "my_comment", "their-reply", "x1"])
    def test_valid_names(self, name):
        assert names(parse("{{" + name + "}}")) == [name]


class TestRepeatedDeclarations:
    def test_first_declaration_wins(self):
        template = parse("{{post: clipboard}} then {{post}}")
        assert template.blanks[0].from_clipboard

    def test_a_later_declaration_does_not_override(self):
        template = parse("{{tone: a | b}} then {{tone: x | y}}")
        assert [o.label for o in template.blanks[0].options] == ["a", "b"]
        assert any("declared twice" in w.message for w in template.warnings)

    def test_a_bare_reference_after_a_declaration_is_silent(self):
        assert parse("{{post: clipboard}} {{post}}").warnings == ()

    def test_a_declaration_after_a_bare_reference_is_adopted(self):
        template = parse("{{post}} then {{post: clipboard}}")
        assert template.blanks[0].from_clipboard
        assert template.warnings == ()


class TestEscapingAndMalformedInput:
    def test_escape_renders_a_literal_brace(self):
        template = parse(r"Use \{{ to open")
        assert literals(template) == "Use {{ to open"
        assert template.blanks == ()

    def test_unclosed_brace_is_text_and_warns(self):
        template = parse("Broken {{post")
        assert template.blanks == ()
        assert any("Unclosed" in w.message for w in template.warnings)

    def test_empty_braces_are_kept_as_text(self):
        template = parse("a {{}} b")
        assert "{{}}" in literals(template)
        assert template.warnings

    def test_empty_modifier_warns_but_still_works(self):
        template = parse("{{post:}}")
        assert template.blanks[0].kind is BlankKind.TEXT

    @pytest.mark.parametrize(
        "body",
        [
            "{{",
            "}}",
            "{{}}",
            "{{{{}}}}",
            "{{a}",
            "{a}}",
            r"\{{a}}",
            "{{a: }}",
            "{{ }}",
            "{{:}}",
            "{{a:|}}",
            "{{a:=}}",
            "{{@}}",
            "{{@@a}}",
            "{{a" + "b" * 500 + "}}",
        ],
    )
    def test_never_raises_on_malformed_input(self, body):
        parse(body)

    def test_multiline_blank_declaration(self):
        assert names(parse("{{tone: a\n| b}}")) == ["tone"]


class TestRoundTrip:
    def test_a_realistic_template(self):
        body = (
            "Write a comment on the post below. Under 80 words.\n\n"
            "{{@social-voice}}\n"
            "{{persona: @me-profile | @agency-info}}\n"
            "{{proof: @my-cases | @agency-cases | none}}\n\n"
            "ANGLE: {{angle: counterpoint | experience | question}}\n\n"
            "POST:\n{{post: clipboard}}\n\n"
            "MY NOTE: {{note: optional}}\n"
        )
        template = parse(body)
        assert names(template) == ["persona", "proof", "angle", "post", "note"]
        assert template.includes == ("social-voice",)
        assert template.warnings == ()
        assert template.blank("post").from_clipboard
        assert template.blank("note").optional
        assert template.blank("proof").options[-1].is_none
