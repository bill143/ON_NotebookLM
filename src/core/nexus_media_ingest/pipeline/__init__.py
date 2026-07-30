"""Vendored media pipeline from claude-video (github.com/bradautomates/claude-video, MIT).

Pure-stdlib modules orchestrating yt-dlp + ffmpeg + Whisper APIs:
- download:   yt-dlp wrapper (URL download + native caption fetch)
- frames:     ffmpeg keyframe/scene extraction with dedup
- transcribe: VTT parsing + timestamped transcript formatting
- whisper:    Groq / OpenAI Whisper clients with 25MB chunking

The modules are intentionally kept close to upstream for easy diffing; the
Nexus-facing wrapper lives in ``src.core.nexus_media_ingest``.
"""
