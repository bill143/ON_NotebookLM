# Coverage Gate Rationale — NEXUS Chat

## Decision

CI coverage gate set to 65% (not 80%) with explicit module omissions for infrastructure-bound code.

## Rationale

The following modules are excluded from the unit test coverage gate because they cannot be meaningfully tested without live infrastructure dependencies:

| Module | Lines (approx.) | Dependency | Coverage Path |
|--------|-------------------|------------|---------------|
| `src/agents/nexus_agent_vision` | 163 | OpenAI Vision API + image processing | Integration tests |
| `src/infra/nexus_local_sync` | 113 | Device sync / offline-first state machine | E2E tests |
| `src/infra/nexus_plugin_bridge` | 102 | Plugin sandbox execution environment | Integration tests |
| `src/core/nexus_audio_join` | 237 | ffmpeg binary + pydub I/O | Integration tests |
| `src/infra/nexus_test_harness` | 115 | Meta-testing infrastructure | Self-validating |

Paths are configured under `[tool.coverage.run] omit` in `pyproject.toml`. Vision and audio join live under `src/agents/` and `src/core/` respectively (not under `src/infra/`), matching the repository layout.

## What IS covered at 65%+

- All FastAPI route handlers (`src/api/`)
- All business logic (`src/core/` — excluding `nexus_audio_join`)
- All infrastructure utilities (`src/infra/` — non-excluded packages)
- Worker task dispatch and retry logic (`src/worker.py`)
- WebSocket broker (`src/infra/nexus_ws_broker/`)
- Vault key encryption/decryption (`src/infra/nexus_vault_keys/`)
- Data persistence layer (`src/infra/nexus_data_persist/`)
- Agent orchestration, model layer, content/embed/voice agents (non-vision)
- Export engine paths (`src/core/nexus_export_engine/`)
- Source ingest paths (`src/core/nexus_source_ingest/`)
- Research grounding paths (`src/core/nexus_research_grounding/`)

## Coverage Roadmap

| Milestone | Target | When |
|-----------|--------|------|
| Current sprint | 65% unit tests | Now |
| Post-Docker verification | 70% unit + integration | Month 1 |
| Stable production | 80% full suite | Month 3 |

## Review Cadence

This decision is reviewed quarterly. If any excluded module accumulates production bugs, it is immediately prioritized for mock infrastructure and added back to the coverage scope.

## Approved by

Bill Asmar — Preconstruction Executive / Platform Owner  
Date: 2026-04-05
