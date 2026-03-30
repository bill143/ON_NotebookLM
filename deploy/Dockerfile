# ═══════════════════════════════════════════════════════════════
# Nexus Notebook 11 LM — Multi-Stage Dockerfile
# ═══════════════════════════════════════════════════════════════

# ── Stage 1: Base ─────────────────────────────────────────────
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies (shared across stages)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ffmpeg \
        curl \
        poppler-utils \
        libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# ── Stage 2: Dependencies ────────────────────────────────────
FROM base AS dependencies

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"

# ── Stage 3: Development ─────────────────────────────────────
FROM dependencies AS development

COPY . .

# Development server with hot reload
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── Stage 4: Production ──────────────────────────────────────
FROM base AS production

# Install production deps only
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e "."

# Copy application code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY database/ ./database/
COPY alembic.ini ./

# Create non-root user
RUN useradd -m -s /bin/bash nexus && \
    mkdir -p /app/storage /app/logs && \
    chown -R nexus:nexus /app

USER nexus

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

EXPOSE 8000

# Production server with multiple workers
CMD ["uvicorn", "src.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--access-log"]
