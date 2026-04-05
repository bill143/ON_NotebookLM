"""Unit tests for nexus_obs_tracing — logging, tracing, metrics, PII redaction."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.infra.nexus_obs_tracing import (
    MetricsCollector,
    _json_formatter,
    _redact_sensitive,
    generate_span_id,
    generate_trace_id,
    request_id_var,
    setup_logging,
    span_id_var,
    tenant_id_var,
    trace_context,
    trace_id_var,
    traced,
    user_id_var,
)

# ── generate_trace_id / generate_span_id ─────────────────────


class TestTraceIdGeneration:
    def test_trace_id_length(self):
        tid = generate_trace_id()
        assert len(tid) == 16

    def test_trace_id_is_hex(self):
        tid = generate_trace_id()
        int(tid, 16)  # should not raise

    def test_trace_ids_unique(self):
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_span_id_length(self):
        sid = generate_span_id()
        assert len(sid) == 8

    def test_span_id_is_hex(self):
        sid = generate_span_id()
        int(sid, 16)

    def test_span_ids_unique(self):
        ids = {generate_span_id() for _ in range(100)}
        assert len(ids) == 100


# ── _redact_sensitive ────────────────────────────────────────


class TestRedactSensitive:
    def test_redacts_api_key(self):
        record = {"message": "Using api_key=sk-12345 for auth"}
        result = _redact_sensitive(record)
        assert "sk-12345" not in result["message"]
        assert "***REDACTED***" in result["message"]

    def test_redacts_password(self):
        record = {"message": "password=my_secret_pass"}
        result = _redact_sensitive(record)
        assert "my_secret_pass" not in result["message"]

    def test_redacts_token(self):
        record = {"message": "Bearer token=abc123xyz"}
        result = _redact_sensitive(record)
        assert "abc123xyz" not in result["message"]

    def test_clean_message_unchanged(self):
        record = {"message": "Normal log about processing data"}
        result = _redact_sensitive(record)
        assert result["message"] == "Normal log about processing data"

    def test_empty_message(self):
        record = {"message": ""}
        result = _redact_sensitive(record)
        assert result["message"] == ""

    def test_no_message_key(self):
        record = {"level": "INFO"}
        result = _redact_sensitive(record)
        assert result == {"level": "INFO"}

    def test_redacts_authorization_header(self):
        record = {"message": "authorization=Bearer eyJhbGciOiJIUzI"}
        result = _redact_sensitive(record)
        assert "eyJhbGciOiJIUzI" not in result["message"]

    def test_redacts_secret(self):
        record = {"message": "client_secret=super_secret_value"}
        result = _redact_sensitive(record)
        assert "super_secret_value" not in result["message"]


# ── _json_formatter ──────────────────────────────────────────


class TestJsonFormatter:
    def _make_record(self, message="Test log", level="INFO", module="test_mod", function="test_fn"):

        class _FakeTime:
            def isoformat(self) -> str:
                return "2025-01-01T00:00:00+00:00"

        class _FakeLevel:
            def __init__(self, name: str) -> None:
                self.name = name

        record: dict[str, Any] = {
            "time": _FakeTime(),
            "level": _FakeLevel(level),
            "message": message,
            "module": module,
            "function": function,
            "line": 42,
            "exception": None,
            "extra": {},
        }
        return record

    def test_returns_json_string(self):
        record = self._make_record()
        result = _json_formatter(record)
        parsed = json.loads(result)
        assert parsed["message"] == "Test log"

    def test_includes_trace_fields(self):
        record = self._make_record()
        result = _json_formatter(record)
        parsed = json.loads(result)
        assert "trace_id" in parsed
        assert "span_id" in parsed
        assert "user_id" in parsed
        assert "tenant_id" in parsed
        assert "request_id" in parsed

    def test_includes_level_and_module(self):
        record = self._make_record(level="ERROR", module="api")
        result = _json_formatter(record)
        parsed = json.loads(result)
        assert parsed["level"] == "ERROR"
        assert parsed["module"] == "api"

    def test_exception_included_when_present(self):
        record = self._make_record()
        record["exception"] = "ValueError: bad value"
        result = _json_formatter(record)
        parsed = json.loads(result)
        assert "exception" in parsed

    def test_extra_fields_truncated(self):
        record = self._make_record()
        record["extra"] = {"long_field": "x" * 1000}
        result = _json_formatter(record)
        parsed = json.loads(result)
        assert len(parsed["extra"]["long_field"]) <= 500

    def test_ends_with_newline(self):
        record = self._make_record()
        result = _json_formatter(record)
        assert result.endswith("\n")


# ── setup_logging ────────────────────────────────────────────


class TestSetupLogging:
    def test_json_format_does_not_raise(self):
        setup_logging(log_level="WARNING", log_format="json")

    def test_text_format_does_not_raise(self):
        setup_logging(log_level="DEBUG", log_format="text")

    def test_default_args(self):
        setup_logging()


# ── trace_context ────────────────────────────────────────────


class TestTraceContext:
    @pytest.mark.asyncio
    async def test_yields_trace_id(self):
        async with trace_context("test.op") as tid:
            assert isinstance(tid, str)
            assert len(tid) == 16

    @pytest.mark.asyncio
    async def test_sets_context_vars(self):
        async with trace_context("test.op", user_id="u1", tenant_id="t1"):
            assert user_id_var.get() == "u1"
            assert tenant_id_var.get() == "t1"
            assert trace_id_var.get() != ""
            assert span_id_var.get() != ""
            assert request_id_var.get() != ""

    @pytest.mark.asyncio
    async def test_propagates_exception(self):
        with pytest.raises(ValueError, match="boom"):
            async with trace_context("failing.op"):
                raise ValueError("boom")

    @pytest.mark.asyncio
    async def test_request_id_format(self):
        async with trace_context("test.op") as tid:
            rid = request_id_var.get()
            assert rid.startswith(tid)
            assert "-" in rid


# ── traced decorator ─────────────────────────────────────────


class TestTracedDecorator:
    @pytest.mark.asyncio
    async def test_async_function(self):
        @traced("test.async_op")
        async def my_func():
            return "result"

        result = await my_func()
        assert result == "result"

    @pytest.mark.asyncio
    async def test_async_function_exception(self):
        @traced("test.fail")
        async def failing():
            raise RuntimeError("async fail")

        with pytest.raises(RuntimeError, match="async fail"):
            await failing()

    def test_sync_function(self):
        @traced("test.sync_op")
        def my_sync():
            return 42

        result = my_sync()
        assert result == 42

    def test_sync_function_exception(self):
        @traced("test.sync_fail")
        def failing_sync():
            raise ValueError("sync fail")

        with pytest.raises(ValueError, match="sync fail"):
            failing_sync()

    @pytest.mark.asyncio
    async def test_restores_parent_span(self):
        parent_span = "parent123"
        span_id_var.set(parent_span)

        @traced("test.child")
        async def child_op():
            assert span_id_var.get() != parent_span
            return True

        await child_op()
        assert span_id_var.get() == parent_span

    def test_default_operation_name(self):
        @traced()
        def auto_named():
            return True

        result = auto_named()
        assert result is True


# ── MetricsCollector ─────────────────────────────────────────


class TestMetricsCollector:
    def test_initialization(self):
        with patch("prometheus_client.Counter"):
            with patch("prometheus_client.Histogram"):
                with patch("prometheus_client.Gauge"):
                    mc = MetricsCollector()
                    assert mc.request_count is not None
                    assert mc.request_latency is not None
                    assert mc.ai_call_count is not None
                    assert mc.ai_call_latency is not None
                    assert mc.ai_tokens is not None
                    assert mc.ai_cost is not None
                    assert mc.active_generations is not None
                    assert mc.queue_depth is not None
                    assert mc.embedding_count is not None

    def test_record_ai_call(self):
        with patch("prometheus_client.Counter"):
            with patch("prometheus_client.Histogram"):
                with patch("prometheus_client.Gauge"):
                    mc = MetricsCollector()
                    mc.record_ai_call(
                        provider="openai",
                        model="gpt-4o",
                        agent="summary",
                        success=True,
                        latency_seconds=1.5,
                        input_tokens=100,
                        output_tokens=50,
                        cost_usd=0.01,
                        tenant_id="t1",
                    )

                    mc.ai_call_count.labels.assert_called()
                    mc.ai_call_latency.labels.assert_called()
                    mc.ai_tokens.labels.assert_called()

    def test_record_ai_call_zero_cost_skips_cost_counter(self):
        with patch("prometheus_client.Counter"):
            with patch("prometheus_client.Histogram"):
                with patch("prometheus_client.Gauge"):
                    mc = MetricsCollector()
                    mc.ai_cost = MagicMock()
                    mc.record_ai_call(
                        provider="openai",
                        model="gpt-4o",
                        agent="test",
                        success=True,
                        latency_seconds=1.0,
                        input_tokens=10,
                        output_tokens=5,
                        cost_usd=0.0,
                    )
                    mc.ai_cost.labels.assert_not_called()
