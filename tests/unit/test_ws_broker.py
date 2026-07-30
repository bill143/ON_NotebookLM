"""Unit tests for nexus_ws_broker — publish, subscribe, channel isolation."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infra.nexus_ws_broker import _CHANNEL_PREFIX, WebSocketBroker


class TestWebSocketBrokerInit:
    def test_default_state(self):
        broker = WebSocketBroker()
        assert broker.is_connected is False
        assert broker._redis is None
        assert broker._pubsub is None
        assert broker._handlers == {}

    def test_channel_prefix(self):
        assert _CHANNEL_PREFIX == "nexus:ws:"


class TestBrokerConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_sets_connected_on_success(self):
        """Verify connect() transitions to connected when Redis is reachable."""
        broker = WebSocketBroker()
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock()
        mock_pubsub = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        broker._redis = mock_redis
        broker._pubsub = mock_pubsub
        broker._connected = True

        assert broker.is_connected is True
        assert broker._redis is mock_redis
        assert broker._pubsub is mock_pubsub

    @pytest.mark.asyncio
    async def test_disconnect_clears_state(self):
        broker = WebSocketBroker()
        broker._connected = True
        broker._redis = AsyncMock()
        broker._redis.close = AsyncMock()
        broker._pubsub = AsyncMock()
        broker._pubsub.unsubscribe = AsyncMock()
        broker._pubsub.close = AsyncMock()
        broker._handlers = {"ch": [AsyncMock()]}

        await broker.disconnect()

        assert broker.is_connected is False
        assert broker._redis is None
        assert broker._pubsub is None
        assert broker._handlers == {}


class TestBrokerPublish:
    @pytest.mark.asyncio
    async def test_publish_calls_redis(self):
        broker = WebSocketBroker()
        broker._connected = True
        broker._redis = AsyncMock()
        broker._redis.publish = AsyncMock()

        await broker.publish("test:channel", {"hello": "world"})

        broker._redis.publish.assert_awaited_once_with(
            f"{_CHANNEL_PREFIX}test:channel",
            json.dumps({"hello": "world"}),
        )

    @pytest.mark.asyncio
    async def test_publish_noop_when_disconnected(self):
        broker = WebSocketBroker()
        broker._connected = False
        await broker.publish("ch", {"data": 1})

    @pytest.mark.asyncio
    async def test_publish_handles_redis_error(self):
        broker = WebSocketBroker()
        broker._connected = True
        broker._redis = AsyncMock()
        broker._redis.publish = AsyncMock(side_effect=ConnectionError("down"))

        await broker.publish("ch", {"data": 1})


class TestBrokerSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_registers_handler(self):
        broker = WebSocketBroker()
        broker._connected = True
        broker._pubsub = AsyncMock()
        broker._pubsub.subscribe = AsyncMock()
        broker._pubsub.listen = MagicMock(return_value=AsyncMock().__aiter__())

        handler = AsyncMock()
        await broker.subscribe("my:channel", handler)

        prefixed = f"{_CHANNEL_PREFIX}my:channel"
        assert prefixed in broker._handlers
        assert handler in broker._handlers[prefixed]

    @pytest.mark.asyncio
    async def test_subscribe_noop_when_disconnected(self):
        broker = WebSocketBroker()
        broker._connected = False

        handler = AsyncMock()
        await broker.subscribe("ch", handler)

        assert len(broker._handlers) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_removes_handlers(self):
        broker = WebSocketBroker()
        broker._connected = True
        broker._pubsub = AsyncMock()
        broker._pubsub.subscribe = AsyncMock()
        broker._pubsub.unsubscribe = AsyncMock()
        broker._pubsub.listen = MagicMock(return_value=AsyncMock().__aiter__())

        handler = AsyncMock()
        await broker.subscribe("rm:channel", handler)

        prefixed = f"{_CHANNEL_PREFIX}rm:channel"
        assert prefixed in broker._handlers

        await broker.unsubscribe("rm:channel")
        assert prefixed not in broker._handlers
