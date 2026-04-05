"""
Nexus WebSocket Broker — Redis Pub/Sub for cross-worker event relay.

Solves the critical architectural limitation where ConnectionManager
and CollaborationHub store all state in-process memory. Without this
broker, scaling the API layer beyond a single Uvicorn worker causes
silent message loss for WebSocket clients connected to different workers.

Usage:
    from src.infra.nexus_ws_broker import ws_broker

    # In FastAPI lifespan:
    await ws_broker.connect()
    yield
    await ws_broker.disconnect()

    # Publishing (any worker):
    await ws_broker.publish("tenant:abc123", {"type": "event", ...})

    # Subscribing (local worker relays to its WebSocket clients):
    await ws_broker.subscribe("tenant:abc123", my_handler)
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from src.config import get_settings

_CHANNEL_PREFIX = "nexus:ws:"


class WebSocketBroker:
    """Redis pub/sub broker for cross-worker WebSocket event distribution."""

    def __init__(self) -> None:
        self._redis: Any = None
        self._pubsub: Any = None
        self._handlers: dict[str, list[Callable[[dict[str, Any]], Awaitable[None]]]] = {}
        self._listener_task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Redis and prepare the pub/sub client."""
        try:
            import redis.asyncio as aioredis

            settings = get_settings()
            self._redis = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._connected = True
            logger.info("WebSocket broker connected to Redis")
        except Exception as exc:
            logger.warning(
                "WebSocket broker Redis unavailable — cross-worker relay disabled",
                error=str(exc),
            )
            self._connected = False

    async def disconnect(self) -> None:
        """Cancel listener, close pub/sub and Redis connection."""
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception as exc:
                logger.debug("WebSocket broker pubsub close failed (ignored): {}", exc)
            self._pubsub = None

        if self._redis:
            try:
                await self._redis.close()
            except Exception as exc:
                logger.debug("WebSocket broker redis close failed (ignored): {}", exc)
            self._redis = None

        self._handlers.clear()
        self._connected = False
        logger.info("WebSocket broker disconnected")

    async def subscribe(
        self,
        channel: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Subscribe to a Redis channel and register a local handler."""
        if not self._connected or not self._pubsub:
            return

        prefixed = f"{_CHANNEL_PREFIX}{channel}"

        if prefixed not in self._handlers:
            self._handlers[prefixed] = []
            await self._pubsub.subscribe(prefixed)

        self._handlers[prefixed].append(handler)

        if self._listener_task is None or self._listener_task.done():
            self._listener_task = asyncio.create_task(self._listen())

    async def unsubscribe(self, channel: str) -> None:
        """Remove all handlers for a channel and unsubscribe from Redis."""
        if not self._connected or not self._pubsub:
            return

        prefixed = f"{_CHANNEL_PREFIX}{channel}"
        self._handlers.pop(prefixed, None)

        try:
            await self._pubsub.unsubscribe(prefixed)
        except Exception as exc:
            logger.debug("WebSocket broker unsubscribe failed (ignored): {}", exc)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        """Publish a JSON message to a Redis channel."""
        if not self._connected or not self._redis:
            return

        prefixed = f"{_CHANNEL_PREFIX}{channel}"
        try:
            await self._redis.publish(prefixed, json.dumps(message))
        except Exception as exc:
            logger.warning(f"WebSocket broker publish failed: {exc}")

    async def _listen(self) -> None:
        """Consume messages from all subscribed channels and dispatch to handlers."""
        if not self._pubsub:
            return

        try:
            async for raw_message in self._pubsub.listen():
                if raw_message is None:
                    continue
                if raw_message.get("type") != "message":
                    continue

                channel = raw_message.get("channel", "")
                data_str = raw_message.get("data", "")

                try:
                    data = json.loads(data_str)
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"WebSocket broker: invalid JSON on {channel}")
                    continue

                handlers = self._handlers.get(channel, [])
                for handler in handlers:
                    try:
                        await handler(data)
                    except Exception as exc:
                        logger.exception(f"WebSocket broker handler error on {channel}: {exc}")

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"WebSocket broker listener crashed: {exc}")

    @property
    def is_connected(self) -> bool:
        return self._connected


ws_broker = WebSocketBroker()
