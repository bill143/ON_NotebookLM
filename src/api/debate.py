"""Nexus API — AI Debate mode (argue both sides of a topic)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/debate", tags=["Debate"])


class DebateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=2000)
    notebook_id: str | None = None
    rounds: int = Field(default=3, ge=1, le=10)


class DebateRound(BaseModel):
    round_number: int
    pro: str
    con: str


class DebateResponse(BaseModel):
    topic: str
    rounds: list[DebateRound] = []
    summary: str = ""


@router.post("", response_model=DebateResponse)
@traced("debate.start")
async def start_debate(
    data: DebateRequest,
    auth: AuthContext = Depends(get_current_user),
) -> DebateResponse:
    """Run an AI debate on a topic grounded in notebook sources (stub — wired for future implementation)."""
    return DebateResponse(
        topic=data.topic,
        rounds=[],
        summary="Debate engine not yet implemented.",
    )
