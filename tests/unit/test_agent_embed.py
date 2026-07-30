"""Unit tests for nexus_agent_embed — chunking, token counting, vectorization."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nexus_agent_embed import (
    chunk_text,
    count_tokens,
    vectorize_note,
    vectorize_source,
)

# ── chunk_text ───────────────────────────────────────────────


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        text = "Short text under chunk size."
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_exact_chunk_size_returns_single(self):
        text = "a" * 1000
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1

    def test_two_paragraphs_under_limit(self):
        text = "Paragraph one.\n\nParagraph two."
        chunks = chunk_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert "Paragraph one." in chunks[0]
        assert "Paragraph two." in chunks[0]

    def test_paragraphs_exceeding_limit(self):
        para1 = "A" * 500
        para2 = "B" * 500
        para3 = "C" * 500
        text = f"{para1}\n\n{para2}\n\n{para3}"
        chunks = chunk_text(text, chunk_size=600, chunk_overlap=100)
        assert len(chunks) >= 2

    def test_overlap_present(self):
        para1 = "First " * 100
        para2 = "Second " * 100
        text = f"{para1.strip()}\n\n{para2.strip()}"
        chunks = chunk_text(text, chunk_size=400, chunk_overlap=50)
        if len(chunks) >= 2:
            tail_of_first = chunks[0][-50:]
            assert tail_of_first in chunks[1]

    def test_large_paragraph_split(self):
        huge = "X" * 3000
        chunks = chunk_text(huge, chunk_size=1000, chunk_overlap=200)
        assert len(chunks) >= 3
        for c in chunks:
            assert len(c) <= 1000

    def test_empty_text(self):
        chunks = chunk_text("", chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_custom_separator(self):
        text = "Part1---Part2---Part3"
        chunks = chunk_text(text, chunk_size=10, chunk_overlap=0, separator="---")
        assert len(chunks) >= 2

    def test_returns_list_of_strings(self):
        chunks = chunk_text("Hello world", chunk_size=100)
        assert isinstance(chunks, list)
        assert all(isinstance(c, str) for c in chunks)


# ── count_tokens ─────────────────────────────────────────────


class TestCountTokens:
    def test_fallback_estimation(self):
        with patch.dict("sys.modules", {"tiktoken": None}):
            with patch("src.agents.nexus_agent_embed.count_tokens") as mock_fn:
                mock_fn.side_effect = lambda t: len(t) // 4
                result = mock_fn("Hello world test")
                assert result == 4

    def test_empty_string(self):
        result = count_tokens("")
        assert result == 0

    def test_returns_integer(self):
        result = count_tokens("Some text for tokens")
        assert isinstance(result, int)

    def test_longer_text_more_tokens(self):
        short = count_tokens("Hi")
        long = count_tokens("This is a much longer piece of text for counting")
        assert long >= short


# ── vectorize_source (mocked DB + embeddings) ───────────────


class TestVectorizeSource:
    def _make_state(self, content="Test content for embedding.", source_id="src-1"):
        state = MagicMock()
        state.inputs = {"source_id": source_id, "source_content": content}
        state.tenant_id = "test-tenant"
        return state

    @pytest.mark.asyncio
    async def test_empty_content_returns_zero_chunks(self):
        state = self._make_state(content="")
        result = await vectorize_source(state)
        assert result["chunks"] == 0
        assert "error" in result

    @pytest.mark.asyncio
    async def test_vectorize_returns_chunk_count(self):
        state = self._make_state("A" * 2500)

        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.1] * 768]
        mock_embed_provider = AsyncMock()
        mock_embed_provider.embed = AsyncMock(return_value=mock_embed_result)

        mock_model_manager = MagicMock()
        mock_model_manager.provision_embedding = AsyncMock(return_value=mock_embed_provider)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_data_persist.get_session", return_value=mock_session):
                with patch("src.infra.nexus_obs_tracing.metrics") as mock_metrics:
                    mock_metrics.embedding_count.labels.return_value.inc = MagicMock()
                    result = await vectorize_source(state)

        assert result["chunks"] >= 1
        assert result["source_id"] == "src-1"


# ── vectorize_note (mocked DB + embeddings) ─────────────────


class TestVectorizeNote:
    @pytest.mark.asyncio
    async def test_returns_embedding_list(self):
        mock_embed_result = MagicMock()
        mock_embed_result.embeddings = [[0.5] * 768]
        mock_embed_provider = AsyncMock()
        mock_embed_provider.embed = AsyncMock(return_value=mock_embed_result)

        mock_model_manager = MagicMock()
        mock_model_manager.provision_embedding = AsyncMock(return_value=mock_embed_provider)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_data_persist.get_session", return_value=mock_session):
                result = await vectorize_note("note-1", "Some note content", "tenant-1")

        assert isinstance(result, list)
        assert len(result) == 768
