"""Nexus API — Research Mode (multi-turn deep research with checkpointing)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user
from src.infra.nexus_obs_tracing import traced
from src.exceptions import NotFoundError

router = APIRouter(prefix="/research", tags=["Research"])


# ── Schemas ──────────────────────────────────────────────────

class ResearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, description="Resume existing session")
    notebook_id: Optional[str] = Field(None, description="Restrict to notebook sources")


class ResearchResult(BaseModel):
    session_id: str
    turn_id: str
    turn_number: int
    answer: str
    citations: list[dict] = []
    follow_up_questions: list[str] = []
    model_used: str = ""
    latency_ms: float = 0.0
    total_turns: int = 0


class ResearchSessionSummary(BaseModel):
    id: str
    title: str
    notebook_id: Optional[str]
    turn_count: int
    total_tokens: int
    created_at: str
    updated_at: str


# ── Endpoints ────────────────────────────────────────────────

@router.post("", response_model=ResearchResult)
@traced("research.query")
async def research_query(
    data: ResearchQuery,
    auth: AuthContext = Depends(get_current_user),
):
    """Execute a research turn — creates or resumes a session."""
    from src.core.nexus_research_grounding import research_graph

    result = await research_graph.execute_turn(
        query=data.query,
        session_id=data.session_id,
        notebook_id=data.notebook_id or "",
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
    )
    return result


@router.get("/sessions", response_model=list[dict])
@traced("research.list_sessions")
async def list_research_sessions(
    auth: AuthContext = Depends(get_current_user),
    notebook_id: Optional[str] = None,
    limit: int = Query(20, le=50),
):
    """List research sessions for the current user."""
    from src.core.nexus_research_grounding import research_graph

    return await research_graph.list_sessions(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=notebook_id,
    )


@router.get("/sessions/{session_id}", response_model=dict)
@traced("research.get_session")
async def get_research_session(
    session_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    """Get full research session with all turns and citations."""
    from src.core.nexus_research_grounding import research_graph

    result = await research_graph.get_session(session_id, auth.tenant_id)
    if not result:
        raise NotFoundError(f"Research session '{session_id}' not found")
    return result
