"""Unit tests for nexus_audio_join — audio concatenation, cross-fade, SRT generation."""

from __future__ import annotations

import io
import json
import struct
from unittest.mock import MagicMock, patch

import pytest

from src.core.nexus_audio_join import (
    AudioConfig,
    AudioEngine,
    AudioResult,
    AudioSegment,
    TranscriptEntry,
    audio_engine,
    format_timestamp,
)

# ── Dataclass existence & defaults ────────────────────────────


class TestAudioSegmentDataclass:
    def test_fields_exist(self):
        seg = AudioSegment(audio_data=b"\x00")
        assert seg.audio_data == b"\x00"
        assert seg.speaker == ""
        assert seg.text == ""
        assert seg.duration_ms == 0.0
        assert seg.sample_rate == 24000
        assert seg.format == "mp3"

    def test_custom_values(self):
        seg = AudioSegment(
            audio_data=b"data",
            speaker="Alice",
            text="Hello",
            duration_ms=1500.0,
            sample_rate=44100,
            format="wav",
        )
        assert seg.speaker == "Alice"
        assert seg.text == "Hello"
        assert seg.duration_ms == 1500.0
        assert seg.sample_rate == 44100
        assert seg.format == "wav"


class TestAudioConfigDefaults:
    def test_defaults(self):
        cfg = AudioConfig()
        assert cfg.crossfade_ms == 150
        assert cfg.pause_between_speakers_ms == 400
        assert cfg.pause_within_speaker_ms == 100
        assert cfg.intro_audio_path is None
        assert cfg.outro_audio_path is None
        assert cfg.intro_duration_ms == 3000
        assert cfg.outro_duration_ms == 3000
        assert cfg.music_volume_db == -18.0
        assert cfg.music_fade_ms == 2000
        assert cfg.target_loudness_dbfs == -16.0
        assert cfg.normalize is True
        assert cfg.sample_rate == 44100
        assert cfg.output_format == "mp3"
        assert cfg.bitrate == "192k"
        assert cfg.channels == 1

    def test_custom_crossfade(self):
        cfg = AudioConfig(crossfade_ms=300, output_format="wav", channels=2)
        assert cfg.crossfade_ms == 300
        assert cfg.output_format == "wav"
        assert cfg.channels == 2


class TestTranscriptEntry:
    def test_fields(self):
        entry = TranscriptEntry(speaker="Bob", text="Hi", start_ms=0.0, end_ms=1000.0)
        assert entry.speaker == "Bob"
        assert entry.text == "Hi"
        assert entry.start_ms == 0.0
        assert entry.end_ms == 1000.0

    def test_to_dict_keys(self):
        entry = TranscriptEntry(speaker="A", text="text", start_ms=500.0, end_ms=2500.0)
        d = entry.to_dict()
        assert d["speaker"] == "A"
        assert d["text"] == "text"
        assert d["start_ms"] == 500.0
        assert d["end_ms"] == 2500.0
        assert "start_formatted" in d
        assert "end_formatted" in d

    def test_to_dict_formatted_uses_format_timestamp(self):
        entry = TranscriptEntry(speaker="X", text="t", start_ms=3661500.0, end_ms=3662000.0)
        d = entry.to_dict()
        assert d["start_formatted"] == format_timestamp(3661500.0)
        assert d["end_formatted"] == format_timestamp(3662000.0)


class TestAudioResultDataclass:
    def test_defaults(self):
        result = AudioResult(
            audio_data=b"audio",
            duration_ms=5000.0,
            format="mp3",
            sample_rate=44100,
            file_size_bytes=1024,
        )
        assert result.transcript == []
        assert result.segments_count == 0
        assert result.speakers == []
        assert result.waveform_data == []


# ── format_timestamp ─────────────────────────────────────────


class TestFormatTimestamp:
    def test_zero_ms(self):
        assert format_timestamp(0.0) == "00:00.00"

    def test_seconds_only(self):
        assert format_timestamp(5000.0) == "00:05.00"

    def test_minutes_and_seconds(self):
        assert format_timestamp(65000.0) == "01:05.00"

    def test_with_fractional_seconds(self):
        assert format_timestamp(1500.0) == "00:01.50"

    def test_hours(self):
        result = format_timestamp(3661000.0)
        assert result.startswith("01:01:")

    def test_large_value(self):
        result = format_timestamp(7200000.0)
        assert result.startswith("02:00:")


# ── SRT timestamp ────────────────────────────────────────────


class TestMsToSrtTime:
    def test_zero(self):
        assert AudioEngine._ms_to_srt_time(0.0) == "00:00:00,000"

    def test_one_second(self):
        assert AudioEngine._ms_to_srt_time(1000.0) == "00:00:01,000"

    def test_complex_time(self):
        result = AudioEngine._ms_to_srt_time(3661500.0)
        assert result == "01:01:01,500"

    def test_minutes(self):
        result = AudioEngine._ms_to_srt_time(65000.0)
        assert result == "00:01:05,000"

    def test_millis_precision(self):
        result = AudioEngine._ms_to_srt_time(1234.0)
        assert result == "00:00:01,234"


# ── AudioEngine.assemble (mocked pydub) ─────────────────────


class TestAudioEngineAssemble:
    @pytest.mark.asyncio
    async def test_assemble_empty_segments_raises(self):
        engine = AudioEngine()
        with pytest.raises(ValueError, match="No audio segments"):
            await engine.assemble([])

    @pytest.mark.asyncio
    async def test_assemble_single_segment(self):
        mock_pydub_seg = MagicMock()
        mock_pydub_seg.__len__ = MagicMock(return_value=2000)
        mock_pydub_seg.__add__ = MagicMock(return_value=mock_pydub_seg)
        mock_pydub_seg.set_frame_rate.return_value = mock_pydub_seg
        mock_pydub_seg.set_channels.return_value = mock_pydub_seg
        mock_pydub_seg.dBFS = -20.0
        mock_pydub_seg.apply_gain.return_value = mock_pydub_seg
        mock_pydub_seg.raw_data = struct.pack("<4h", 100, -100, 50, -50)
        mock_pydub_seg.sample_width = 2

        io.BytesIO(b"fake_mp3_data")
        mock_pydub_seg.export = MagicMock(side_effect=lambda buf, **kw: buf.write(b"fake_mp3"))

        with patch("src.core.nexus_audio_join.AudioSegment.__init_subclass__", create=True):
            with patch("pydub.AudioSegment") as mock_audio_segment:
                mock_audio_segment.from_file.return_value = mock_pydub_seg
                mock_audio_segment.silent.return_value = mock_pydub_seg

                seg = AudioSegment(audio_data=b"\x00" * 100, speaker="Host", text="Hello")
                engine = AudioEngine()
                result = await engine.assemble([seg])

                assert isinstance(result, AudioResult)
                assert result.segments_count == 1
                assert "Host" in result.speakers

    @pytest.mark.asyncio
    async def test_assemble_all_malformed_raises(self):
        with patch("pydub.AudioSegment") as mock_audio_segment:
            mock_audio_segment.from_file.side_effect = Exception("bad audio")
            mock_audio_segment.silent.return_value = MagicMock(__len__=MagicMock(return_value=0))

            seg = AudioSegment(audio_data=b"bad")
            engine = AudioEngine()
            with pytest.raises(ValueError, match="No valid audio"):
                await engine.assemble([seg])


# ── AudioEngine._normalize_loudness ──────────────────────────


class TestNormalizeLoudness:
    def test_applies_gain_delta(self):
        engine = AudioEngine()
        mock_audio = MagicMock()
        mock_audio.dBFS = -20.0
        mock_audio.apply_gain.return_value = mock_audio
        engine._normalize_loudness(mock_audio, -16.0)
        mock_audio.apply_gain.assert_called_once_with(4.0)

    def test_silent_audio_returns_unchanged(self):
        engine = AudioEngine()
        mock_audio = MagicMock()
        mock_audio.dBFS = float("-inf")
        result = engine._normalize_loudness(mock_audio, -16.0)
        assert result is mock_audio
        mock_audio.apply_gain.assert_not_called()


# ── AudioEngine._extract_waveform ────────────────────────────


class TestExtractWaveform:
    def test_empty_audio_returns_zeros(self):
        engine = AudioEngine()
        mock_audio = MagicMock()
        mock_audio.raw_data = b""
        mock_audio.sample_width = 2
        result = engine._extract_waveform(mock_audio, num_points=10)
        assert result == [0.0] * 10

    def test_16bit_samples(self):
        engine = AudioEngine()
        samples = [100, -100, 200, -200, 50, -50, 150, -150]
        raw = struct.pack(f"<{len(samples)}h", *samples)
        mock_audio = MagicMock()
        mock_audio.raw_data = raw
        mock_audio.sample_width = 2
        result = engine._extract_waveform(mock_audio, num_points=4)
        assert len(result) == 4
        assert all(0.0 <= v <= 1.0 for v in result)

    def test_unsupported_sample_width_returns_zeros(self):
        engine = AudioEngine()
        mock_audio = MagicMock()
        mock_audio.raw_data = b"\x00" * 30
        mock_audio.sample_width = 3
        result = engine._extract_waveform(mock_audio, num_points=5)
        assert result == [0.0] * 5


# ── Global singleton ─────────────────────────────────────────


class TestGlobalSingleton:
    def test_audio_engine_is_instance(self):
        assert isinstance(audio_engine, AudioEngine)


# ── save_to_file (mocked I/O) ────────────────────────────────


class TestSaveToFile:
    @pytest.mark.asyncio
    async def test_save_creates_files(self, tmp_path):
        engine = AudioEngine()
        transcript = [
            TranscriptEntry(speaker="A", text="Hello", start_ms=0, end_ms=1000),
        ]
        result = AudioResult(
            audio_data=b"audio_bytes",
            duration_ms=1000.0,
            format="mp3",
            sample_rate=44100,
            file_size_bytes=11,
            transcript=transcript,
            speakers=["A"],
        )
        output_file = tmp_path / "output.mp3"
        paths = await engine.save_to_file(result, str(output_file))

        assert "audio" in paths
        assert output_file.exists()
        assert output_file.read_bytes() == b"audio_bytes"

        assert "transcript" in paths
        transcript_file = tmp_path / "output.json"
        assert transcript_file.exists()
        data = json.loads(transcript_file.read_text())
        assert data["duration_ms"] == 1000.0
        assert len(data["segments"]) == 1

        assert "subtitles" in paths
        srt_file = tmp_path / "output.srt"
        assert srt_file.exists()
        srt_content = srt_file.read_text()
        assert "[A] Hello" in srt_content
        assert "-->" in srt_content

    @pytest.mark.asyncio
    async def test_save_no_transcript(self, tmp_path):
        engine = AudioEngine()
        result = AudioResult(
            audio_data=b"data",
            duration_ms=500.0,
            format="mp3",
            sample_rate=44100,
            file_size_bytes=4,
        )
        output_file = tmp_path / "out.mp3"
        paths = await engine.save_to_file(result, str(output_file), save_transcript=False)
        assert "audio" in paths
        assert "transcript" not in paths
        assert "subtitles" not in paths
