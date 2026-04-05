"""Nexus API — Notebooks (CRUD + source management)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.exceptions import NotFoundError
from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/notebooks", tags=["Notebooks"])


# ── Schemas ──────────────────────────────────────────────────


class NotebookCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: str = ""
    icon: str = "📓"
    color: str = "#6366f1"
    tags: list[str] = []


class NotebookUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color: str | None = None
    archived: bool | None = None
    pinned: bool | None = None
    tags: list[str] | None = None


class NotebookResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    icon: str = "📓"
    color: str = "#6366f1"
    archived: bool = False
    pinned: bool = False
    tags: list[str] = []
    source_count: int = 0


class SourceLink(BaseModel):
    source_id: str


# ── Endpoints ────────────────────────────────────────────────


@router.post("", response_model=NotebookResponse, status_code=201)
@traced("notebooks.create")
async def create_notebook(
    data: NotebookCreate,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Create a new notebook."""
    from src.infra.nexus_data_persist import audit_repo, notebooks_repo

    result = await notebooks_repo.create(
        data={
            "user_id": auth.user_id,
            **data.model_dump(),
        },
        tenant_id=auth.tenant_id,
    )

    await audit_repo.create(
        data={
            "tenant_id": auth.tenant_id,
            "user_id": auth.user_id,
            "action": "notebook.create",
            "resource_type": "notebook",
            "resource_id": result["id"],
        }
    )

    return {**result, "source_count": 0}


@router.get("", response_model=list[NotebookResponse])
@traced("notebooks.list")
async def list_notebooks(
    auth: AuthContext = Depends(get_current_user),
    archived: bool = False,
    limit: int = Query(50, le=100),
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List notebooks for the current user."""
    from src.infra.nexus_data_persist import notebooks_repo

    return await notebooks_repo.list_all(
        auth.tenant_id,
        limit=limit,
        offset=offset,
        filters={"user_id": auth.user_id, "archived": archived},
    )


@router.get("/{notebook_id}", response_model=dict)
@traced("notebooks.get")
async def get_notebook(
    notebook_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Get a notebook with its sources."""
    from src.infra.nexus_data_persist import notebooks_repo

    result = await notebooks_repo.get_with_sources(notebook_id, auth.tenant_id)
    if not result:
        raise NotFoundError(f"Notebook '{notebook_id}' not found")
    return result


@router.patch("/{notebook_id}", response_model=dict)
@traced("notebooks.update")
async def update_notebook(
    notebook_id: str,
    data: NotebookUpdate,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Update a notebook."""
    from src.infra.nexus_data_persist import notebooks_repo

    update_data = data.model_dump(exclude_none=True)
    if not update_data:
        raise NotFoundError("No fields to update")

    result = await notebooks_repo.update(notebook_id, update_data, auth.tenant_id)
    if not result:
        raise NotFoundError(f"Notebook '{notebook_id}' not found")
    return result


@router.delete("/{notebook_id}", status_code=204)
@traced("notebooks.delete")
async def delete_notebook(
    notebook_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> None:
    """Soft-delete a notebook."""
    from src.infra.nexus_data_persist import notebooks_repo

    deleted = await notebooks_repo.soft_delete(notebook_id, auth.tenant_id)
    if not deleted:
        raise NotFoundError(f"Notebook '{notebook_id}' not found")


@router.get("/{notebook_id}/delete-preview")
@traced("notebooks.delete_preview")
async def delete_preview(
    notebook_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Preview cascade delete counts (Repo #7 pattern)."""
    from src.infra.nexus_data_persist import notebooks_repo

    counts = await notebooks_repo.cascade_delete_preview(notebook_id, auth.tenant_id)
    return {"notebook_id": notebook_id, "affected": counts}


@router.post("/{notebook_id}/sources", status_code=201)
@traced("notebooks.add_source")
async def add_source_to_notebook(
    notebook_id: str,
    link: SourceLink,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Link a source to a notebook."""
    from sqlalchemy import text

    from src.infra.nexus_data_persist import get_session

    async with get_session(auth.tenant_id) as session:
        await session.execute(
            text("""
                INSERT INTO notebook_sources (notebook_id, source_id)
                VALUES (:notebook_id, :source_id)
                ON CONFLICT DO NOTHING
            """),
            {"notebook_id": notebook_id, "source_id": link.source_id},
        )

    return {"notebook_id": notebook_id, "source_id": link.source_id, "linked": True}


@router.delete("/{notebook_id}/sources/{source_id}", status_code=204)
@traced("notebooks.remove_source")
async def remove_source_from_notebook(
    notebook_id: str,
    source_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> None:
    """Unlink a source from a notebook."""
    from sqlalchemy import text

    from src.infra.nexus_data_persist import get_session

    async with get_session(auth.tenant_id) as session:
        await session.execute(
            text("DELETE FROM notebook_sources WHERE notebook_id = :nid AND source_id = :sid"),
            {"nid": notebook_id, "sid": source_id},
        )
