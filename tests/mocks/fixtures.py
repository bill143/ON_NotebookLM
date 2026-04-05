"""Reusable pytest fixtures that patch all external AI provider SDKs."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.mocks.ai_providers import get_mock_clients


@pytest.fixture
def mock_ai_providers() -> Any:
    """Patches all external AI provider clients for unit tests."""
    clients = get_mock_clients()

    patches = [
        patch("openai.AsyncOpenAI", return_value=clients["openai"]),
        patch("anthropic.AsyncAnthropic", return_value=clients["anthropic"]),
    ]

    with contextlib.ExitStack() as stack:
        for p in patches:
            try:
                stack.enter_context(p)
            except Exception:
                pass
        yield clients


@pytest.fixture
def mock_export_libs() -> Any:
    """Patches ReportLab, python-docx, and ebooklib for unit tests."""
    clients = get_mock_clients()

    with contextlib.ExitStack() as stack:
        for target in [
            "reportlab.pdfgen.canvas.Canvas",
            "docx.Document",
            "ebooklib.epub.write_epub",
        ]:
            try:
                stack.enter_context(patch(target, return_value=MagicMock()))
            except Exception:
                pass
        yield clients


@pytest.fixture
def mock_model_manager() -> MagicMock:
    """Provides a mock ModelManager that returns mock LLM/embedding/TTS providers."""

    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(
        return_value=MagicMock(
            content="Mock LLM response.",
            model="mock-model",
            provider="mock",
            input_tokens=50,
            output_tokens=120,
            cached_tokens=0,
            latency_ms=100.0,
            cost_usd=0.001,
            finish_reason="stop",
        )
    )

    async def _stream_gen(*args: Any, **kwargs: Any) -> Any:
        for word in ["Hello", " ", "world"]:
            yield word

    llm_mock.stream = _stream_gen
    llm_mock.config = MagicMock(
        model_id_string="mock-model",
        provider=MagicMock(value="mock"),
    )

    embedding_mock = AsyncMock()
    embedding_mock.embed = AsyncMock(
        return_value=MagicMock(
            embeddings=[[0.01] * 1536],
            model="mock-embed",
            provider="mock",
            token_count=10,
            latency_ms=50.0,
        )
    )

    tts_mock = AsyncMock()
    tts_mock.synthesize = AsyncMock(
        return_value=MagicMock(
            audio_data=b"\xff\xfb\x90\x00" * 100,
            model="mock-tts",
            provider="mock",
            format="mp3",
            duration_seconds=5.0,
            latency_ms=200.0,
        )
    )

    manager = MagicMock()
    manager.provision_llm = AsyncMock(return_value=llm_mock)
    manager.provision_embedding = AsyncMock(return_value=embedding_mock)
    manager.provision_tts = AsyncMock(return_value=tts_mock)
    manager.list_models = AsyncMock(return_value=[])
    manager.get_model = AsyncMock(return_value=MagicMock())
    manager.get_default_model = AsyncMock(return_value=MagicMock())
    manager.get_credential = AsyncMock(return_value="sk-mock-key")

    return manager


@pytest.fixture
def mock_db_session() -> Any:
    """Provides a mock async database session context manager."""
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(
            mappings=MagicMock(
                return_value=MagicMock(
                    all=MagicMock(return_value=[]),
                    first=MagicMock(return_value=None),
                )
            ),
            rowcount=0,
            first=MagicMock(return_value=None),
        )
    )

    @contextlib.asynccontextmanager
    async def _session(tenant_id: str | None = None) -> Any:
        yield session

    return _session
