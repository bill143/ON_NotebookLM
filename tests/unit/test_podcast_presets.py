"""Unit tests for podcast preset normalization and catalogs."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.podcast_presets import (
    normalize_podcast_config,
    podcast_preset_catalog,
    resolve_speakers,
    resolve_voice_map,
)


class TestPodcastPresets:
    def test_normalize_podcast_config_defaults(self):
        cfg = normalize_podcast_config({})
        assert cfg["format"] == "conversational"
        assert cfg["length"] == "medium"
        assert cfg["speaker_profile"] == "expert_student"
        assert cfg["speech_rate"] == pytest.approx(1.0)

    def test_normalize_podcast_config_rejects_invalid(self):
        with pytest.raises(ValidationError):
            normalize_podcast_config({"format": "unknown"})

    def test_speaker_and_voice_resolution(self):
        speakers = resolve_speakers("interviewer_guest")
        voice_map = resolve_voice_map("interviewer_guest")
        assert len(speakers) == 2
        assert "Person1" in voice_map
        assert "Person2" in voice_map

    def test_catalog_contains_expected_sections(self):
        catalog = podcast_preset_catalog()
        assert "default" in catalog
        assert "formats" in catalog
        assert "lengths" in catalog
        assert "speaker_profiles" in catalog
