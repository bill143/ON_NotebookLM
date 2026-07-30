"""Nexus API — Source Verification (fact-check and confidence scoring)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/verify", tags=["Verification"])


class VerifyRequest(BaseModel):
    claim: str = Field(..., min_length=1, max_length=5000)
    notebook_id: str | None = None
    source_ids: list[str] | None = None


class VerifyResponse(BaseModel):
    claim: str
    verdict: str = "unverified"
    confidence: float = 0.0
    supporting_sources: list[dict] = []
    explanation: str = ""


@router.post("", response_model=VerifyResponse)
@traced("verify.claim")
async def verify_claim(
    data: VerifyRequest,
    auth: AuthContext = Depends(get_current_user),
) -> VerifyResponse:
    """Verify a claim against notebook sources (stub — wired for future implementation)."""
    return VerifyResponse(
        claim=data.claim,
        verdict="unverified",
        confidence=0.0,
        explanation="Verification engine not yet implemented.",
    )
