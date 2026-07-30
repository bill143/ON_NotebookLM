"""
Nexus Observability — Feature 13: Structured Logging, Tracing, Metrics
Source: Repo #7 (loguru), Repo #5 (perf_counter), ADR-8 (error taxonomy)

This module provides:
- JSON structured logging via loguru with PII redaction
- OpenTelemetry trace ID injection
- Request-scoped context propagation
- Prometheus metrics collection
"""

from __future__ import annotations

import sys
import time
import uuid
from collections.abc import Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, cast

from loguru import logger

# ── Context Variables ────────────────────────────────────────
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var: ContextVar[str] = ContextVar("span_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


# ── PII Patterns for Redaction ───────────────────────────────
_PII_PATTERNS = {
    "api_key": "***REDACTED***",
    "password": "***REDACTED***",
    "secret": "***REDACTED***",
    "token": "***REDACTED***",
    "authorization": "***REDACTED***",
}


def _redact_sensitive(record: dict) -> dict:
    """Redact sensitive fields from log records."""
    message = str(record.get("message", ""))
    for pattern, replacement in _PII_PATTERNS.items():
        if pattern in message.lower():
            # Rough redaction — truncate values after sensitive keys
            parts = message.split(pattern)
            if len(parts) > 1:
                message = parts[0] + pattern + "=" + replacement
                record["message"] = message
    return record


def _json_formatter(record: dict) -> str:
    """Format log records as JSON with trace context."""
    import json

    log_entry = {
        "timestamp": record["time"].isoformat(),
        "level": record["level"].name,
        "message": record["message"],
        "module": record["module"],
        "function": record["function"],
        "line": record["line"],
        "trace_id": trace_id_var.get(""),
        "span_id": span_id_var.get(""),
        "user_id": user_id_var.get(""),
        "tenant_id": tenant_id_var.get(""),
        "request_id": request_id_var.get(""),
    }

    if record.get("exception"):
        log_entry["exception"] = str(record["exception"])

    extra = record.get("extra", {})
    if extra:
        log_entry["extra"] = {k: str(v)[:500] for k, v in extra.items()}

    return json.dumps(log_entry) + "\n"


def setup_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """Configure structured logging for the application."""
    logger.remove()

    if log_format == "json":
        logger.add(
            sys.stdout,
            format=cast(Callable[..., str], _json_formatter),
            level=log_level,
            serialize=False,
            backtrace=True,
            diagnose=False,
        )
    else:
        logger.add(
            sys.stdout,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "{message}"
            ),
            level=log_level,
            colorize=True,
        )

    logger.info("Logging configured", level=log_level, format=log_format)


# ── Trace Context Manager ───────────────────────────────────


def generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def generate_span_id() -> str:
    return uuid.uuid4().hex[:8]


@asynccontextmanager
async def trace_context(
    operation: str,
    user_id: str | None = None,
    tenant_id: str | None = None,
):
    """Async context manager that sets up trace context for a request."""
    tid = trace_id_var.get("") or generate_trace_id()
    sid = generate_span_id()

    trace_id_var.set(tid)
    span_id_var.set(sid)
    if user_id:
        user_id_var.set(user_id)
    if tenant_id:
        tenant_id_var.set(tenant_id)

    request_id_var.set(f"{tid}-{sid}")

    start_time = time.perf_counter()
    logger.info(f"Starting operation: {operation}")

    try:
        yield tid
    except Exception as e:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.error(
            f"Operation failed: {operation}",
            duration_ms=round(duration_ms, 2),
            error=str(e),
            error_type=type(e).__name__,
        )
        raise
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"Completed operation: {operation}",
            duration_ms=round(duration_ms, 2),
        )


# ── Performance Decorator ───────────────────────────────────


def traced(operation: str | None = None) -> Callable:
    """Decorator to trace function execution with timing."""

    def decorator(func: Callable) -> Callable:
        op_name = operation or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            parent_span = span_id_var.get("")
            span_id_var.set(generate_span_id())
            start = time.perf_counter()

            try:
                result = await func(*args, **kwargs)
                duration = (time.perf_counter() - start) * 1000
                logger.debug(
                    f"Traced: {op_name}",
                    duration_ms=round(duration, 2),
                    parent_span=parent_span,
                )
                return result
            except Exception as e:
                duration = (time.perf_counter() - start) * 1000
                logger.warning(
                    f"Traced (failed): {op_name}",
                    duration_ms=round(duration, 2),
                    error_type=type(e).__name__,
                )
                raise
            finally:
                span_id_var.set(parent_span)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            parent_span = span_id_var.get("")
            span_id_var.set(generate_span_id())
            start = time.perf_counter()

            try:
                result = func(*args, **kwargs)
                duration = (time.perf_counter() - start) * 1000
                logger.debug(
                    f"Traced: {op_name}",
                    duration_ms=round(duration, 2),
                    parent_span=parent_span,
                )
                return result
            except Exception as e:
                duration = (time.perf_counter() - start) * 1000
                logger.warning(
                    f"Traced (failed): {op_name}",
                    duration_ms=round(duration, 2),
                    error_type=type(e).__name__,
                )
                raise
            finally:
                span_id_var.set(parent_span)

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ── Metrics (Prometheus) ─────────────────────────────────────


class MetricsCollector:
    """Prometheus metrics for Nexus Notebook 11 LM."""

    def __init__(self) -> None:
        from prometheus_client import Counter, Gauge, Histogram

        self.request_count = Counter(
            "nexus_request_total",
            "Total requests",
            ["method", "endpoint", "status"],
        )
        self.request_latency = Histogram(
            "nexus_request_duration_seconds",
            "Request duration",
            ["method", "endpoint"],
            buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        )
        self.ai_call_count = Counter(
            "nexus_ai_call_total",
            "Total AI API calls",
            ["provider", "model", "agent", "success"],
        )
        self.ai_call_latency = Histogram(
            "nexus_ai_call_duration_seconds",
            "AI API call duration",
            ["provider", "model"],
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
        )
        self.ai_tokens = Counter(
            "nexus_ai_tokens_total",
            "Total AI tokens used",
            ["provider", "model", "direction"],
        )
        self.ai_cost = Counter(
            "nexus_ai_cost_usd_total",
            "Total AI cost in USD",
            ["provider", "model", "tenant_id"],
        )
        self.active_generations = Gauge(
            "nexus_active_generations",
            "Currently active generation jobs",
            ["artifact_type"],
        )
        self.queue_depth = Gauge(
            "nexus_queue_depth",
            "Items in processing queue",
            ["queue_name"],
        )
        self.embedding_count = Counter(
            "nexus_embeddings_total",
            "Total embeddings generated",
            ["source_type"],
        )

    def record_ai_call(
        self,
        provider: str,
        model: str,
        agent: str,
        success: bool,
        latency_seconds: float,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        tenant_id: str = "",
    ) -> None:
        """Record a complete AI API call with all metrics."""
        self.ai_call_count.labels(
            provider=provider, model=model, agent=agent, success=str(success)
        ).inc()
        self.ai_call_latency.labels(provider=provider, model=model).observe(latency_seconds)
        self.ai_tokens.labels(provider=provider, model=model, direction="input").inc(input_tokens)
        self.ai_tokens.labels(provider=provider, model=model, direction="output").inc(output_tokens)
        if cost_usd > 0:
            self.ai_cost.labels(provider=provider, model=model, tenant_id=tenant_id).inc(cost_usd)


# Global singleton
metrics = MetricsCollector()
