# AI MODEL REGISTRY — Nexus Notebook 11 LM
## v4.2 Mandatory Deliverable | Capability-Level Model Mapping

**Generated:** 2026-04-15
**Source:** Codebase audit of `src/agents/nexus_model_layer/__init__.py` (811 lines)
**Architecture:** Esperanto Pattern (ADR-1) — all models database-configurable, zero hardcoded

---

## Capability-Level Registry

| AI Capability | Provider(s) Supported | File, ~Line | Hardcoded or Configurable? | Local Alternative? | Cloud Fallback? |
|---|---|---|---|---|---|
| Text / LLM (general) | OpenAI, Anthropic, Google, Ollama | `src/agents/nexus_model_layer/__init__.py:~430-600` | **Configurable** — DB `ai_models` table, task_type="chat" | YES — Ollama (any GGUF model) | YES — all cloud providers |
| Text / LLM (structured output) | OpenAI, Anthropic, Google | Same as above, task_type="transformation" | **Configurable** — same DB table | YES — Ollama with JSON mode | YES |
| Text-to-Speech (TTS) | OpenAI TTS, ElevenLabs, Edge-TTS, Kokoro | `src/agents/nexus_model_layer/__init__.py:~650-700` | **Configurable** — DB + Settings | YES — Kokoro TTS (local) | YES — OpenAI/ElevenLabs |
| Speech-to-Text (STT) | OpenAI Whisper | `src/config.py:~95` (config only) | **Configurable** — Settings | YES — whisper.cpp (local) | YES — OpenAI Whisper API |
| Embedding model | OpenAI text-embedding | `src/agents/nexus_model_layer/__init__.py:~600-650` | **Configurable** — DB, task_type="embedding" | YES — Ollama embedding models | YES — OpenAI |
| Vector database | PostgreSQL + pgvector | `src/infra/nexus_data_persist/__init__.py` | **Configurable** — DATABASE_URL env | YES — local PostgreSQL | YES — managed Postgres |
| OCR / document vision | OpenAI Vision (GPT-4V) | `src/agents/nexus_agent_vision/__init__.py:~1-457` | **Configurable** — task_type="vision" | Partial — Ollama vision models | YES — OpenAI |
| Image generation | NOT IMPLEMENTED | — | — | — | — |
| Video generation | NOT IMPLEMENTED (frame assembly only) | `src/core/nexus_video_engine/__init__.py` | N/A — no AI model, just composition | N/A | N/A |
| Web search / retrieval API | NOT IMPLEMENTED | — | — | — | — |
| Re-ranking model | NOT IMPLEMENTED | — | — | — | — |

---

## Provider Registry

| Provider | Enum Value | Credential Source | Capabilities | Config Location |
|---|---|---|---|---|
| OpenAI | `OPENAI` | Vault (AES-256-GCM) or env `OPENAI_API_KEY` | Chat, Embedding, TTS, Vision, STT | DB `ai_credentials` + `src/config.py` |
| Anthropic | `ANTHROPIC` | Vault or env `ANTHROPIC_API_KEY` | Chat | DB `ai_credentials` + `src/config.py` |
| Google | `GOOGLE` | Vault or env `GOOGLE_API_KEY` | Chat | DB `ai_credentials` + `src/config.py` |
| Ollama | `OLLAMA` | No auth (local) | Chat, Embedding, Vision | `src/config.py:ollama_base_url` |
| ElevenLabs | `ELEVENLABS` | Vault or env `ELEVENLABS_API_KEY` | TTS | DB `ai_credentials` + `src/config.py` |
| Edge-TTS | `EDGE_TTS` | No auth (free) | TTS | Built-in |
| Kokoro | `KOKORO` | No auth (local) | TTS | `src/config.py:kokoro_tts_base_url` |
| LiteLLM | `LITELLM` | Varies by provider | Chat (proxy) | `src/config.py` |

---

## Model Selection Flow

```
User Request
    → Router identifies task_type (chat, embedding, tts, vision, etc.)
    → model_manager.provision_llm(tenant_id, task_type)
        → Look up tenant-specific default in DB
        → Fall back to system default
        → Resolve credentials from Vault
        → Return configured provider instance
```

**Key principle:** No model name appears in application code. All model selection is data-driven via the `ai_models` and `default_models` database tables.

---

## Vendor Lock-in Assessment

| Risk | Status | Mitigation |
|---|---|---|
| Hardcoded model names | **NONE FOUND** | All configurable via DB |
| Single-provider dependency | **NONE** | 4 LLM providers, 4 TTS providers, 2 embedding providers |
| Provider-specific API patterns | **MITIGATED** | BaseLLMProvider / BaseEmbeddingProvider / BaseTTSProvider abstractions |
| Credential coupling | **MITIGATED** | Vault-based credential storage with provider-agnostic interface |
| Local-first capability | **SUPPORTED** | Ollama + Kokoro provide fully offline operation |

---

## Seed Data (database/seeds/seed_models.py)

The database seeder provisions default models for new deployments. Models can be added/changed via the `/api/v1/models` API without code changes.

---

## NOT IMPLEMENTED (require original engineering)

1. **Image generation** — No AI image generation model integrated
2. **Web search API** — No search provider (Tavily/SerpAPI/Brave) integrated
3. **Re-ranking model** — No re-ranker for search result quality improvement
4. **Video AI** — Video engine does frame assembly only, no AI video generation
