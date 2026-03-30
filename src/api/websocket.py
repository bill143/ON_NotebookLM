"""
Nexus WebSocket — Real-Time Chat Streaming & Live Events
Codename: ESPERANTO

Provides:
- Authenticated WebSocket connections with tenant isolation
- Real-time token-by-token chat streaming
- Artifact generation progress updates
- Connection lifecycle management
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger

from src.exceptions import AuthError
from src.infra.nexus_obs_tracing import traced, trace_id_var, generate_trace_id

router = APIRouter(tags=["WebSocket"])


# ── Connection Manager ───────────────────────────────────────

@dataclass
class ActiveConnection:
    """Represents an active WebSocket connection."""
    websocket: WebSocket
    user_id: str
    tenant_id: str
    session_id: str = ""
    connected_at: float = field(default_factory=time.time)


class ConnectionManager:
    """Manages WebSocket connections per user and tenant."""

    def __init__(self) -> None:
        self._connections: dict[str, ActiveConnection] = {}
        self._user_connections: dict[str, list[str]] = {}
        self._tenant_connections: dict[str, list[str]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str,
        tenant_id: str,
        session_id: str = "",
    ) -> str:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        conn_id = str(uuid.uuid4())[:12]

        self._connections[conn_id] = ActiveConnection(
            websocket=websocket,
            user_id=user_id,
            tenant_id=tenant_id,
            session_id=session_id,
        )

        # Track by user
        if user_id not in self._user_connections:
            self._user_connections[user_id] = []
        self._user_connections[user_id].append(conn_id)

        # Track by tenant
        if tenant_id not in self._tenant_connections:
            self._tenant_connections[tenant_id] = []
        self._tenant_connections[tenant_id].append(conn_id)

        logger.info(f"WebSocket connected: {conn_id}", user_id=user_id, tenant_id=tenant_id)
        return conn_id

    def disconnect(self, conn_id: str) -> None:
        """Remove a WebSocket connection."""
        conn = self._connections.pop(conn_id, None)
        if conn:
            # Remove from user tracking
            if conn.user_id in self._user_connections:
                self._user_connections[conn.user_id] = [
                    c for c in self._user_connections[conn.user_id] if c != conn_id
                ]
            # Remove from tenant tracking
            if conn.tenant_id in self._tenant_connections:
                self._tenant_connections[conn.tenant_id] = [
                    c for c in self._tenant_connections[conn.tenant_id] if c != conn_id
                ]
            logger.info(f"WebSocket disconnected: {conn_id}")

    async def send_to_connection(self, conn_id: str, data: dict) -> None:
        """Send data to a specific connection."""
        conn = self._connections.get(conn_id)
        if conn:
            try:
                await conn.websocket.send_json(data)
            except Exception as e:
                logger.warning(f"Failed to send to {conn_id}: {e}")
                self.disconnect(conn_id)

    async def send_to_user(self, user_id: str, data: dict) -> None:
        """Send data to all connections of a user."""
        conn_ids = self._user_connections.get(user_id, [])
        for conn_id in conn_ids:
            await self.send_to_connection(conn_id, data)

    async def broadcast_to_tenant(self, tenant_id: str, data: dict) -> None:
        """Broadcast data to all connections in a tenant."""
        conn_ids = self._tenant_connections.get(tenant_id, [])
        for conn_id in conn_ids:
            await self.send_to_connection(conn_id, data)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Global connection manager
manager = ConnectionManager()


# ── Authentication ───────────────────────────────────────────

def authenticate_websocket(token: str) -> tuple[str, str]:
    """Authenticate WebSocket connection and return (user_id, tenant_id)."""
    from src.infra.nexus_vault_keys import verify_token
    try:
        payload = verify_token(token)
        return payload["sub"], payload["tid"]
    except Exception as e:
        raise AuthError(f"WebSocket auth failed: {e}")


# ── WebSocket Endpoints ──────────────────────────────────────

@router.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),
    session_id: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time chat streaming.

    Protocol:
    Client → Server: {"type": "message", "content": "...", "notebook_id": "..."}
    Server → Client: {"type": "token", "content": "Hello"}
    Server → Client: {"type": "token", "content": " world"}
    Server → Client: {"type": "done", "session_id": "...", "input_tokens": 10, "output_tokens": 20}
    Server → Client: {"type": "error", "message": "..."}
    """
    # Authenticate
    try:
        user_id, tenant_id = authenticate_websocket(token)
    except AuthError:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    conn_id = await manager.connect(websocket, user_id, tenant_id, session_id or "")

    try:
        # Send connection acknowledgment
        await websocket.send_json({
            "type": "connected",
            "connection_id": conn_id,
            "user_id": user_id,
        })

        while True:
            # Receive message from client
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = data.get("type", "message")

            if msg_type == "message":
                await _handle_chat_message(websocket, data, user_id, tenant_id, session_id)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})

            elif msg_type == "subscribe":
                # Subscribe to artifact progress updates
                artifact_id = data.get("artifact_id")
                if artifact_id:
                    conn = manager._connections.get(conn_id)
                    if conn:
                        conn.session_id = f"artifact:{artifact_id}"
                    await websocket.send_json({
                        "type": "subscribed",
                        "artifact_id": artifact_id,
                    })

    except WebSocketDisconnect:
        manager.disconnect(conn_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(conn_id)
        try:
            await websocket.close(code=1011, reason="Internal error")
        except Exception:
            pass


async def _handle_chat_message(
    websocket: WebSocket,
    data: dict,
    user_id: str,
    tenant_id: str,
    session_id: Optional[str],
) -> None:
    """Process a chat message and stream the response."""
    from src.agents.nexus_model_layer import model_manager
    from src.infra.nexus_prompt_registry import prompt_registry
    from src.infra.nexus_cost_tracker import cost_tracker, UsageRecord
    from src.infra.nexus_data_persist import get_session as db_session, sessions_repo, sources_repo
    from sqlalchemy import text

    content = data.get("content", "")
    notebook_id = data.get("notebook_id")
    model_override = data.get("model_override")

    if not content.strip():
        await websocket.send_json({"type": "error", "message": "Empty message"})
        return

    # Send acknowledgment
    await websocket.send_json({"type": "ack", "status": "processing"})

    try:
        # 1. Get or create session
        if not session_id:
            session_data = await sessions_repo.create(
                data={
                    "user_id": user_id,
                    "notebook_id": notebook_id,
                    "session_type": "chat",
                    "title": content[:100],
                },
                tenant_id=tenant_id,
            )
            session_id = session_data["id"]
            await websocket.send_json({"type": "session", "session_id": session_id})

        # 2. Get context from sources
        context_text = ""
        if notebook_id:
            try:
                async with db_session(tenant_id) as session:
                    result = await session.execute(
                        text("SELECT source_id FROM notebook_sources WHERE notebook_id = :nid"),
                        {"nid": notebook_id},
                    )
                    source_ids = [row["source_id"] for row in result.mappings().all()]

                if source_ids:
                    embedding_provider = await model_manager.provision_embedding(tenant_id=tenant_id)
                    embedding_result = await embedding_provider.embed([content])
                    chunks = await sources_repo.vector_search(
                        query_embedding=embedding_result.embeddings[0],
                        source_ids=source_ids,
                        tenant_id=tenant_id,
                        limit=5,
                    )
                    context_text = "\n\n".join(c["content"] for c in chunks)
            except Exception as e:
                logger.warning(f"Context retrieval failed: {e}")

        # 3. Build messages
        prompt_result = await prompt_registry.resolve(
            "chat", "system",
            variables={"context": context_text},
        )

        # Load history
        async with db_session(tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT role, content FROM chat_messages
                    WHERE session_id = :sid ORDER BY turn_number ASC LIMIT 30
                """),
                {"sid": session_id},
            )
            history = [dict(row) for row in result.mappings().all()]

        messages = [{"role": "system", "content": str(prompt_result)}]
        messages.extend(history)
        messages.append({"role": "user", "content": content})

        # 4. Stream response token by token
        llm = await model_manager.provision_llm(
            model_id=model_override,
            task_type="chat",
            tenant_id=tenant_id,
        )

        full_response = ""
        token_count = 0
        start_time = time.perf_counter()

        async for token in llm.stream(messages, temperature=0.7):
            full_response += token
            token_count += 1
            await websocket.send_json({
                "type": "token",
                "content": token,
                "token_index": token_count,
            })

        latency_ms = (time.perf_counter() - start_time) * 1000

        # 5. Save messages to DB
        turn = len(history) // 2 + 1

        async with db_session(tenant_id) as session:
            await session.execute(
                text("""
                    INSERT INTO chat_messages (id, session_id, role, content, turn_number)
                    VALUES (uuid_generate_v4(), :sid, 'user', :content, :turn)
                """),
                {"sid": session_id, "content": content, "turn": turn * 2 - 1},
            )
            await session.execute(
                text("""
                    INSERT INTO chat_messages (id, session_id, role, content, turn_number,
                        token_count_output, model_used, latency_ms)
                    VALUES (uuid_generate_v4(), :sid, 'assistant', :content, :turn,
                        :tokens, :model, :latency)
                """),
                {
                    "sid": session_id,
                    "content": full_response,
                    "turn": turn * 2,
                    "tokens": token_count,
                    "model": llm.config.model_id_string,
                    "latency": int(latency_ms),
                },
            )

        # 6. Send completion message
        await websocket.send_json({
            "type": "done",
            "session_id": session_id,
            "turn_number": turn,
            "output_tokens": token_count,
            "latency_ms": round(latency_ms, 2),
            "model": llm.config.model_id_string,
        })

        # 7. Record usage
        await cost_tracker.record_usage(UsageRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            model_name=llm.config.model_id_string,
            provider=llm.config.provider.value,
            feature_id="2A",
            agent_id="chat_ws",
            output_tokens=token_count,
            latency_ms=latency_ms,
        ))

    except Exception as e:
        logger.error(f"Chat streaming error: {e}")
        await websocket.send_json({
            "type": "error",
            "message": "An error occurred while generating the response.",
        })


# ── Artifact Progress Updates ────────────────────────────────

async def notify_artifact_progress(
    tenant_id: str,
    artifact_id: str,
    status: str,
    progress_pct: float = 0,
    message: str = "",
) -> None:
    """Send artifact generation progress to subscribed WebSocket clients."""
    await manager.broadcast_to_tenant(tenant_id, {
        "type": "artifact_progress",
        "artifact_id": artifact_id,
        "status": status,
        "progress_pct": progress_pct,
        "message": message,
    })


@router.get("/ws/status")
async def websocket_status():
    """Get WebSocket connection statistics."""
    return {
        "active_connections": manager.active_count,
    }
