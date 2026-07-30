"""Hybrid retrieval helpers using Reciprocal Rank Fusion (RRF)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SearchProfile:
    """Runtime tuning parameters for retrieval quality vs latency."""

    candidate_multiplier: int
    vector_weight: float
    text_weight: float


SEARCH_PROFILES: dict[str, SearchProfile] = {
    "fast": SearchProfile(candidate_multiplier=2, vector_weight=1.0, text_weight=1.0),
    "balanced": SearchProfile(candidate_multiplier=3, vector_weight=1.15, text_weight=1.0),
    "deep": SearchProfile(candidate_multiplier=5, vector_weight=1.25, text_weight=1.0),
}


def get_search_profile(name: str) -> SearchProfile:
    """Return a valid search profile, defaulting to balanced."""
    return SEARCH_PROFILES.get(name, SEARCH_PROFILES["balanced"])


def reciprocal_rank_fusion(
    *,
    vector_results: list[dict[str, Any]],
    text_results: list[dict[str, Any]],
    limit: int,
    k: int = 60,
    vector_weight: float = 1.0,
    text_weight: float = 1.0,
) -> list[dict[str, Any]]:
    """
    Merge ranked lists with Reciprocal Rank Fusion.

    Score formula:
        score = sum(weight / (k + rank))
    where rank starts at 1 for each ranked list.
    """
    merged: dict[str, dict[str, Any]] = {}

    def upsert(
        item: dict[str, Any],
        *,
        rank: int,
        weight: float,
        source: str,
    ) -> None:
        item_id = str(item.get("source_id") or item.get("id") or "")
        if not item_id:
            return

        if item_id not in merged:
            merged[item_id] = dict(item)
            merged[item_id]["id"] = item.get("id") or item_id
            merged[item_id]["source_id"] = item.get("source_id") or item_id
            merged[item_id]["retrieval"] = {
                "vector_rank": None,
                "text_rank": None,
                "rrf_score": 0.0,
            }

        score_delta = weight / (k + rank)
        merged[item_id]["retrieval"]["rrf_score"] += score_delta
        if source == "vector":
            merged[item_id]["retrieval"]["vector_rank"] = rank
        else:
            merged[item_id]["retrieval"]["text_rank"] = rank

    for idx, row in enumerate(vector_results):
        upsert(row, rank=idx + 1, weight=vector_weight, source="vector")

    for idx, row in enumerate(text_results):
        upsert(row, rank=idx + 1, weight=text_weight, source="text")

    ranked = sorted(
        merged.values(),
        key=lambda item: item["retrieval"]["rrf_score"],
        reverse=True,
    )
    return ranked[:limit]
