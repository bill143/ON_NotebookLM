"""
Nexus Audio Engine — Production Audio Processing with pydub
Codename: ESPERANTO — Feature 3D: Audio Synthesis & Export

Provides:
- Segment concatenation with cross-fade transitions
- Intro/outro music overlay with volume ducking
- Multi-speaker audio assembly from TTS segments
- Audio normalization and loudness targeting
- Export to MP3, WAV, OGG with metadata
- Timestamped transcript generation
- Audio waveform data for frontend visualization
"""

from __future__ import annotations

import io
import json
import os
import struct
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.infra.nexus_obs_tracing import traced


# ── Types ────────────────────────────────────────────────────

@dataclass
class AudioSegment:
    """A single audio segment (e.g., one TTS line)."""
    audio_data: bytes
    speaker: str = ""
    text: str = ""
    duration_ms: float = 0.0
    sample_rate: int = 24000
    format: str = "mp3"         # "mp3", "wav", "ogg"


@dataclass
class AudioConfig:
    """Configuration for audio assembly."""
    # Cross-fade settings
    crossfade_ms: int = 150              # Overlap between segments
    pause_between_speakers_ms: int = 400  # Silence gap when speaker changes
    pause_within_speaker_ms: int = 100    # Short gap same speaker

    # Intro/Outro
    intro_audio_path: Optional[str] = None
    outro_audio_path: Optional[str] = None
    intro_duration_ms: int = 3000        # How long intro plays before speech
    outro_duration_ms: int = 3000        # How long outro plays after speech
    music_volume_db: float = -18.0       # Background music volume during speech
    music_fade_ms: int = 2000            # Fade in/out duration for music

    # Normalization
    target_loudness_dbfs: float = -16.0  # Target overall loudness
    normalize: bool = True
    sample_rate: int = 44100             # Output sample rate

    # Output
    output_format: str = "mp3"           # "mp3", "wav", "ogg"
    bitrate: str = "192k"               # MP3 bitrate
    channels: int = 1                    # 1=mono, 2=stereo


@dataclass
class TranscriptEntry:
    """A timestamped transcript entry."""
    speaker: str
    text: str
    start_ms: float
    end_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "speaker": self.speaker,
            "text": self.text,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "start_formatted": format_timestamp(self.start_ms),
            "end_formatted": format_timestamp(self.end_ms),
        }


@dataclass
class AudioResult:
    """Final assembled audio output."""
    audio_data: bytes
    duration_ms: float
    format: str
    sample_rate: int
    file_size_bytes: int
    transcript: list[TranscriptEntry] = field(default_factory=list)
    segments_count: int = 0
    speakers: list[str] = field(default_factory=list)
    waveform_data: list[float] = field(default_factory=list)


# ── Helpers ──────────────────────────────────────────────────

def format_timestamp(ms: float) -> str:
    """Convert milliseconds to HH:MM:SS.mmm format."""
    total_seconds = ms / 1000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"


# ── Audio Engine ─────────────────────────────────────────────

class AudioEngine:
    """
    Production audio assembly engine using pydub.
    Handles cross-fading, normalization, intro/outro, and export.
    """

    @traced("audio.assemble")
    async def assemble(
        self,
        segments: list[AudioSegment],
        config: Optional[AudioConfig] = None,
    ) -> AudioResult:
        """
        Assemble multiple audio segments into a single production-ready audio file.

        Pipeline:
        1. Load all segments as pydub AudioSegments
        2. Apply cross-fades / pauses between segments
        3. Overlay intro/outro music with volume ducking
        4. Normalize to target loudness
        5. Export and generate metadata
        """
        from pydub import AudioSegment as PydubSegment
        from pydub.effects import normalize as pydub_normalize

        if not config:
            config = AudioConfig()

        if not segments:
            raise ValueError("No audio segments to assemble")

        logger.info(f"Assembling {len(segments)} audio segments")

        # 1. Convert all segments to pydub
        pydub_parts: list[tuple[PydubSegment, AudioSegment]] = []
        for seg in segments:
            try:
                audio = PydubSegment.from_file(
                    io.BytesIO(seg.audio_data),
                    format=seg.format,
                )
                pydub_parts.append((audio, seg))
            except Exception as e:
                logger.warning(f"Skipping malformed audio segment: {e}")

        if not pydub_parts:
            raise ValueError("No valid audio segments could be loaded")

        # 2. Concatenate with cross-fades and pauses
        transcript: list[TranscriptEntry] = []
        current_position_ms: float = 0.0

        # Start with intro silence if we have intro music
        combined = PydubSegment.silent(duration=0)

        if config.intro_audio_path and os.path.exists(config.intro_audio_path):
            combined = PydubSegment.silent(duration=config.intro_duration_ms)
            current_position_ms = float(config.intro_duration_ms)

        prev_speaker = ""

        for i, (audio_part, seg_meta) in enumerate(pydub_parts):
            # Determine pause duration
            if i > 0:
                if seg_meta.speaker != prev_speaker and seg_meta.speaker:
                    pause_ms = config.pause_between_speakers_ms
                else:
                    pause_ms = config.pause_within_speaker_ms

                # Cross-fade or gap
                if config.crossfade_ms > 0 and len(combined) > config.crossfade_ms:
                    # Add pause then cross-fade
                    if pause_ms > config.crossfade_ms:
                        silence = PydubSegment.silent(
                            duration=pause_ms - config.crossfade_ms
                        )
                        combined = combined + silence
                        current_position_ms += pause_ms - config.crossfade_ms

                    combined = combined.append(audio_part, crossfade=config.crossfade_ms)
                    current_position_ms += pause_ms
                else:
                    silence = PydubSegment.silent(duration=pause_ms)
                    combined = combined + silence + audio_part
                    current_position_ms += pause_ms
            else:
                combined = combined + audio_part

            # Record transcript entry
            segment_duration = len(audio_part)
            transcript.append(TranscriptEntry(
                speaker=seg_meta.speaker,
                text=seg_meta.text,
                start_ms=current_position_ms,
                end_ms=current_position_ms + segment_duration,
            ))

            current_position_ms += segment_duration
            prev_speaker = seg_meta.speaker

        # 3. Overlay intro/outro music with ducking
        if config.intro_audio_path and os.path.exists(config.intro_audio_path):
            combined = self._overlay_intro(combined, config)

        if config.outro_audio_path and os.path.exists(config.outro_audio_path):
            combined = self._overlay_outro(combined, config)

        # 4. Normalize loudness
        if config.normalize:
            combined = self._normalize_loudness(combined, config.target_loudness_dbfs)

        # 5. Set sample rate and channels
        combined = combined.set_frame_rate(config.sample_rate)
        combined = combined.set_channels(config.channels)

        # 6. Export
        output_buffer = io.BytesIO()
        export_params = {}
        if config.output_format == "mp3":
            export_params["bitrate"] = config.bitrate
        combined.export(output_buffer, format=config.output_format, **export_params)
        output_data = output_buffer.getvalue()

        # 7. Generate waveform data for frontend visualization
        waveform = self._extract_waveform(combined, num_points=200)

        # Collect unique speakers
        speakers = list(set(s.speaker for s in segments if s.speaker))

        result = AudioResult(
            audio_data=output_data,
            duration_ms=float(len(combined)),
            format=config.output_format,
            sample_rate=config.sample_rate,
            file_size_bytes=len(output_data),
            transcript=transcript,
            segments_count=len(segments),
            speakers=speakers,
            waveform_data=waveform,
        )

        logger.info(
            f"Audio assembled: {result.duration_ms/1000:.1f}s, "
            f"{result.file_size_bytes/1024:.0f}KB, "
            f"{result.segments_count} segments, "
            f"{len(speakers)} speakers"
        )

        return result

    def _overlay_intro(
        self,
        combined: Any,
        config: AudioConfig,
    ) -> Any:
        """Overlay intro music with fade-in and volume ducking."""
        from pydub import AudioSegment as PydubSegment

        intro = PydubSegment.from_file(config.intro_audio_path)

        # Trim to desired length + fade time
        total_intro_ms = config.intro_duration_ms + config.music_fade_ms
        if len(intro) > total_intro_ms:
            intro = intro[:total_intro_ms]

        # Adjust volume
        intro = intro + config.music_volume_db

        # Fade in at start
        intro = intro.fade_in(min(config.music_fade_ms, len(intro) // 2))

        # Fade out where speech begins
        intro = intro.fade_out(config.music_fade_ms)

        # Overlay (intro plays at the beginning)
        return intro.overlay(combined, position=0)

    def _overlay_outro(
        self,
        combined: Any,
        config: AudioConfig,
    ) -> Any:
        """Overlay outro music with fade-out at the end."""
        from pydub import AudioSegment as PydubSegment

        outro = PydubSegment.from_file(config.outro_audio_path)

        # Trim
        if len(outro) > config.outro_duration_ms:
            outro = outro[:config.outro_duration_ms]

        # Adjust volume
        outro = outro + config.music_volume_db

        # Fade in and out
        outro = outro.fade_in(config.music_fade_ms)
        outro = outro.fade_out(config.music_fade_ms)

        # Overlay at the end of combined
        position = max(0, len(combined) - config.outro_duration_ms)
        combined = combined.overlay(outro, position=position)

        # Add trailing silence + fade
        combined = combined + PydubSegment.silent(duration=500)
        combined = combined.fade_out(1000)

        return combined

    def _normalize_loudness(self, audio: Any, target_dbfs: float) -> Any:
        """Normalize audio to target loudness (dBFS)."""
        current_dbfs = audio.dBFS
        if current_dbfs == float("-inf"):
            return audio

        delta = target_dbfs - current_dbfs
        return audio.apply_gain(delta)

    def _extract_waveform(self, audio: Any, num_points: int = 200) -> list[float]:
        """
        Extract amplitude waveform data for frontend visualization.
        Returns normalized amplitudes between 0.0 and 1.0.
        """
        raw = audio.raw_data
        sample_width = audio.sample_width
        n_samples = len(raw) // sample_width

        if n_samples == 0:
            return [0.0] * num_points

        # Read all samples
        if sample_width == 1:
            fmt = f"<{n_samples}B"
            samples = [s - 128 for s in struct.unpack(fmt, raw)]
        elif sample_width == 2:
            fmt = f"<{n_samples}h"
            samples = list(struct.unpack(fmt, raw))
        elif sample_width == 4:
            fmt = f"<{n_samples}i"
            samples = list(struct.unpack(fmt, raw))
        else:
            return [0.0] * num_points

        # Downsample to num_points
        chunk_size = max(1, n_samples // num_points)
        waveform = []
        max_val = max(abs(s) for s in samples) or 1

        for i in range(0, n_samples, chunk_size):
            chunk = samples[i : i + chunk_size]
            rms = (sum(s * s for s in chunk) / len(chunk)) ** 0.5
            waveform.append(rms / max_val)

        # Pad or trim to exact num_points
        while len(waveform) < num_points:
            waveform.append(0.0)
        return waveform[:num_points]

    @traced("audio.save")
    async def save_to_file(
        self,
        result: AudioResult,
        output_path: str,
        save_transcript: bool = True,
    ) -> dict[str, str]:
        """Save assembled audio and transcript to disk."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Save audio
        with open(output, "wb") as f:
            f.write(result.audio_data)

        paths = {"audio": str(output)}

        # Save transcript
        if save_transcript and result.transcript:
            transcript_path = output.with_suffix(".json")
            with open(transcript_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "duration_ms": result.duration_ms,
                        "speakers": result.speakers,
                        "segments": [t.to_dict() for t in result.transcript],
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            paths["transcript"] = str(transcript_path)

            # SRT subtitle file
            srt_path = output.with_suffix(".srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                for i, entry in enumerate(result.transcript, 1):
                    start = self._ms_to_srt_time(entry.start_ms)
                    end = self._ms_to_srt_time(entry.end_ms)
                    label = f"[{entry.speaker}] " if entry.speaker else ""
                    f.write(f"{i}\n{start} --> {end}\n{label}{entry.text}\n\n")
            paths["subtitles"] = str(srt_path)

        logger.info(f"Audio saved: {paths}")
        return paths

    @staticmethod
    def _ms_to_srt_time(ms: float) -> str:
        """Convert ms to SRT timestamp format (HH:MM:SS,mmm)."""
        total_s = ms / 1000
        hours = int(total_s // 3600)
        minutes = int((total_s % 3600) // 60)
        seconds = int(total_s % 60)
        millis = int(ms % 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

    @traced("audio.generate_silence")
    async def generate_silence(self, duration_ms: int, format: str = "mp3") -> bytes:
        """Generate a silence audio segment."""
        from pydub import AudioSegment as PydubSegment

        silence = PydubSegment.silent(duration=duration_ms)
        buffer = io.BytesIO()
        silence.export(buffer, format=format)
        return buffer.getvalue()

    @traced("audio.mix_background")
    async def mix_background_music(
        self,
        speech: AudioResult,
        music_path: str,
        music_volume_db: float = -20.0,
        loop_music: bool = True,
    ) -> AudioResult:
        """Mix background music under existing speech audio."""
        from pydub import AudioSegment as PydubSegment

        speech_audio = PydubSegment.from_file(
            io.BytesIO(speech.audio_data), format=speech.format
        )
        music = PydubSegment.from_file(music_path)

        # Loop music if needed
        if loop_music and len(music) < len(speech_audio):
            repeats = (len(speech_audio) // len(music)) + 1
            music = music * repeats

        # Trim to speech length
        music = music[: len(speech_audio)]

        # Apply volume reduction
        music = music + music_volume_db

        # Fade in/out
        music = music.fade_in(2000).fade_out(3000)

        # Overlay
        mixed = speech_audio.overlay(music)

        # Export
        output = io.BytesIO()
        mixed.export(output, format=speech.format, bitrate="192k")
        output_data = output.getvalue()

        return AudioResult(
            audio_data=output_data,
            duration_ms=float(len(mixed)),
            format=speech.format,
            sample_rate=speech.sample_rate,
            file_size_bytes=len(output_data),
            transcript=speech.transcript,
            segments_count=speech.segments_count,
            speakers=speech.speakers,
            waveform_data=self._extract_waveform(mixed),
        )


# Global singleton
audio_engine = AudioEngine()
