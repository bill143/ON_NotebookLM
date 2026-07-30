"""
Nexus Media Ingest — Video & Audio Understanding for the Source Pipeline
Codename: ESPERANTO — Media extension: MP3/MP4/video-URL ingestion

Turns audio (mp3/wav/m4a) and video (mp4/mov/mkv/webm, or any yt-dlp URL)
into a timestamped transcript for RAG and artifact generation (e.g. meeting
minutes), plus optional keyframes for downstream vision analysis.

Transcript strategy (cheapest first):
1. Native captions via yt-dlp (URLs only) — free, instant.
2. Whisper API fallback (Groq preferred, OpenAI otherwise) — required for
   local files and caption-less URLs. Keys come from settings/env.

Frames (video only) are written to ``<storage>/media/<digest>/frames`` with a
``manifest.json`` so the vision agent can analyze them later without
re-decoding the video.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from loguru import logger

from src.exceptions import EmptyContentError, SourceProcessingError
from src.infra.nexus_obs_tracing import traced

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wma"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv", ".wmv"}

MAX_VIDEO_FRAMES = 50  # keyframe cap — matches the upstream "efficient" tier


@dataclass
class MediaExtract:
    """Result of a media extraction run."""

    transcript: str  # "[MM:SS] line" per segment; "" when unavailable
    segments: list[dict] = field(default_factory=list)
    transcript_origin: str = "none"  # captions | whisper (groq|openai) | none
    duration_seconds: float | None = None
    frame_count: int = 0
    frame_manifest_path: str | None = None
    media_dir: str | None = None


class MediaExtractor:
    """Runs the vendored claude-video pipeline behind an async interface."""

    def __init__(self, media_root: str | Path | None = None) -> None:
        self._media_root = Path(media_root) if media_root else None

    def _root(self) -> Path:
        if self._media_root is None:
            from src.config import get_settings

            self._media_root = Path(get_settings().storage_local_path) / "media"
        self._media_root.mkdir(parents=True, exist_ok=True)
        return self._media_root

    @staticmethod
    def _ensure_tools_on_path() -> None:
        """The pipeline locates yt-dlp/ffmpeg via PATH. When the app runs from
        an unactivated venv, the venv's scripts dir (where pip put yt-dlp)
        isn't on PATH — prepend it so subprocess resolution works."""
        import sys

        scripts_dir = str(Path(sys.executable).parent)
        if scripts_dir not in os.environ.get("PATH", ""):
            os.environ["PATH"] = scripts_dir + os.pathsep + os.environ.get("PATH", "")

    @staticmethod
    def _seed_whisper_env() -> None:
        """Expose configured provider keys to the pipeline, which reads env vars.

        Esperanto note: Whisper STT is an infrastructure call (no model layer
        binding yet, per AI_MODEL_REGISTRY "STT — config only"); once STT joins
        the model layer, swap this for a provision call.
        """
        try:
            from src.config import get_settings

            settings = get_settings()
            if settings.openai_api_key and not os.environ.get("OPENAI_API_KEY"):
                os.environ["OPENAI_API_KEY"] = settings.openai_api_key
            groq_key = getattr(settings, "groq_api_key", None)
            if groq_key and not os.environ.get("GROQ_API_KEY"):
                os.environ["GROQ_API_KEY"] = groq_key
        except Exception as e:  # settings unavailable in some unit-test contexts
            logger.debug("Whisper env seeding skipped", error=str(e))

    @traced("media.extract")
    async def extract(
        self,
        *,
        kind: Literal["video", "audio"],
        file_path: str = "",
        url: str = "",
    ) -> MediaExtract:
        """Extract transcript (and frames for video) from a media source."""
        if not file_path and not url:
            raise SourceProcessingError("Media extraction needs a file_path or url")
        return await asyncio.to_thread(self._extract_sync, kind, file_path, url)

    # ── sync worker (runs in a thread) ───────────────────────

    def _extract_sync(self, kind: str, file_path: str, url: str) -> MediaExtract:
        from .pipeline import download, transcribe

        self._ensure_tools_on_path()
        self._seed_whisper_env()
        source_key = url or file_path
        digest = hashlib.sha256(source_key.encode("utf-8")).hexdigest()[:16]
        work = self._root() / digest
        work.mkdir(parents=True, exist_ok=True)

        segments: list[dict] = []
        origin = "none"
        media_path: str | None = None

        try:
            if url:
                cap = download.fetch_captions(url, work / "download")
                if cap.get("subtitle_path"):
                    segments = transcribe.parse_vtt(cap["subtitle_path"])
                    origin = "captions"
                # Video kind always needs pixels for frames; caption-less
                # sources need the media for Whisper.
                if kind == "video" or not segments:
                    dl = download.download_url(url, work / "download", audio_only=(kind == "audio"))
                    media_path = dl.get("video_path")
                    if not segments and dl.get("subtitle_path"):
                        segments = transcribe.parse_vtt(dl["subtitle_path"])
                        origin = "captions"
            else:
                path = Path(file_path).expanduser()
                if not path.exists():
                    raise SourceProcessingError(f"Media file not found: {path}")
                media_path = str(path)

            if not segments and media_path:
                segments, origin = self._whisper(media_path, work)

            duration = self._duration(media_path, segments)
            frame_count, manifest = 0, None
            if kind == "video" and media_path:
                frame_count, manifest = self._frames(media_path, work, duration)

            transcript = transcribe.format_transcript(segments) if segments else ""
            if not transcript and frame_count == 0:
                raise EmptyContentError(
                    "No transcript could be produced (no captions and no Whisper "
                    "key configured — set GROQ_API_KEY or OPENAI_API_KEY) and no "
                    "frames were extracted."
                )

            logger.info(
                "Media extracted",
                kind=kind,
                origin=origin,
                segments=len(segments),
                frames=frame_count,
                media_dir=str(work),
            )
            return MediaExtract(
                transcript=transcript,
                segments=segments,
                transcript_origin=origin,
                duration_seconds=duration,
                frame_count=frame_count,
                frame_manifest_path=manifest,
                media_dir=str(work),
            )
        except (EmptyContentError, SourceProcessingError):
            raise
        except SystemExit as e:  # vendored pipeline signals failures via SystemExit
            raise SourceProcessingError(f"Media pipeline failed: {e}") from e
        except Exception as e:
            raise SourceProcessingError(f"Media extraction failed: {e}", original_error=e) from e

    def _whisper(self, media_path: str, work: Path) -> tuple[list[dict], str]:
        from .pipeline import whisper

        backend, key = whisper.load_api_key()
        if not key:
            return [], "none"
        try:
            segments, used = whisper.transcribe_video(media_path, work / "audio.mp3", backend, key)
            return segments, f"whisper ({used})"
        except SystemExit as e:
            raise SourceProcessingError(f"Whisper transcription failed: {e}") from e

    @staticmethod
    def _duration(media_path: str | None, segments: list[dict]) -> float | None:
        if media_path:
            try:
                from .pipeline import frames

                meta = frames.get_metadata(media_path)
                if meta.get("duration"):
                    return float(meta["duration"])
            except (Exception, SystemExit) as e:  # vendored pipeline raises SystemExit
                logger.debug("ffprobe duration unavailable", error=str(e))
        if segments:
            last = segments[-1]
            return float(last.get("end") or last.get("start") or 0) or None
        return None

    def _frames(
        self, media_path: str, work: Path, duration: float | None
    ) -> tuple[int, str | None]:
        """Extract keyframes for later vision analysis. Best-effort: a frame
        failure never fails the source (the transcript is the primary content)."""
        from .pipeline import frames as frames_mod

        try:
            frames_dir = work / "frames"
            selected, _meta = frames_mod.extract_keyframes(
                media_path, frames_dir, max_frames=MAX_VIDEO_FRAMES
            )
            manifest = {
                "media_path": media_path,
                "duration_seconds": duration,
                "frames": [
                    {
                        "path": str(f.get("path")),
                        "timestamp_seconds": f.get("timestamp_seconds"),
                        "reason": f.get("reason"),
                    }
                    for f in selected
                ],
            }
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return len(selected), str(manifest_path)
        except (Exception, SystemExit) as e:  # best-effort: transcript is the primary content
            logger.warning("Frame extraction skipped", error=str(e))
            return 0, None


def kind_for_extension(ext: str) -> str | None:
    """Map a file extension to a media kind, or None if not media."""
    ext = ext.lower()
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return None


# Global singleton (matches source_processor / content_agent convention)
media_extractor = MediaExtractor()
