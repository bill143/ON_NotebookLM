"""
Unit Tests — Nexus Export Engine (Multi-Format Document Export)

Tests cover: class existence, data classes, pure-function exporters
(markdown, text, HTML), filename sanitisation, markdown parsing, and
section splitting — all without touching real file I/O or libraries.
"""

from __future__ import annotations

from src.core.nexus_export_engine import (
    DOCXExporter,
    EPUBExporter,
    ExportContent,
    ExportEngine,
    ExportFormat,
    ExportOptions,
    ExportResult,
    MarkdownParser,
    PDFExporter,
)

# ── Helpers ──────────────────────────────────────────────────


def _make_content(**overrides) -> ExportContent:
    defaults = {
        "title": "Test Document",
        "content": "## Introduction\n\nHello world.\n\n## Details\n\nMore content here.",
    }
    defaults.update(overrides)
    return ExportContent(**defaults)


# ── Existence / Import Tests ────────────────────────────────


class TestExportClassesExist:
    def test_export_engine_exists(self):
        assert ExportEngine is not None
        engine = ExportEngine()
        assert hasattr(engine, "export")
        assert hasattr(engine, "export_batch")

    def test_pdf_exporter_exists(self):
        assert PDFExporter is not None
        exporter = PDFExporter()
        assert hasattr(exporter, "export")

    def test_docx_exporter_exists(self):
        assert DOCXExporter is not None
        exporter = DOCXExporter()
        assert hasattr(exporter, "export")

    def test_epub_exporter_exists(self):
        assert EPUBExporter is not None
        exporter = EPUBExporter()
        assert hasattr(exporter, "export")


# ── ExportFormat Constants ──────────────────────────────────


class TestExportFormats:
    def test_supported_formats(self):
        assert ExportFormat.PDF == "pdf"
        assert ExportFormat.DOCX == "docx"
        assert ExportFormat.EPUB == "epub"
        assert ExportFormat.MARKDOWN == "markdown"
        assert ExportFormat.HTML == "html"
        assert ExportFormat.TXT == "txt"


# ── Data Class Tests ────────────────────────────────────────


class TestExportResult:
    def test_export_result_dataclass(self):
        result = ExportResult(
            data=b"binary-data",
            filename="test.pdf",
            mime_type="application/pdf",
            format="pdf",
            file_size_bytes=11,
        )
        assert result.data == b"binary-data"
        assert result.filename == "test.pdf"
        assert result.mime_type == "application/pdf"
        assert result.format == "pdf"
        assert result.file_size_bytes == 11


class TestExportContent:
    def test_export_content_defaults(self):
        ec = ExportContent(title="T", content="C")
        assert ec.author == "Nexus Notebook 11 LM"
        assert ec.created_at is None
        assert ec.notebook_name == ""
        assert ec.content_type == ""
        assert ec.sections == []
        assert ec.metadata == {}


class TestExportOptions:
    def test_export_options_defaults(self):
        opts = ExportOptions()
        assert opts.format == ExportFormat.PDF
        assert opts.include_toc is True
        assert opts.page_size == "A4"
        assert opts.font_size == 11
        assert opts.line_spacing == 1.4
        assert opts.margin_mm == 25
        assert opts.branding_color == "#6366f1"
        assert opts.watermark is None


# ── Pure-Function Exporter Tests ─────────────────────────────


class TestMarkdownExport:
    def test_markdown_export_returns_content(self):
        engine = ExportEngine()
        content = _make_content(title="My Notes", content="Some **bold** text.")
        result = engine._export_markdown(content)

        assert isinstance(result, ExportResult)
        assert result.format == "markdown"
        assert result.mime_type == "text/markdown"
        assert result.filename.endswith(".md")
        decoded = result.data.decode("utf-8")
        assert "# My Notes" in decoded
        assert "Some **bold** text." in decoded
        assert result.file_size_bytes == len(result.data)


class TestTextExport:
    def test_text_export_returns_content(self):
        engine = ExportEngine()
        content = _make_content(title="Plain Export", content="Hello **world**.")
        result = engine._export_text(content)

        assert isinstance(result, ExportResult)
        assert result.format == "txt"
        assert result.mime_type == "text/plain"
        assert result.filename.endswith(".txt")
        decoded = result.data.decode("utf-8")
        assert "Plain Export" in decoded
        assert "Hello world." in decoded  # markdown stripped
        assert result.file_size_bytes == len(result.data)


class TestHTMLExport:
    def test_html_export_returns_content(self):
        engine = ExportEngine()
        content = _make_content(title="HTML Doc", content="Paragraph here.")
        options = ExportOptions(format=ExportFormat.HTML)
        result = engine._export_html(content, options)

        assert isinstance(result, ExportResult)
        assert result.format == "html"
        assert result.mime_type == "text/html"
        assert result.filename.endswith(".html")
        decoded = result.data.decode("utf-8")
        assert "<html" in decoded
        assert "HTML Doc" in decoded
        assert result.file_size_bytes == len(result.data)


# ── Filename Sanitisation ────────────────────────────────────


class TestSafeFilename:
    def test_export_sanitizes_filename(self):
        result = PDFExporter._safe_filename("Hello World! @#$% Test (1)")
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "%" not in result
        assert "(" not in result
        assert ")" not in result
        assert "!" not in result
        assert len(result) <= 80

    def test_safe_filename_truncates_long_titles(self):
        long_title = "A" * 200
        result = PDFExporter._safe_filename(long_title)
        assert len(result) <= 80

    def test_safe_filename_handles_empty(self):
        result = PDFExporter._safe_filename("")
        assert isinstance(result, str)

    def test_safe_filename_lowercases(self):
        result = PDFExporter._safe_filename("UPPER Case Title")
        assert result == result.lower()


# ── Markdown Parser Tests ────────────────────────────────────


class TestMarkdownParser:
    def test_content_to_html_handles_markdown(self):
        html = MarkdownParser.to_html("# Title\n\nSome text.")
        assert isinstance(html, str)
        assert len(html) > 0
        assert "Title" in html

    def test_strip_markdown_removes_bold(self):
        result = MarkdownParser.strip_markdown("This is **bold** text")
        assert "**" not in result
        assert "bold" in result

    def test_strip_markdown_removes_italic(self):
        result = MarkdownParser.strip_markdown("This is *italic* text")
        assert result.count("*") == 0
        assert "italic" in result

    def test_strip_markdown_removes_code(self):
        result = MarkdownParser.strip_markdown("Use `code` here")
        assert "`" not in result
        assert "code" in result

    def test_strip_markdown_removes_links(self):
        result = MarkdownParser.strip_markdown("Visit [Google](https://google.com)")
        assert "Google" in result
        assert "https://google.com" not in result

    def test_strip_markdown_removes_headers(self):
        result = MarkdownParser.strip_markdown("### My Header")
        assert "###" not in result
        assert "My Header" in result

    def test_section_parser_handles_empty(self):
        sections = MarkdownParser.parse_sections("")
        assert isinstance(sections, list)
        assert len(sections) <= 1  # may produce one empty section

    def test_section_parser_splits_by_h1(self):
        md = "# Section One\n\nContent 1.\n\n# Section Two\n\nContent 2."
        sections = MarkdownParser.parse_sections(md)
        titles = [s["title"] for s in sections]
        assert "Section One" in titles
        assert "Section Two" in titles

    def test_section_parser_splits_by_h2(self):
        md = "## Intro\n\nParagraph.\n\n## Body\n\nMore."
        sections = MarkdownParser.parse_sections(md)
        assert len(sections) >= 2

    def test_section_parser_includes_level(self):
        md = "# H1\n\nBody\n\n### H3\n\nDeep body"
        sections = MarkdownParser.parse_sections(md)
        levels = {s["level"] for s in sections}
        assert "1" in levels or "3" in levels
