# Nexus Notebook 11 LM — Deployment Runbook

## Prerequisites

| Component | Version | Purpose |
|-----------|---------|---------|
| Docker | 24+ | Container runtime |
| Docker Compose | 2.20+ | Service orchestration |
| Node.js | 20 LTS | Frontend build |
| Python | 3.11+ | Backend runtime |
| PostgreSQL | 16+ | Database (via pgvector) |
| Redis | 7+ | Cache/broker |

## Quick Start (Development)

```bash
# 1. Clone and configure
git clone <repo> && cd nexus-notebook-lm
cp .env.example .env    # Edit with your API keys

# 2. Start infrastructure
docker compose -f deploy/docker-compose.yml up -d postgres redis

# 3. Apply database schema
PGPASSWORD=nexus_dev_2024 psql -h localhost -U nexus -d nexus_notebook_11 \
  -f database/schema/001_initial.sql

# 4. Run migrations
alembic upgrade head

# 5. Seed AI models
python -m database.seeds.seed_models

# 6. Start backend
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000

# 7. Start frontend
cd frontend && npm install && npm run dev
```

## Production Deployment

### Full Stack (Docker Compose)

```bash
# All services including Celery, monitoring
docker compose -f deploy/docker-compose.yml \
  --profile monitoring \
  --profile frontend \
  up -d --build

# Verify
docker compose ps
curl http://localhost:8000/health/ready
```

### Scaling Workers

```bash
# Scale Celery workers for high throughput
docker compose -f deploy/docker-compose.yml \
  up -d --scale nexus-worker=4
```

### Database Migrations

```bash
# Generate new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Service Architecture

```
┌──────────────────┐     ┌──────────────────┐
│   Next.js 14     │────▶│   FastAPI App     │
│   (Port 3000)    │     │   (Port 8000)     │
└──────────────────┘     └────────┬──────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼              ▼
             ┌───────────┐ ┌───────────┐ ┌───────────┐
             │ PostgreSQL│ │   Redis   │ │  Celery   │
             │ + pgvector│ │  (Broker) │ │  Workers  │
             │ (Port 5432│ │ (Port 6379│ │           │
             └───────────┘ └───────────┘ └───────────┘
```

## Monitoring

| Dashboard | URL | Purpose |
|-----------|-----|---------|
| API Health | `http://localhost:8000/health/ready` | Service status |
| Flower | `http://localhost:5555` | Celery monitoring |
| Prometheus | `http://localhost:9090` | Metrics collection |
| Grafana | `http://localhost:3001` | Visualization |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `JWT_SECRET` | Yes | JWT signing secret (32+ chars) |
| `CSRF_SECRET` | Yes | CSRF token secret |
| `ENCRYPTION_KEY` | Yes | AES-256 key for API keys |
| `GOOGLE_API_KEY` | No | Gemini API access |
| `OPENAI_API_KEY` | No | OpenAI API access |
| `ELEVENLABS_API_KEY` | No | TTS provider |
| `ANTHROPIC_API_KEY` | No | Claude access |

## Troubleshooting

### Container won't start
```bash
docker compose logs nexus-api --tail 50
```

### Database connection failed
```bash
docker compose exec postgres pg_isready -U nexus
```

### Celery tasks stuck
```bash
# Check worker status
docker compose exec nexus-worker celery -A src.core.nexus_studio_queue inspect active

# Purge all queued tasks (⚠️ destructive)
docker compose exec nexus-worker celery -A src.core.nexus_studio_queue purge
```

### Redis memory full
```bash
docker compose exec redis redis-cli info memory
```
