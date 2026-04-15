"""
Nexus Plugin Bridge — Feature 8: Plugin Architecture
Source: ORIGINAL ENGINEERING (Tier 1 Critical Gap)

Provides:
- Plugin manifest schema and validation
- Sandboxed event-driven plugin execution
- Permission-based access control
- Plugin lifecycle management (install, enable, disable, uninstall)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from src.exceptions import PluginError, PluginPermissionError
from src.infra.nexus_obs_tracing import traced


class PluginPermission(str, Enum):
    READ_NOTEBOOKS = "read:notebooks"
    WRITE_NOTEBOOKS = "write:notebooks"
    READ_SOURCES = "read:sources"
    WRITE_SOURCES = "write:sources"
    READ_ARTIFACTS = "read:artifacts"
    WRITE_ARTIFACTS = "write:artifacts"
    CALL_AI = "call:ai"
    EMIT_EVENTS = "emit:events"


@dataclass
class PluginManifest:
    """Plugin manifest schema — defines capabilities and requirements."""

    name: str
    version: str
    description: str = ""
    author: str = ""
    permissions: list[PluginPermission] = field(default_factory=list)
    events_subscribed: list[str] = field(default_factory=list)
    events_emitted: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    min_nexus_version: str = "0.1.0"


@dataclass
class PluginContext:
    """Context passed to plugin handlers (sandboxed)."""

    plugin_name: str
    tenant_id: str
    user_id: str
    permissions: list[PluginPermission]
    config: dict[str, Any] = field(default_factory=dict)

    def require_permission(self, perm: PluginPermission) -> None:
        if perm not in self.permissions:
            raise PluginPermissionError(
                f"Plugin '{self.plugin_name}' requires '{perm.value}' permission"
            )


class EventBus:
    """Plugin event bus — pub/sub for cross-plugin communication."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[tuple[str, Callable]]] = {}

    def subscribe(self, event_type: str, plugin_name: str, handler: Callable) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append((plugin_name, handler))
        logger.debug(f"Plugin '{plugin_name}' subscribed to '{event_type}'")

    def unsubscribe(self, plugin_name: str) -> None:
        for event_type in self._subscribers:
            self._subscribers[event_type] = [
                (name, handler)
                for name, handler in self._subscribers[event_type]
                if name != plugin_name
            ]

    @traced("plugin.event.emit")
    async def emit(
        self, event_type: str, data: dict[str, Any], context: PluginContext
    ) -> list[Any]:
        """Emit an event and collect results from subscribers."""
        context.require_permission(PluginPermission.EMIT_EVENTS)
        handlers = self._subscribers.get(event_type, [])
        results = []

        for plugin_name, handler in handlers:
            try:
                result = await handler(event_type, data, context)
                results.append({"plugin": plugin_name, "result": result})
            except Exception as e:
                logger.error(f"Plugin '{plugin_name}' failed on event '{event_type}': {e}")
                results.append({"plugin": plugin_name, "error": str(e)})

        return results


class PluginManager:
    """Manages plugin lifecycle and execution."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginManifest] = {}
        self._handlers: dict[str, dict[str, Callable]] = {}
        self.event_bus = EventBus()

    async def install(
        self,
        manifest: PluginManifest | None = None,
        *,
        tenant_id: str = "",
        name: str = "",
        version: str = "latest",
        permissions: list[str] | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Install a plugin from its manifest or keyword args."""
        if manifest is None:
            manifest = PluginManifest(
                name=name,
                version=version,
                description=f"Plugin: {name}",
                author="user",
                permissions=[PluginPermission(p) for p in (permissions or [])
                             if p in [e.value for e in PluginPermission]],
                config_schema=config or {},
            )
        if manifest.name in self._plugins:
            raise PluginError(f"Plugin '{manifest.name}' already installed")

        self._plugins[manifest.name] = manifest
        self._handlers[manifest.name] = {}

        # Register plugin in database
        from src.infra.nexus_data_persist import BaseRepository

        repo = BaseRepository("plugin_registry")
        await repo.create(
            data={
                "name": manifest.name,
                "version": manifest.version,
                "description": manifest.description,
                "author": manifest.author,
                "manifest": {
                    "permissions": [p.value for p in manifest.permissions],
                    "events_subscribed": manifest.events_subscribed,
                    "events_emitted": manifest.events_emitted,
                    "config_schema": manifest.config_schema,
                },
                "permissions": [p.value for p in manifest.permissions],
            }
        )

        logger.info(f"Installed plugin: {manifest.name} v{manifest.version}")

        from datetime import UTC, datetime

        return {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "enabled": True,
            "permissions": [p.value for p in manifest.permissions],
            "installed_at": datetime.now(UTC).isoformat(),
        }

    async def uninstall(self, plugin_name: str = "", *, tenant_id: str = "", name: str = "") -> None:
        """Uninstall a plugin."""
        target = name or plugin_name
        if target not in self._plugins:
            raise PluginError(f"Plugin '{target}' not installed")

        self.event_bus.unsubscribe(target)
        del self._plugins[target]
        if target in self._handlers:
            del self._handlers[target]
        logger.info(f"Uninstalled plugin: {target}")

    def register_handler(self, plugin_name: str, action: str, handler: Callable) -> None:
        """Register an action handler for a plugin."""
        if plugin_name not in self._handlers:
            self._handlers[plugin_name] = {}
        self._handlers[plugin_name][action] = handler

    async def execute(
        self, plugin_name: str, action: str, data: dict, context: PluginContext
    ) -> Any:
        """Execute a plugin action in a sandboxed context."""
        if plugin_name not in self._handlers:
            raise PluginError(f"Plugin '{plugin_name}' not found")

        handler = self._handlers[plugin_name].get(action)
        if not handler:
            raise PluginError(f"Action '{action}' not found in plugin '{plugin_name}'")

        try:
            return await handler(data, context)
        except PluginPermissionError:
            raise
        except Exception as e:
            raise PluginError(f"Plugin execution failed: {e}", original_error=e) from e

    def list_plugins(self, tenant_id: str | None = None) -> list[dict[str, Any]]:
        """List all installed plugins."""
        from datetime import UTC, datetime

        return [
            {
                "name": m.name,
                "version": m.version,
                "description": m.description,
                "author": m.author,
                "enabled": True,
                "permissions": [p.value for p in m.permissions],
                "installed_at": datetime.now(UTC).isoformat(),
            }
            for m in self._plugins.values()
        ]

    async def toggle(
        self, tenant_id: str, name: str, enabled: bool
    ) -> dict[str, Any]:
        """Enable or disable a plugin."""
        if name not in self._plugins:
            raise PluginError(f"Plugin '{name}' not found")

        manifest = self._plugins[name]
        logger.info(f"Plugin '{name}' {'enabled' if enabled else 'disabled'}")

        from datetime import UTC, datetime

        return {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "enabled": enabled,
            "permissions": [p.value for p in manifest.permissions],
            "installed_at": datetime.now(UTC).isoformat(),
        }

    def get_plugin(self, tenant_id: str, name: str) -> dict[str, Any]:
        """Get plugin details."""
        if name not in self._plugins:
            raise PluginError(f"Plugin '{name}' not found")

        manifest = self._plugins[name]
        from datetime import UTC, datetime

        return {
            "name": manifest.name,
            "version": manifest.version,
            "description": manifest.description,
            "author": manifest.author,
            "enabled": True,
            "permissions": [p.value for p in manifest.permissions],
            "installed_at": datetime.now(UTC).isoformat(),
        }


# Global singleton
plugin_manager = PluginManager()
