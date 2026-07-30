"""Unit tests for nexus_video_engine (HTML fallback and parsing)."""

from __future__ import annotations

import pytest

from src.core.nexus_video_engine import (
    VideoConfig,
    VideoEngine,
    VideoScene,
    video_engine,
)


def test_hex_to_rgb() -> None:
    assert VideoEngine._hex_to_rgb("#010203") == (1, 2, 3)


def test_parse_scenes_from_transcript() -> None:
    eng = VideoEngine()
    tr = [
        {"text": "hello", "start_ms": 0, "end_ms": 1000},
        {"text": "world", "start_ms": 1000, "end_ms": 2500},
    ]
    scenes = eng._parse_scenes("", tr)
    assert len(scenes) == 2
    assert scenes[0].scene_id == "scene_1"
    assert scenes[0].duration_ms == 1000


def test_parse_scenes_from_script_paragraphs() -> None:
    eng = VideoEngine()
    script = "First block.\n\nSecond block.\n\n"
    scenes = eng._parse_scenes(script, [])
    assert len(scenes) == 2
    assert "First" in scenes[0].narration_text


def test_parse_scenes_empty_uses_fallback() -> None:
    eng = VideoEngine()
    scenes = eng._parse_scenes("", [])
    assert len(scenes) == 1
    assert scenes[0].scene_id == "scene_1"


@pytest.mark.asyncio
async def test_compose_import_error_uses_html_slideshow(monkeypatch: pytest.MonkeyPatch) -> None:
    eng = VideoEngine()

    async def _raise(*_a: object, **_kw: object) -> None:
        raise ImportError("moviepy missing")

    monkeypatch.setattr(eng, "_compose_with_moviepy", _raise)
    out = await eng.compose({"script": "A\n\nB"}, {"output_format": "mp4"})
    assert out["type"] == "slideshow"
    assert out["format"] == "html"
    assert "slide" in out["content"]
    assert out["scenes"] == 2


@pytest.mark.asyncio
async def test_generate_html_slideshow_wrapper() -> None:
    eng = VideoEngine()
    scenes = [
        VideoScene("1", "T", "narration", "vis", duration_ms=1000, subtitle_text="sub"),
    ]
    cfg = VideoConfig()
    out = await eng.generate_html_slideshow(scenes, cfg)
    assert out["scenes"] == 1
    assert "Nexus Video" in out["content"]


def test_singleton_video_engine() -> None:
    assert isinstance(video_engine, VideoEngine)
