"""Unit tests for WebSocket ConnectionManager and auth (mocked broker)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.api.websocket import (
    MAX_CONNECTIONS_PER_USER,
    ActiveConnection,
    ConnectionManager,
    authenticate_websocket,
    manager,
)


@pytest.mark.asyncio
async def test_connect_registers_and_returns_id() -> None:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    m = ConnectionManager()
    with (
        patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock),
    ):
        cid = await m.connect(ws, "u1", "t1", "sess1")
    assert cid is not None
    assert len(cid) == 12
    ws.accept.assert_awaited_once()
    assert m.active_count == 1


@pytest.mark.asyncio
async def test_connect_limit_closes_socket() -> None:
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        for _ in range(MAX_CONNECTIONS_PER_USER):
            w = AsyncMock()
            w.accept = AsyncMock()
            await m.connect(w, "u1", "t1")
        blocked = AsyncMock()
        blocked.close = AsyncMock()
        out = await m.connect(blocked, "u1", "t1")
    assert out is None
    blocked.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect_removes_connection() -> None:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        cid = await m.connect(ws, "u2", "t2")
    assert cid is not None
    m.disconnect(cid)
    assert m.active_count == 0


@pytest.mark.asyncio
async def test_send_to_connection_success() -> None:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        cid = await m.connect(ws, "u3", "t3")
    assert cid
    await m.send_to_connection(cid, {"type": "ping"})
    ws.send_json.assert_awaited()


@pytest.mark.asyncio
async def test_send_to_connection_failure_disconnects() -> None:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock(side_effect=RuntimeError("send fail"))
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        cid = await m.connect(ws, "u4", "t4")
    await m.send_to_connection(cid, {"x": 1})
    assert m.active_count == 0


@pytest.mark.asyncio
async def test_send_to_user_publishes() -> None:
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.publish", new_callable=AsyncMock) as pub:
        await m.send_to_user("u5", {"a": 1})
    pub.assert_awaited_once_with("user:u5", {"a": 1})


@pytest.mark.asyncio
async def test_broadcast_to_tenant_publishes() -> None:
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.publish", new_callable=AsyncMock) as pub:
        await m.broadcast_to_tenant("t5", {"b": 2})
    pub.assert_awaited_once_with("tenant:t5", {"b": 2})


@pytest.mark.asyncio
async def test_relay_to_local_user() -> None:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        await m.connect(ws, "u6", "t6")
    await m._relay_to_local_user("u6", {"type": "evt"})
    ws.send_json.assert_awaited()


@pytest.mark.asyncio
async def test_relay_to_local_tenant() -> None:
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    m = ConnectionManager()
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        await m.connect(ws, "u7", "t7")
    await m._relay_to_local_tenant("t7", {"type": "evt2"})
    ws.send_json.assert_awaited()


def test_authenticate_websocket_ok() -> None:
    with patch(
        "src.infra.nexus_vault_keys.verify_token",
        return_value={"sub": "user-x", "tid": "tenant-y"},
    ):
        uid, tid = authenticate_websocket("tok")
    assert uid == "user-x"
    assert tid == "tenant-y"


def test_authenticate_websocket_raises() -> None:
    with patch("src.infra.nexus_vault_keys.verify_token", side_effect=ValueError("bad")):
        from src.exceptions import AuthError

        with pytest.raises(AuthError, match="WebSocket auth failed"):
            authenticate_websocket("bad")


def test_active_connection_dataclass() -> None:
    ws = AsyncMock()
    ac = ActiveConnection(websocket=ws, user_id="a", tenant_id="b", session_id="c")
    assert ac.user_id == "a"


def test_singleton_manager() -> None:
    assert isinstance(manager, ConnectionManager)
