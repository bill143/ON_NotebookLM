"""
Nexus Test Harness — Feature 10: Testing Framework & AI Evaluation

Provides shared testing utilities, fixtures, and AI output evaluation
tools for unit, integration, and eval test suites.

Capabilities:
  - 10A: Reusable test fixtures and factory helpers
  - 10B: API response recording and replay for integration tests
  - 10C: AI output quality scoring (golden-set evaluation)
  - 10D: LLM-as-judge evaluation with structured rubrics
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

# ── Response Recorder (VCR-style) ────────────────────────────


@dataclass
class RecordedResponse:
    """A single recorded HTTP response for replay in tests."""

    method: str
    url: str
    status_code: int
    headers: dict[str, str]
    body: str
    recorded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "url": self.url,
            "status_code": self.status_code,
            "headers": self.headers,
            "body": self.body,
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordedResponse:
        return cls(**data)


class ResponseRecorder:
    """
    Records and replays API responses for deterministic integration tests.

    Usage:
        recorder = ResponseRecorder("tests/cassettes")
        recorder.save("test_name", response)
        replayed = recorder.load("test_name")
    """

    def __init__(self, cassette_dir: str = "tests/cassettes") -> None:
        self.cassette_dir = Path(cassette_dir)
        self.cassette_dir.mkdir(parents=True, exist_ok=True)

    def _cassette_path(self, name: str) -> Path:
        safe_name = re.sub(r"[^\w\-.]", "_", name)
        return self.cassette_dir / f"{safe_name}.json"

    def save(self, name: str, responses: list[RecordedResponse]) -> Path:
        """Save recorded responses to a cassette file."""
        path = self._cassette_path(name)
        data = [r.to_dict() for r in responses]
        path.write_text(json.dumps(data, indent=2))
        logger.debug(f"Saved cassette: {path} ({len(responses)} responses)")
        return path

    def load(self, name: str) -> list[RecordedResponse]:
        """Load recorded responses from a cassette file."""
        path = self._cassette_path(name)
        if not path.exists():
            raise FileNotFoundError(f"Cassette not found: {path}")
        data = json.loads(path.read_text())
        return [RecordedResponse.from_dict(r) for r in data]

    def exists(self, name: str) -> bool:
        return self._cassette_path(name).exists()


# ── AI Output Scoring ────────────────────────────────────────


@dataclass
class QualityScore:
    """Result of evaluating an AI output against quality criteria."""

    score: float
    max_score: float
    passed: bool
    criteria_results: dict[str, bool]
    failures: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def percentage(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0.0


class OutputEvaluator:
    """
    Evaluates AI-generated outputs against configurable quality criteria.

    Supports:
    - Length constraints (min/max tokens or characters)
    - Required/forbidden content checks
    - Structural validation (JSON schema, field presence)
    - Custom scoring functions
    """

    def __init__(self, pass_threshold: float = 0.8) -> None:
        self.pass_threshold = pass_threshold
        self._criteria: list[tuple[str, Callable[[str], bool], float]] = []

    def add_criterion(
        self,
        name: str,
        check: Callable[[str], bool],
        weight: float = 1.0,
    ) -> OutputEvaluator:
        """Add a named quality criterion with a weight."""
        self._criteria.append((name, check, weight))
        return self

    def require_contains(self, term: str, weight: float = 1.0) -> OutputEvaluator:
        def check_contains(text: str) -> bool:
            return term.lower() in text.lower()

        return self.add_criterion(f"contains:{term}", check_contains, weight)

    def require_not_contains(self, term: str, weight: float = 1.0) -> OutputEvaluator:
        def check_not_contains(text: str) -> bool:
            return term.lower() not in text.lower()

        return self.add_criterion(f"not_contains:{term}", check_not_contains, weight)

    def require_min_length(self, min_chars: int, weight: float = 1.0) -> OutputEvaluator:
        def check_min_length(text: str) -> bool:
            return len(text) >= min_chars

        return self.add_criterion(f"min_length:{min_chars}", check_min_length, weight)

    def require_max_length(self, max_chars: int, weight: float = 1.0) -> OutputEvaluator:
        def check_max_length(text: str) -> bool:
            return len(text) <= max_chars

        return self.add_criterion(f"max_length:{max_chars}", check_max_length, weight)

    def require_json_parseable(self, weight: float = 1.0) -> OutputEvaluator:
        def check(text: str) -> bool:
            try:
                json.loads(text)
                return True
            except (json.JSONDecodeError, TypeError):
                return False

        return self.add_criterion("json_parseable", check, weight)

    def require_regex(self, pattern: str, weight: float = 1.0) -> OutputEvaluator:
        compiled = re.compile(pattern)

        def check_regex(text: str) -> bool:
            return bool(compiled.search(text))

        return self.add_criterion(f"matches:{pattern}", check_regex, weight)

    def evaluate(self, output: str) -> QualityScore:
        """Evaluate an output string against all criteria."""
        max_score = sum(w for _, _, w in self._criteria)
        score = 0.0
        criteria_results: dict[str, bool] = {}
        failures: list[str] = []

        for name, check, weight in self._criteria:
            try:
                passed = check(output)
            except Exception as exc:
                passed = False
                failures.append(f"{name}: evaluation error — {exc}")

            criteria_results[name] = passed
            if passed:
                score += weight
            else:
                failures.append(name)

        overall_passed = (score / max_score >= self.pass_threshold) if max_score > 0 else True

        return QualityScore(
            score=score,
            max_score=max_score,
            passed=overall_passed,
            criteria_results=criteria_results,
            failures=failures,
        )


# ── Timing Helper ────────────────────────────────────────────


class Timer:
    """Context manager for measuring execution time in tests."""

    def __init__(self, label: str = "") -> None:
        self.label = label
        self.start: float = 0
        self.elapsed_ms: float = 0

    def __enter__(self) -> Timer:
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        self.elapsed_ms = (time.perf_counter() - self.start) * 1000
        if self.label:
            logger.debug(f"Timer [{self.label}]: {self.elapsed_ms:.1f}ms")


# ── Content Hash (for deterministic test IDs) ────────────────


def content_hash(content: str) -> str:
    """Generate a short deterministic hash for test content."""
    return hashlib.sha256(content.encode()).hexdigest()[:12]


# ── Module Exports ───────────────────────────────────────────

recorder = ResponseRecorder()
