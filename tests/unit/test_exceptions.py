"""
Unit Tests — Error Taxonomy & Exception Classification
"""

from __future__ import annotations

from src.exceptions import (
    AIProviderError,
    AuthError,
    ChainExecutionError,
    ErrorSeverity,
    GenerationError,
    NexusError,
    PromptInjectionDetected,
    ProviderAuthError,
    ProviderTimeoutError,
    RateLimitError,
    TenantIsolationError,
    TokenBudgetExceeded,
    classify_error,
)


class TestErrorTaxonomy:
    """Test error class hierarchy and serialization."""

    def test_base_error_defaults(self):
        err = NexusError("something broke")
        assert err.status_code == 500
        assert err.severity == ErrorSeverity.HIGH
        assert err.error_code == "NEXUS_INTERNAL_ERROR"
        assert err.retryable is False

    def test_auth_error(self):
        err = AuthError("bad token")
        assert err.status_code == 401
        assert err.severity == ErrorSeverity.MEDIUM

    def test_rate_limit_error(self):
        err = RateLimitError("slow down", retry_after_seconds=30.0)
        assert err.status_code == 429
        assert err.retryable is True
        assert err.retry_after_seconds == 30.0

    def test_tenant_isolation_critical(self):
        err = TenantIsolationError("cross-tenant breach")
        assert err.severity == ErrorSeverity.CRITICAL
        assert err.status_code == 403

    def test_token_budget_exceeded(self):
        err = TokenBudgetExceeded("budget blown")
        assert err.status_code == 402
        assert err.retryable is False

    def test_chain_execution_error(self):
        err = ChainExecutionError(
            "agent failed",
            failed_agent="embedder",
            completed_agents=["extractor"],
            partial_results={"extractor": "some data"},
        )
        assert err.failed_agent == "embedder"
        assert len(err.completed_agents) == 1

    def test_to_dict_no_internals(self):
        """Serialized error should not leak internal details."""
        err = NexusError("internal details here", details={"secret": "value"})
        d = err.to_dict()
        assert "secret" not in str(d)
        assert d["error"]["code"] == "NEXUS_INTERNAL_ERROR"
        assert "retryable" in d["error"]

    def test_prompt_injection_detected(self):
        err = PromptInjectionDetected("caught you")
        assert err.severity == ErrorSeverity.CRITICAL
        assert err.status_code == 400


class TestErrorClassifier:
    """Test classify_error() maps raw exceptions correctly."""

    def test_rate_limit_detection(self):
        cls, msg = classify_error(Exception("429 Too Many Requests"))
        assert cls == RateLimitError

    def test_auth_detection(self):
        cls, msg = classify_error(Exception("401 Unauthorized: Invalid API key"))
        assert cls == ProviderAuthError

    def test_timeout_detection(self):
        cls, msg = classify_error(Exception("Request timed out after 30s"))
        assert cls == ProviderTimeoutError

    def test_connection_detection(self):
        cls, msg = classify_error(Exception("Connection refused"))
        assert cls == AIProviderError

    def test_unknown_error_default(self):
        cls, msg = classify_error(Exception("something random"))
        assert cls == NexusError
        assert "unexpected" in msg.lower()

    def test_content_filter_detection(self):
        cls, msg = classify_error(Exception("blocked by content filter"))
        assert cls == GenerationError
        assert "filtered" in msg.lower()

    def test_token_limit_detection(self):
        cls, msg = classify_error(Exception("context length exceeded — too long"))
        assert cls == GenerationError
        assert "context" in msg.lower()
