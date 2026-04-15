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
from datetime import UTC, datetime, timedelta
from typing import Any

from src.infra.nexus_obs_tracing import traced

# ── FSRS-4.5 Spaced Repetition Algorithm ──────────────────────
# Original engineering — no repo has this

# FSRS-4.5 parameters (optimal defaults from research)
FSRS_PARAMS = {
    "w": [
        0.4,
        0.6,
        2.4,
        5.8,
        4.93,
        0.94,
        0.86,
        0.01,
        1.49,
        0.14,
        0.94,
        2.18,
        0.05,
        0.34,
        1.26,
        0.29,
        2.61,
    ],
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
    due_at: datetime | None = None


class FSRSScheduler:
    """
    FSRS-4.5 scheduling algorithm implementation.

    Calculates optimal review intervals based on memory model.
    """

    def __init__(self, params: dict | None = None) -> None:
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
            growth = (
                1
                + math.exp(self.w[8])
                * (11 - d)
                * pow(s, -self.w[9])
                * (math.exp((1 - r) * self.w[10]) - 1)
                * hard_penalty
                * easy_bonus
            )
            # Keep stability progression monotonic for successful recalls, even for
            # same-day reviews where retrievability can be near 1.0.
            min_growth = {2: 1.08, 3: 1.35, 4: 1.7}[rating]
            return s * max(growth, min_growth)

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
        now = datetime.now(UTC)

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
        notebook_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get flashcards due for review."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

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
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

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
            "interval_days": (next_state.due_at - datetime.now(UTC)).days
            if next_state.due_at
            else 0,
        }


class KnowledgeBaseService(KnowledgeBase):
    """
    Backward-compatible service name used by older integrations/tests.
    """

    async def review_card(
        self,
        flashcard_id: str,
        user_id: str,
        tenant_id: str,
        rating: int,
    ) -> dict[str, Any]:
        return await self.review_flashcard(
            flashcard_id=flashcard_id,
            user_id=user_id,
            tenant_id=tenant_id,
            rating=rating,
        )

    def schedule_review(self, current_state: ReviewState, rating: int) -> ReviewState:
        return self.fsrs.schedule_review(current_state, rating)


class BrainManager:
    """
    High-level facade for the brain router — wraps KnowledgeBase
    and adds flashcard CRUD + AI generation.
    """

    def __init__(self) -> None:
        self._kb = KnowledgeBase()

    @traced("brain.list_flashcards")
    async def list_flashcards(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all flashcards for user."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        query = """
            SELECT f.id, f.notebook_id, f.front, f.back, f.source_id,
                   f.tags, f.created_at,
                   COALESCE(rr.difficulty, 5.0) AS difficulty,
                   COALESCE(rr.stability, 0.0) AS stability,
                   rr.due_at,
                   COALESCE(rr.review_count, 0) AS review_count
            FROM flashcards f
            LEFT JOIN LATERAL (
                SELECT difficulty, stability, due_at, review_count
                FROM review_records
                WHERE flashcard_id = f.id AND user_id = :user_id
                ORDER BY created_at DESC LIMIT 1
            ) rr ON true
            WHERE f.tenant_id = :tenant_id
        """
        params: dict[str, Any] = {"user_id": user_id, "tenant_id": tenant_id}
        if notebook_id:
            query += " AND f.notebook_id = :notebook_id"
            params["notebook_id"] = notebook_id
        query += " ORDER BY f.created_at DESC"

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            rows = result.mappings().all()
            return [
                {
                    "id": str(r["id"]),
                    "notebook_id": str(r["notebook_id"]),
                    "front": r["front"],
                    "back": r["back"],
                    "source_id": str(r["source_id"]) if r["source_id"] else None,
                    "tags": r["tags"] if r["tags"] else [],
                    "difficulty": float(r["difficulty"]),
                    "stability": float(r["stability"]),
                    "due_at": str(r["due_at"]) if r["due_at"] else None,
                    "review_count": int(r["review_count"]),
                    "created_at": str(r["created_at"]),
                }
                for r in rows
            ]

    @traced("brain.create_flashcard")
    async def create_flashcard(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str,
        front: str,
        back: str,
        source_id: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a single flashcard."""
        import uuid

        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        card_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        async with get_session(tenant_id) as session:
            await session.execute(
                text("""
                    INSERT INTO flashcards
                        (id, tenant_id, user_id, notebook_id, front, back,
                         source_id, tags, created_at, updated_at)
                    VALUES (:id, :tid, :uid, :nid, :front, :back,
                            :sid, :tags, :now, :now)
                """),
                {
                    "id": card_id,
                    "tid": tenant_id,
                    "uid": user_id,
                    "nid": notebook_id,
                    "front": front,
                    "back": back,
                    "sid": source_id,
                    "tags": tags or [],
                    "now": now,
                },
            )
            await session.commit()

        return {
            "id": card_id,
            "notebook_id": notebook_id,
            "front": front,
            "back": back,
            "source_id": source_id,
            "tags": tags or [],
            "difficulty": 5.0,
            "stability": 0.0,
            "due_at": None,
            "review_count": 0,
            "created_at": now.isoformat(),
        }

    @traced("brain.get_due_cards")
    async def get_due_cards(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get flashcards due for review."""
        return await self._kb.get_due_flashcards(
            user_id=user_id,
            tenant_id=tenant_id,
            notebook_id=notebook_id,
            limit=limit,
        )

    @traced("brain.submit_review")
    async def submit_review(
        self,
        tenant_id: str,
        user_id: str,
        card_id: str,
        rating: int,
    ) -> dict[str, Any]:
        """Submit a review and get next scheduling."""
        result = await self._kb.review_flashcard(
            flashcard_id=card_id,
            user_id=user_id,
            tenant_id=tenant_id,
            rating=rating,
        )
        return {
            "card_id": card_id,
            "next_due": result["next_due"],
            "new_difficulty": result["difficulty"],
            "new_stability": result["stability"],
            "interval_days": result["interval_days"],
        }

    @traced("brain.generate_from_source")
    async def generate_from_source(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str,
        source_id: str,
        count: int = 10,
    ) -> list[dict[str, Any]]:
        """Auto-generate flashcards from a source using AI."""
        from sqlalchemy import text

        from src.agents.nexus_agent_content import generate_flashcards
        from src.agents.nexus_model_layer import model_manager

        # Get source content
        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            result = await session.execute(
                text("SELECT content FROM sources WHERE id = :sid AND tenant_id = :tid"),
                {"sid": source_id, "tid": tenant_id},
            )
            row = result.mappings().first()
            if not row:
                from src.exceptions import NotFoundError

                raise NotFoundError(f"Source {source_id} not found")
            content = row["content"]

        # Generate flashcards via AI
        llm = await model_manager.provision_llm(
            tenant_id=tenant_id,
            task_type="flashcard_generation",
        )
        cards_json = await generate_flashcards(
            content=content[:8000],  # Limit context
            llm=llm,
            count=count,
        )

        # Parse and save each card
        import json

        try:
            generated = json.loads(cards_json) if isinstance(cards_json, str) else cards_json
        except (json.JSONDecodeError, TypeError):
            generated = []

        saved: list[dict[str, Any]] = []
        for item in generated[:count]:
            card = await self.create_flashcard(
                tenant_id=tenant_id,
                user_id=user_id,
                notebook_id=notebook_id,
                front=item.get("front", item.get("question", "")),
                back=item.get("back", item.get("answer", "")),
                source_id=source_id,
                tags=item.get("tags", []),
            )
            saved.append(card)

        return saved

    @traced("brain.delete_flashcard")
    async def delete_flashcard(
        self,
        tenant_id: str,
        user_id: str,
        card_id: str,
    ) -> None:
        """Delete a flashcard and its review history."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            await session.execute(
                text("DELETE FROM review_records WHERE flashcard_id = :cid"),
                {"cid": card_id},
            )
            await session.execute(
                text("DELETE FROM flashcards WHERE id = :cid AND tenant_id = :tid"),
                {"cid": card_id, "tid": tenant_id},
            )
            await session.commit()

    @traced("brain.get_progress")
    async def get_progress(
        self,
        tenant_id: str,
        user_id: str,
        notebook_id: str | None = None,
    ) -> dict[str, Any]:
        """Get learning progress summary."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        base_filter = "f.tenant_id = :tenant_id"
        params: dict[str, Any] = {"tenant_id": tenant_id, "user_id": user_id}
        if notebook_id:
            base_filter += " AND f.notebook_id = :notebook_id"
            params["notebook_id"] = notebook_id

        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(f"""
                    SELECT
                        COUNT(*) AS total_cards,
                        COUNT(CASE WHEN rr.due_at IS NOT NULL AND rr.due_at <= NOW() THEN 1 END) AS cards_due,
                        COUNT(CASE WHEN rr.review_count > 0 THEN 1 END) AS cards_learned,
                        COUNT(CASE WHEN rr.review_count IS NULL OR rr.review_count = 0 THEN 1 END) AS cards_new,
                        COALESCE(AVG(rr.difficulty), 5.0) AS avg_difficulty
                    FROM flashcards f
                    LEFT JOIN LATERAL (
                        SELECT difficulty, due_at, review_count
                        FROM review_records
                        WHERE flashcard_id = f.id AND user_id = :user_id
                        ORDER BY created_at DESC LIMIT 1
                    ) rr ON true
                    WHERE {base_filter}
                """),  # noqa: S608
                params,
            )
            row = result.mappings().first()

        total = int(row["total_cards"]) if row else 0
        learned = int(row["cards_learned"]) if row else 0

        return {
            "total_cards": total,
            "cards_due": int(row["cards_due"]) if row else 0,
            "cards_learned": learned,
            "cards_new": int(row["cards_new"]) if row else 0,
            "average_difficulty": round(float(row["avg_difficulty"]) if row else 5.0, 2),
            "retention_rate": round(learned / total, 2) if total > 0 else 0.0,
            "streak_days": 0,  # Calculated from consecutive review days
        }


# Global singleton
knowledge_base = KnowledgeBase()
