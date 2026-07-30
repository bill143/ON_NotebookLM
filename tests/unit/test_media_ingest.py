"""Unit tests for nexus_media_ingest — video/audio extraction + meeting minutes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.nexus_media_ingest import (
    AUDIO_EXTS,
    VIDEO_EXTS,
    MediaExtract,
    MediaExtractor,
    kind_for_extension,
    media_extractor,
)
from src.exceptions import SourceProcessingError

# ── kind_for_extension ───────────────────────────────────────


class TestKindForExtension:
    def test_audio_extensions(self):
        assert kind_for_extension(".mp3") == "audio"
        assert kind_for_extension(".WAV") == "audio"
        assert kind_for_extension(".m4a") == "audio"

    def test_video_extensions(self):
        assert kind_for_extension(".mp4") == "video"
        assert kind_for_extension(".MOV") == "video"
        assert kind_for_extension(".mkv") == "video"

    def test_non_media(self):
        assert kind_for_extension(".pdf") is None
        assert kind_for_extension(".txt") is None
        assert kind_for_extension("") is None

    def test_sets_are_disjoint(self):
        assert not (AUDIO_EXTS & VIDEO_EXTS)


# ── MediaExtractor ───────────────────────────────────────────


class TestMediaExtractor:
    @pytest.mark.asyncio
    async def test_requires_source(self, tmp_path: Path):
        with pytest.raises(SourceProcessingError):
            await MediaExtractor(media_root=tmp_path).extract(kind="audio")

    @pytest.mark.asyncio
    async def test_missing_file_raises(self, tmp_path: Path):
        extractor = MediaExtractor(media_root=tmp_path)
        with pytest.raises(SourceProcessingError, match="not found"):
            await extractor.extract(kind="audio", file_path=str(tmp_path / "nope.mp3"))

    @pytest.mark.asyncio
    async def test_local_audio_whisper_flow(self, tmp_path: Path):
        """A local audio file goes to Whisper and yields a timestamped transcript."""
        media = tmp_path / "meeting.mp3"
        media.write_bytes(b"fake-audio")
        extractor = MediaExtractor(media_root=tmp_path / "store")

        segments = [
            {"start": 0.0, "end": 4.0, "text": "Welcome to the coordination meeting."},
            {"start": 65.0, "end": 70.0, "text": "Steel delivery slips to Thursday."},
        ]
        with patch.object(extractor, "_whisper", return_value=(segments, "whisper (groq)")):
            result = await extractor.extract(kind="audio", file_path=str(media))

        assert isinstance(result, MediaExtract)
        assert result.transcript_origin == "whisper (groq)"
        assert "[00:00] Welcome to the coordination meeting." in result.transcript
        assert "[01:05] Steel delivery slips to Thursday." in result.transcript
        assert result.frame_count == 0
        assert result.duration_seconds == 70.0

    @pytest.mark.asyncio
    async def test_no_transcript_and_no_frames_raises_empty(self, tmp_path: Path):
        media = tmp_path / "silent.mp3"
        media.write_bytes(b"fake-audio")
        extractor = MediaExtractor(media_root=tmp_path / "store")

        with patch.object(extractor, "_whisper", return_value=([], "none")):
            with pytest.raises(SourceProcessingError):
                await extractor.extract(kind="audio", file_path=str(media))


# ── ContentExtractor routing ─────────────────────────────────


class TestSourceIngestRouting:
    @pytest.mark.asyncio
    async def test_video_routes_to_media_extractor(self):
        from src.core.nexus_source_ingest import ContentExtractor

        fake = MediaExtract(transcript="[00:00] hello", transcript_origin="captions")
        with patch.object(media_extractor, "extract", AsyncMock(return_value=fake)) as mock_ext:
            out = await ContentExtractor().extract("video", url="https://youtu.be/abc")

        assert out == "[00:00] hello"
        mock_ext.assert_awaited_once_with(kind="video", file_path="", url="https://youtu.be/abc")

    @pytest.mark.asyncio
    async def test_audio_routes_to_media_extractor(self, tmp_path: Path):
        from src.core.nexus_source_ingest import ContentExtractor

        rec = str(tmp_path / "rec.mp3")
        fake = MediaExtract(transcript="[00:07] action item", transcript_origin="whisper (openai)")
        with patch.object(media_extractor, "extract", AsyncMock(return_value=fake)) as mock_ext:
            out = await ContentExtractor().extract("audio", file_path=rec)

        assert out == "[00:07] action item"
        mock_ext.assert_awaited_once_with(kind="audio", file_path=rec, url="")

    @pytest.mark.asyncio
    async def test_unknown_type_still_rejected(self):
        from src.core.nexus_source_ingest import ContentExtractor
        from src.exceptions import UnsupportedFormatError

        with pytest.raises(UnsupportedFormatError):
            await ContentExtractor().extract("hologram")


# ── Upload mime mapping ──────────────────────────────────────


class TestUploadMimeMapping:
    def test_media_mimes_supported(self):
        from src.api.sources import MEDIA_MIME_TO_TYPE, SUPPORTED_MIME_TYPES

        assert "video/mp4" in SUPPORTED_MIME_TYPES
        assert "audio/mpeg" in SUPPORTED_MIME_TYPES
        assert MEDIA_MIME_TO_TYPE["video/mp4"] == "video"
        assert MEDIA_MIME_TO_TYPE["audio/mpeg"] == "audio"

    def test_media_size_budget_larger_than_default(self):
        from src.api.sources import MAX_FILE_SIZE_MB, MAX_MEDIA_FILE_SIZE_MB

        assert MAX_MEDIA_FILE_SIZE_MB > MAX_FILE_SIZE_MB


# ── Studio queue artifact ────────────────────────────────────


class TestMeetingMinutesArtifact:
    def test_artifact_type_registered(self):
        from src.core.nexus_studio_queue import ARTIFACT_PIPELINES, ArtifactType

        art = ArtifactType("meeting_minutes")
        assert art is ArtifactType.MEETING_MINUTES
        assert ARTIFACT_PIPELINES[art] == ["gather_sources", "generate_content", "format_output"]

    def test_prompt_file_exists_and_grounded(self):
        prompt = Path("prompts/studio/meeting_minutes.md").read_text(encoding="utf-8")
        assert "{{ source_content }}" in prompt
        assert "Action Items" in prompt
        assert "Decisions" in prompt


# ── Content agent generator ──────────────────────────────────


def _make_state(overrides=None):
    state = MagicMock()
    state.inputs = {
        "source_content": "[00:00] Kickoff. [01:00] Bill approves the budget.",
        "meeting_title": "Weekly Coordination",
    }
    if overrides:
        state.inputs.update(overrides)
    state.tenant_id = "test-tenant"
    state.user_id = "test-user"
    return state


def _mock_llm_response(content="## Minutes", model="test-model"):
    resp = MagicMock()
    resp.content = content
    resp.model = model
    resp.provider = "test"
    resp.input_tokens = 100
    resp.output_tokens = 50
    resp.cost_usd = 0.001
    resp.latency_ms = 10
    return resp


class TestGenerateMeetingMinutes:
    @pytest.mark.asyncio
    async def test_returns_minutes_and_model(self):
        from src.agents.nexus_agent_content import generate_meeting_minutes

        state = _make_state()
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=_mock_llm_response())
        mock_model_manager = MagicMock()
        mock_model_manager.provision_llm = AsyncMock(return_value=mock_llm)
        mock_registry = MagicMock()
        mock_registry.resolve = AsyncMock(return_value="rendered prompt")

        with patch("src.agents.nexus_model_layer.model_manager", mock_model_manager):
            with patch("src.infra.nexus_prompt_registry.prompt_registry", mock_registry):
                with patch("src.agents.nexus_agent_content.cost_tracker") as mock_cost:
                    mock_cost.record_usage = AsyncMock()
                    result = await generate_meeting_minutes(state)

        assert result["meeting_minutes"] == "## Minutes"
        assert result["model"] == "test-model"
        mock_registry.resolve.assert_awaited_once()
        args, kwargs = mock_registry.resolve.call_args
        assert args == ("studio", "meeting_minutes")
        assert "Bill approves the budget" in kwargs["variables"]["source_content"]

    @pytest.mark.asyncio
    async def test_dispatched_from_content_agent(self):
        from src.agents.nexus_agent_content import content_agent

        with patch(
            "src.agents.nexus_agent_content.generate_meeting_minutes",
            AsyncMock(return_value={"meeting_minutes": "ok"}),
        ) as mock_gen:
            result = await content_agent.generate(
                artifact_type="meeting_minutes",
                source_content="[00:00] hi",
                config={},
                tenant_id="t1",
            )

        assert result == {"meeting_minutes": "ok"}
        mock_gen.assert_awaited_once()
