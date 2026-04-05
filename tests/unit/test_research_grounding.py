"""
Unit Tests — Nexus Research Grounding (Research Graph, Profiles, Checkpoints)
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.nexus_research_grounding import (
    PROFILE_SETTINGS,
    CheckpointStore,
    ResearchCheckpoint,
    ResearchGraph,
    ResearchPhase,
    ResearchProfile,
    ResearchTurn,
    SourceReference,
)

# ── ResearchPhase Enum ──────────────────────────────────────


class TestResearchPhase:
    def test_research_phase_enum(self):
        assert ResearchPhase.UNDERSTAND == "understand"
        assert ResearchPhase.RETRIEVE == "retrieve"
        assert ResearchPhase.ANALYZE == "analyze"
        assert ResearchPhase.SYNTHESIZE == "synthesize"
        assert ResearchPhase.SUGGEST == "suggest"
        assert ResearchPhase.COMPLETE == "complete"

    def test_research_phase_count(self):
        assert len(ResearchPhase) == 6

    def test_research_phase_from_value(self):
        assert ResearchPhase("understand") is ResearchPhase.UNDERSTAND


# ── ResearchProfile Enum ────────────────────────────────────


class TestResearchProfile:
    def test_research_profile_enum(self):
        assert ResearchProfile.QUICK == "quick"
        assert ResearchProfile.STANDARD == "standard"
        assert ResearchProfile.DEEP == "deep"
        assert ResearchProfile.AUTO == "auto"

    def test_research_profile_count(self):
        assert len(ResearchProfile) == 4


# ── PROFILE_SETTINGS ────────────────────────────────────────


class TestProfileSettings:
    def test_profile_settings_keys(self):
        for profile in ResearchProfile:
            assert profile in PROFILE_SETTINGS, f"Missing settings for {profile}"

    def test_profile_settings_quick(self):
        quick = PROFILE_SETTINGS[ResearchProfile.QUICK]
        assert quick["search_query_limit"] == 2
        assert quick["retrieve_limit"] == 5
        assert quick["follow_up_count"] == 2

    def test_profile_settings_standard(self):
        std = PROFILE_SETTINGS[ResearchProfile.STANDARD]
        assert std["search_query_limit"] == 4
        assert std["retrieve_limit"] == 10
        assert std["follow_up_count"] == 3

    def test_profile_settings_deep(self):
        deep = PROFILE_SETTINGS[ResearchProfile.DEEP]
        assert deep["search_query_limit"] == 6
        assert deep["retrieve_limit"] == 16
        assert deep["follow_up_count"] == 5

    def test_profile_settings_deep_higher_than_quick(self):
        quick = PROFILE_SETTINGS[ResearchProfile.QUICK]
        deep = PROFILE_SETTINGS[ResearchProfile.DEEP]
        assert deep["search_query_limit"] > quick["search_query_limit"]
        assert deep["retrieve_limit"] > quick["retrieve_limit"]
        assert deep["synthesis_max_tokens"] > quick["synthesis_max_tokens"]
        assert deep["context_chars_per_chunk"] > quick["context_chars_per_chunk"]

    def test_profile_search_query_limit(self):
        """search_query_limit differs between QUICK and DEEP."""
        q = PROFILE_SETTINGS[ResearchProfile.QUICK]["search_query_limit"]
        d = PROFILE_SETTINGS[ResearchProfile.DEEP]["search_query_limit"]
        assert q != d

    def test_profile_follow_up_count(self):
        """follow_up_count differs between QUICK and DEEP."""
        q = PROFILE_SETTINGS[ResearchProfile.QUICK]["follow_up_count"]
        d = PROFILE_SETTINGS[ResearchProfile.DEEP]["follow_up_count"]
        assert q < d

    def test_profile_settings_all_have_required_keys(self):
        required = {
            "search_query_limit",
            "retrieve_limit",
            "context_chars_per_chunk",
            "synthesis_max_tokens",
            "follow_up_count",
        }
        for profile, settings in PROFILE_SETTINGS.items():
            assert required.issubset(settings.keys()), (
                f"{profile} missing keys: {required - settings.keys()}"
            )


# ── SourceReference ─────────────────────────────────────────


class TestSourceReference:
    def test_source_reference_init(self):
        ref = SourceReference(
            source_id="src-1",
            source_title="My Paper",
            chunk_index=3,
            content_preview="First 250 chars...",
            relevance_score=0.87,
        )
        assert ref.source_id == "src-1"
        assert ref.source_title == "My Paper"
        assert ref.chunk_index == 3
        assert ref.content_preview == "First 250 chars..."
        assert ref.relevance_score == 0.87

    def test_source_reference_consulted_at_default(self):
        before = time.time()
        ref = SourceReference(
            source_id="s",
            source_title="t",
            chunk_index=0,
            content_preview="",
            relevance_score=0.0,
        )
        after = time.time()
        assert before <= ref.consulted_at <= after


# ── ResearchTurn ────────────────────────────────────────────


class TestResearchTurn:
    def test_research_turn_defaults(self):
        turn = ResearchTurn(
            turn_id="t1",
            query="What is X?",
            answer="X is ...",
            phase=ResearchPhase.COMPLETE,
        )
        assert turn.sources_consulted == []
        assert turn.follow_up_questions == []
        assert turn.model_used == ""
        assert turn.input_tokens == 0
        assert turn.output_tokens == 0
        assert turn.latency_ms == 0.0


# ── ResearchCheckpoint ──────────────────────────────────────


class TestResearchCheckpoint:
    def test_research_checkpoint_init(self):
        cp = ResearchCheckpoint(
            session_id="sess-1",
            notebook_id="nb-1",
            tenant_id="t-1",
            user_id="u-1",
        )
        assert cp.session_id == "sess-1"
        assert cp.turns == []
        assert cp.accumulated_context == {}
        assert cp.source_ids_consulted == set()
        assert cp.current_phase == ResearchPhase.UNDERSTAND
        assert cp.total_tokens == 0
        assert cp.total_cost_usd == 0.0

    def test_research_checkpoint_defaults(self):
        cp = ResearchCheckpoint()
        assert cp.session_id == ""
        assert cp.notebook_id == ""
        assert cp.title == ""

    def test_research_checkpoint_to_dict(self):
        cp = ResearchCheckpoint(session_id="s1", tenant_id="t1", user_id="u1")
        d = cp.to_dict()
        assert d["session_id"] == "s1"
        assert d["tenant_id"] == "t1"
        assert d["current_phase"] == "understand"
        assert isinstance(d["turns"], list)
        assert isinstance(d["source_ids_consulted"], list)

    def test_research_checkpoint_roundtrip(self):
        """to_dict → from_dict should preserve data."""
        cp = ResearchCheckpoint(
            session_id="rt-1",
            notebook_id="nb",
            tenant_id="t",
            user_id="u",
            title="test roundtrip",
            total_tokens=500,
            total_cost_usd=0.01,
        )
        turn = ResearchTurn(
            turn_id="t1",
            query="q?",
            answer="a.",
            phase=ResearchPhase.COMPLETE,
            follow_up_questions=["follow?"],
            model_used="gpt-4o",
            input_tokens=100,
            output_tokens=200,
        )
        turn.sources_consulted.append(
            SourceReference(
                source_id="s1",
                source_title="Paper A",
                chunk_index=0,
                content_preview="preview",
                relevance_score=0.9,
            )
        )
        cp.turns.append(turn)
        cp.source_ids_consulted.add("s1")

        d = cp.to_dict()
        restored = ResearchCheckpoint.from_dict(d)

        assert restored.session_id == "rt-1"
        assert restored.title == "test roundtrip"
        assert restored.total_tokens == 500
        assert len(restored.turns) == 1
        assert restored.turns[0].query == "q?"
        assert restored.turns[0].model_used == "gpt-4o"
        assert len(restored.turns[0].sources_consulted) == 1
        assert restored.turns[0].sources_consulted[0].source_title == "Paper A"
        assert "s1" in restored.source_ids_consulted

    def test_research_checkpoint_from_dict_minimal(self):
        data = {
            "session_id": "min",
            "turns": [],
        }
        cp = ResearchCheckpoint.from_dict(data)
        assert cp.session_id == "min"
        assert cp.notebook_id == ""
        assert cp.turns == []


# ── ResearchGraph ───────────────────────────────────────────


class TestResearchGraph:
    def test_research_graph_init(self):
        graph = ResearchGraph()
        assert isinstance(graph.checkpoint_store, CheckpointStore)

    @pytest.mark.asyncio
    @patch("src.core.nexus_research_grounding.cost_tracker")
    async def test_execute_turn_calls_pipeline(self, mock_cost_tracker):
        """execute_turn wires through all 5 phases and returns expected keys."""
        graph = ResearchGraph()

        mock_cost_tracker.record_usage = AsyncMock()

        mock_checkpoint_store = MagicMock()
        mock_checkpoint_store.load = AsyncMock(return_value=None)
        mock_checkpoint_store.save = AsyncMock()
        graph.checkpoint_store = mock_checkpoint_store

        graph._understand = AsyncMock(
            return_value={
                "core_question": "test",
                "search_terms": ["test"],
                "depth": "standard",
            }
        )
        graph._retrieve = AsyncMock(
            return_value={
                "context": "some context",
                "references": [],
            }
        )
        graph._analyze = AsyncMock(return_value="analyzed context")
        graph._synthesize = AsyncMock(
            return_value=(
                "The answer is 42.",
                "gpt-4o",
                {"input": 100, "output": 50, "cost": 0.005},
            )
        )
        graph._suggest_follow_ups = AsyncMock(return_value=["Why 42?"])

        result = await graph.execute_turn(
            query="What is the meaning?",
            notebook_id="nb-1",
            tenant_id="t-1",
            user_id="u-1",
        )

        assert "session_id" in result
        assert result["answer"] == "The answer is 42."
        assert result["model_used"] == "gpt-4o"
        assert result["follow_up_questions"] == ["Why 42?"]
        assert result["total_turns"] == 1
        mock_checkpoint_store.save.assert_awaited_once()
        mock_cost_tracker.record_usage.assert_awaited_once()
