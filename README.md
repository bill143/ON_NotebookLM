# 🧠 Nexus Notebook 11 LM

> **Codename: ESPERANTO** — Provider-agnostic, production-grade NotebookLM module

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16+-336791.svg)](https://postgresql.org)
[![License](https://img.shields.io/badge/License-Proprietary-red.svg)]()

---

## Overview

Nexus Notebook 11 LM is a production-grade AI-powered research and learning platform that synthesizes the best patterns from 9 open-source NotebookLM implementations into a single, unified, enterprise-ready module. The system is designed as a modular component for the ONeill Web Portal.

### Key Differentiators

- **🔄 Esperanto Pattern (ADR-1)**: Provider-agnostic AI model abstraction — zero vendor lock-in
- **🔒 Multi-tenant Isolation**: PostgreSQL RLS with per-request tenant context injection
- **💰 Cost Engine**: Per-request token accounting with budget enforcement
- **🎙️ Multi-Speaker Audio**: Podcast-style content generation with local TTS support
- **🧠 FSRS-4.5 Spaced Repetition**: Scientifically-backed learning retention
- **🔌 Plugin Architecture**: Event-driven extensibility with sandboxed execution
- **📡 Local-First**: Full offline operation with Ollama + Kokoro TTS
- **🔬 Deep Research**: Multi-turn LangGraph research with checkpoint persistence
- **📊 Export Engine**: PDF, DOCX, EPUB, Markdown, HTML conversion
- **🎬 Video & Slides**: MoviePy composition + branded PPTX generation
- **👥 Real-Time Collab**: WebSocket-based presence, cursors, and locking
- **🏭 Studio Queue**: 12+ artifact types via Celery pipeline with progress streaming

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     NEXUS NOTEBOOK 11 LM                     │
├─────────────────────────────────────────────────────────────┤
│                        API LAYER                             │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │Notebooks │ Sources  │Artifacts │  Chat    │  Models  │  │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┘  │
├───────┼──────────┼──────────┼──────────┼──────────┼─────────┤
│                     AGENT LAYER                              │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐  │
│  │ Content  │Researcher│  Voice   │  Embed   │  Vision  │  │
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┘  │
│       └──────────┴──────────┴──────────┴──────────┘         │
│                    ORCHESTRATOR (LangGraph)                   │
├─────────────────────────────────────────────────────────────┤
│                     CORE LAYER                               │
│  ┌──────────┬──────────┬──────────┬──────────┐             │
│  │Source    │Brain     │Studio    │Export    │              │
│  │Ingest   │Knowledge │Queue     │Engine   │              │
│  └──────────┴──────────┴──────────┴──────────┘             │
├─────────────────────────────────────────────────────────────┤
│                   INFRA LAYER                                │
│  ┌───────┬───────┬───────┬───────┬───────┬───────┬───────┐ │
│  │Persist│Vault  │Cost   │Prompt │Plugin │  Obs  │ Local │ │
│  │(DB)   │(Auth) │Track  │Regist │Bridge │Trace  │ Sync  │ │
│  └───────┴───────┴───────┴───────┴───────┴───────┴───────┘ │
├─────────────────────────────────────────────────────────────┤
│                   MODEL LAYER (ESPERANTO)                     │
│  ┌──────────┬──────────┬──────────┬──────────┐             │
│  │ OpenAI   │Anthropic │ Google   │ Ollama   │ ← Providers │
│  └──────────┴──────────┴──────────┴──────────┘             │
│  ┌──────────┬──────────┬──────────┐                        │
│  │AIFactory │ModelMgr  │CostTrack │ ← Abstractions         │
│  └──────────┴──────────┴──────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16+ with `pgvector` extension
- Redis 7+
- Docker & Docker Compose (recommended)

### 1. Clone & Setup

```bash
cp .env.example .env
# Edit .env with your API keys and database credentials
```

### 2. Start Infrastructure

```bash
# Core services only
docker compose -f deploy/docker-compose.yml up -d

# With local AI models (Ollama + Kokoro TTS)
docker compose -f deploy/docker-compose.yml --profile local-ai up -d
```

### 3. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 4. Run Database Migrations

```bash
# The initial schema is auto-applied by Docker Compose
# For manual setup:
psql -U nexus -d nexus_notebook_11 -f database/schema/001_initial.sql
```

### 5. Start the Application

```bash
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### 6. Verify

```bash
# Health check
curl http://localhost:8000/health/ready

# API docs
open http://localhost:8000/api/docs
```

---

## Project Structure

```
NEXUS NOTEBOOK LM MAIN/
├── src/
│   ├── main.py                          # FastAPI entry point
│   ├── config.py                        # Pydantic settings
│   ├── exceptions.py                    # Error taxonomy (20+ types)
│   ├── api/                             # REST API routes
│   │   ├── notebooks.py                 # CRUD + source linking
│   │   ├── sources.py                   # Upload, ingest, search
│   │   ├── artifacts.py                 # Generation queue
│   │   ├── chat.py                      # Conversational Q&A
│   │   └── models.py                    # Model registry
│   ├── agents/                          # AI Agent Layer
│   │   ├── nexus-model-layer/           # ESPERANTO — provider abstraction
│   │   ├── nexus-agent-orchestrator/    # Chain executor (LangGraph)
│   │   ├── nexus-agent-content/         # Content generation
│   │   ├── nexus-agent-researcher/      # Deep research + citation
│   │   ├── nexus-agent-voice/           # Multi-speaker TTS
│   │   └── nexus-agent-embed/           # Vectorization
│   ├── core/                            # Business Logic
│   │   ├── nexus-source-ingest/         # Multi-format extraction
│   │   ├── nexus-brain-knowledge/       # FSRS-4.5 learning system
│   │   ├── nexus-studio-queue/          # 12-type artifact pipeline
│   │   ├── nexus-research-engine/       # LangGraph multi-turn research
│   │   ├── nexus-export-engine/         # PDF/DOCX/EPUB converter
│   │   ├── nexus-collab-ws/             # WebSocket collaboration hub
│   │   ├── nexus-video-engine/          # MoviePy + HTML slideshow
│   │   ├── nexus-slide-engine/          # Branded PPTX generation
│   │   ├── nexus-audio-engine/          # Cross-fade + SRT transcripts
│   │   ├── nexus-vision-agent/          # PDF/image/diagram analysis
│   │   └── nexus-ui-shell/              # Keyboard/toast/command palette
│   └── infra/                           # Infrastructure
│       ├── nexus-data-persist/          # Database + repositories
│       ├── nexus-vault-keys/            # Auth + encryption
│       ├── nexus-cost-tracker/          # Budget enforcement
│       ├── nexus-obs-tracing/           # Logging + metrics
│       ├── nexus-prompt-registry/       # Versioned prompts
│       ├── nexus-plugin-bridge/         # Plugin architecture
│       └── nexus-local-sync/            # Offline-first sync
├── frontend/                            # Next.js 14 (shadcn/ui)
│   ├── src/app/page.tsx                 # Main application page
│   ├── src/components/                  # Research, Notes, Settings panels
│   ├── src/lib/api.ts                   # Typed HTTP/WS client
│   └── src/lib/store.ts                 # Zustand state management
├── database/
│   ├── schema/001_initial.sql           # PostgreSQL DDL (16+ tables)
│   └── migrations/versions/             # Alembic migrations
├── tests/
│   └── test_integration.py              # Full integration test suite
├── prompts/                             # Prompt templates
├── deploy/
│   ├── Dockerfile                       # Multi-stage (dev + prod)
│   ├── docker-compose.yml               # Full stack (12 services)
│   └── prometheus.yml                   # Monitoring config
├── docs/
│   ├── deployment-runbook.md            # Ops guide
│   └── adrs/                            # Architecture decisions
├── .github/workflows/ci.yml             # CI/CD pipeline
├── pyproject.toml                       # Python project config
└── alembic.ini                          # Migration config
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/notebooks` | Create notebook |
| `GET` | `/api/v1/notebooks` | List notebooks |
| `GET` | `/api/v1/notebooks/:id` | Get notebook with sources |
| `POST` | `/api/v1/sources/upload` | Upload file source |
| `POST` | `/api/v1/sources/from-url` | Create from URL |
| `POST` | `/api/v1/sources/search` | Hybrid vector+text search |
| `POST` | `/api/v1/artifacts` | Queue artifact generation |
| `POST` | `/api/v1/chat` | Send chat message |
| `POST` | `/api/v1/chat/stream` | Stream chat via SSE |
| `POST` | `/api/v1/research` | Multi-turn deep research |
| `GET` | `/api/v1/research/sessions` | List research sessions |
| `POST` | `/api/v1/export` | Export content (PDF/DOCX/EPUB) |
| `GET` | `/api/v1/export/formats` | Available export formats |
| `GET` | `/api/v1/brain/flashcards/due` | FSRS due flashcards |
| `POST` | `/api/v1/brain/flashcards/:id/review` | Review flashcard |
| `POST` | `/api/v1/models` | Register AI model |
| `POST` | `/api/v1/models/credentials` | Store encrypted API key |
| `GET` | `/api/v1/models/usage/summary` | Usage statistics |
| `GET` | `/api/v1/models/usage/budget` | Budget status |
| `WS` | `/api/v1/ws/chat` | Real-time chat streaming |
| `WS` | `/api/v1/ws/collab` | Collaboration presence |
| `GET` | `/health/ready` | Readiness probe |
| `GET` | `/metrics` | Prometheus metrics |

---

## Architecture Decision Records

| ADR | Decision | Source |
|-----|----------|--------|
| ADR-1 | Esperanto Pattern (provider abstraction) | Repo #7 |
| ADR-2 | PostgreSQL + pgvector (unified storage) | Repo #7, #5 |
| ADR-3 | LangGraph (agent orchestration) | Repo #7 |
| ADR-4 | OpenAI-compatible TTS abstraction | Repo #9, #1 |
| ADR-5 | Supabase SSR auth | Repo #6 |
| ADR-6 | Prompt versioning via DB | Repo #7, #9 |
| ADR-7 | Local-first via OpenAI-compatible APIs | Repo #1, #8 |
| ADR-8 | Hierarchical error taxonomy | Repo #5, #7 |
| ADR-9 | LangGraph checkpointing | Repo #7 |
| ADR-10 | Monorepo with domain-scoped modules | All repos |

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.11+, FastAPI, Uvicorn |
| **Frontend** | Next.js 14, TypeScript, Zustand, shadcn/ui |
| **Database** | PostgreSQL 16 + pgvector + pg_trgm |
| **Cache/Broker** | Redis 7 (cache + Celery broker) |
| **Async Tasks** | Celery 5 (workers, beat, flower) |
| **AI Orchestration** | LangGraph |
| **AI Providers** | OpenAI, Anthropic, Google, Ollama |
| **TTS** | OpenAI TTS, ElevenLabs, Kokoro (local) |
| **Export** | ReportLab (PDF), python-docx, ebooklib (EPUB) |
| **Video/Slides** | MoviePy, python-pptx |
| **Auth** | JWT (HS256), AES-256-GCM with Argon2id KDF, tenant RLS |
| **Observability** | Loguru, Prometheus, Grafana, Sentry |
| **CI/CD** | GitHub Actions (lint, test, build, scan) |
| **Deploy** | Docker (multi-stage), Docker Compose |

---

## License

Proprietary — ONeill Contractors, Inc. All rights reserved.
