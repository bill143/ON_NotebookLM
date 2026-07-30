"""Nexus API — Artifacts (generation queue, status, download)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, model_validator

from src.core.podcast_presets import normalize_podcast_config, podcast_preset_catalog
from src.exceptions import NotFoundError
from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/artifacts", tags=["Artifacts"])


# ── Schemas ──────────────────────────────────────────────────


class ArtifactCreate(BaseModel):
    notebook_id: str
    title: str = Field(..., min_length=1, max_length=1000)
    artifact_type: str = Field(
        ..., description="audio | report | quiz | podcast | summary | slide_deck"
    )
    generation_config: dict = Field(
        default_factory=dict, description="Type-specific generation config"
    )

    @model_validator(mode="after")
    def validate_generation_config(self) -> ArtifactCreate:
        if self.artifact_type in {"audio", "podcast"}:
            self.generation_config = normalize_podcast_config(self.generation_config)
        return self


class ArtifactResponse(BaseModel):
    id: str
    title: str
    artifact_type: str
    status: str
    content: str | None = None
    storage_url: str | None = None
    duration_seconds: float | None = None


# ── Endpoints ────────────────────────────────────────────────


@router.post("", response_model=ArtifactResponse, status_code=201)
@traced("artifacts.create")
async def create_artifact(
    data: ArtifactCreate,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Queue a new artifact for generation."""
    from src.infra.nexus_cost_tracker import cost_tracker
    from src.infra.nexus_data_persist import artifacts_repo

    # Budget check before generation
    await cost_tracker.check_budget(auth.tenant_id, auth.user_id, estimated_cost=0.05)

    result = await artifacts_repo.create(
        data={
            "notebook_id": data.notebook_id,
            "user_id": auth.user_id,
            "title": data.title,
            "artifact_type": data.artifact_type,
            "status": "queued",
            "generation_config": data.generation_config,
        },
        tenant_id=auth.tenant_id,
    )

    # Dispatch generation to Celery worker
    from src.worker import generate_artifact as generate_artifact_task

    generate_artifact_task.delay(result["id"], auth.tenant_id)

    return result


@router.get("", response_model=list[ArtifactResponse])
@traced("artifacts.list")
async def list_artifacts(
    auth: AuthContext = Depends(get_current_user),
    notebook_id: str | None = None,
    status: str | None = None,
    artifact_type: str | None = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List artifacts for the current user."""
    from src.infra.nexus_data_persist import artifacts_repo

    filters = {"user_id": auth.user_id}
    if notebook_id:
        filters["notebook_id"] = notebook_id
    if status:
        filters["status"] = status
    if artifact_type:
        filters["artifact_type"] = artifact_type

    return await artifacts_repo.list_all(
        auth.tenant_id, limit=limit, offset=offset, filters=filters
    )


@router.get("/podcast/presets", response_model=dict)
@traced("artifacts.podcast_presets")
async def podcast_presets(
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Return podcast generation presets for UI/API clients."""
    return podcast_preset_catalog()


@router.get("/{artifact_id}", response_model=dict)
@traced("artifacts.get")
async def get_artifact(
    artifact_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Get artifact details and content."""
    from src.infra.nexus_data_persist import artifacts_repo

    result = await artifacts_repo.get_by_id(artifact_id, auth.tenant_id)
    if not result:
        raise NotFoundError(f"Artifact '{artifact_id}' not found")
    return result


@router.post("/{artifact_id}/cancel", response_model=dict)
@traced("artifacts.cancel")
async def cancel_artifact(
    artifact_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Cancel a queued or processing artifact."""
    from src.infra.nexus_data_persist import artifacts_repo

    result = await artifacts_repo.update(
        artifact_id,
        {"status": "cancelled"},
        auth.tenant_id,
    )
    if not result:
        raise NotFoundError(f"Artifact '{artifact_id}' not found")
    return result


@router.delete("/{artifact_id}", status_code=204)
@traced("artifacts.delete")
async def delete_artifact(
    artifact_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> None:
    """Soft-delete an artifact."""
    from src.infra.nexus_data_persist import artifacts_repo

    deleted = await artifacts_repo.soft_delete(artifact_id, auth.tenant_id)
    if not deleted:
        raise NotFoundError(f"Artifact '{artifact_id}' not found")


@router.get("/queue/status", response_model=dict)
@traced("artifacts.queue_status")
async def queue_status(
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the current generation queue status."""
    from src.infra.nexus_data_persist import artifacts_repo

    queued = await artifacts_repo.count(auth.tenant_id, filters={"status": "queued"})
    processing = await artifacts_repo.count(auth.tenant_id, filters={"status": "processing"})

    return {
        "queued": queued,
        "processing": processing,
        "capacity": 10,  # TODO: Make configurable
    }
