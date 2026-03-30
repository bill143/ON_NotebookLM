"""Nexus API — Chat (conversational Q&A with source grounding)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user
from src.infra.nexus_obs_tracing import traced
from src.exceptions import NotFoundError

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Schemas ──────────────────────────────────────────────────

class ChatMessage(BaseModel):
    content: str = Field(..., min_length=1, max_length=50_000)
    session_id: Optional[str] = None
    notebook_id: Optional[str] = None
    source_ids: Optional[list[str]] = None
    model_override: Optional[str] = None
    stream: bool = True


class ChatResponse(BaseModel):
    session_id: str
    turn_number: int
    content: str
    citations: list[dict] = []
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class SessionCreate(BaseModel):
    notebook_id: Optional[str] = None
    session_type: str = "chat"
    title: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=ChatResponse)
@traced("chat.send")
async def send_message(
    data: ChatMessage,
    auth: AuthContext = Depends(get_current_user),
):
    """Send a chat message and get a grounded response."""
    from src.infra.nexus_data_persist import get_session as db_session, sessions_repo
    from src.infra.nexus_cost_tracker import cost_tracker, UsageRecord
    from src.infra.nexus_prompt_registry import prompt_registry
    from src.agents.nexus_model_layer import model_manager
    from sqlalchemy import text
    import json

    # 1. Get or create session
    session_id = data.session_id
    if not session_id:
        session_data = await sessions_repo.create(
            data={
                "user_id": auth.user_id,
                "notebook_id": data.notebook_id,
                "session_type": "chat",
                "title": data.content[:100],
                "model_override": data.model_override,
            },
            tenant_id=auth.tenant_id,
        )
        session_id = session_data["id"]

    # 2. Load chat history
    async with db_session(auth.tenant_id) as session:
        result = await session.execute(
            text("""
                SELECT role, content FROM chat_messages
                WHERE session_id = :session_id
                ORDER BY turn_number ASC
                LIMIT 50
            """),
            {"session_id": session_id},
        )
        history = [dict(row) for row in result.mappings().all()]

    # 3. Get context from sources
    context_text = ""
    if data.source_ids or data.notebook_id:
        source_ids = data.source_ids or []

        # If notebook specified, get all its sources
        if data.notebook_id and not source_ids:
            async with db_session(auth.tenant_id) as session:
                result = await session.execute(
                    text("SELECT source_id FROM notebook_sources WHERE notebook_id = :nid"),
                    {"nid": data.notebook_id},
                )
                source_ids = [row["source_id"] for row in result.mappings().all()]

        if source_ids:
            from src.infra.nexus_data_persist import sources_repo

            # Vector search for relevant context
            try:
                embedding_provider = await model_manager.provision_embedding(tenant_id=auth.tenant_id)
                embedding_result = await embedding_provider.embed([data.content])
                chunks = await sources_repo.vector_search(
                    query_embedding=embedding_result.embeddings[0],
                    source_ids=source_ids,
                    tenant_id=auth.tenant_id,
                    limit=5,
                )
                context_text = "\n\n".join(c["content"] for c in chunks)
            except Exception as e:
                from loguru import logger
                logger.warning(f"Context retrieval failed: {e}")

    # 4. Build messages with system prompt
    prompt_result = await prompt_registry.resolve(
        "chat", "system",
        variables={"context": context_text, "notebook": {"name": "Current Notebook"}},
    )

    messages = [{"role": "system", "content": str(prompt_result)}]
    messages.extend(history)
    messages.append({"role": "user", "content": data.content})

    # 5. Get LLM response
    llm = await model_manager.provision_llm(
        model_id=data.model_override,
        task_type="chat",
        tenant_id=auth.tenant_id,
    )
    response = await llm.generate(messages, temperature=0.7)

    # 6. Get next turn number
    turn = len(history) // 2 + 1

    # 7. Save messages
    async with db_session(auth.tenant_id) as session:
        # Save user message
        await session.execute(
            text("""
                INSERT INTO chat_messages (id, session_id, role, content, turn_number)
                VALUES (uuid_generate_v4(), :session_id, 'user', :content, :turn)
            """),
            {"session_id": session_id, "content": data.content, "turn": turn * 2 - 1},
        )

        # Save assistant message
        await session.execute(
            text("""
                INSERT INTO chat_messages (id, session_id, role, content, token_count_input,
                    token_count_output, model_used, latency_ms, turn_number)
                VALUES (uuid_generate_v4(), :session_id, 'assistant', :content,
                    :input_tokens, :output_tokens, :model, :latency, :turn)
            """),
            {
                "session_id": session_id,
                "content": response.content,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "model": response.model,
                "latency": int(response.latency_ms),
                "turn": turn * 2,
            },
        )

    # 8. Record usage
    await cost_tracker.record_usage(UsageRecord(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        model_name=response.model,
        provider=response.provider,
        feature_id="2A",
        agent_id="researcher",
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
        cost_usd=response.cost_usd,
        latency_ms=response.latency_ms,
    ))

    return ChatResponse(
        session_id=session_id,
        turn_number=turn,
        content=response.content,
        model_used=response.model,
        input_tokens=response.input_tokens,
        output_tokens=response.output_tokens,
    )


@router.post("/stream")
@traced("chat.stream")
async def stream_message(
    data: ChatMessage,
    auth: AuthContext = Depends(get_current_user),
):
    """Stream a chat response via SSE."""
    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_prompt_registry import prompt_registry
    import json

    # Build messages
    prompt_result = await prompt_registry.resolve("chat", "system", variables={"context": ""})
    messages = [
        {"role": "system", "content": str(prompt_result)},
        {"role": "user", "content": data.content},
    ]

    llm = await model_manager.provision_llm(
        model_id=data.model_override,
        task_type="chat",
        tenant_id=auth.tenant_id,
    )

    async def generate():
        async for token in llm.stream(messages):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/sessions", response_model=list[dict])
@traced("chat.list_sessions")
async def list_sessions(
    auth: AuthContext = Depends(get_current_user),
    notebook_id: Optional[str] = None,
):
    """List chat sessions."""
    from src.infra.nexus_data_persist import sessions_repo

    filters = {"user_id": auth.user_id}
    if notebook_id:
        filters["notebook_id"] = notebook_id

    return await sessions_repo.list_all(auth.tenant_id, filters=filters)


@router.get("/sessions/{session_id}/messages", response_model=list[dict])
@traced("chat.get_messages")
async def get_session_messages(
    session_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    """Get all messages in a session."""
    from src.infra.nexus_data_persist import get_session as db_session
    from sqlalchemy import text

    async with db_session(auth.tenant_id) as session:
        result = await session.execute(
            text("""
                SELECT id, role, content, citations, token_count_input,
                       token_count_output, model_used, latency_ms, turn_number, created_at
                FROM chat_messages
                WHERE session_id = :session_id
                ORDER BY turn_number ASC
            """),
            {"session_id": session_id},
        )
        return [dict(row) for row in result.mappings().all()]
