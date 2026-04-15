"""
Local-First & Offline API — Feature 12: Local Model Management, Sync Status
Codename: ESPERANTO
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/local", tags=["Local-First & Offline"])


# ── Schemas ──────────────────────────────────────────────────


class LocalModelInfo(BaseModel):
    name: str
    provider: str = "ollama"
    size_gb: float
    quantization: str
    capabilities: list[str]
    status: str  # "available", "downloading", "not_installed"
    download_progress: float | None = None


class SyncStatusResponse(BaseModel):
    mode: str  # "online", "offline", "syncing"
    pending_operations: int
    last_sync_at: str | None = None
    conflicts: int
    queue_size: int


class FeatureAvailability(BaseModel):
    feature: str
    online: bool
    offline: bool
    degraded_note: str | None = None


class SyncConflict(BaseModel):
    id: str
    resource_type: str
    resource_id: str
    local_version: str
    remote_version: str
    strategy: str
    created_at: str


class ConflictResolution(BaseModel):
    strategy: str = Field(description="local_wins, remote_wins, or merge")


# ── Endpoints ────────────────────────────────────────────────


@router.get("/models")
async def list_local_models(
    auth: AuthContext = Depends(get_current_user),
) -> list[LocalModelInfo]:
    """List available local AI models (Ollama)."""
    from src.infra.nexus_local_sync import LocalModelManager

    manager = LocalModelManager()
    models = await manager.list_models()
    return [LocalModelInfo(**m) for m in models]


@router.post("/models/{model_name}/pull")
async def pull_model(
    model_name: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Start downloading a local model."""
    from src.infra.nexus_local_sync import LocalModelManager

    manager = LocalModelManager()
    await manager.pull_model(model_name)
    return {"status": "downloading", "model": model_name}


@router.delete("/models/{model_name}")
async def remove_model(
    model_name: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Remove a local model."""
    auth.require_role("admin")
    from src.infra.nexus_local_sync import LocalModelManager

    manager = LocalModelManager()
    await manager.remove_model(model_name)
    return {"status": "removed", "model": model_name}


@router.get("/sync/status")
async def get_sync_status(
    auth: AuthContext = Depends(get_current_user),
) -> SyncStatusResponse:
    """Get current sync status."""
    from src.infra.nexus_local_sync import SyncManager

    sync = SyncManager()
    status = await sync.get_status(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    return SyncStatusResponse(**status)


@router.post("/sync/trigger")
async def trigger_sync(
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Manually trigger a sync operation."""
    from src.infra.nexus_local_sync import SyncManager

    sync = SyncManager()
    await sync.trigger_sync(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    return {"status": "sync_started"}


@router.get("/sync/conflicts")
async def list_conflicts(
    auth: AuthContext = Depends(get_current_user),
) -> list[SyncConflict]:
    """List unresolved sync conflicts."""
    from src.infra.nexus_local_sync import SyncManager

    sync = SyncManager()
    conflicts = await sync.list_conflicts(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    return [SyncConflict(**c) for c in conflicts]


@router.post("/sync/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    data: ConflictResolution,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Resolve a sync conflict."""
    from src.infra.nexus_local_sync import SyncManager

    sync = SyncManager()
    await sync.resolve_conflict(
        tenant_id=auth.tenant_id,
        conflict_id=conflict_id,
        strategy=data.strategy,
    )
    return {"status": "resolved", "conflict_id": conflict_id}


@router.get("/features")
async def get_feature_matrix(
    auth: AuthContext = Depends(get_current_user),
) -> list[FeatureAvailability]:
    """Get feature availability matrix (online vs offline)."""
    from src.infra.nexus_local_sync import get_feature_matrix

    return [FeatureAvailability(**f) for f in get_feature_matrix()]
