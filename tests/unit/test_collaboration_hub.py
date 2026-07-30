"""Unit tests for CollaborationHub and collaboration datatypes."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.api.collaboration import (
    ActivityType,
    CollaborationEvent,
    CollaborationHub,
    NotebookLock,
    PresenceUser,
    UserStatus,
)


def test_user_status_values() -> None:
    assert UserStatus.ACTIVE.value == "active"


def test_presence_user_to_dict_excludes_websocket() -> None:
    ws = AsyncMock()
    u = PresenceUser(
        user_id="u1",
        tenant_id="t1",
        display_name="Bob",
        avatar_color="#fff",
        connection_id="c1",
        websocket=ws,
        notebook_id="nb",
    )
    d = u.to_presence_dict()
    assert d["user_id"] == "u1"
    assert "websocket" not in d


def test_notebook_lock_is_expired() -> None:
    lock = NotebookLock(
        notebook_id="n",
        section_id="s",
        locked_by="u",
        locked_at=0.0,
        expires_at=1.0,
    )
    with patch("src.api.collaboration.time.time", return_value=999.0):
        assert lock.is_expired is True


def test_collaboration_event_to_dict() -> None:
    ev = CollaborationEvent(
        event_id="e1",
        event_type=ActivityType.JOIN,
        user_id="u",
        display_name="D",
        notebook_id="nb",
        timestamp=1.0,
        data={"k": 1},
    )
    d = ev.to_dict()
    assert d["event_type"] == "join"
    assert d["data"]["k"] == 1


@pytest.mark.asyncio
async def test_hub_connect_handle_ping_disconnect() -> None:
    hub = CollaborationHub()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        cid = await hub.connect(ws, "u1", "t1", "Alice", "nb1")
    assert cid in hub._users

    pong = await hub.handle_event(cid, {"type": "ping"})
    assert pong is not None
    assert pong["type"] == "pong"

    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        await hub.disconnect(cid)
    assert cid not in hub._users


@pytest.mark.asyncio
async def test_hub_handle_unknown_connection() -> None:
    hub = CollaborationHub()
    out = await hub.handle_event("missing", {"type": "ping"})
    assert out is not None
    assert out["type"] == "error"


@pytest.mark.asyncio
async def test_hub_get_presence_and_activity() -> None:
    hub = CollaborationHub()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        cid = await hub.connect(ws, "u2", "t2", "Bob", "nb2")

    pres = await hub.handle_event(cid, {"type": "get_presence"})
    assert pres is not None
    assert pres["type"] == "presence_list"
    assert isinstance(pres["users"], list)

    feed = await hub.handle_event(cid, {"type": "get_activity"})
    assert feed is not None
    assert feed["type"] == "activity_feed"

    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        await hub.disconnect(cid)


@pytest.mark.asyncio
async def test_hub_cursor_and_selection() -> None:
    hub = CollaborationHub()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        cid = await hub.connect(ws, "u3", "t3", "Cara", "nb3")

    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        await hub.handle_event(cid, {"type": "cursor_move", "position": {"x": 1}})
        await hub.handle_event(
            cid,
            {"type": "selection_change", "selection": {"start": 0, "end": 1}},
        )

    user = hub._users[cid]
    assert user.cursor_position == {"x": 1}
    assert user.selection == {"start": 0, "end": 1}

    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        await hub.disconnect(cid)


@pytest.mark.asyncio
async def test_hub_typing_and_unknown_event() -> None:
    hub = CollaborationHub()
    ws = AsyncMock()
    ws.accept = AsyncMock()
    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        cid = await hub.connect(ws, "u4", "t4", "Dan", "nb4")

    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        await hub.handle_event(cid, {"type": "typing_start"})
        await hub.handle_event(cid, {"type": "typing_stop"})

    assert await hub.handle_event(cid, {"type": "unknown_event_xyz"}) is None

    with patch("src.api.collaboration.ws_broker.publish", new_callable=AsyncMock):
        await hub.disconnect(cid)
