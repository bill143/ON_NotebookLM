"""Unit tests for nexus_agent_voice — dialogue parsing, TTS synthesis."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.nexus_agent_voice import (
    DialogueSegment,
    parse_dialogue,
    synthesize_dialogue,
    synthesize_single,
)

# ── DialogueSegment dataclass ────────────────────────────────


class TestDialogueSegment:
    def test_fields_exist(self):
        seg = DialogueSegment(speaker="Person1", text="Hello", speaker_index=1)
        assert seg.speaker == "Person1"
        assert seg.text == "Hello"
        assert seg.speaker_index == 1

    def test_different_speakers(self):
        seg = DialogueSegment(speaker="Person2", text="World", speaker_index=2)
        assert seg.speaker == "Person2"
        assert seg.speaker_index == 2


# ── parse_dialogue ───────────────────────────────────────────


class TestParseDialogue:
    def test_tagged_person1_person2(self):
        script = "<Person1>Hello there!</Person1><Person2>Hi back!</Person2>"
        segments = parse_dialogue(script)
        assert len(segments) == 2
        assert segments[0].speaker == "Person1"
        assert segments[0].text == "Hello there!"
        assert segments[0].speaker_index == 1
        assert segments[1].speaker == "Person2"
        assert segments[1].text == "Hi back!"
        assert segments[1].speaker_index == 2

    def test_tagged_with_whitespace(self):
        script = "<Person1>\n  Some content with whitespace  \n</Person1>"
        segments = parse_dialogue(script)
        assert len(segments) == 1
        assert segments[0].text == "Some content with whitespace"

    def test_tagged_empty_text_skipped(self):
        script = "<Person1></Person1><Person2>Only me</Person2>"
        segments = parse_dialogue(script)
        assert len(segments) == 1
        assert segments[0].speaker == "Person2"

    def test_tagged_multiline_content(self):
        script = "<Person1>Line one.\nLine two.\nLine three.</Person1>"
        segments = parse_dialogue(script)
        assert len(segments) == 1
        assert "Line one." in segments[0].text
        assert "Line three." in segments[0].text

    def test_fallback_no_tags_paragraph_splitting(self):
        script = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph."
        segments = parse_dialogue(script)
        assert len(segments) == 3
        assert segments[0].speaker == "Person1"
        assert segments[0].speaker_index == 1
        assert segments[1].speaker == "Person2"
        assert segments[1].speaker_index == 2
        assert segments[2].speaker == "Person1"
        assert segments[2].speaker_index == 1

    def test_fallback_single_paragraph(self):
        script = "Just one paragraph of content."
        segments = parse_dialogue(script)
        assert len(segments) == 1
        assert segments[0].speaker == "Person1"
        assert segments[0].text == "Just one paragraph of content."

    def test_empty_input(self):
        segments = parse_dialogue("")
        assert segments == []

    def test_whitespace_only_input(self):
        segments = parse_dialogue("   \n\n   ")
        assert segments == []

    def test_mixed_tagged_and_untagged(self):
        script = "<Person1>Tagged content</Person1>"
        segments = parse_dialogue(script)
        assert len(segments) == 1
        assert segments[0].speaker == "Person1"

    def test_higher_numbered_persons(self):
        script = "<Person3>Speaker three</Person3>"
        segments = parse_dialogue(script)
        assert len(segments) == 1
        assert segments[0].speaker == "Person3"
        assert segments[0].speaker_index == 3


# ── synthesize_dialogue (mocked TTS) ────────────────────────


class TestSynthesizeDialogue:
    def _make_state(self, script="<Person1>Hello</Person1>", config=None):
        state = MagicMock()
        state.inputs = {
            "script": script,
            "generation_config": config or {},
        }
        state.outputs = {}
        state.tenant_id = "test-tenant"
        state.user_id = "test-user"
        return state

    @pytest.mark.asyncio
    async def test_synthesize_success(self):
        state = self._make_state("<Person1>Hello</Person1><Person2>World</Person2>")

        mock_tts = AsyncMock()
        mock_tts_response = MagicMock()
        mock_tts_response.audio_data = b"audio_chunk"
        mock_tts_response.duration_seconds = 1.5
        mock_tts_response.latency_ms = 200
        mock_tts.synthesize = AsyncMock(return_value=mock_tts_response)

        mock_model_manager = MagicMock()
        mock_model_manager.provision_tts = AsyncMock(return_value=mock_tts)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                mock_cost.record_usage = AsyncMock()
                result = await synthesize_dialogue(state)

        assert result["format"] == "mp3"
        assert result["segment_count"] == 2
        assert result["total_segments"] == 2
        assert result["duration_seconds"] == 3.0
        assert result["audio_data"] == b"audio_chunkaudio_chunk"

    @pytest.mark.asyncio
    async def test_synthesize_no_segments_returns_error(self):
        state = self._make_state("")

        with patch("src.infra.nexus_cost_tracker.cost_tracker"):
            result = await synthesize_dialogue(state)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_synthesize_tts_failure_skips_segment(self):
        state = self._make_state("<Person1>Hello</Person1><Person2>World</Person2>")

        mock_tts = AsyncMock()
        mock_tts.synthesize = AsyncMock(
            side_effect=[
                Exception("TTS failed"),
                MagicMock(audio_data=b"ok", duration_seconds=1.0, latency_ms=100),
            ]
        )

        mock_model_manager = MagicMock()
        mock_model_manager.provision_tts = AsyncMock(return_value=mock_tts)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                mock_cost.record_usage = AsyncMock()
                result = await synthesize_dialogue(state)

        assert result["segment_count"] == 1
        assert result["total_segments"] == 2

    @pytest.mark.asyncio
    async def test_synthesize_uses_script_from_outputs_fallback(self):
        state = MagicMock()
        state.inputs = {"generation_config": {}}
        state.outputs = {"script_generator": {"script": "<Person1>Fallback</Person1>"}}
        state.tenant_id = "t"
        state.user_id = "u"

        mock_tts = AsyncMock()
        mock_tts.synthesize = AsyncMock(
            return_value=MagicMock(audio_data=b"x", duration_seconds=0.5, latency_ms=50)
        )
        mock_model_manager = MagicMock()
        mock_model_manager.provision_tts = AsyncMock(return_value=mock_tts)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_cost_tracker.cost_tracker") as mock_cost:
                mock_cost.record_usage = AsyncMock()
                result = await synthesize_dialogue(state)

        assert result["total_segments"] == 1


# ── synthesize_single (mocked TTS) ──────────────────────────


class TestSynthesizeSingle:
    @pytest.mark.asyncio
    async def test_synthesize_single_returns_bytes(self):
        mock_tts = AsyncMock()
        mock_tts.synthesize = AsyncMock(return_value=MagicMock(audio_data=b"single_audio"))
        mock_model_manager = MagicMock()
        mock_model_manager.provision_tts = AsyncMock(return_value=mock_tts)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            result = await synthesize_single("Hello world", voice="nova", tenant_id="t1")

        assert result == b"single_audio"
        mock_tts.synthesize.assert_called_once_with(text="Hello world", voice="nova", speed=1.0)

    @pytest.mark.asyncio
    async def test_synthesize_single_custom_speed(self):
        mock_tts = AsyncMock()
        mock_tts.synthesize = AsyncMock(return_value=MagicMock(audio_data=b"fast"))
        mock_model_manager = MagicMock()
        mock_model_manager.provision_tts = AsyncMock(return_value=mock_tts)

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            await synthesize_single("Fast", speed=1.2, tenant_id="t2")

        mock_tts.synthesize.assert_called_once_with(text="Fast", voice="alloy", speed=1.2)
