"""Unit tests for hybrid retrieval fusion (RRF)."""

from __future__ import annotations

from src.core.hybrid_search import get_search_profile, reciprocal_rank_fusion


class TestHybridSearch:
    def test_get_search_profile_defaults_to_balanced(self):
        profile = get_search_profile("unknown-profile")
        assert profile.candidate_multiplier == 3
        assert profile.vector_weight == 1.15

    def test_rrf_merges_and_ranks_deduplicated_results(self):
        vector_results = [
            {"source_id": "s1", "content": "alpha"},
            {"source_id": "s2", "content": "beta"},
        ]
        text_results = [
            {"id": "s2", "title": "beta"},
            {"id": "s3", "title": "gamma"},
        ]

        merged = reciprocal_rank_fusion(
            vector_results=vector_results,
            text_results=text_results,
            limit=10,
            k=60,
            vector_weight=1.0,
            text_weight=1.0,
        )

        ids = [item.get("source_id") or item.get("id") for item in merged]
        assert len(ids) == 3
        assert ids[0] == "s2"

    def test_rrf_respects_limit(self):
        vector_results = [{"source_id": "a"}, {"source_id": "b"}, {"source_id": "c"}]
        text_results: list[dict[str, str]] = []

        merged = reciprocal_rank_fusion(
            vector_results=vector_results,
            text_results=text_results,
            limit=2,
            k=60,
        )

        assert len(merged) == 2

    def test_rrf_skips_items_without_source_or_id(self) -> None:
        """Empty identifier upsert path (early return in fusion)."""
        merged = reciprocal_rank_fusion(
            vector_results=[{"content": "orphan"}],
            text_results=[],
            limit=5,
            k=60,
        )
        assert merged == []
