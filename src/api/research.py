"""Nexus API — Research Mode (multi-turn deep research with checkpointing)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.exceptions import NotFoundError
from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/research", tags=["Research"])


# ── Schemas ──────────────────────────────────────────────────


class ResearchQuery(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    session_id: str | None = Field(None, description="Resume existing session")
    notebook_id: str | None = Field(None, description="Restrict to notebook sources")
    profile: str = Field(
        default="standard",
        description="Research depth profile: auto | quick | standard | deep",
    )
    max_follow_ups: int | None = Field(
        default=None,
        ge=0,
        le=10,
        description="Override the number of generated follow-up questions",
    )


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
    profile_used: str = "standard"


class ResearchSessionSummary(BaseModel):
    id: str
    title: str
    notebook_id: str | None
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
) -> ResearchResult:
    """Execute a research turn — creates or resumes a session."""
    from src.core.nexus_research_grounding import research_graph

    result = await research_graph.execute_turn(
        query=data.query,
        session_id=data.session_id,
        notebook_id=data.notebook_id or "",
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        profile=data.profile,
        max_follow_ups=data.max_follow_ups,
    )
    return ResearchResult.model_validate(result)


@router.get("/profiles", response_model=dict)
@traced("research.profiles")
async def research_profiles(
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """List supported research profiles and tuning knobs."""
    return {
        "default": "standard",
        "profiles": {
            "quick": {
                "description": "Fast response with lighter retrieval and fewer follow-ups",
                "best_for": ["quick checks", "low-latency answers"],
            },
            "standard": {
                "description": "Balanced quality, latency, and token usage",
                "best_for": ["general research", "iterative exploration"],
            },
            "deep": {
                "description": "Maximum context retrieval and richer synthesis",
                "best_for": ["complex analysis", "exhaustive source synthesis"],
            },
            "auto": {
                "description": "Automatically chooses quick/standard/deep from query complexity",
                "best_for": ["mixed workloads", "hands-off optimization"],
            },
        },
    }


@router.get("/sessions", response_model=list[dict])
@traced("research.list_sessions")
async def list_research_sessions(
    auth: AuthContext = Depends(get_current_user),
    notebook_id: str | None = None,
    limit: int = Query(20, le=50),
) -> list[dict[str, Any]]:
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
) -> dict[str, Any]:
    """Get full research session with all turns and citations."""
    from src.core.nexus_research_grounding import research_graph

    result = await research_graph.get_session(session_id, auth.tenant_id)
    if not result:
        raise NotFoundError(f"Research session '{session_id}' not found")
    return result


@router.get("/sessions/{session_id}/citations")
@traced("research.export_citations")
async def export_citations(
    session_id: str,
    format: str = "json",
    auth: AuthContext = Depends(get_current_user),
) -> Any:
    """Export citations from a research session (Feature 2C).

    Formats: json (default), bibtex, markdown
    """
    from src.core.nexus_research_grounding import research_graph

    session = await research_graph.get_session(session_id, auth.tenant_id)
    if not session:
        raise NotFoundError(f"Research session '{session_id}' not found")

    # Collect all unique citations across turns
    citations: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for turn in session.get("turns", []):
        for cit in turn.get("sources_consulted", []):
            cid = cit.get("source_id", "")
            if cid and cid not in seen_ids:
                seen_ids.add(cid)
                citations.append(cit)

    if format == "bibtex":
        lines = []
        for i, c in enumerate(citations, 1):
            key = c.get("source_id", f"ref{i}").replace(":", "_").replace("/", "_")
            title = c.get("source_title", "Untitled")
            lines.append(f"@misc{{{key},")
            lines.append(f"  title = {{{title}}},")
            lines.append(f"  note = {{{c.get('content_preview', '')[:200]}}},")
            lines.append(f"  relevance = {{{c.get('relevance_score', 0):.2f}}}",)
            lines.append("}")
            lines.append("")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines), media_type="text/plain")

    if format == "markdown":
        lines = [f"# Citations — {session.get('title', 'Research Session')}", ""]
        for i, c in enumerate(citations, 1):
            title = c.get("source_title", "Untitled")
            preview = c.get("content_preview", "")
            score = c.get("relevance_score", 0)
            lines.append(f"{i}. **{title}** (relevance: {score:.0%})")
            if preview:
                lines.append(f"   > {preview[:200]}")
            lines.append("")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")

    # Default: JSON
    return {
        "session_id": session_id,
        "citation_count": len(citations),
        "citations": citations,
    }
