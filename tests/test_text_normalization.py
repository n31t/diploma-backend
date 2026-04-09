"""Tests for TextNormalizationService.

Covers each pipeline step in isolation and integration through ``normalize()``.
"""

import pytest

from src.dtos.normalization_dto import StructuredBlock
from src.services.text_normalization_service import TextNormalizationService


@pytest.fixture
def svc() -> TextNormalizationService:
    return TextNormalizationService()


# ── Unicode NFKC ────────────────────────────────────────────────────────────

class TestUnicodeNormalization:
    def test_fullwidth_chars_normalized(self, svc: TextNormalizationService):
        text = "\uff21\uff22\uff23"  # fullwidth ABC
        result = svc.normalize(text, source_format="text")
        assert result.normalized_text == "ABC"

    def test_ligature_normalized(self, svc: TextNormalizationService):
        text = "\ufb01nance"  # fi-ligature + "nance"
        result = svc.normalize(text, source_format="text")
        assert result.normalized_text == "finance"


# ── Whitespace normalization ────────────────────────────────────────────────

class TestWhitespaceNormalization:
    def test_collapse_repeated_spaces(self, svc: TextNormalizationService):
        text = "Hello    world"
        result = svc.normalize(text, source_format="text")
        assert "    " not in result.normalized_text
        assert "Hello world" in result.normalized_text

    def test_collapse_tabs(self, svc: TextNormalizationService):
        text = "Hello\t\tworld"
        result = svc.normalize(text, source_format="text")
        assert "\t" not in result.normalized_text

    def test_nbsp_replaced(self, svc: TextNormalizationService):
        text = "Hello\u00a0world"
        result = svc.normalize(text, source_format="text")
        assert "\u00a0" not in result.normalized_text
        assert "Hello world" in result.normalized_text

    def test_trailing_spaces_stripped(self, svc: TextNormalizationService):
        text = "Hello   \nworld   "
        result = svc.normalize(text, source_format="text")
        for line in result.normalized_text.split("\n"):
            assert line == line.rstrip()

    def test_excessive_blank_lines_collapsed(self, svc: TextNormalizationService):
        text = "Paragraph one.\n\n\n\n\nParagraph two."
        result = svc.normalize(text, source_format="text")
        assert "\n\n\n" not in result.normalized_text
        assert "Paragraph one.\n\nParagraph two." == result.normalized_text

    def test_paragraph_separation_preserved(self, svc: TextNormalizationService):
        text = "Paragraph one.\n\nParagraph two."
        result = svc.normalize(text, source_format="text")
        assert "\n\n" in result.normalized_text

    def test_messy_whitespace_txt(self, svc: TextNormalizationService):
        text = "  Hello\t\t  world  \n\n\n\n\nAnother   paragraph.\n\nThird.  "
        result = svc.normalize(text, source_format="txt")
        assert "\t" not in result.normalized_text
        assert "\n\n\n" not in result.normalized_text
        assert "Another paragraph." in result.normalized_text


# ── Hyphenation repair ──────────────────────────────────────────────────────

class TestHyphenationRepair:
    def test_simple_english_hyphenation(self, svc: TextNormalizationService):
        text = "This is a detec-\ntion of AI text."
        result = svc.normalize(text, source_format="docx")
        assert "detection" in result.normalized_text
        assert "detec-\ntion" not in result.normalized_text

    def test_cyrillic_hyphenation(self, svc: TextNormalizationService):
        text = "Это тести-\nрование текста."
        result = svc.normalize(text, source_format="docx")
        assert "тестирование" in result.normalized_text

    def test_real_compound_preserved(self, svc: TextNormalizationService):
        """Hyphenated compounds on a single line must not be merged."""
        text = "This is a well-known fact."
        result = svc.normalize(text, source_format="docx")
        assert "well-known" in result.normalized_text

    def test_hyphenation_fix_count(self, svc: TextNormalizationService):
        text = "detec-\ntion and classifi-\ncation"
        result = svc.normalize(text, source_format="docx")
        assert result.metadata.hyphenation_fixes_count == 2


# ── Boilerplate removal ────────────────────────────────────────────────────

class TestBoilerplateRemoval:
    def test_repeated_headers_removed(self, svc: TextNormalizationService):
        header = "Company Confidential"
        body = "\n".join(
            f"{header}\nParagraph {i} content that is reasonably long."
            for i in range(5)
        )
        result = svc.normalize(body, source_format="docx")
        assert header not in result.normalized_text

    def test_page_numbers_removed(self, svc: TextNormalizationService):
        parts = []
        for i in range(1, 6):
            parts.append(f"Content of page {i} goes here with enough text.")
            parts.append(str(i))
        text = "\n".join(parts)
        result = svc.normalize(text, source_format="docx")
        lines = result.normalized_text.split("\n")
        pure_number_lines = [l for l in lines if l.strip().isdigit()]
        assert len(pure_number_lines) == 0

    def test_no_boilerplate_on_text_source(self, svc: TextNormalizationService):
        """source_format='text' skips boilerplate removal."""
        header = "Repeated Line"
        body = "\n".join(f"{header}\nContent {i}." for i in range(5))
        result = svc.normalize(body, source_format="text")
        assert header in result.normalized_text

    def test_pptx_repeated_footer_removed(self, svc: TextNormalizationService):
        footer = "© 2025 Company Inc."
        slides = "\n".join(
            f"Slide {i} content about topic.\n{footer}" for i in range(5)
        )
        result = svc.normalize(slides, source_format="pptx")
        assert footer not in result.normalized_text
        assert result.metadata.headers_footers_removed_count >= 5


# ── Deduplication ───────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_consecutive_lines_removed(self, svc: TextNormalizationService):
        text = "Line one.\nLine one.\nLine two."
        result = svc.normalize(text, source_format="text")
        lines = [l for l in result.normalized_text.split("\n") if l.strip()]
        assert lines.count("Line one.") == 1

    def test_duplicate_consecutive_paragraphs_removed(self, svc: TextNormalizationService):
        text = "Paragraph A.\n\nParagraph A.\n\nParagraph B."
        result = svc.normalize(text, source_format="text")
        paragraphs = [p.strip() for p in result.normalized_text.split("\n\n") if p.strip()]
        assert paragraphs.count("Paragraph A.") == 1
        assert result.metadata.repeated_paragraphs_removed == 1

    def test_non_consecutive_duplicates_kept(self, svc: TextNormalizationService):
        text = "First.\n\nSecond.\n\nFirst."
        result = svc.normalize(text, source_format="text")
        paragraphs = [p.strip() for p in result.normalized_text.split("\n\n") if p.strip()]
        assert paragraphs.count("First.") == 2


# ── Structure markers ──────────────────────────────────────────────────────

class TestStructureMarkers:
    def test_table_markers(self, svc: TextNormalizationService):
        blocks = [
            StructuredBlock(type="table", content="A | B\nC | D"),
        ]
        result = svc.normalize("Some text.", source_format="docx", structured_blocks=blocks)
        assert "[TABLE]" in result.normalized_text
        assert "[/TABLE]" in result.normalized_text
        assert "A | B" in result.normalized_text
        assert result.metadata.tables_detected == 1

    def test_slide_markers(self, svc: TextNormalizationService):
        blocks = [
            StructuredBlock(type="slide", content="[TITLE] Intro\n[BODY]\nBullet 1\n[/BODY]", index=1),
            StructuredBlock(type="slide", content="[TITLE] Main\n[BODY]\nBullet 2\n[/BODY]", index=2),
        ]
        result = svc.normalize("", source_format="pptx", structured_blocks=blocks)
        assert "[SLIDE 1]" in result.normalized_text
        assert "[SLIDE 2]" in result.normalized_text
        assert result.metadata.slides_detected == 2

    def test_no_markers_without_blocks(self, svc: TextNormalizationService):
        result = svc.normalize("Plain text.", source_format="docx")
        assert "[TABLE]" not in result.normalized_text
        assert "[SLIDE" not in result.normalized_text


# ── HTML residual cleanup ───────────────────────────────────────────────────

class TestHtmlResidual:
    def test_script_tags_stripped(self, svc: TextNormalizationService):
        text = "Hello <script>alert('x')</script> world."
        result = svc.normalize(text, source_format="html")
        assert "<script>" not in result.normalized_text
        assert "alert" not in result.normalized_text
        assert "Hello" in result.normalized_text

    def test_style_tags_stripped(self, svc: TextNormalizationService):
        text = "Content <style>body{color:red}</style> here."
        result = svc.normalize(text, source_format="html")
        assert "<style>" not in result.normalized_text
        assert "body{color" not in result.normalized_text


# ── Quality flags ───────────────────────────────────────────────────────────

class TestQualityFlags:
    def test_short_text_flag(self, svc: TextNormalizationService):
        text = "Short text here with some words."  # < 200 chars
        result = svc.normalize(text, source_format="text")
        assert result.quality_flags.short_text is True

    def test_very_short_text_flag(self, svc: TextNormalizationService):
        text = "Tiny."  # < 50 chars
        result = svc.normalize(text, source_format="text")
        assert result.quality_flags.very_short_text is True
        assert result.quality_flags.short_text is True

    def test_long_text_not_short(self, svc: TextNormalizationService):
        text = "A" * 300
        result = svc.normalize(text, source_format="text")
        assert result.quality_flags.short_text is False
        assert result.quality_flags.very_short_text is False

    def test_excessive_repetition_flag(self, svc: TextNormalizationService):
        line = "The same line repeating."
        text = "\n".join([line] * 20 + ["Unique line one.", "Unique line two."])
        result = svc.normalize(text, source_format="text")
        assert result.quality_flags.excessive_repetition is True

    def test_low_alpha_ratio_flag(self, svc: TextNormalizationService):
        text = "123 456 789 !!!??? $$$ %%% 111 222 333 444 555 666"
        result = svc.normalize(text, source_format="text")
        assert result.quality_flags.low_alpha_ratio is True

    def test_slide_like_format_flag(self, svc: TextNormalizationService):
        result = svc.normalize("Slide content.", source_format="pptx")
        assert result.quality_flags.slide_like_format is True

    def test_not_slide_like_for_docx(self, svc: TextNormalizationService):
        result = svc.normalize("Document content.", source_format="docx")
        assert result.quality_flags.slide_like_format is False


# ── Metadata ────────────────────────────────────────────────────────────────

class TestMetadata:
    def test_char_counts(self, svc: TextNormalizationService):
        text = "Hello    world"
        result = svc.normalize(text, source_format="text")
        assert result.metadata.original_char_count == len(text)
        assert result.metadata.normalized_char_count <= result.metadata.original_char_count

    def test_line_counts(self, svc: TextNormalizationService):
        text = "Line 1\nLine 2\nLine 3"
        result = svc.normalize(text, source_format="text")
        assert result.metadata.original_line_count == 3
        assert result.metadata.normalized_line_count >= 1

    def test_source_format_stored(self, svc: TextNormalizationService):
        result = svc.normalize("Content.", source_format="docx")
        assert result.metadata.source_format == "docx"


# ── Preservation guarantees ─────────────────────────────────────────────────

class TestPreservation:
    def test_no_global_lowercasing(self, svc: TextNormalizationService):
        text = "Hello World, This Is Mixed Case."
        result = svc.normalize(text, source_format="text")
        assert "Hello World" in result.normalized_text
        assert "Mixed Case" in result.normalized_text

    def test_no_punctuation_stripping(self, svc: TextNormalizationService):
        text = 'She said: "Hello!" — and left... (or did she?)'
        result = svc.normalize(text, source_format="text")
        for ch in ['"', '!', '—', '...', '(', ')', '?']:
            assert ch in result.normalized_text

    def test_paragraph_boundaries_preserved(self, svc: TextNormalizationService):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = svc.normalize(text, source_format="text")
        paragraphs = [p.strip() for p in result.normalized_text.split("\n\n") if p.strip()]
        assert len(paragraphs) == 3

    def test_raw_text_unchanged(self, svc: TextNormalizationService):
        original = "Some  text   with\u00a0nbsp."
        result = svc.normalize(original, source_format="text")
        assert result.raw_text == original
        assert result.raw_text is not result.normalized_text


# ── Determinism ─────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_input_same_output(self, svc: TextNormalizationService):
        text = "The quick brown fox jumps over the lazy dog.\n\nAnother paragraph."
        r1 = svc.normalize(text, source_format="text")
        r2 = svc.normalize(text, source_format="text")
        assert r1.normalized_text == r2.normalized_text
        assert r1.metadata == r2.metadata
        assert r1.quality_flags == r2.quality_flags


# ── DOC format ──────────────────────────────────────────────────────────────

class TestDocFormat:
    def test_doc_format_not_in_local_extensions(self):
        """`.doc` is not in the local extraction set — it should be rejected
        upstream by GeminiTextExtractor (requires google.generativeai at
        import time, so we only assert the constant here)."""
        try:
            from src.services.gemini_service import _LOCAL_TEXT_EXTRACTION_EXTENSIONS
            assert ".doc" not in _LOCAL_TEXT_EXTRACTION_EXTENSIONS
        except ImportError:
            pytest.skip("google.generativeai not installed locally")
