# Media Ingest — Video & Audio Sources + Meeting Minutes

**Added:** 2026-07-30 · **Module:** `src/core/nexus_media_ingest/`

Nexus can now ingest **audio files (mp3/wav/m4a/…), video files (mp4/mov/mkv/webm/…),
and video URLs** (YouTube, Vimeo, TikTok, X — anything yt-dlp supports) as first-class
sources, and generate a **Meeting Minutes** studio artifact from them.

## What it fixes / adds

- Audio mimes (`audio/mpeg` etc.) were accepted at upload but mapped to source_type
  `"upload"`, which had **no extractor** — processing failed downstream. They now route
  to a real transcription path.
- The old `youtube` source type is caption-only and fails on caption-less videos. The
  new `video` type covers hundreds of sites, falls back to Whisper, and also extracts
  keyframes for future vision analysis.
- New `meeting_minutes` artifact: structured minutes (overview, attendees, per-topic
  discussion, decisions table, action-items table with owners, open issues, follow-ups)
  with every item cited to a `[MM:SS]` timestamp.

## How it works

```
source (file or URL)
  └─ nexus_source_ingest  ("video" | "audio")
       └─ nexus_media_ingest.MediaExtractor        (async, runs in a thread)
            ├─ URL:   yt-dlp captions first (free) → download if needed
            ├─ File:  ffmpeg audio extract → Whisper API (Groq preferred, OpenAI fallback)
            ├─ Video: ffmpeg keyframes (≤50) → <storage>/media/<digest>/frames + manifest.json
            └─ returns timestamped transcript "[MM:SS] line"
  └─ full_text ← transcript  (RAG embedding + chat work as with any source)
  └─ studio queue: artifact_type="meeting_minutes"
       └─ content agent → prompt registry "studio/meeting_minutes" → model layer
          (Esperanto: task_type="transformation", DB-configured provider)
```

Vendored pipeline (`src/core/nexus_media_ingest/pipeline/`) comes from
[claude-video](https://github.com/bradautomates/claude-video) (MIT) — pure-stdlib,
kept close to upstream for easy diffing (ruff per-file-ignores cover it).

## Requirements

| Need | For | Install |
|---|---|---|
| `ffmpeg` + `ffprobe` on PATH | all media | `winget install Gyan.FFmpeg` / `apt install ffmpeg` |
| `yt-dlp` (now a project dependency) | URLs | comes with `pip install -e .` |
| `GROQ_API_KEY` (preferred) or `OPENAI_API_KEY` | Whisper fallback — required for local files and caption-less URLs | env or Settings (`openai_api_key`) |

Behind a TLS-inspecting corporate proxy, `pip-system-certs` (auto-installed on
Windows via pyproject marker) makes Python trust the Windows cert store — without it
yt-dlp/Whisper fail with `CERTIFICATE_VERIFY_FAILED`.

## Usage

**Upload:** `POST /api/v1/sources/upload` with an mp3/mp4/etc. — mime (or extension
fallback) maps to source_type `audio`/`video`; media files get a 1 GB budget
(`MAX_MEDIA_FILE_SIZE_MB`) instead of the 100 MB document limit.

**URL:** create a source with `source_type: "video"` and the URL in `asset_url`.

**Minutes:** submit a studio job with `artifact_type: "meeting_minutes"`. Optional
config keys: `meeting_title`, `meeting_date`, `attendees_hint`, `focus`.

## Test coverage

`tests/unit/test_media_ingest.py` — 17 tests (extension mapping, extractor flows,
routing, upload mime/size rules, artifact registration, generator + dispatch).
Full unit suite after integration: **595 passed**; the one failure
(`test_slide_engine.py::test_generate_returns_expected_keys`) pre-dates this change
(fails on the pristine tree — python-pptx drift).

## Deliberate scope cuts (Phase 2 candidates)

- **Frames → vision agent:** keyframes + `manifest.json` are already written per
  video, but nothing consumes them yet. Next step: feed them through
  `nexus_agent_vision` (register a vision-capable Anthropic model in the registry —
  currently Anthropic is Chat-only and the vision row cites GPT-4V-era naming).
- **Speaker diarization:** Whisper API returns text segments, not speakers; the
  minutes prompt therefore uses "Speaker N" unless names appear in the audio.
- **STT through the model layer:** Whisper keys are read from env/Settings
  (registry lists STT as "config only"); when STT joins Esperanto, swap
  `MediaExtractor._seed_whisper_env` for a provision call.
- **Frontend:** the upload panel's accepted-types list and an artifact card for
  minutes need the corresponding frontend additions.
