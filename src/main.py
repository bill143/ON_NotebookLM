"""
Nexus Notebook 11 LM — FastAPI Application Entry Point
Codename: ESPERANTO

Unified API surface with:
- Health check endpoints (liveness, readiness, startup)
- Auth middleware with tenant context injection
- CORS, error handling, and request tracing
- Prometheus metrics endpoint
- API versioning (/api/v1/)
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from src.config import get_settings
from src.exceptions import NexusError

# ── Lifespan ─────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()

    # Startup
    from src.infra.nexus_obs_tracing import setup_logging

    setup_logging(settings.log_level.value, settings.log_format)
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    from src.infra.nexus_ws_broker import ws_broker

    await ws_broker.connect()

    from src.infra.nexus_data_persist import init_database

    await init_database()
    logger.info("Database initialized")

    # Sentry integration
    if settings.sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            traces_sample_rate=0.1,
            environment=settings.environment.value,
            release=settings.app_version,
        )
        logger.info("Sentry initialized")

    logger.info(f"{settings.app_name} ready — {settings.environment.value}")
    yield

    # Shutdown
    from src.infra.nexus_data_persist import close_database

    await close_database()
    await ws_broker.disconnect()
    logger.info("Application shutdown complete")


# ── Application ──────────────────────────────────────────────

app = FastAPI(
    title="Nexus Notebook 11 LM",
    description="Production-grade NotebookLM module — Codename: ESPERANTO",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — origins loaded from settings (CORS_ORIGINS env var or .env)
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request Middleware ───────────────────────────────────────


@app.middleware("http")
async def request_context_middleware(request: Request, call_next) -> Response:
    """Inject trace context and tenant isolation on every request."""
    from src.infra.nexus_obs_tracing import request_id_var, trace_context

    # Extract trace ID from header or generate new
    request.headers.get("X-Trace-ID", "")

    # Extract tenant from auth header (if present)
    user_id = ""
    tenant_id = ""
    auth = request.headers.get("Authorization", "")
    if auth:
        try:
            from src.infra.nexus_vault_keys import AuthContext

            ctx = AuthContext.from_token(auth.replace("Bearer ", ""))
            user_id = ctx.user_id
            tenant_id = ctx.tenant_id
        except Exception:
            logger.debug(
                "Optional auth parse for tracing skipped (invalid or missing token)",
                exc_info=True,
            )

    async with trace_context(
        f"{request.method} {request.url.path}",
        user_id=user_id,
        tenant_id=tenant_id,
    ) as tid:
        response = await call_next(request)
        response.headers["X-Trace-ID"] = tid
        response.headers["X-Request-ID"] = request_id_var.get("")
        return cast(Response, response)


# ── Error Handlers ───────────────────────────────────────────


@app.exception_handler(NexusError)
async def nexus_error_handler(request: Request, exc: NexusError) -> JSONResponse:
    """Handle all NexusError subclasses with proper status codes."""
    safe_msg = str(exc.message).replace("{", "{{").replace("}", "}}")
    logger.log(
        "ERROR" if exc.severity.value in ("high", "critical") else "WARNING",
        f"API Error: {exc.error_code} — {safe_msg}",
        status_code=exc.status_code,
        error_code=exc.error_code,
        path=str(request.url.path),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak internals."""
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "retryable": False,
            }
        },
    )


# ── Health Checks (Feature 13E) ──────────────────────────────


@app.get("/health/live", tags=["Health"])
async def health_live() -> dict[str, Any]:
    """Liveness probe — is the process running?"""
    return {"status": "alive"}


@app.get("/health/ready", tags=["Health"])
async def health_ready() -> JSONResponse:
    """Readiness probe — can the service handle requests?"""
    checks = {}

    # Database check
    try:
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )


@app.get("/health/startup", tags=["Health"], response_model=None)
async def health_startup() -> JSONResponse | dict[str, Any]:
    """Startup probe — has initialization completed?"""
    from src.infra.nexus_data_persist import _engine

    if _engine is None:
        return JSONResponse(status_code=503, content={"status": "starting"})
    return {"status": "started"}


# ── Metrics Endpoint ─────────────────────────────────────────


@app.get("/metrics", tags=["Observability"])
async def prometheus_metrics() -> Response:
    """Prometheus metrics endpoint."""
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# ── API Routes ───────────────────────────────────────────────

from src.api.admin import router as admin_router
from src.api.artifacts import router as artifacts_router
from src.api.brain import router as brain_router
from src.api.chat import router as chat_router
from src.api.collaboration import router as collab_router
from src.api.debate import router as debate_router
from src.api.export import router as export_router
from src.api.local import router as local_router
from src.api.mindmap import router as mindmap_router
from src.api.models import router as models_router
from src.api.notebooks import router as notebooks_router
from src.api.plugins import router as plugins_router
from src.api.prompts import router as prompts_router
from src.api.research import router as research_router
from src.api.sources import router as sources_router
from src.api.verification import router as verification_router
from src.api.websocket import router as websocket_router

app.include_router(notebooks_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(artifacts_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(models_router, prefix="/api/v1")
app.include_router(websocket_router, prefix="/api/v1")
app.include_router(research_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(collab_router, prefix="/api/v1")
app.include_router(verification_router, prefix="/api/v1")
app.include_router(mindmap_router, prefix="/api/v1")
app.include_router(debate_router, prefix="/api/v1")
app.include_router(brain_router, prefix="/api/v1")
app.include_router(plugins_router, prefix="/api/v1")
app.include_router(local_router, prefix="/api/v1")
app.include_router(prompts_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")


@app.get("/api/v1", tags=["Root"])
async def api_root() -> dict[str, Any]:
    settings = get_settings()
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "codename": "ESPERANTO",
    }
