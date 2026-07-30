"""Unit tests for nexus_slide_engine — PPTX generation, content parsing, hex conversion."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.nexus_slide_engine import (
    SlideConfig,
    SlideContent,
    SlideEngine,
    SlideResult,
    slide_engine,
)

# ── Dataclass existence & defaults ────────────────────────────


class TestSlideContentDataclass:
    def test_defaults(self):
        sc = SlideContent()
        assert sc.layout == "content"
        assert sc.title == ""
        assert sc.body == ""
        assert sc.bullets == []
        assert sc.left_content == ""
        assert sc.right_content == ""
        assert sc.notes == ""
        assert sc.image_path is None

    def test_custom_values(self):
        sc = SlideContent(
            layout="two_column",
            title="Test Slide",
            body="body text",
            bullets=["a", "b"],
            notes="speaker notes",
        )
        assert sc.layout == "two_column"
        assert sc.title == "Test Slide"
        assert sc.bullets == ["a", "b"]
        assert sc.notes == "speaker notes"


class TestSlideConfigDefaults:
    def test_defaults(self):
        cfg = SlideConfig()
        assert cfg.title == "Nexus Presentation"
        assert cfg.subtitle == ""
        assert cfg.author == "Nexus Notebook 11 LM"
        assert cfg.brand_color == "#6366f1"
        assert cfg.accent_color == "#8b5cf6"
        assert cfg.font_title == "Calibri"
        assert cfg.font_body == "Calibri"
        assert cfg.width_inches == 13.333
        assert cfg.height_inches == 7.5

    def test_custom_config(self):
        cfg = SlideConfig(title="Custom", brand_color="#ff0000")
        assert cfg.title == "Custom"
        assert cfg.brand_color == "#ff0000"


class TestSlideResultDataclass:
    def test_fields(self):
        sr = SlideResult(data=b"pptx", filename="test.pptx", slide_count=5, file_size_bytes=2048)
        assert sr.data == b"pptx"
        assert sr.filename == "test.pptx"
        assert sr.slide_count == 5
        assert sr.file_size_bytes == 2048


# ── _hex_to_rgb ──────────────────────────────────────────────


class TestHexToRgb:
    def test_standard_hex(self):
        assert SlideEngine._hex_to_rgb("#ff0000") == (255, 0, 0)

    def test_without_hash(self):
        assert SlideEngine._hex_to_rgb("00ff00") == (0, 255, 0)

    def test_blue(self):
        assert SlideEngine._hex_to_rgb("#0000ff") == (0, 0, 255)

    def test_brand_color(self):
        assert SlideEngine._hex_to_rgb("#6366f1") == (99, 102, 241)

    def test_white(self):
        assert SlideEngine._hex_to_rgb("#ffffff") == (255, 255, 255)

    def test_black(self):
        assert SlideEngine._hex_to_rgb("#000000") == (0, 0, 0)


# ── _parse_content ───────────────────────────────────────────


class TestParseContent:
    def setup_method(self):
        self.engine = SlideEngine()

    def test_parse_list_of_dicts(self):
        content = [
            {"title": "Slide 1", "body": "Body 1", "layout": "content"},
            {"title": "Slide 2", "bullets": ["a", "b"]},
        ]
        slides = self.engine._parse_content(content)
        assert len(slides) == 2
        assert slides[0].title == "Slide 1"
        assert slides[0].body == "Body 1"
        assert slides[1].bullets == ["a", "b"]

    def test_parse_list_dict_defaults(self):
        content = [{"title": "Only Title"}]
        slides = self.engine._parse_content(content)
        assert slides[0].layout == "content"
        assert slides[0].body == ""
        assert slides[0].bullets == []

    def test_parse_dict_converts_to_json_string(self):
        content = {"key": "value"}
        slides = self.engine._parse_content(content)
        assert len(slides) >= 1

    def test_parse_markdown_heading_1_creates_section(self):
        content = "# Main Section\n\nSome body text."
        slides = self.engine._parse_content(content)
        section_slides = [s for s in slides if s.layout == "section"]
        assert len(section_slides) >= 1
        assert section_slides[0].title == "Main Section"

    def test_parse_markdown_heading_2_with_bullets(self):
        content = "## Features\n- Feature A\n- Feature B\n- Feature C"
        slides = self.engine._parse_content(content)
        bullet_slides = [s for s in slides if s.bullets]
        assert len(bullet_slides) >= 1
        assert "Feature A" in bullet_slides[0].bullets

    def test_parse_no_headings_uses_first_line_as_title(self):
        content = "First line title\nSecond line body\nThird line"
        slides = self.engine._parse_content(content)
        assert len(slides) >= 1
        assert slides[0].title == "First line title"

    def test_parse_empty_returns_fallback(self):
        slides = self.engine._parse_content("")
        assert len(slides) >= 1

    def test_parse_list_empty_items_filtered(self):
        content = [{"title": "Valid"}, "not a dict"]
        slides = self.engine._parse_content(content)
        assert len(slides) == 1
        assert slides[0].title == "Valid"


# ── generate (mocked pptx) ──────────────────────────────────


class TestSlideEngineGenerate:
    @pytest.mark.asyncio
    async def test_generate_returns_expected_keys(self):
        mock_prs = MagicMock()
        mock_prs.slides = MagicMock()
        mock_prs.slides.__len__ = MagicMock(return_value=3)
        mock_prs.slides.__iter__ = MagicMock(
            return_value=iter([MagicMock(), MagicMock(), MagicMock()])
        )
        mock_slide = MagicMock()
        mock_slide.shapes.title.text = ""
        mock_slide.shapes.title.text_frame.paragraphs = []
        mock_slide.placeholders = {1: MagicMock()}
        mock_slide.placeholders[1].text_frame.paragraphs = [MagicMock()]
        mock_slide.placeholders[1].text_frame.clear = MagicMock()
        mock_slide.placeholders[1].text_frame.add_paragraph = MagicMock(return_value=MagicMock())
        mock_prs.slides.add_slide.return_value = mock_slide
        mock_prs.slide_layouts = [MagicMock() for _ in range(10)]
        mock_prs.save = MagicMock(side_effect=lambda buf: buf.write(b"PPTX_DATA"))

        with patch("pptx.Presentation", return_value=mock_prs):
            with patch("pptx.util.Inches", side_effect=lambda x: x):
                with patch("pptx.util.Pt", side_effect=lambda x: x):
                    with patch("pptx.dml.color.RGBColor", side_effect=lambda r, g, b: (r, g, b)):
                        engine = SlideEngine()
                        result = await engine.generate(
                            [{"title": "Test", "body": "Content"}],
                        )

        assert "type" in result
        assert result["type"] == "pptx"
        assert "data" in result
        assert "filename" in result
        assert "slide_count" in result
        assert "file_size_bytes" in result

    @pytest.mark.asyncio
    async def test_generate_missing_pptx_raises(self):
        from src.exceptions import ValidationError

        with patch.dict("sys.modules", {"pptx": None}):
            engine = SlideEngine()
            with pytest.raises(ValidationError, match="python-pptx"):
                await engine.generate("# Title\nBody")


# ── Global singleton ─────────────────────────────────────────


class TestGlobalSingleton:
    def test_slide_engine_is_instance(self):
        assert isinstance(slide_engine, SlideEngine)
