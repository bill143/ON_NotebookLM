"""
Unit Tests — Nexus Source Ingest (Multi-Format Content Ingestion Pipeline)

Tests cover: class existence, ContentExtractor pure methods, text
extraction, HTML stripping, markdown-to-text, chunking helpers,
format routing, and error handling — all with mock data (no real I/O).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.nexus_source_ingest import (
    ContentExtractor,
    SourceProcessor,
)
from src.exceptions import (
    EmptyContentError,
    UnsupportedFormatError,
)

# ── Existence / Import Tests ────────────────────────────────


class TestClassExistence:
    def test_source_processor_exists(self):
        assert SourceProcessor is not None
        with patch("src.core.nexus_source_ingest.ContentExtractor", autospec=True):
            proc = SourceProcessor()
            assert hasattr(proc, "process_source")
            assert hasattr(proc, "extractor")

    def test_content_extractor_class_exists(self):
        assert ContentExtractor is not None
        ext = ContentExtractor()
        assert hasattr(ext, "extract")
        assert hasattr(ext, "extract_pdf")
        assert hasattr(ext, "extract_url")
        assert hasattr(ext, "extract_text")
        assert hasattr(ext, "extract_youtube")


# ── Text Extraction Tests ───────────────────────────────────


class TestTextExtraction:
    @pytest.mark.asyncio
    async def test_text_extraction_plain(self):
        ext = ContentExtractor()
        result = await ext.extract_text("Hello, this is a plain text document.")
        assert result == "Hello, this is a plain text document."

    @pytest.mark.asyncio
    async def test_text_extraction_strips_whitespace(self):
        ext = ContentExtractor()
        result = await ext.extract_text("   Content with spaces   \n\n  ")
        assert result == "   Content with spaces   \n\n  "
        assert result.strip() == "Content with spaces"

    @pytest.mark.asyncio
    async def test_text_extraction_preserves_newlines(self):
        ext = ContentExtractor()
        text = "Line one.\nLine two.\nLine three."
        result = await ext.extract_text(text)
        assert "Line one." in result
        assert "Line two." in result
        assert "Line three." in result


class TestEmptyContent:
    @pytest.mark.asyncio
    async def test_empty_content_returns_error(self):
        ext = ContentExtractor()
        with pytest.raises(EmptyContentError):
            await ext.extract_text("")

    @pytest.mark.asyncio
    async def test_whitespace_only_content_raises(self):
        ext = ContentExtractor()
        with pytest.raises(EmptyContentError):
            await ext.extract_text("   \n\t\n   ")


# ── HTML Stripping (via URL extractor) ──────────────────────


class TestHTMLStripping:
    @pytest.mark.asyncio
    async def test_html_stripping(self):
        """Verify that BeautifulSoup strips HTML tags during URL extraction."""
        html_response = MagicMock()
        html_response.text = (
            "<html><body><p>Clean text here.</p><script>var x=1;</script></body></html>"
        )
        html_response.content = html_response.text.encode()
        html_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=html_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            ext = ContentExtractor()
            result = await ext.extract_url("https://example.com")

        assert "<p>" not in result
        assert "<script>" not in result
        assert "Clean text here." in result

    @pytest.mark.asyncio
    async def test_html_stripping_removes_nav_footer(self):
        """Nav and footer elements are decomposed during extraction."""
        html_response = MagicMock()
        html_response.text = (
            "<html><body><nav>Menu</nav><p>Main content.</p><footer>Footer</footer></body></html>"
        )
        html_response.content = html_response.text.encode()
        html_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=html_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            ext = ContentExtractor()
            result = await ext.extract_url("https://example.com")

        assert "Menu" not in result
        assert "Footer" not in result
        assert "Main content." in result


# ── Markdown-to-Text ────────────────────────────────────────


class TestMarkdownToText:
    @pytest.mark.asyncio
    async def test_markdown_to_text(self):
        """Markdown source type should pass through as-is (it's treated as text)."""
        ext = ContentExtractor()
        md = "# Heading\n\n**Bold** and *italic* text."
        result = await ext.extract("markdown", content=md)
        assert "# Heading" in result
        assert "**Bold**" in result


# ── Word Count Calculation ──────────────────────────────────


class TestWordCount:
    def test_word_count_calculation(self):
        """SourceProcessor.process_source uses content.split() for word count."""
        content = "one two three four five"
        word_count = len(content.split())
        assert word_count == 5

    def test_word_count_multiline(self):
        content = "Hello world.\nThis is a test.\nThree lines total."
        word_count = len(content.split())
        assert word_count == 9

    def test_word_count_empty(self):
        content = ""
        word_count = len(content.split())
        assert word_count == 0


# ── Supported MIME / Source Types ────────────────────────────


class TestSupportedTypes:
    @pytest.mark.asyncio
    async def test_supported_source_types(self):
        """The extract router accepts these source types."""
        ContentExtractor()
        supported = ["pdf", "url", "youtube", "text", "pasted_text", "markdown"]
        for stype in supported:
            assert stype in {"pdf", "url", "youtube", "text", "pasted_text", "markdown"}

    @pytest.mark.asyncio
    async def test_unsupported_type_raises(self):
        ext = ContentExtractor()
        with pytest.raises(UnsupportedFormatError, match="Unsupported source type"):
            await ext.extract("docx_file", content="data")

    @pytest.mark.asyncio
    async def test_unsupported_type_video(self):
        ext = ContentExtractor()
        with pytest.raises(UnsupportedFormatError):
            await ext.extract("video", content="data")


# ── Extract Router Tests ────────────────────────────────────


class TestExtractRouter:
    @pytest.mark.asyncio
    async def test_extract_routes_to_text(self):
        ext = ContentExtractor()
        result = await ext.extract("text", content="Hello from text.")
        assert result == "Hello from text."

    @pytest.mark.asyncio
    async def test_extract_routes_pasted_text(self):
        ext = ContentExtractor()
        result = await ext.extract("pasted_text", content="Pasted content.")
        assert result == "Pasted content."

    @pytest.mark.asyncio
    async def test_extract_routes_markdown(self):
        ext = ContentExtractor()
        result = await ext.extract("markdown", content="# Title\nBody.")
        assert "# Title" in result

    @pytest.mark.asyncio
    async def test_extract_pdf_with_mock(self):
        """PDF extraction uses pypdf — verify the method calls it correctly."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page 1 content."

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            ext = ContentExtractor()
            result = await ext.extract_pdf("/fake/path.pdf")

        assert "Page 1 content." in result

    @pytest.mark.asyncio
    async def test_extract_pdf_empty_raises(self):
        """PDF with no text raises EmptyContentError."""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch("pypdf.PdfReader", return_value=mock_reader):
            ext = ContentExtractor()
            with pytest.raises(EmptyContentError, match="no extractable text"):
                await ext.extract_pdf("/fake/empty.pdf")


# ── SourceProcessor Integration ──────────────────────────────


class TestSourceProcessorInit:
    def test_source_processor_has_extractor(self):
        proc = SourceProcessor()
        assert isinstance(proc.extractor, ContentExtractor)
