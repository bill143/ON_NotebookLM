"""
Nexus Agent Voice — TTS/Audio Production Agent
Source: Repo #9 (TTSProvider factory), Repo #1 (multi-speaker, voice blending)

Handles: Multi-speaker synthesis, segment concatenation, and audio export.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_cost_tracker import cost_tracker, UsageRecord


@dataclass
class DialogueSegment:
    """A single dialogue segment from a podcast script."""
    speaker: str
    text: str
    speaker_index: int


def parse_dialogue(script: str) -> list[DialogueSegment]:
    """
    Parse <Person1>/<Person2> tagged dialogue into segments.
    Source: Repo #9, tts/base.py ~L57-89 — split_qa pattern
    """
    segments = []
    pattern = r"<Person(\d+)>(.*?)</Person\1>"
    matches = re.findall(pattern, script, re.DOTALL)

    for idx_str, text in matches:
        speaker_idx = int(idx_str)
        cleaned = text.strip()
        if cleaned:
            segments.append(DialogueSegment(
                speaker=f"Person{speaker_idx}",
                text=cleaned,
                speaker_index=speaker_idx,
            ))

    # Fallback: if no tags found, treat each paragraph as a segment
    if not segments:
        paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            segments.append(DialogueSegment(
                speaker=f"Person{(i % 2) + 1}",
                text=para,
                speaker_index=(i % 2) + 1,
            ))

    return segments


@traced("agent.voice.synthesize_dialogue")
async def synthesize_dialogue(state: Any) -> dict[str, Any]:
    """
    Synthesize multi-speaker dialogue into audio.

    Pipeline:
    1. Parse script into dialogue segments
    2. Map speakers to voices
    3. Synthesize each segment via TTS provider
    4. Concatenate audio segments
    """
    from src.agents.nexus_model_layer import model_manager

    script = state.inputs.get("script", state.outputs.get("script_generator", {}).get("script", ""))
    config = state.inputs.get("generation_config", {})
    tenant_id = state.tenant_id

    # Voice mapping
    voice_map = config.get("voice_map", {
        "Person1": "alloy",
        "Person2": "nova",
        "Person3": "echo",
        "Person4": "onyx",
        "Person5": "fable",
        "Person6": "shimmer",
    })

    # Parse dialogue
    segments = parse_dialogue(script)
    if not segments:
        return {"error": "No dialogue segments found in script"}

    logger.info(f"Synthesizing {len(segments)} dialogue segments")

    # Provision TTS
    tts = await model_manager.provision_tts(tenant_id=tenant_id)

    # Synthesize each segment
    audio_segments: list[bytes] = []
    total_duration = 0.0

    for i, segment in enumerate(segments):
        voice = voice_map.get(segment.speaker, "alloy")

        try:
            tts_response = await tts.synthesize(
                text=segment.text,
                voice=voice,
                speed=config.get("speed", 1.0),
                format="mp3",
            )
            audio_segments.append(tts_response.audio_data)
            total_duration += tts_response.duration_seconds

            logger.debug(
                f"Segment {i+1}/{len(segments)} synthesized",
                speaker=segment.speaker,
                voice=voice,
                duration_ms=tts_response.latency_ms,
            )

        except Exception as e:
            logger.error(f"TTS failed for segment {i+1}: {e}")
            continue

    # Concatenate audio
    combined_audio = b"".join(audio_segments)

    await cost_tracker.record_usage(UsageRecord(
        tenant_id=tenant_id,
        user_id=state.user_id,
        model_name="tts",
        provider="tts",
        feature_id="3C",
        agent_id="voice_synthesizer",
        input_tokens=len(script),
        output_tokens=0,
        latency_ms=0,
    ))

    return {
        "audio_data": combined_audio,
        "format": "mp3",
        "duration_seconds": total_duration,
        "segment_count": len(audio_segments),
        "total_segments": len(segments),
    }


@traced("agent.voice.synthesize_single")
async def synthesize_single(
    text: str,
    *,
    voice: str = "alloy",
    speed: float = 1.0,
    tenant_id: str = "",
) -> bytes:
    """Synthesize a single text segment to audio."""
    from src.agents.nexus_model_layer import model_manager

    tts = await model_manager.provision_tts(tenant_id=tenant_id)
    response = await tts.synthesize(text=text, voice=voice, speed=speed)
    return response.audio_data
