"""Nexus API — Mind Map generation from notebook sources."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/mindmap", tags=["Mind Map"])


class MindMapRequest(BaseModel):
    notebook_id: str
    focus_query: str | None = Field(None, max_length=1000)
    max_depth: int = Field(default=3, ge=1, le=6)


class MindMapNode(BaseModel):
    id: str
    label: str
    children: list[MindMapNode] = []


class MindMapResponse(BaseModel):
    notebook_id: str
    root: MindMapNode
    node_count: int = 0


@router.post("", response_model=MindMapResponse)
@traced("mindmap.generate")
async def generate_mindmap(
    data: MindMapRequest,
    auth: AuthContext = Depends(get_current_user),
) -> MindMapResponse:
    """Generate a hierarchical mind map from notebook sources (stub — wired for future implementation)."""
    return MindMapResponse(
        notebook_id=data.notebook_id,
        root=MindMapNode(id="root", label="Topics", children=[]),
        node_count=1,
    )
