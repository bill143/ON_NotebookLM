"""Unit tests for nexus_agent_researcher (mocked DB / LLM)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_deep_research_with_source_chunks() -> None:
    from src.agents.nexus_agent_researcher import deep_research

    state = SimpleNamespace(
        inputs={"query": "What is X?", "source_ids": ["s1"], "notebook_id": ""},
        tenant_id="t1",
        user_id="u1",
    )

    mock_embed = AsyncMock()
    mock_embed.embed = AsyncMock(
        return_value=SimpleNamespace(embeddings=[[0.01] * 8]),
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=SimpleNamespace(
            content="Grounded answer",
            model="gpt-4",
            provider="openai",
            input_tokens=10,
            output_tokens=20,
            cost_usd=0.01,
            latency_ms=100,
        ),
    )
    mock_mm = AsyncMock()
    mock_mm.provision_embedding = AsyncMock(return_value=mock_embed)
    mock_mm.provision_llm = AsyncMock(return_value=mock_llm)

    chunk = {"source_id": "s1", "content": "chunk text " * 5, "score": 0.9}

    with (
        patch("src.agents.nexus_model_layer.model_manager", mock_mm),
        patch("src.infra.nexus_data_persist.sources_repo") as sr,
        patch(
            "src.infra.nexus_prompt_registry.prompt_registry.resolve",
            new_callable=AsyncMock,
            return_value="sys",
        ),
        patch(
            "src.infra.nexus_cost_tracker.cost_tracker.record_usage",
            new_callable=AsyncMock,
        ),
    ):
        sr.vector_search = AsyncMock(return_value=[chunk])
        sr.get_by_id = AsyncMock(return_value={"title": "Doc A"})

        out = await deep_research(state)

    assert out["answer"] == "Grounded answer"
    assert out["sources_used"] == 1
    assert len(out["citations"]) == 1
    assert out["citations"][0]["source_id"] == "s1"


@pytest.mark.asyncio
async def test_deep_research_loads_sources_from_notebook() -> None:
    from src.agents.nexus_agent_researcher import deep_research

    state = SimpleNamespace(
        inputs={"query": "Q", "source_ids": [], "notebook_id": "nb1"},
        tenant_id="t1",
        user_id="u1",
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.mappings.return_value.all.return_value = [{"source_id": "sx"}]
    mock_session.execute = AsyncMock(return_value=mock_result)

    @asynccontextmanager
    async def fake_get_session(_tenant_id: str | None = None):
        yield mock_session

    mock_embed = AsyncMock()
    mock_embed.embed = AsyncMock(
        return_value=SimpleNamespace(embeddings=[[0.02] * 8]),
    )
    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=SimpleNamespace(
            content="A",
            model="m",
            provider="p",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_ms=1,
        ),
    )
    mock_mm = AsyncMock()
    mock_mm.provision_embedding = AsyncMock(return_value=mock_embed)
    mock_mm.provision_llm = AsyncMock(return_value=mock_llm)

    with (
        patch("src.infra.nexus_data_persist.get_session", fake_get_session),
        patch("src.agents.nexus_model_layer.model_manager", mock_mm),
        patch("src.infra.nexus_data_persist.sources_repo") as sr,
        patch(
            "src.infra.nexus_prompt_registry.prompt_registry.resolve",
            new_callable=AsyncMock,
            return_value="sys",
        ),
        patch(
            "src.infra.nexus_cost_tracker.cost_tracker.record_usage",
            new_callable=AsyncMock,
        ),
    ):
        sr.vector_search = AsyncMock(return_value=[])
        out = await deep_research(state)

    assert out["answer"] == "A"
    mock_session.execute.assert_awaited()


@pytest.mark.asyncio
async def test_deep_research_no_sources_still_generates() -> None:
    from src.agents.nexus_agent_researcher import deep_research

    state = SimpleNamespace(
        inputs={"query": "Q", "source_ids": [], "notebook_id": ""},
        tenant_id="t1",
        user_id="u1",
    )

    mock_llm = AsyncMock()
    mock_llm.generate = AsyncMock(
        return_value=SimpleNamespace(
            content="No-src",
            model="m",
            provider="p",
            input_tokens=1,
            output_tokens=1,
            cost_usd=0.0,
            latency_ms=1,
        ),
    )
    mock_mm = AsyncMock()
    mock_mm.provision_llm = AsyncMock(return_value=mock_llm)

    with (
        patch("src.agents.nexus_model_layer.model_manager", mock_mm),
        patch(
            "src.infra.nexus_prompt_registry.prompt_registry.resolve",
            new_callable=AsyncMock,
            return_value="sys",
        ),
        patch(
            "src.infra.nexus_cost_tracker.cost_tracker.record_usage",
            new_callable=AsyncMock,
        ),
    ):
        out = await deep_research(state)

    assert out["answer"] == "No-src"
    assert out["citations"] == []
    assert out["sources_used"] == 0
