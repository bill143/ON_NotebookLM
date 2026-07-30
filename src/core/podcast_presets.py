"""Podcast preset definitions and normalization helpers."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PodcastFormat = Literal[
    "deep_dive",
    "briefing",
    "debate",
    "critique",
    "conversational",
]
PodcastLength = Literal["short", "medium", "long", "longform"]
SpeakerProfile = Literal[
    "expert_student",
    "two_experts",
    "interviewer_guest",
    "debate_hosts",
    "storyteller_analyst",
]


DEFAULT_LANGUAGE = "English"


FORMAT_TO_TONE: dict[PodcastFormat, str] = {
    "deep_dive": "analytical and explanatory",
    "briefing": "clear and concise",
    "debate": "respectfully adversarial",
    "critique": "skeptical and evidence-focused",
    "conversational": "friendly and approachable",
}


FORMAT_TO_INSTRUCTIONS: dict[PodcastFormat, str] = {
    "deep_dive": "Prioritize nuance, definitions, and layered explanations.",
    "briefing": "Focus on key points and actionable takeaways quickly.",
    "debate": "Present competing viewpoints with rebuttals and synthesis.",
    "critique": "Stress-test claims, assumptions, and limitations.",
    "conversational": "Keep it lively, practical, and listener-friendly.",
}


SPEAKER_PROFILES: dict[SpeakerProfile, list[dict[str, str]]] = {
    "expert_student": [
        {"name": "Alex", "expertise": "Subject matter expert", "style": "analytical"},
        {"name": "Jordan", "expertise": "Curious learner", "style": "engaging"},
    ],
    "two_experts": [
        {"name": "Maya", "expertise": "Domain expert", "style": "insightful"},
        {"name": "Noah", "expertise": "Systems expert", "style": "precise"},
    ],
    "interviewer_guest": [
        {"name": "Riley", "expertise": "Interviewer and host", "style": "curious"},
        {"name": "Casey", "expertise": "Guest specialist", "style": "confident"},
    ],
    "debate_hosts": [
        {"name": "Taylor", "expertise": "Pro position", "style": "assertive"},
        {"name": "Avery", "expertise": "Counter position", "style": "critical"},
    ],
    "storyteller_analyst": [
        {"name": "Quinn", "expertise": "Narrative storyteller", "style": "warm"},
        {"name": "Blake", "expertise": "Technical analyst", "style": "structured"},
    ],
}


VOICE_MAPS: dict[SpeakerProfile, dict[str, str]] = {
    "expert_student": {"Person1": "alloy", "Person2": "nova"},
    "two_experts": {"Person1": "echo", "Person2": "onyx"},
    "interviewer_guest": {"Person1": "alloy", "Person2": "fable"},
    "debate_hosts": {"Person1": "onyx", "Person2": "nova"},
    "storyteller_analyst": {"Person1": "shimmer", "Person2": "echo"},
}


class PodcastGenerationConfig(BaseModel):
    """Validated podcast configuration inspired by NotebookLM/Podcastfy controls."""

    format: PodcastFormat = "conversational"
    length: PodcastLength = "medium"
    language: str = Field(default=DEFAULT_LANGUAGE, min_length=2, max_length=48)
    speaker_profile: SpeakerProfile = "expert_student"
    speech_rate: float = Field(default=1.0, ge=0.8, le=1.25)


def normalize_podcast_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Validate and normalize podcast config for persistence and generation."""
    cfg = PodcastGenerationConfig(**(raw or {}))
    return cfg.model_dump()


def resolve_speakers(profile: SpeakerProfile) -> list[dict[str, str]]:
    """Return canonical speaker templates for the selected profile."""
    return SPEAKER_PROFILES.get(profile, SPEAKER_PROFILES["expert_student"])


def resolve_voice_map(profile: SpeakerProfile) -> dict[str, str]:
    """Return default speaker-to-voice mapping for TTS synthesis."""
    return VOICE_MAPS.get(profile, VOICE_MAPS["expert_student"])


def podcast_preset_catalog() -> dict[str, Any]:
    """Expose preset metadata for API/UI consumers."""
    default_cfg = PodcastGenerationConfig().model_dump()
    return {
        "default": default_cfg,
        "formats": list(FORMAT_TO_TONE.keys()),
        "lengths": ["short", "medium", "long", "longform"],
        "speaker_profiles": list(SPEAKER_PROFILES.keys()),
        "languages_hint": ["English", "Spanish", "French", "German", "Portuguese"],
        "speech_rate_range": {"min": 0.8, "max": 1.25},
    }
