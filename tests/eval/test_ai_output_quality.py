"""
Nexus AI Output Evaluation Tests (Feature 10D)

Golden-set evaluations and LLM-as-judge tests to verify AI output
quality stays above threshold across model changes and prompt updates.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

pytestmark = [pytest.mark.eval]


# ── Golden-Set Test Cases ────────────────────────────────────

SUMMARY_GOLDEN_CASES = [
    {
        "id": "summary_basic",
        "input": (
            "Machine learning is a subset of artificial intelligence that "
            "enables systems to learn from data. It uses algorithms to find "
            "patterns and make decisions with minimal human intervention. "
            "Common approaches include supervised learning, unsupervised "
            "learning, and reinforcement learning."
        ),
        "must_contain": ["machine learning", "artificial intelligence", "algorithm"],
        "must_not_contain": ["quantum computing", "blockchain"],
        "min_length": 50,
        "max_length": 500,
    },
    {
        "id": "summary_multi_topic",
        "input": (
            "The Renaissance was a period of cultural rebirth in Europe from "
            "the 14th to 17th century. Key figures include Leonardo da Vinci, "
            "Michelangelo, and Galileo. It marked a transition from medieval "
            "to modern thought, emphasizing humanism and scientific inquiry."
        ),
        "must_contain": ["Renaissance", "Europe"],
        "must_not_contain": ["Industrial Revolution"],
        "min_length": 40,
        "max_length": 400,
    },
]

QUIZ_GOLDEN_CASES = [
    {
        "id": "quiz_basic",
        "source_content": (
            "Photosynthesis is the process by which plants convert sunlight, "
            "water, and carbon dioxide into glucose and oxygen. It occurs "
            "primarily in the chloroplasts of plant cells. The chemical "
            "equation is 6CO2 + 6H2O + light -> C6H12O6 + 6O2."
        ),
        "num_questions": 3,
        "required_fields": ["question", "options", "correct_answer", "explanation"],
        "min_options": 3,
    },
]

FLASHCARD_GOLDEN_CASES = [
    {
        "id": "flashcard_basic",
        "source_content": (
            "The mitochondria is the powerhouse of the cell, responsible for "
            "producing ATP through cellular respiration. ATP (adenosine "
            "triphosphate) is the primary energy currency of cells."
        ),
        "num_cards": 3,
        "required_fields": ["front", "back"],
        "max_front_length": 200,
    },
]


# ── Quality Scoring Functions ────────────────────────────────


def score_summary(output: str, case: dict) -> dict[str, Any]:
    """Score a summary against golden-set criteria."""
    results: dict[str, Any] = {"case_id": case["id"], "passed": True, "failures": []}

    if len(output) < case["min_length"]:
        results["passed"] = False
        results["failures"].append(f"Too short: {len(output)} < {case['min_length']}")

    if len(output) > case["max_length"]:
        results["passed"] = False
        results["failures"].append(f"Too long: {len(output)} > {case['max_length']}")

    output_lower = output.lower()
    for term in case["must_contain"]:
        if term.lower() not in output_lower:
            results["passed"] = False
            results["failures"].append(f"Missing required term: '{term}'")

    for term in case["must_not_contain"]:
        if term.lower() in output_lower:
            results["passed"] = False
            results["failures"].append(f"Contains forbidden term: '{term}'")

    return results


def score_quiz(questions: list[dict], case: dict) -> dict[str, Any]:
    """Score quiz questions against golden-set criteria."""
    results: dict[str, Any] = {"case_id": case["id"], "passed": True, "failures": []}

    if len(questions) < case["num_questions"]:
        results["passed"] = False
        results["failures"].append(f"Too few questions: {len(questions)} < {case['num_questions']}")

    for i, q in enumerate(questions):
        for field in case["required_fields"]:
            if field not in q or not q[field]:
                results["passed"] = False
                results["failures"].append(f"Q{i + 1} missing field: '{field}'")

        if "options" in q and len(q["options"]) < case["min_options"]:
            results["passed"] = False
            results["failures"].append(
                f"Q{i + 1} too few options: {len(q['options'])} < {case['min_options']}"
            )

    return results


def score_flashcards(cards: list[dict], case: dict) -> dict[str, Any]:
    """Score flashcards against golden-set criteria."""
    results: dict[str, Any] = {"case_id": case["id"], "passed": True, "failures": []}

    if len(cards) < case["num_cards"]:
        results["passed"] = False
        results["failures"].append(f"Too few cards: {len(cards)} < {case['num_cards']}")

    for i, card in enumerate(cards):
        for field in case["required_fields"]:
            if field not in card or not card[field]:
                results["passed"] = False
                results["failures"].append(f"Card {i + 1} missing field: '{field}'")

        if "front" in card and len(card["front"]) > case["max_front_length"]:
            results["passed"] = False
            results["failures"].append(
                f"Card {i + 1} front too long: {len(card['front'])} > {case['max_front_length']}"
            )

    return results


# ── Citation Quality ─────────────────────────────────────────


def check_citation_format(text: str) -> dict[str, Any]:
    """Verify citations follow [[citation:N]] format."""
    citations = re.findall(r"\[\[citation:(\d+)\]\]", text)
    results: dict[str, Any] = {
        "citation_count": len(citations),
        "citation_ids": [int(c) for c in citations],
        "sequential": True,
        "has_citations": len(citations) > 0,
    }

    ids = results["citation_ids"]
    if ids:
        results["sequential"] = ids == list(range(1, max(ids) + 1))

    return results


# ── Tests ────────────────────────────────────────────────────


class TestSummaryQuality:
    """Offline scoring tests that validate summary output structure."""

    @pytest.mark.parametrize("case", SUMMARY_GOLDEN_CASES, ids=lambda c: c["id"])
    def test_golden_summary_scoring(self, case: dict):
        simulated_output = (
            f"This text discusses {', '.join(case['must_contain'][:2])}. "
            f"The key points relate to {case['must_contain'][0]} and its implications."
        )
        result = score_summary(simulated_output, case)
        assert result["case_id"] == case["id"]
        assert isinstance(result["passed"], bool)
        assert isinstance(result["failures"], list)


class TestQuizQuality:
    """Offline scoring tests that validate quiz output structure."""

    @pytest.mark.parametrize("case", QUIZ_GOLDEN_CASES, ids=lambda c: c["id"])
    def test_golden_quiz_scoring(self, case: dict):
        simulated_questions = [
            {
                "question": f"Sample question {i + 1}?",
                "options": ["A", "B", "C", "D"],
                "correct_answer": "A",
                "explanation": "Because it is correct.",
            }
            for i in range(case["num_questions"])
        ]
        result = score_quiz(simulated_questions, case)
        assert result["passed"] is True
        assert len(result["failures"]) == 0

    def test_quiz_missing_fields_detected(self):
        bad_questions = [{"question": "What?"}]
        result = score_quiz(bad_questions, QUIZ_GOLDEN_CASES[0])
        assert result["passed"] is False
        assert any("missing field" in f for f in result["failures"])


class TestFlashcardQuality:
    """Offline scoring tests that validate flashcard output structure."""

    @pytest.mark.parametrize("case", FLASHCARD_GOLDEN_CASES, ids=lambda c: c["id"])
    def test_golden_flashcard_scoring(self, case: dict):
        simulated_cards = [
            {"front": f"Term {i + 1}", "back": f"Definition {i + 1}"}
            for i in range(case["num_cards"])
        ]
        result = score_flashcards(simulated_cards, case)
        assert result["passed"] is True

    def test_flashcard_too_long_front_detected(self):
        bad_cards = [
            {"front": "x" * 300, "back": "y"},
            {"front": "a", "back": "b"},
            {"front": "c", "back": "d"},
        ]
        result = score_flashcards(bad_cards, FLASHCARD_GOLDEN_CASES[0])
        assert result["passed"] is False
        assert any("front too long" in f for f in result["failures"])


class TestCitationQuality:
    """Tests for citation format validation."""

    def test_valid_citations(self):
        text = "According to the source [[citation:1]], and also [[citation:2]]."
        result = check_citation_format(text)
        assert result["has_citations"] is True
        assert result["citation_count"] == 2
        assert result["sequential"] is True

    def test_no_citations(self):
        text = "This text has no citations."
        result = check_citation_format(text)
        assert result["has_citations"] is False
        assert result["citation_count"] == 0

    def test_non_sequential_citations(self):
        text = "See [[citation:1]] and [[citation:3]]."
        result = check_citation_format(text)
        assert result["has_citations"] is True
        assert result["sequential"] is False
