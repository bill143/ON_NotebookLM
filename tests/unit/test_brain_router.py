"""Unit tests for brain router schemas and endpoint wiring."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.brain import (
    FlashcardCreate,
    FlashcardResponse,
    GenerateFlashcardsRequest,
    ProgressSummary,
    ReviewResponse,
    ReviewSubmit,
    router,
)


class TestSchemas:
    def test_flashcard_create_valid(self):
        fc = FlashcardCreate(
            notebook_id="nb-1", front="What is X?", back="Answer"
        )
        assert fc.notebook_id == "nb-1"
        assert fc.tags == []

    def test_flashcard_create_with_tags(self):
        fc = FlashcardCreate(
            notebook_id="nb-1",
            front="Q",
            back="A",
            tags=["math", "calculus"],
        )
        assert len(fc.tags) == 2

    def test_review_submit_valid_ratings(self):
        for rating in [1, 2, 3, 4]:
            rs = ReviewSubmit(card_id="c-1", rating=rating)
            assert rs.rating == rating

    def test_review_submit_invalid_rating(self):
        with pytest.raises(Exception):
            ReviewSubmit(card_id="c-1", rating=0)
        with pytest.raises(Exception):
            ReviewSubmit(card_id="c-1", rating=5)

    def test_generate_flashcards_defaults(self):
        req = GenerateFlashcardsRequest(
            notebook_id="nb-1", source_id="src-1"
        )
        assert req.count == 10

    def test_generate_flashcards_limits(self):
        with pytest.raises(Exception):
            GenerateFlashcardsRequest(
                notebook_id="nb-1", source_id="src-1", count=0
            )
        with pytest.raises(Exception):
            GenerateFlashcardsRequest(
                notebook_id="nb-1", source_id="src-1", count=51
            )

    def test_progress_summary(self):
        ps = ProgressSummary(
            total_cards=100,
            cards_due=5,
            cards_learned=80,
            cards_new=20,
            average_difficulty=4.5,
            retention_rate=0.85,
            streak_days=7,
        )
        assert ps.total_cards == 100
        assert ps.retention_rate == 0.85

    def test_review_response(self):
        rr = ReviewResponse(
            card_id="c-1",
            next_due="2026-04-20T00:00:00",
            new_difficulty=4.2,
            new_stability=12.5,
            interval_days=5.0,
        )
        assert rr.interval_days == 5.0


class TestRouterRegistration:
    def test_router_has_correct_prefix(self):
        assert router.prefix == "/brain"

    def test_router_has_routes(self):
        paths = [r.path for r in router.routes]
        expected = ["/brain/flashcards", "/brain/flashcards/due",
                    "/brain/flashcards/review", "/brain/flashcards/generate",
                    "/brain/progress"]
        for p in expected:
            assert p in paths, f"Missing route: {p}"

    def test_router_mounts_in_app(self):
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        client = TestClient(app, raise_server_exceptions=False)
        # Auth error (422) proves the route exists; 404 would mean it doesn't
        response = client.get("/api/v1/brain/flashcards")
        assert response.status_code in (401, 403, 422, 500)
