"""
Nexus Agent Researcher — Deep Research Agent
Source: Repo #7 (LangGraph chat with context assembly), Repo #5 (citations)

Handles: Multi-turn research with source grounding and citation chains.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_cost_tracker import cost_tracker, UsageRecord


@dataclass
class Citation:
    """A citation reference (Repo #5 pattern: source_id + cited_text + char offsets)."""
    source_id: str
    source_title: str
    cited_text: str
    relevance_score: float = 0.0


@traced("agent.researcher.research")
async def deep_research(state: Any) -> dict[str, Any]:
    """
    Execute deep research with multi-source grounding.
    1. Retrieve relevant chunks via vector search
    2. Build grounded context with citations
    3. Generate answer with inline citations
    4. Extract citation references
    """
    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_prompt_registry import prompt_registry
    from src.infra.nexus_data_persist import sources_repo, get_session
    from sqlalchemy import text

    query = state.inputs.get("query", "")
    source_ids = state.inputs.get("source_ids", [])
    notebook_id = state.inputs.get("notebook_id", "")
    tenant_id = state.tenant_id

    # 1. Get source IDs from notebook if not specified
    if not source_ids and notebook_id:
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text("SELECT source_id FROM notebook_sources WHERE notebook_id = :nid"),
                {"nid": notebook_id},
            )
            source_ids = [row["source_id"] for row in result.mappings().all()]

    # 2. Vector search for relevant context
    context_chunks = []
    citations = []

    if source_ids:
        embedding_provider = await model_manager.provision_embedding(tenant_id=tenant_id)
        embedding_result = await embedding_provider.embed([query])
        query_embedding = embedding_result.embeddings[0]

        chunks = await sources_repo.vector_search(
            query_embedding=query_embedding,
            source_ids=source_ids,
            tenant_id=tenant_id,
            limit=8,
            min_score=0.4,
        )

        # Build context with source attribution
        for chunk in chunks:
            # Get source title
            source_data = await sources_repo.get_by_id(chunk["source_id"], tenant_id)
            source_title = source_data.get("title", "Unknown") if source_data else "Unknown"

            context_chunks.append(f"[Source: {source_title}]\n{chunk['content']}")
            citations.append({
                "source_id": chunk["source_id"],
                "source_title": source_title,
                "cited_text": chunk["content"][:200],
                "relevance_score": chunk.get("score", 0),
            })

    # 3. Build grounded prompt
    context_text = "\n\n---\n\n".join(context_chunks) if context_chunks else "No sources available."

    prompt = await prompt_registry.resolve(
        "research", "grounding",
        variables={
            "sources": [{"title": c.get("source_title", ""), "context": c.get("cited_text", "")} for c in citations],
        },
    )

    messages = [
        {"role": "system", "content": str(prompt)},
        {"role": "user", "content": f"Context:\n{context_text}\n\nQuestion: {query}"},
    ]

    # 4. Generate grounded answer
    llm = await model_manager.provision_llm(task_type="research", tenant_id=tenant_id)
    response = await llm.generate(messages, temperature=0.3)

    await cost_tracker.record_usage(UsageRecord(
        tenant_id=tenant_id,
        user_id=state.user_id,
        model_name=response.model,
        provider=response.provider,
        feature_id="2A",
        agent_id="researcher",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
    ))

    return {
        "answer": response.content,
        "citations": citations,
        "sources_used": len(set(c["source_id"] for c in citations)),
        "model": response.model,
    }
