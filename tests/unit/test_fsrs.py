"""
Unit Tests — FSRS-4.5 Spaced Repetition Algorithm
Verifies the core scheduling math independently of any database.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from src.core.nexus_brain_knowledge import FSRSScheduler, ReviewState


class TestFSRSScheduler:
    """Test the FSRS-4.5 scheduling algorithm."""

    def setup_method(self):
        self.scheduler = FSRSScheduler()

    def test_init_difficulty_good(self):
        """Initial difficulty for 'good' rating should be moderate."""
        d = self.scheduler.init_difficulty(3)  # good
        assert 1.0 <= d <= 10.0

    def test_init_difficulty_easy(self):
        """Easy rating should produce lower difficulty."""
        d_easy = self.scheduler.init_difficulty(4)
        d_hard = self.scheduler.init_difficulty(2)
        assert d_easy < d_hard

    def test_init_stability_increases_with_rating(self):
        """Higher rating → higher initial stability."""
        s1 = self.scheduler.init_stability(1)  # again
        s3 = self.scheduler.init_stability(3)  # good
        assert s3 > s1

    def test_next_interval_positive(self):
        """Next interval must always be positive."""
        for s in [0.1, 1.0, 5.0, 30.0, 365.0]:
            interval = self.scheduler.next_interval(s)
            assert interval >= 1.0

    def test_retrievability_decreases(self):
        """Retrievability decreases over time."""
        r_day1 = self.scheduler.retrievability(10.0, 1.0)
        r_day7 = self.scheduler.retrievability(10.0, 7.0)
        r_day30 = self.scheduler.retrievability(10.0, 30.0)
        assert r_day1 > r_day7 > r_day30

    def test_retrievability_perfect_at_zero(self):
        """Retrievability should be ~1.0 immediately after review."""
        r = self.scheduler.retrievability(10.0, 0.0)
        assert r == pytest.approx(1.0, abs=0.01)

    def test_schedule_new_card_good(self):
        """Scheduling a new card with 'good' should move to review state."""
        state = ReviewState(
            difficulty=0, stability=0, retrievability=1.0,
            state=0, review_count=0, lapses=0,
        )
        result = self.scheduler.schedule_review(state, rating=3)  # good

        assert result.state == 2  # review
        assert result.review_count == 1
        assert result.stability > 0
        assert result.due_at is not None

    def test_schedule_new_card_again(self):
        """Scheduling a new card with 'again' should go to learning."""
        state = ReviewState(
            difficulty=0, stability=0, retrievability=1.0,
            state=0, review_count=0, lapses=0,
        )
        result = self.scheduler.schedule_review(state, rating=1)  # again

        assert result.state == 1  # learning
        assert result.review_count == 1

    def test_schedule_review_card_good(self):
        """Good rating on review card should extend interval."""
        state = ReviewState(
            difficulty=5.0, stability=10.0, retrievability=0.9,
            state=2, review_count=5, lapses=0,
            due_at=datetime.now(timezone.utc),
        )
        result = self.scheduler.schedule_review(state, rating=3)

        assert result.stability > state.stability
        assert result.due_at > datetime.now(timezone.utc)

    def test_schedule_review_card_again_increases_lapses(self):
        """'Again' rating should increment lapses."""
        state = ReviewState(
            difficulty=5.0, stability=10.0, retrievability=0.9,
            state=2, review_count=5, lapses=2,
            due_at=datetime.now(timezone.utc),
        )
        result = self.scheduler.schedule_review(state, rating=1)

        assert result.lapses == 3
        assert result.state == 3  # relearning

    def test_difficulty_bounded(self):
        """Difficulty should stay within [1, 10]."""
        # Push difficulty high
        d = self.scheduler.next_difficulty(9.5, 1)  # again
        assert d <= 10.0

        # Push difficulty low
        d = self.scheduler.next_difficulty(1.5, 4)  # easy
        assert d >= 1.0

    def test_stability_never_negative(self):
        """Stability must never go negative."""
        s = self.scheduler.next_stability(10.0, 0.5, 0.1, 1)
        assert s >= 0.1


class TestFSRSIntegration:
    """Test realistic review sequences."""

    def test_full_review_sequence(self):
        """Simulate a card being reviewed over multiple sessions."""
        scheduler = FSRSScheduler()
        state = ReviewState(
            difficulty=0, stability=0, retrievability=1.0,
            state=0, review_count=0, lapses=0,
        )

        # First review: good
        state = scheduler.schedule_review(state, 3)
        assert state.review_count == 1

        # Second review: good
        state = scheduler.schedule_review(state, 3)
        assert state.review_count == 2

        # Third review: easy
        state = scheduler.schedule_review(state, 4)
        assert state.review_count == 3

        # Interval should be getting longer
        assert state.stability > 5.0

    def test_lapse_recovery(self):
        """After a lapse, stability should recover with good reviews."""
        scheduler = FSRSScheduler()
        state = ReviewState(
            difficulty=5.0, stability=30.0, retrievability=0.9,
            state=2, review_count=10, lapses=0,
            due_at=datetime.now(timezone.utc),
        )

        # Lapse
        state = scheduler.schedule_review(state, 1)
        lapse_stability = state.stability
        assert state.lapses == 1

        # Recovery
        state = scheduler.schedule_review(state, 3)
        state = scheduler.schedule_review(state, 3)
        assert state.stability > lapse_stability
