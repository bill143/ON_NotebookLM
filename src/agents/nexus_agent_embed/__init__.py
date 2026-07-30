"""
Nexus Agent Embed — Embedding & Vectorization Agent
Source: Repo #7 (async vectorization via background jobs)

Handles: Document chunking, embedding generation, and vector storage.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.infra.nexus_obs_tracing import traced

# ── Chunking ─────────────────────────────────────────────────


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    separator: str = "\n\n",
) -> list[str]:
    """
    Split text into overlapping chunks for embedding.
    Prefers splitting on paragraph boundaries.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    paragraphs = text.split(separator)
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + len(separator) <= chunk_size:
            current_chunk += (separator if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            # Handle paragraphs larger than chunk_size
            if len(para) > chunk_size:
                for i in range(0, len(para), chunk_size - chunk_overlap):
                    sub = para[i : i + chunk_size]
                    chunks.append(sub.strip())
                current_chunk = ""
            else:
                # Include overlap from end of previous chunk
                if chunks:
                    overlap = chunks[-1][-chunk_overlap:]
                    current_chunk = overlap + separator + para
                else:
                    current_chunk = para

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def count_tokens(text: str) -> int:
    """Estimate token count (rough approximation: 4 chars ≈ 1 token)."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return len(text) // 4


# ── Embedding Agent ──────────────────────────────────────────


@traced("agent.embed.vectorize_source")
async def vectorize_source(state: Any) -> dict[str, Any]:
    """
    Vectorize a source document: chunk → embed → store.

    Source: Repo #7, notebook.py ~L411-457 (embed_source command)
    """
    from sqlalchemy import text

    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_data_persist import get_session

    source_id = state.inputs.get("source_id", "")
    source_content = state.inputs.get("source_content", "")
    tenant_id = state.tenant_id

    if not source_content:
        return {"chunks": 0, "error": "No content to vectorize"}

    # 1. Chunk the content
    chunks = chunk_text(source_content, chunk_size=1000, chunk_overlap=200)
    logger.info(f"Chunked source into {len(chunks)} chunks", source_id=source_id)

    # 2. Generate embeddings (batch)
    embedding_provider = await model_manager.provision_embedding(tenant_id=tenant_id)

    # Process in batches of 20
    batch_size = 20
    all_embeddings: list[list[float]] = []

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        result = await embedding_provider.embed(batch)
        all_embeddings.extend(result.embeddings)

    # 3. Store embeddings
    async with get_session(tenant_id) as session:
        # Delete existing embeddings for this source
        await session.execute(
            text("DELETE FROM source_embeddings WHERE source_id = :sid"),
            {"sid": source_id},
        )

        # Insert new embeddings
        for idx, (chunk_text_content, embedding) in enumerate(
            zip(chunks, all_embeddings, strict=False)
        ):
            token_cnt = count_tokens(chunk_text_content)
            await session.execute(
                text("""
                    INSERT INTO source_embeddings (id, tenant_id, source_id, chunk_index, content, token_count, embedding)
                    VALUES (uuid_generate_v4(), :tenant_id, :source_id, :chunk_index, :content, :token_count, :embedding::vector)
                """),
                {
                    "tenant_id": tenant_id,
                    "source_id": source_id,
                    "chunk_index": idx,
                    "content": chunk_text_content,
                    "token_count": token_cnt,
                    "embedding": str(embedding),
                },
            )

        # Update source chunk count
        await session.execute(
            text("UPDATE sources SET chunk_count = :count WHERE id = :id"),
            {"count": len(chunks), "id": source_id},
        )

    from src.infra.nexus_obs_tracing import metrics

    metrics.embedding_count.labels(source_type="source").inc(len(chunks))

    logger.info(f"Vectorized source: {len(chunks)} chunks embedded", source_id=source_id)
    return {"chunks": len(chunks), "source_id": source_id}


@traced("agent.embed.vectorize_note")
async def vectorize_note(
    note_id: str,
    content: str,
    tenant_id: str,
) -> list[float]:
    """Generate and store embedding for a single note."""
    from sqlalchemy import text

    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_data_persist import get_session

    embedding_provider = await model_manager.provision_embedding(tenant_id=tenant_id)
    result = await embedding_provider.embed([content])
    embedding = result.embeddings[0]

    async with get_session(tenant_id) as session:
        await session.execute(
            text("UPDATE notes SET embedding = :embedding::vector WHERE id = :id"),
            {"embedding": str(embedding), "id": note_id},
        )

    return embedding
