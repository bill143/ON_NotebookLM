"""
Plugin Management API — Feature 8: Plugin Architecture
Codename: ESPERANTO
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/plugins", tags=["Plugins"])


# ── Schemas ──────────────────────────────────────────────────


class PluginInstallRequest(BaseModel):
    name: str
    version: str = "latest"
    permissions: list[str] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class PluginResponse(BaseModel):
    name: str
    version: str
    description: str
    author: str
    enabled: bool
    permissions: list[str]
    installed_at: str


class PluginToggleRequest(BaseModel):
    enabled: bool


# ── Endpoints ────────────────────────────────────────────────


@router.get("")
async def list_plugins(
    auth: AuthContext = Depends(get_current_user),
) -> list[PluginResponse]:
    """List all installed plugins for this tenant."""
    auth.require_role("admin")
    from src.infra.nexus_plugin_bridge import plugin_manager

    plugins = plugin_manager.list_plugins(tenant_id=auth.tenant_id)
    return [PluginResponse(**p) for p in plugins]


@router.post("")
async def install_plugin(
    data: PluginInstallRequest,
    auth: AuthContext = Depends(get_current_user),
) -> PluginResponse:
    """Install a plugin."""
    auth.require_role("admin")
    from src.infra.nexus_plugin_bridge import plugin_manager

    plugin = await plugin_manager.install(
        tenant_id=auth.tenant_id,
        name=data.name,
        version=data.version,
        permissions=data.permissions,
        config=data.config,
    )
    return PluginResponse(**plugin)


@router.patch("/{plugin_name}")
async def toggle_plugin(
    plugin_name: str,
    data: PluginToggleRequest,
    auth: AuthContext = Depends(get_current_user),
) -> PluginResponse:
    """Enable or disable a plugin."""
    auth.require_role("admin")
    from src.infra.nexus_plugin_bridge import plugin_manager

    plugin = await plugin_manager.toggle(
        tenant_id=auth.tenant_id,
        name=plugin_name,
        enabled=data.enabled,
    )
    return PluginResponse(**plugin)


@router.delete("/{plugin_name}")
async def uninstall_plugin(
    plugin_name: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Uninstall a plugin."""
    auth.require_role("admin")
    from src.infra.nexus_plugin_bridge import plugin_manager

    await plugin_manager.uninstall(
        tenant_id=auth.tenant_id,
        name=plugin_name,
    )
    return {"status": "uninstalled", "plugin": plugin_name}


@router.get("/{plugin_name}")
async def get_plugin(
    plugin_name: str,
    auth: AuthContext = Depends(get_current_user),
) -> PluginResponse:
    """Get plugin details."""
    auth.require_role("admin")
    from src.infra.nexus_plugin_bridge import plugin_manager

    plugin = plugin_manager.get_plugin(
        tenant_id=auth.tenant_id,
        name=plugin_name,
    )
    return PluginResponse(**plugin)
