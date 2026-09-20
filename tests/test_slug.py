from __future__ import annotations

import pytest

from prompt_cache.core.slug import extract_tags, make_slug, title_from_body


class TestTitleFromBody:
    def test_first_line_becomes_the_title(self):
        assert title_from_body("Write a comment\n\nrest of it") == "Write a comment"

    def test_leading_markdown_hashes_are_stripped(self):
        assert title_from_body("## My prompt\nbody") == "My prompt"

    def test_leading_blank_lines_are_skipped(self):
        assert title_from_body("\n\n  Actual title\nbody") == "Actual title"

    def test_a_line_of_only_hashes_is_skipped(self):
        assert title_from_body("###\nReal title") == "Real title"

    @pytest.mark.parametrize("body", ["", "   ", "\n\n\n", "#", "##  ##"])
    def test_empty_bodies_fall_back(self, body: str):
        assert title_from_body(body) == "Untitled"

    def test_long_titles_are_truncated(self):
        assert len(title_from_body("x" * 500)) == 120


class TestMakeSlug:
    def test_basic(self):
        assert make_slug("LinkedIn comment") == "linkedin-comment"

    def test_punctuation_and_case(self):
        assert make_slug("Reply to a Reply!! (v2)") == "reply-to-a-reply-v2"

    def test_unicode_is_transliterated(self):
        assert make_slug("Café résumé") == "cafe-resume"

    def test_unsluggable_input_falls_back(self):
        assert make_slug("!!!") == "untitled"
        assert make_slug("") == "untitled"


class TestExtractTags:
    def test_finds_inline_tags(self):
        assert extract_tags("A prompt #social #outreach") == ("social", "outreach")

    def test_lowercases_and_deduplicates_preserving_order(self):
        assert extract_tags("#Social text #social more #Outreach") == ("social", "outreach")

    def test_markdown_headings_are_not_tags(self):
        assert extract_tags("# Heading\n## Another") == ()

    def test_numeric_and_bare_hashes_are_not_tags(self):
        assert extract_tags("#1 #123 # #") == ()

    def test_hash_inside_a_word_is_not_a_tag(self):
        assert extract_tags("C#, item a#b") == ()

    def test_fenced_code_blocks_are_ignored(self):
        body = "Real #keeper\n\n```bash\n# a comment\necho '#notatag'\n```\n\n#alsokept"
        assert extract_tags(body) == ("keeper", "alsokept")

    def test_tilde_fences_are_ignored_too(self):
        assert extract_tags("~~~\n#hidden\n~~~\n#shown") == ("shown",)

    def test_hyphens_and_underscores_are_allowed(self):
        assert extract_tags("#multi-word #snake_case") == ("multi-word", "snake_case")

    def test_no_tags(self):
        assert extract_tags("plain text with no tags") == ()
