# ADR-003: Celery + Redis for Async Artifact Generation

**Status:** Accepted  
**Date:** 2026-03-30

## Context

Artifact generation (podcasts, videos, slides, exports) can take 30s–5min per job.
Blocking the API process is unacceptable.

## Decision

Use **Celery** with **Redis** as broker and result backend for all long-running tasks:

- **Queues**: `default`, `studio`, `export`, `research` (priority-based routing)
- **Workers**: Prefork pool with configurable concurrency
- **Progress**: Real-time updates via WebSocket (job status emitted per step)
- **Retry**: Exponential backoff with max 3 retries
- **Monitoring**: Flower dashboard for worker health

## Task Flow

```
Client → API → Celery Task → Worker → Progress WS → Client
                    ↓
             Result → DB + Storage → Download URL
```

## Consequences

### Positive
- API stays responsive (< 100ms for task submission)
- Horizontal scaling via worker count
- Built-in retry and dead-letter handling
- Real-time progress feedback

### Negative
- Redis becomes a critical dependency
- Worker process management adds ops complexity
- Task serialization limits (no complex Python objects)
