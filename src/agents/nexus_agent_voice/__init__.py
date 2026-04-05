"""
Nexus Agent Voice — TTS/Audio Production Agent
Source: Repo #9 (TTSProvider factory), Repo #1 (multi-speaker, voice blending)

Handles: Multi-speaker synthesis, segment concatenation, and audio export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from loguru import logger

from src.core.podcast_presets import normalize_podcast_config, resolve_voice_map
from src.infra.nexus_cost_tracker import UsageRecord, cost_tracker
from src.infra.nexus_obs_tracing import traced


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
            segments.append(
                DialogueSegment(
                    speaker=f"Person{speaker_idx}",
                    text=cleaned,
                    speaker_index=speaker_idx,
                )
            )

    # Fallback: if no tags found, treat each paragraph as a segment
    if not segments:
        paragraphs = [p.strip() for p in script.split("\n\n") if p.strip()]
        for i, para in enumerate(paragraphs):
            segments.append(
                DialogueSegment(
                    speaker=f"Person{(i % 2) + 1}",
                    text=para,
                    speaker_index=(i % 2) + 1,
                )
            )

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
    config = normalize_podcast_config(state.inputs.get("generation_config", {}))
    tenant_id = state.tenant_id

    default_voice_map = resolve_voice_map(config["speaker_profile"])
    # Allow explicit per-speaker overrides while keeping profile defaults.
    voice_map = {
        **default_voice_map,
        **state.inputs.get("generation_config", {}).get("voice_map", {}),
    }

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
                speed=config.get("speech_rate", 1.0),
                audio_format="mp3",
            )
            audio_segments.append(tts_response.audio_data)
            total_duration += tts_response.duration_seconds

            logger.debug(
                f"Segment {i + 1}/{len(segments)} synthesized",
                speaker=segment.speaker,
                voice=voice,
                duration_ms=tts_response.latency_ms,
            )

        except Exception as e:
            logger.error(f"TTS failed for segment {i + 1}: {e}")
            continue

    # Concatenate audio
    combined_audio = b"".join(audio_segments)

    await cost_tracker.record_usage(
        UsageRecord(
            tenant_id=tenant_id,
            user_id=state.user_id,
            model_name="tts",
            provider="tts",
            feature_id="3C",
            agent_id="voice_synthesizer",
            input_tokens=len(script),
            output_tokens=0,
            latency_ms=0,
        )
    )

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


class VoiceAgent:
    """Studio-facing facade over `synthesize_dialogue` (per-segment `AudioSegment` list)."""

    async def synthesize_script(
        self,
        *,
        script: Any,
        config: dict[str, Any],
        tenant_id: str,
    ) -> list[Any]:
        from src.core.nexus_audio_join import AudioSegment

        script_text = script
        if isinstance(script, dict):
            script_text = script.get("script", script.get("generated_content", ""))
        if not isinstance(script_text, str):
            script_text = str(script_text)

        from src.agents.nexus_model_layer import model_manager

        norm_config = normalize_podcast_config(config.get("generation_config", config))
        default_voice_map = resolve_voice_map(norm_config["speaker_profile"])
        voice_map = {**default_voice_map, **config.get("voice_map", {})}

        segments = parse_dialogue(script_text)
        if not segments:
            return []

        tts = await model_manager.provision_tts(tenant_id=tenant_id)
        out: list[Any] = []
        for segment in segments:
            voice = voice_map.get(segment.speaker, "alloy")
            try:
                tts_response = await tts.synthesize(
                    text=segment.text,
                    voice=voice,
                    speed=norm_config.get("speech_rate", 1.0),
                    audio_format="mp3",
                )
                out.append(
                    AudioSegment(
                        audio_data=tts_response.audio_data,
                        speaker=segment.speaker,
                        text=segment.text,
                        duration_ms=tts_response.duration_seconds * 1000,
                        format="mp3",
                    )
                )
            except Exception as e:
                logger.error(f"TTS failed for segment: {e}")
        return out


voice_agent = VoiceAgent()
