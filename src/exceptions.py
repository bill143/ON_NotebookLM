"""
Nexus Exceptions — Hierarchical Error Taxonomy (ADR-8)
Source: Repo #5 (RPCError hierarchy), Repo #7 (error_classifier)

Every exception type maps to:
- An HTTP status code for API responses
- An error severity for observability routing
- A user-safe message (no internal details leaked)
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorSeverity(str, Enum):
    LOW = "low"  # Expected errors (validation, not found)
    MEDIUM = "medium"  # Operational errors (rate limit, timeout)
    HIGH = "high"  # System errors (DB down, provider failure)
    CRITICAL = "critical"  # Security errors (auth breach, injection)


class NexusError(Exception):
    """Base exception for all Nexus Notebook 11 LM errors."""

    status_code: int = 500
    severity: ErrorSeverity = ErrorSeverity.HIGH
    error_code: str = "NEXUS_INTERNAL_ERROR"
    retryable: bool = False

    def __init__(
        self,
        message: str = "An internal error occurred",
        *,
        details: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.original_error = original_error

    def to_dict(self) -> dict[str, Any]:
        """Serialize to API response format (no internal details)."""
        return {
            "error": {
                "code": self.error_code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }


# ── Authentication & Authorization ───────────────────────────


class AuthError(NexusError):
    """Authentication failed — invalid or expired credentials."""

    status_code = 401
    severity = ErrorSeverity.MEDIUM
    error_code = "AUTH_ERROR"


class ForbiddenError(NexusError):
    """Authorization failed — insufficient permissions."""

    status_code = 403
    severity = ErrorSeverity.MEDIUM
    error_code = "FORBIDDEN"


class TenantIsolationError(NexusError):
    """Cross-tenant data access attempt detected."""

    status_code = 403
    severity = ErrorSeverity.CRITICAL
    error_code = "TENANT_ISOLATION_VIOLATION"


# ── Validation ───────────────────────────────────────────────


class ValidationError(NexusError):
    """Input validation failed."""

    status_code = 422
    severity = ErrorSeverity.LOW
    error_code = "VALIDATION_ERROR"


class NotFoundError(NexusError):
    """Requested resource not found."""

    status_code = 404
    severity = ErrorSeverity.LOW
    error_code = "NOT_FOUND"


class ConflictError(NexusError):
    """Resource conflict (duplicate, version mismatch)."""

    status_code = 409
    severity = ErrorSeverity.LOW
    error_code = "CONFLICT"


# ── AI Provider Errors ───────────────────────────────────────


class AIProviderError(NexusError):
    """Base class for AI provider errors."""

    status_code = 502
    severity = ErrorSeverity.HIGH
    error_code = "AI_PROVIDER_ERROR"
    retryable = True


class ModelNotFoundError(AIProviderError):
    """Requested AI model not found or not configured."""

    status_code = 404
    severity = ErrorSeverity.MEDIUM
    error_code = "MODEL_NOT_FOUND"
    retryable = False


class RateLimitError(AIProviderError):
    """AI provider rate limit exceeded."""

    status_code = 429
    severity = ErrorSeverity.MEDIUM
    error_code = "RATE_LIMIT"
    retryable = True

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after_seconds: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(AIProviderError):
    """AI provider request timed out."""

    status_code = 504
    severity = ErrorSeverity.MEDIUM
    error_code = "PROVIDER_TIMEOUT"
    retryable = True


class ProviderAuthError(AIProviderError):
    """AI provider authentication failed (invalid API key)."""

    status_code = 502
    severity = ErrorSeverity.HIGH
    error_code = "PROVIDER_AUTH_ERROR"
    retryable = False


class TokenBudgetExceeded(AIProviderError):
    """Token or cost budget exceeded for tenant/user."""

    status_code = 402
    severity = ErrorSeverity.MEDIUM
    error_code = "BUDGET_EXCEEDED"
    retryable = False


# ── Source Processing Errors ─────────────────────────────────


class SourceProcessingError(NexusError):
    """Error during source content extraction."""

    status_code = 422
    severity = ErrorSeverity.MEDIUM
    error_code = "SOURCE_PROCESSING_ERROR"


class EmptyContentError(SourceProcessingError):
    """Source extraction returned no content."""

    error_code = "EMPTY_CONTENT"


class UnsupportedFormatError(SourceProcessingError):
    """Source format not supported."""

    error_code = "UNSUPPORTED_FORMAT"


class FileTooLargeError(SourceProcessingError):
    """Source file exceeds size limit."""

    status_code = 413
    error_code = "FILE_TOO_LARGE"


# ── Generation Errors ────────────────────────────────────────


class GenerationError(NexusError):
    """Error during artifact generation."""

    status_code = 500
    severity = ErrorSeverity.HIGH
    error_code = "GENERATION_ERROR"


class ChainExecutionError(GenerationError):
    """Error in agent chain execution."""

    error_code = "CHAIN_EXECUTION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        failed_agent: str | None = None,
        completed_agents: list[str] | None = None,
        partial_results: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, **kwargs)
        self.failed_agent = failed_agent
        self.completed_agents = completed_agents or []
        self.partial_results = partial_results


# ── Database Errors ──────────────────────────────────────────


class DatabaseError(NexusError):
    """Database operation failed."""

    status_code = 500
    severity = ErrorSeverity.HIGH
    error_code = "DATABASE_ERROR"
    retryable = True


class TransactionConflictError(DatabaseError):
    """Database transaction conflict (concurrent modification)."""

    error_code = "TRANSACTION_CONFLICT"
    retryable = True


# ── Plugin Errors ────────────────────────────────────────────


class PluginError(NexusError):
    """Plugin execution error (sandboxed)."""

    status_code = 500
    severity = ErrorSeverity.MEDIUM
    error_code = "PLUGIN_ERROR"


class PluginPermissionError(PluginError):
    """Plugin attempted unauthorized action."""

    status_code = 403
    error_code = "PLUGIN_PERMISSION_DENIED"


# ── Prompt Errors ────────────────────────────────────────────


class PromptError(NexusError):
    """Prompt resolution or rendering error."""

    status_code = 500
    severity = ErrorSeverity.HIGH
    error_code = "PROMPT_ERROR"


class PromptInjectionDetected(PromptError):
    """Potential prompt injection detected in user input."""

    status_code = 400
    severity = ErrorSeverity.CRITICAL
    error_code = "PROMPT_INJECTION_DETECTED"


# ── Error Classifier ────────────────────────────────────────


def classify_error(error: Exception) -> tuple[type[NexusError], str]:
    """
    Classify a raw exception into a NexusError subtype.
    Source: Repo #7, utils/error_classifier.py

    Returns (ErrorClass, user_safe_message).
    """
    error_str = str(error).lower()

    # Rate limiting
    if any(term in error_str for term in ["rate limit", "429", "too many requests"]):
        return RateLimitError, "AI service is temporarily busy. Please try again in a moment."

    # Authentication
    if any(
        term in error_str for term in ["unauthorized", "401", "invalid api key", "authentication"]
    ):
        return (
            ProviderAuthError,
            "AI service authentication failed. Check your API key configuration.",
        )

    # Timeout
    if any(term in error_str for term in ["timeout", "timed out", "deadline exceeded"]):
        return ProviderTimeoutError, "AI service took too long to respond. Please try again."

    # Connection
    if any(
        term in error_str for term in ["connection refused", "connection error", "dns", "network"]
    ):
        return AIProviderError, "Unable to reach AI service. Check your connection."

    # Content
    if any(term in error_str for term in ["content filter", "safety", "blocked"]):
        return GenerationError, "Content was filtered by the AI provider's safety system."

    # Token limit
    if any(term in error_str for term in ["token limit", "context length", "too long"]):
        return GenerationError, "Input exceeds the model's context window. Try with less content."

    # Default
    return NexusError, "An unexpected error occurred. Our team has been notified."
