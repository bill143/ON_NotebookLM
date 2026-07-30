"""WebSocket HTTP routes and helpers (TestClient + mocks)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.infra.nexus_vault_keys import create_access_token


@pytest.fixture
def sync_app_client() -> TestClient:
    with (
        patch(
            "src.infra.nexus_obs_tracing.setup_logging",
            MagicMock(),
        ),
        patch(
            "src.infra.nexus_data_persist.init_database",
            new_callable=AsyncMock,
        ),
        patch(
            "src.infra.nexus_data_persist.close_database",
            new_callable=AsyncMock,
        ),
        patch(
            "src.infra.nexus_ws_broker.ws_broker.connect",
            new_callable=AsyncMock,
        ),
        patch(
            "src.infra.nexus_ws_broker.ws_broker.disconnect",
            new_callable=AsyncMock,
        ),
    ):
        from src.main import app

        with TestClient(app) as client:
            yield client


def test_websocket_status_json(sync_app_client: TestClient) -> None:
    r = sync_app_client.get("/api/v1/ws/status")
    assert r.status_code == 200
    data = r.json()
    assert "active_connections" in data
    assert isinstance(data["active_connections"], int)


@pytest.mark.asyncio
async def test_notify_artifact_progress_publishes() -> None:
    with patch(
        "src.api.websocket.manager.broadcast_to_tenant",
        new_callable=AsyncMock,
    ) as pub:
        from src.api.websocket import notify_artifact_progress

        await notify_artifact_progress("t1", "art1", "running", 50, "busy")
    pub.assert_awaited_once()
    call_kw = pub.await_args[0][1]
    assert call_kw["type"] == "artifact_progress"
    assert call_kw["artifact_id"] == "art1"


@pytest.mark.asyncio
async def test_handle_chat_message_empty_content() -> None:
    from src.api.websocket import _handle_chat_message

    ws = AsyncMock()
    ws.send_json = AsyncMock()
    await _handle_chat_message(ws, {"content": "  \t  "}, "u1", "t1", None)
    ws.send_json.assert_awaited_with({"type": "error", "message": "Empty message"})


def test_ws_chat_rejects_invalid_token(sync_app_client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect):
        with sync_app_client.websocket_connect("/api/v1/ws/chat?token=not-valid-jwt"):
            pass


def test_ws_chat_ping_pong(sync_app_client: TestClient) -> None:
    tok = create_access_token("ws-user", "ws-tenant", ["member"])
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        with sync_app_client.websocket_connect(f"/api/v1/ws/chat?token={tok}") as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
            assert "timestamp" in pong


def test_ws_chat_invalid_json(sync_app_client: TestClient) -> None:
    tok = create_access_token("ws-user2", "ws-tenant2", ["member"])
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        with sync_app_client.websocket_connect(f"/api/v1/ws/chat?token={tok}") as ws:
            ws.receive_json()
            ws.send_text("not-json-at-all")
            err = ws.receive_json()
            assert err["type"] == "error"
            assert "JSON" in err["message"]


def test_ws_chat_subscribe_artifact(sync_app_client: TestClient) -> None:
    tok = create_access_token("ws-user3", "ws-tenant3", ["member"])
    with patch("src.api.websocket.ws_broker.subscribe", new_callable=AsyncMock):
        with sync_app_client.websocket_connect(f"/api/v1/ws/chat?token={tok}") as ws:
            ws.receive_json()
            ws.send_json({"type": "subscribe", "artifact_id": "art-99"})
            sub = ws.receive_json()
            assert sub["type"] == "subscribed"
            assert sub["artifact_id"] == "art-99"
