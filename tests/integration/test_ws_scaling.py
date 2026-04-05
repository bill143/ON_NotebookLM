"""
Integration Tests — WebSocket Redis Pub/Sub Scaling

Verifies cross-worker message delivery, connection limits,
reconnection behavior, and tenant isolation.

Requires: Redis running at REDIS_URL (or localhost:6379)
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.infra.nexus_ws_broker import WebSocketBroker


@pytest.fixture
async def broker():
    """Create a fresh broker connected to Redis."""
    b = WebSocketBroker()
    await b.connect()
    yield b
    await b.disconnect()


@pytest.mark.asyncio
class TestCrossWorkerBroadcast:
    async def test_cross_worker_broadcast(self, broker: WebSocketBroker):
        """Message published to Redis is received by a subscribed handler."""
        received: list[dict] = []

        async def handler(msg: dict) -> None:
            received.append(msg)

        await broker.subscribe("test:broadcast", handler)
        await asyncio.sleep(0.1)

        await broker.publish("test:broadcast", {"type": "hello", "data": "world"})
        await asyncio.sleep(0.5)

        assert len(received) == 1
        assert received[0]["type"] == "hello"
        assert received[0]["data"] == "world"

    async def test_tenant_isolation(self, broker: WebSocketBroker):
        """Message to tenant A is NOT received by tenant B handler."""
        tenant_a_msgs: list[dict] = []
        tenant_b_msgs: list[dict] = []

        async def handler_a(msg: dict) -> None:
            tenant_a_msgs.append(msg)

        async def handler_b(msg: dict) -> None:
            tenant_b_msgs.append(msg)

        await broker.subscribe("tenant:tenant-a", handler_a)
        await broker.subscribe("tenant:tenant-b", handler_b)
        await asyncio.sleep(0.1)

        await broker.publish("tenant:tenant-a", {"for": "a-only"})
        await asyncio.sleep(0.5)

        assert len(tenant_a_msgs) == 1
        assert len(tenant_b_msgs) == 0

    async def test_handler_exception_does_not_stop_listener(self, broker: WebSocketBroker):
        """A crashing handler should not break the listener for other handlers."""
        good_msgs: list[dict] = []

        async def bad_handler(msg: dict) -> None:
            raise RuntimeError("handler crash")

        async def good_handler(msg: dict) -> None:
            good_msgs.append(msg)

        await broker.subscribe("test:resilience", bad_handler)
        await broker.subscribe("test:resilience", good_handler)
        await asyncio.sleep(0.1)

        await broker.publish("test:resilience", {"test": "resilience"})
        await asyncio.sleep(0.5)

        assert len(good_msgs) == 1


@pytest.mark.asyncio
class TestConnectionLimit:
    async def test_connection_limit_enforced(self):
        """6th WebSocket connection from same user is rejected with code 4008."""
        from src.api.websocket import MAX_CONNECTIONS_PER_USER, ConnectionManager

        mgr = ConnectionManager()

        for _i in range(MAX_CONNECTIONS_PER_USER):
            ws = AsyncMock()
            ws.close = AsyncMock()
            result = await mgr.connect(ws, "user-1", "tenant-1")
            assert result is not None

        ws_rejected = AsyncMock()
        ws_rejected.close = AsyncMock()
        result = await mgr.connect(ws_rejected, "user-1", "tenant-1")
        assert result is None
        ws_rejected.close.assert_awaited_once_with(code=4008, reason="Connection limit reached")
