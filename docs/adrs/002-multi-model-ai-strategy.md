# ADR-002: Multi-Model AI Strategy with Budget Controls

**Status:** Accepted  
**Date:** 2026-03-30

## Context

Nexus uses multiple AI providers (Google, OpenAI, Anthropic, local/Ollama) for different capabilities.
Without governance, costs can spiral and vendor lock-in becomes a risk.

## Decision

1. **Model Registry**: All models are registered in `ai_models` table with cost metadata
2. **Budget Engine**: Per-user monthly budget with 80% warning and 100% hard stop
3. **Provider Abstraction**: `AIGateway` routes requests through a unified interface
4. **Local Fallbacks**: Every cloud capability has a documented local alternative
5. **Usage Tracking**: Every token is logged to `ai_usage_log` with cost attribution

## Cost Model

| Capability | Primary | Local Fallback |
|------------|---------|----------------|
| Chat/Research | Gemini 2.5 Flash | Ollama/Llama 3.3 |
| Embedding | text-embedding-3-small | nomic-embed-text |
| TTS | ElevenLabs | Kokoro/Edge TTS |
| Vision | Gemini 2.5 Pro | Ollama/Llava |

## Consequences

### Positive
- No surprise bills
- Can operate fully offline with local models
- Clear cost attribution per feature

### Negative
- Additional complexity in model routing
- Local models have lower quality
- Budget enforcement adds latency (one Redis check per request)
