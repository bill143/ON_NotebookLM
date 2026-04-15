"""
Brain & Learning API — Feature 5: Spaced Repetition, Flashcards, Progress
Codename: ESPERANTO
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/brain", tags=["Brain & Learning"])


# ── Schemas ──────────────────────────────────────────────────


class FlashcardCreate(BaseModel):
    notebook_id: str
    front: str
    back: str
    source_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class FlashcardResponse(BaseModel):
    id: str
    notebook_id: str
    front: str
    back: str
    source_id: str | None = None
    tags: list[str]
    difficulty: float
    stability: float
    due_at: str | None = None
    review_count: int
    created_at: str


class ReviewSubmit(BaseModel):
    card_id: str
    rating: int = Field(ge=1, le=4, description="1=Again, 2=Hard, 3=Good, 4=Easy")


class ReviewResponse(BaseModel):
    card_id: str
    next_due: str
    new_difficulty: float
    new_stability: float
    interval_days: float


class ProgressSummary(BaseModel):
    total_cards: int
    cards_due: int
    cards_learned: int
    cards_new: int
    average_difficulty: float
    retention_rate: float
    streak_days: int


class GenerateFlashcardsRequest(BaseModel):
    notebook_id: str
    source_id: str
    count: int = Field(default=10, ge=1, le=50)


# ── Endpoints ────────────────────────────────────────────────


@router.get("/flashcards")
async def list_flashcards(
    notebook_id: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
) -> list[FlashcardResponse]:
    """List flashcards, optionally filtered by notebook."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    cards = await brain.list_flashcards(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=notebook_id,
    )
    return [FlashcardResponse(**c) for c in cards]


@router.post("/flashcards")
async def create_flashcard(
    data: FlashcardCreate,
    auth: AuthContext = Depends(get_current_user),
) -> FlashcardResponse:
    """Create a manual flashcard."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    card = await brain.create_flashcard(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=data.notebook_id,
        front=data.front,
        back=data.back,
        source_id=data.source_id,
        tags=data.tags,
    )
    return FlashcardResponse(**card)


@router.get("/flashcards/due")
async def get_due_cards(
    notebook_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    auth: AuthContext = Depends(get_current_user),
) -> list[FlashcardResponse]:
    """Get flashcards due for review."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    cards = await brain.get_due_cards(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=notebook_id,
        limit=limit,
    )
    return [FlashcardResponse(**c) for c in cards]


@router.post("/flashcards/review")
async def submit_review(
    data: ReviewSubmit,
    auth: AuthContext = Depends(get_current_user),
) -> ReviewResponse:
    """Submit a flashcard review and get next scheduling."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    result = await brain.submit_review(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        card_id=data.card_id,
        rating=data.rating,
    )
    return ReviewResponse(**result)


@router.post("/flashcards/generate")
async def generate_flashcards(
    data: GenerateFlashcardsRequest,
    auth: AuthContext = Depends(get_current_user),
) -> list[FlashcardResponse]:
    """Auto-generate flashcards from a source using AI."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    cards = await brain.generate_from_source(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=data.notebook_id,
        source_id=data.source_id,
        count=data.count,
    )
    return [FlashcardResponse(**c) for c in cards]


@router.delete("/flashcards/{card_id}")
async def delete_flashcard(
    card_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Delete a flashcard."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    await brain.delete_flashcard(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        card_id=card_id,
    )
    return {"status": "deleted", "card_id": card_id}


@router.get("/progress")
async def get_progress(
    notebook_id: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_user),
) -> ProgressSummary:
    """Get learning progress summary."""
    from src.core.nexus_brain_knowledge import BrainManager

    brain = BrainManager()
    progress = await brain.get_progress(
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        notebook_id=notebook_id,
    )
    return ProgressSummary(**progress)
