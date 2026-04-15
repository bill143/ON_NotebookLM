# NEXUS NOTEBOOK 11 LM — BUILD PLAN
## Derived from NEXUS_DEPTH_AUDIT.md | Mapped to v4.2 5-Phase Roadmap

**Date:** 2026-04-15
**Baseline:** 485/489 unit tests passing, 55-60% v4.2 coverage
**Strategy:** Fix foundations first (Phase 0 gaps), then build outward by v4.2 phase order
**Vault:** LOCKED — no modifications

---

## PHASE 0 FOUNDATION GAPS (v4.2 Phase 0 — must complete first)

These are Phase 0 requirements per v4.2 that exist but have issues:

| # | Gap | Module | Action | Priority | Est. Tests |
|---|-----|--------|--------|----------|------------|
| 0.1 | Fix asyncio deprecation | nexus_obs_tracing:228 | Replace `asyncio.iscoroutinefunction` with `inspect.iscoroutinefunction` | P0 | Existing 334-line suite |
| 0.2 | Fix pypdf dependency | pyproject.toml | Add `pypdf>=4.0` to dependencies | P0 | Fixes 2 failing tests |
| 0.3 | Fix event loop compat | test_worker.py | Update `run_async()` for Python 3.14 | P0 | Fixes 2 failing tests |
| 0.4 | Wire Sentry init | main.py lifespan | Add `sentry_sdk.init()` from config | P0 | Integration test |
| 0.5 | Prometheus alert rules | deploy/prometheus.yml | Add basic alert definitions | P1 | Manual verify |

**Completion criteria:** All 489 unit tests pass, zero deprecation warnings

---

## PHASE 1 CORE INTELLIGENCE (v4.2 Phase 1 — Tier 1 Critical)

### 1.1 Missing API Routers (5 new routers)

| Router | v4.2 Feature | Endpoints | Integration Points |
|--------|-------------|-----------|-------------------|
| `/api/v1/brain` | 5A-5D | GET/POST flashcards, POST review, GET progress, GET due-cards | nexus_brain_knowledge, data_persist |
| `/api/v1/plugins` | 8A-8D | GET/POST plugins, POST enable/disable, GET registry | nexus_plugin_bridge, vault_keys |
| `/api/v1/local` | 12A-12E | GET models, POST sync, GET sync-status, GET feature-matrix | nexus_local_sync, model_layer |
| `/api/v1/prompts` | 14A-14B | GET/POST prompts, GET versions, POST rollback | nexus_prompt_registry |
| `/api/v1/admin` | 9D, 7E | POST backup, POST restore, GET audit-log | data_persist |

**Tests per router:** 8-12 unit tests + 1 integration test each

### 1.2 AI Model Registry (v4.2 mandatory deliverable)

Must produce `AI_MODEL_REGISTRY.md` documenting:
- All model references found in codebase with file:line citations
- Hardcoded vs configurable status for each
- Local alternative availability
- Cloud fallback chain

### 1.3 Web Search Integration (Feature 2A)

| Component | Implementation |
|-----------|---------------|
| Provider | Tavily Search API (free tier available, LangChain integration) |
| Fallback | DuckDuckGo search via `duckduckgo-search` package |
| Integration | Add to nexus_research_grounding as `web_search` phase |
| Config | `TAVILY_API_KEY` in Settings, optional |

### 1.4 Citation Export (Feature 2C)

Add to research router:
- `GET /api/v1/research/sessions/{id}/citations?format=bibtex|json|markdown`
- BibTeX, JSON-LD, Markdown inline format

### 1.5 Wire VisionAgent to Source Ingest (Feature 4C-4D)

- Add OCR extraction path in source_ingest for image-type sources
- Wire `VisionAgent.extract_table()` and `extract_chart()` into processing chain
- Add `source_type: "image_ocr"` support

---

## PHASE 2 AI DEPTH (v4.2 Phase 2)

### 2.1 Interactive "Join" Audio Mode (Feature 3A — largest new build)

| Component | Design |
|-----------|--------|
| Architecture | WebSocket endpoint `/ws/audio-join` |
| Flow | User speaks → STT → inject into conversation → LLM response → TTS → stream back |
| STT Provider | Whisper (OpenAI API or local whisper.cpp) |
| Interrupt Handling | Cancel current TTS stream, inject user turn, re-prompt LLM |
| Latency Target | <2s end-to-end (STT + LLM + TTS) |
| Fallback | If STT unavailable, text-only "Join" via WebSocket chat |

### 2.2 Prompt/Response Cache (Feature 11C)

| Component | Design |
|-----------|--------|
| Cache Layer | Redis with TTL (5 min default) |
| Key Strategy | SHA-256 hash of (prompt_template_version + rendered_variables) |
| Integration | Wrap model_manager.provision_llm() calls |
| Cache Hit Metric | Prometheus counter `nexus_cache_hits_total` |

### 2.3 Model Cost Routing (Feature 11D)

| Component | Design |
|-----------|--------|
| Router Logic | In model_layer: if estimated_tokens < 500 → use cheap model, else → use primary |
| Config | `default_cheap_model` in Settings |
| Criteria | Token estimate, task complexity flag, user override |

### 2.4 Source Conflict Detection (Feature 4E)

- Compare embeddings of overlapping content across sources
- Flag contradictions when cosine similarity is high but semantic meaning differs
- Surface in chat responses and research output

### 2.5 Adaptive Difficulty (Feature 5D)

- Track review accuracy per card difficulty
- Adjust FSRS parameters based on performance trends
- Expose difficulty stats in brain API

---

## PHASE 3 PLATFORM LAYER (v4.2 Phase 3)

### 3.1 Plugin System Completion (Feature 8)

- Persist plugin registry to database (new `plugins` table)
- Subprocess sandboxing for plugin execution
- Semver compatibility checking
- Plugin event bus (emit/subscribe pattern)

### 3.2 Local-First Completion (Feature 12)

- Wire sync queue to API endpoint
- Local storage encryption (Fernet for local DB files)
- Feature degradation UI indicators
- Model download management for Ollama

### 3.3 Data Export & Compliance (Feature 9E)

- GDPR erasure endpoint: `DELETE /api/v1/users/{id}/data`
- Full notebook export as ZIP (sources + artifacts + chat history)
- Artifact versioning table + diff API

### 3.4 Prompt Testing Framework (Feature 14C)

- Golden-set test cases per prompt template
- Automated regression detection on prompt changes
- Quality scoring with LLM-as-judge pattern

---

## PHASE 4 PRODUCTION HARDENING (v4.2 Phase 4)

### 4.1 E2E Test Suite

- Playwright for browser testing
- Smoke test: create notebook → upload PDF → generate podcast → chat → export
- Run in CI on every PR

### 4.2 Security Hardening

- Input sanitization for file uploads (zip bomb detection, SSRF protection)
- CSP headers in frontend
- Rate limiting on all public endpoints (already have RateLimiter in vault)

### 4.3 Performance

- SLA definitions (p50 < 200ms API, p95 < 2s AI calls)
- k6 load test scripts
- Connection pool tuning

### 4.4 Docker Hardening

- Automated pg_dump backup cron in docker-compose
- Grafana dashboard JSON provisioning
- Health check all containers

---

## PHASE 5 UI/UX POLISH (v4.2 Phase 5)

### 5.1 Frontend Rebuild (largest work item)

The frontend needs major expansion from 3 components to a full NLM-class application.

**Component Inventory Required:**

| Component | v4.2 Feature | Priority |
|-----------|-------------|----------|
| StudioPanel | 1A-1E | P0 — artifact generation, queue, download |
| AudioPlayer | 3C-3D | P0 — playback, streaming, waveform |
| BrainPanel | 5A-5D | P1 — flashcards, review, progress |
| SourceUpload | 4B | P0 — drag-drop, progress, type selection |
| ChatPanel (enhanced) | 5C, 6E | P0 — inline citations, retry, streaming |
| CollabPresence | Collab | P2 — user avatars, cursors |
| OnboardingFlow | 6C | P2 — first-run, empty states |
| CommandPalette | 6D | P2 — keyboard shortcuts, search |
| ThemeToggle | 6A | P1 — dark/light mode |
| ErrorBoundary | 6E | P1 — global error handling |
| ModelSelector | 15C | P1 — provider/model picker |
| PluginManager | 8A | P3 — plugin install/config UI |

### 5.2 Mobile Responsive

- Sidebar collapse on mobile
- Touch-friendly controls
- Responsive breakpoints

---

## EXECUTION ORDER (sequential with parallelizable items noted)

```
BATCH 1 (Foundation — do first, serial):
  0.1 Fix asyncio deprecation
  0.2 Fix pypdf dependency
  0.3 Fix event loop tests
  0.4 Wire Sentry
  → GATE: All 489 tests pass ✅

BATCH 2 (Routers + Registry — parallelizable):
  1.1a Brain router
  1.1b Plugin router
  1.1c Local router
  1.1d Prompts router
  1.1e Admin router
  1.2  AI Model Registry document
  → GATE: 5 new routers with tests, registry document ✅

BATCH 3 (Feature Depth — parallelizable):
  1.3 Web search integration
  1.4 Citation export
  1.5 Vision/OCR wiring
  2.2 Prompt/response cache
  2.3 Model cost routing
  → GATE: Research has web search, sources have OCR, cache working ✅

BATCH 4 (Complex Features — serial):
  2.1 Interactive Join audio mode
  2.4 Source conflict detection
  2.5 Adaptive difficulty
  → GATE: Join mode functional, brain adaptive ✅

BATCH 5 (Platform — parallelizable):
  3.1 Plugin persistence
  3.2 Local-first wiring
  3.3 Export/compliance
  3.4 Prompt testing
  → GATE: All 15 domains have backend coverage ✅

BATCH 6 (Frontend — serial, largest batch):
  5.1 Full frontend rebuild
  5.2 Mobile responsive
  → GATE: All features accessible in browser ✅

BATCH 7 (Hardening — parallelizable):
  4.1 E2E tests
  4.2 Security hardening
  4.3 Performance testing
  4.4 Docker hardening
  → GATE: All verification criteria from mission brief pass ✅
```

---

## DATA CONTRACTS REFERENCED

| Integration | Producer | Consumer | Contract |
|------------|----------|----------|----------|
| Cost wrapping | All agents | nexus_cost_tracker | UsageRecord dataclass |
| Auth injection | nexus_vault_keys | All routers | AuthContext + get_current_user |
| Prompt resolution | nexus_prompt_registry | All agents | resolve(name, version, variables) |
| Trace propagation | nexus_obs_tracing | All modules | @traced decorator + trace_id_var |
| Queue dispatch | API routers | Celery worker | generate_artifact task signature |
| Model provision | nexus_model_layer | All agents | model_manager.provision_llm/embedding/tts |

---

## ASSUMPTIONS (documented per mission brief)

1. **SurrealDB vs PostgreSQL:** v4.2 references SurrealDB via Open-Notebook. The existing codebase uses PostgreSQL with pgvector. **Decision: Keep PostgreSQL.** It's production-proven, has 4 Alembic migrations, RLS-ready schema, and full async support. Re-platforming to SurrealDB would be a regression. The Open-Notebook SurrealDB patterns are extracted as architectural guidance, not as a migration target.

2. **Supabase Auth vs custom JWT:** Existing code uses custom JWT via vault_keys. v4.2 mentions Supabase SSR. **Decision: Keep custom JWT** since vault_keys is verified complete and handles all auth/RBAC/tenant isolation. Supabase can be added as an optional auth provider later.

3. **Celery vs fire-and-forget:** Open-Notebook uses SurrealDB commands as a job queue. Existing code uses Celery with Redis. **Decision: Keep Celery** — it's more mature for production workloads with monitoring (Flower), retry logic, and dead-letter queues.

---

**Proceeding to Phase 2 Execution automatically.**
