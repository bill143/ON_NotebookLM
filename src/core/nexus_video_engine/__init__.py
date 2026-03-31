"""
Nexus Video Engine — Feature 1B: Video Generation Pipeline
Codename: ESPERANTO

Provides:
- Audio + visual frame composition
- Scene-based video assembly
- Subtitle overlay
- Export to MP4/WebM
"""

from __future__ import annotations

import io
import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.infra.nexus_obs_tracing import traced


@dataclass
class VideoScene:
    """A single scene in a video."""
    scene_id: str
    title: str
    narration_text: str
    visual_description: str
    duration_ms: float = 0.0
    audio_data: Optional[bytes] = None
    image_data: Optional[bytes] = None
    subtitle_text: str = ""


@dataclass
class VideoConfig:
    """Video generation configuration."""
    resolution: tuple[int, int] = (1920, 1080)
    fps: int = 30
    output_format: str = "mp4"       # "mp4", "webm"
    codec: str = "libx264"
    bitrate: str = "4000k"
    include_subtitles: bool = True
    background_color: str = "#0f172a"  # Dark blue
    text_color: str = "#f8fafc"
    accent_color: str = "#6366f1"
    font_size: int = 48
    title_font_size: int = 72
    transition_ms: int = 500


@dataclass
class VideoResult:
    """Output from video composition."""
    video_data: bytes
    duration_ms: float
    format: str
    scenes_count: int
    file_size_bytes: int
    subtitle_data: Optional[str] = None


class VideoEngine:
    """
    Composes videos from audio + visual elements.
    Uses scene-based assembly with title cards and subtitle overlay.
    """

    @traced("video.compose")
    async def compose(
        self,
        context: dict[str, Any],
        config_dict: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        Compose a video from generation context.
        Falls back to audio-only if video libraries unavailable.
        """
        config = VideoConfig(**(config_dict or {}))

        script = context.get("script", context.get("generated_content", ""))
        audio_data = context.get("audio_data")
        transcript = context.get("transcript", [])

        # Generate scene descriptions from script
        scenes = self._parse_scenes(script, transcript)

        try:
            # Try full video composition with moviepy
            result = await self._compose_with_moviepy(scenes, audio_data, config)
            return {
                "type": "video",
                "format": config.output_format,
                "duration_ms": result.duration_ms,
                "scenes": len(scenes),
                "file_size": result.file_size_bytes,
            }
        except ImportError:
            logger.warning("moviepy not installed — generating slideshow HTML instead")
            return await self._compose_html_slideshow(scenes, config)

    def _parse_scenes(
        self,
        script: str,
        transcript: list[dict],
    ) -> list[VideoScene]:
        """Parse script into individual scenes."""
        scenes: list[VideoScene] = []

        if transcript:
            for i, entry in enumerate(transcript):
                scenes.append(VideoScene(
                    scene_id=f"scene_{i+1}",
                    title=f"Scene {i+1}",
                    narration_text=entry.get("text", ""),
                    visual_description=entry.get("text", "")[:100],
                    duration_ms=entry.get("end_ms", 0) - entry.get("start_ms", 0),
                    subtitle_text=entry.get("text", ""),
                ))
        elif isinstance(script, str):
            paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()]
            avg_duration = 8000  # 8 seconds per scene
            for i, para in enumerate(paragraphs[:20]):
                scenes.append(VideoScene(
                    scene_id=f"scene_{i+1}",
                    title=f"Scene {i+1}",
                    narration_text=para,
                    visual_description=para[:100],
                    duration_ms=avg_duration,
                    subtitle_text=para[:200],
                ))

        return scenes or [VideoScene(
            scene_id="scene_1",
            title="Introduction",
            narration_text=str(script)[:500],
            visual_description="Title card",
            duration_ms=5000,
        )]

    async def _compose_with_moviepy(
        self,
        scenes: list[VideoScene],
        audio_data: Optional[bytes],
        config: VideoConfig,
    ) -> VideoResult:
        """Full video composition using moviepy."""
        from moviepy.editor import (
            TextClip, CompositeVideoClip, concatenate_videoclips,
            AudioFileClip, ColorClip,
        )

        clips = []
        for scene in scenes:
            duration_s = max(1, scene.duration_ms / 1000)

            bg = ColorClip(
                size=config.resolution,
                color=self._hex_to_rgb(config.background_color),
                duration=duration_s,
            )

            text = TextClip(
                scene.subtitle_text[:150] or scene.narration_text[:150],
                fontsize=config.font_size,
                color=config.text_color,
                size=(config.resolution[0] - 200, None),
                method="caption",
            ).set_duration(duration_s).set_position("center")

            clip = CompositeVideoClip([bg, text])
            clips.append(clip)

        final = concatenate_videoclips(clips, method="compose")

        # Overlay audio if available
        if audio_data:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp.write(audio_data)
                tmp_path = tmp.name
            audio_clip = AudioFileClip(tmp_path)
            final = final.set_audio(audio_clip)

        # Export
        output = tempfile.NamedTemporaryFile(suffix=f".{config.output_format}", delete=False)
        final.write_videofile(
            output.name,
            fps=config.fps,
            codec=config.codec,
            bitrate=config.bitrate,
            logger=None,
        )

        video_data = Path(output.name).read_bytes()

        return VideoResult(
            video_data=video_data,
            duration_ms=final.duration * 1000,
            format=config.output_format,
            scenes_count=len(scenes),
            file_size_bytes=len(video_data),
        )

    async def _compose_html_slideshow(
        self,
        scenes: list[VideoScene],
        config: VideoConfig,
    ) -> dict[str, Any]:
        """Fallback: generate an interactive HTML slideshow."""
        slides_html = []
        for i, scene in enumerate(scenes):
            slides_html.append(f"""
            <div class="slide" id="slide-{i}" style="display:{'flex' if i == 0 else 'none'}">
                <h2>{scene.title}</h2>
                <p>{scene.narration_text[:300]}</p>
            </div>""")

        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Nexus Video</title>
<style>
body {{ background: {config.background_color}; color: {config.text_color};
       font-family: Inter, sans-serif; margin: 0; display: flex;
       align-items: center; justify-content: center; height: 100vh; }}
.slide {{ text-align: center; padding: 4rem; max-width: 900px;
          flex-direction: column; align-items: center; justify-content: center; }}
h2 {{ color: {config.accent_color}; font-size: 2.5rem; margin-bottom: 1.5rem; }}
p {{ font-size: 1.3rem; line-height: 1.8; opacity: 0.9; }}
.controls {{ position: fixed; bottom: 2rem; display: flex; gap: 1rem; }}
button {{ padding: 0.75rem 2rem; border: 1px solid {config.accent_color};
          background: transparent; color: {config.text_color}; border-radius: 8px;
          cursor: pointer; font-size: 1rem; }}
button:hover {{ background: {config.accent_color}; }}
</style></head><body>
{"".join(slides_html)}
<div class="controls">
<button onclick="prev()">← Previous</button>
<button onclick="next()">Next →</button>
</div>
<script>
let current = 0; const total = {len(scenes)};
function show(i) {{ document.querySelectorAll('.slide').forEach((s,j) => s.style.display = j===i?'flex':'none'); }}
function next() {{ current = (current + 1) % total; show(current); }}
function prev() {{ current = (current - 1 + total) % total; show(current); }}
document.addEventListener('keydown', e => {{ if(e.key==='ArrowRight')next(); if(e.key==='ArrowLeft')prev(); }});
</script></body></html>"""

        return {
            "type": "slideshow",
            "format": "html",
            "content": html,
            "scenes": len(scenes),
        }

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

    # Public alias so callers and tests can discover the HTML slideshow fallback
    generate_html_slideshow = _compose_html_slideshow


# Global singleton
video_engine = VideoEngine()
