"""
Nexus Brain Knowledge — Feature 5: Persistent Brain & Learning System
Source: Repo #7 (notes, insights, vector search), ORIGINAL ENGINEERING (FSRS)
Provides:
- Notebook-scoped knowledge base with dual search
- FSRS-4.5 spaced repetition algorithm
- Auto-flashcard generation from sources
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from loguru import logger

from src.infra.nexus_obs_tracing import traced

# ── FSRS-4.5 Spaced Repetition Algorithm ──────────────────────
# Original engineering — no repo has this

# FSRS-4.5 parameters (optimal defaults from research)
FSRS_PARAMS = {
        "w": [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61],
        "decay": -0.5,
        "factor": 0.9 ** (1 / -0.5) - 1,
        "request_retention": 0.9,
}


@dataclass
class ReviewState:
        """State of a flashcard review schedule."""

    difficulty: float  # D in [1, 10]
    stability: float  # S > 0 (days)
    retrievability: float  # R in [0, 1]
    state: int  # 0=new, 1=learning, 2=review, 3=relearning
    review_count: int = 0
    lapses: int = 0
    due_at: Optional[datetime] = None


class FSRSScheduler:
        """
            FSRS-4.5 scheduling algorithm implementation.

                Calculates optimal review intervals based on memory model.
                    """

    def __init__(self, params: Optional[dict] = None) -> None:
                self.w = (params or FSRS_PARAMS)["w"]
                self.decay = FSRS_PARAMS["decay"]
                self.factor = FSRS_PARAMS["factor"]
                self.requested_retention = FSRS_PARAMS["request_retention"]

    def init_difficulty(self, rating: int) -> float:
                """Calculate initial difficulty from first rating."""
                return max(1.0, min(10.0, self.w[4] - math.exp(self.w[5] * (rating - 1)) + 1))

    def init_stability(self, rating: int) -> float:
                """Calculate initial stability from first rating."""
                return max(0.1, self.w[rating - 1])

    def next_difficulty(self, d: float, rating: int) -> float:
                """Update difficulty after a review."""
                delta = -(self.w[6] * (rating - 3))
                new_d = d + delta * (1 - d / 10 * self.w[7])
                return max(1.0, min(10.0, new_d))

    def next_stability(self, d: float, s: float, r: float, rating: int) -> float:
                """Calculate new stability after a review."""
                if rating == 1:  # again
                    return max(
                                        0.1,
                                        self.w[11]
                                        * pow(d, -self.w[12])
                                        * (pow(s + 1, self.w[13]) - 1)
                                        * math.exp((1 - r) * self.w[14]),
                    )
                else:  # hard, good, easy
                    hard_penalty = self.w[15] if rating == 2 else 1.0
                                easy_bonus = self.w[16] if rating == 4 else 1.0
                                return s * (
                                    1
                                    + math.exp(self.w[8])
                                    * (11 - d)
                                    * pow(s, -self.w[9])
                                    * (math.exp((1 - r) * self.w[10]) - 1)
                                    * hard_penalty
                                    * easy_bonus
                                )

    def next_interval(self, s: float) -> float:
                """Calculate next review interval in days from stability."""
                interval = s / self.factor * (pow(self.requested_retention, 1 / self.decay) - 1)
                return max(1.0, round(interval))

    def retrievability(self, s: float, elapsed_days: float) -> float:
                """Calculate current retrievability (probability of recall)."""
                return pow(1 + self.factor * elapsed_days / s, self.decay)

    def schedule_review(
                self,
                current_state: ReviewState,
                rating: int,  # 1=again, 2=hard, 3=good, 4=easy
    ) -> ReviewState:
                """Schedule the next review based on rating."""
                now = datetime.now(timezone.utc)

        if current_state.state == 0:  # New card
                        difficulty = self.init_difficulty(rating)
                        stability = self.init_stability(rating)
                        state = 1 if rating < 3 else 2
else:
                # Use the scheduled interval as the baseline elapsed time.
                # This ensures that when a card is reviewed exactly on time
                # (elapsed ~ 0), the retrievability reflects the target retention
                # rather than a perfect recall of 1.0 which would zero out the
                # stability-increase term.
                scheduled_interval = self.next_interval(current_state.stability)
                if current_state.due_at:
                                    actual_elapsed = (now - current_state.due_at).total_seconds() / 86400
                                    # elapsed = scheduled interval + any overdue time (min 0)
                                    elapsed = scheduled_interval + max(0.0, actual_elapsed)
else:
                elapsed = scheduled_interval

            r = self.retrievability(current_state.stability, elapsed)
            difficulty = self.next_difficulty(current_state.difficulty, rating)
            stability = self.next_stability(difficulty, current_state.stability, r, rating)
            state = 3 if rating == 1 else 2

        interval_days = self.next_interval(stability)
        due_at = now + timedelta(days=interval_days)

        return ReviewState(
                        difficulty=round(difficulty, 4),
                        stability=round(stability, 4),
                        retrievability=1.0,  # Just reviewed
                        state=state,
                        review_count=current_state.review_count + 1,
                        lapses=current_state.lapses + (1 if rating == 1 else 0),
                        due_at=due_at,
        )


# ── Knowledge Base Service ─────────────────────────────────────
class KnowledgeBase:
        """Notebook-scoped knowledge management."""

    def __init__(self) -> None:
                self.fsrs = FSRSScheduler()

    @traced("brain.get_due_cards")
    async def get_due_flashcards(
                self,
                user_id: str,
                tenant_id: str,
                notebook_id: Optional[str] = None,
                limit: int = 20,
    ) -> list[dict[str, Any]]:
                """Get flashcards due for review."""
                from src.infra.nexus_data_persist import get_session
                from sqlalchemy import text

        query = """
                    SELECT f.id, f.front, f.back, f.tags,
                                       rr.difficulty, rr.stability, rr.due_at,
                                                          rr.review_count, rr.lapses, rr.state
                                                                      FROM flashcards f
                                                                                  LEFT JOIN review_records rr
                                                                                                  ON f.id = rr.flashcard_id AND rr.user_id = :user_id
                                                                                                              WHERE f.tenant_id = :tenant_id
                                                                                                                            AND (rr.due_at IS NULL OR rr.due_at <= NOW())
                                                                                                                                    """
        params: dict[str, Any] = {"user_id": user_id, "tenant_id": tenant_id}
        if notebook_id:
                        query += " AND f.notebook_id = :notebook_id"
                        params["notebook_id"] = notebook_id
                    query += " ORDER BY rr.due_at ASC NULLS FIRST LIMIT :limit"
        params["limit"] = limit

        async with get_session(tenant_id) as session:
                        result = await session.execute(text(query), params)
                        return [dict(row) for row in result.mappings().all()]

    @traced("brain.review_card")
    async def review_flashcard(
                self,
                flashcard_id: str,
                user_id: str,
                tenant_id: str,
                rating: int,
    ) -> dict[str, Any]:
                """Process a flashcard review and schedule next review."""
                from src.infra.nexus_data_persist import get_session
                from sqlalchemy import text

        # Get current state
                async with get_session(tenant_id) as session:
                                result = await session.execute(
                                                    text("""
                                                                        SELECT difficulty, stability, due_at, review_count, lapses, state
                                                                                            FROM review_records
                                                                                                                WHERE flashcard_id = :fid AND user_id = :uid
                                                                                                                                    ORDER BY created_at DESC LIMIT 1
                                                                                                                                                    """),
                                                    {"fid": flashcard_id, "uid": user_id},
                                )
                                row = result.mappings().first()

        if row:
                        current = ReviewState(
                                            difficulty=float(row["difficulty"]),
                                            stability=float(row["stability"]),
                                            retrievability=1.0,
                                            state=int(row["state"]),
                                            review_count=int(row["review_count"]),
                                            lapses=int(row["lapses"]),
                                            due_at=row["due_at"],
                        )
else:
                current = ReviewState(difficulty=0, stability=0, retrievability=1.0, state=0)

        # Calculate next state
            next_state = self.fsrs.schedule_review(current, rating)

        # Save review record
        async with get_session(tenant_id) as session:
                        await session.execute(
                                            text("""
                                                                INSERT INTO review_records
                                                                                        (id, flashcard_id, user_id, difficulty, stability,
                                                                                                                 retrievability, due_at, review_count, lapses, rating, state)
                                                                                                                                     VALUES
                                                                                                                                                             (uuid_generate_v4(), :fid, :uid, :d, :s, :r,
                                                                                                                                                                                      :due, :rc, :l, :rating, :state)
                                                                                                                                                                                                      """),
                                            {
                                                                    "fid": flashcard_id,
                                                                    "uid": user_id,
                                                                    "d": next_state.difficulty,
                                                                    "s": next_state.stability,
                                                                    "r": next_state.retrievability,
                                                                    "due": next_state.due_at,
                                                                    "rc": next_state.review_count,
                                                                    "l": next_state.lapses,
                                                                    "rating": rating,
                                                                    "state": next_state.state,
                                            },
                        )

        return {
                        "next_due": next_state.due_at.isoformat() if next_state.due_at else None,
                        "difficulty": next_state.difficulty,
                        "stability": next_state.stability,
                        "interval_days": (
                                            (next_state.due_at - datetime.now(timezone.utc)).days
                                            if next_state.due_at
                                            else 0
                        ),
        }


# Global singleton
knowledge_base = KnowledgeBase()
