"""
Nexus Notebook 11 LM — Application Configuration
Codename: ESPERANTO

Centralized configuration using pydantic-settings.
All secrets loaded from environment variables (never hardcoded — ADR-5, Tier 4 Security).
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StorageBackend(str, Enum):
    LOCAL = "local"
    S3 = "s3"


def _default_api_bind_host() -> str:
    """127.0.0.1 for local dev; 0.0.0.0 when running in a container or non-dev env.

    Actual listen address for Docker/K8s is still set by uvicorn `--host` in the image CMD.
    """
    in_container = Path("/.dockerenv").exists() or os.environ.get("CONTAINER", "").lower() in (
        "1",
        "true",
    )
    env = os.environ.get("ENVIRONMENT", "development").lower()
    if in_container or env in ("production", "staging"):
        return "0.0.0.0"  # noqa: S104 — intentional bind-all for containerized/staged deployments; dev uses 127.0.0.1
    return "127.0.0.1"


class Settings(BaseSettings):
    """Application settings — loaded from .env file and environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "Nexus Notebook 11 LM"
    app_version: str = "0.1.0"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    host: str = Field(default_factory=_default_api_bind_host)
    port: int = 8000
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # ── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://nexus:password@localhost:5432/nexus_notebook_11"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # ── Authentication (Supabase SSR — ADR-5) ────────────────
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    jwt_secret: str = "change-me-in-production"  # noqa: S105 — pydantic placeholder; override via JWT_SECRET in env
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    csrf_secret: str = "change-me-in-production"  # noqa: S105 — pydantic placeholder; override via CSRF_SECRET in env

    # ── AI Providers (ADR-1 — Esperanto Pattern) ─────────────
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None

    # ── Local Models (ADR-7) ─────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    kokoro_tts_base_url: str = "http://localhost:8880"

    # ── TTS Providers (ADR-4) ────────────────────────────────
    elevenlabs_api_key: str | None = None
    edge_tts_enabled: bool = True

    # ── Web Search (Feature 2A) ─────────────────────────────
    tavily_api_key: str | None = None

    # ── Storage ──────────────────────────────────────────────
    storage_backend: StorageBackend = StorageBackend.LOCAL
    storage_local_path: str = "./storage"
    s3_bucket: str | None = None
    s3_region: str | None = None

    # ── Redis (Caching) ──────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600

    # ── Observability (Feature 13) ───────────────────────────
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "json"
    sentry_dsn: str | None = None
    otel_exporter_endpoint: str | None = None
    otel_service_name: str = "nexus-notebook-11"

    # ── Cost Tracking (Feature 11) ───────────────────────────
    cost_tracking_enabled: bool = True
    budget_alert_webhook: str | None = None

    # ── Encryption ───────────────────────────────────────────
    encryption_key: str = Field(
        default="change-me-32-byte-key-for-prod!!",
        description="32-byte key for credential encryption (AES-256)",
    )

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        if len(v) < 32 and v != "change-me-32-byte-key-for-prod!!":
            raise ValueError("Encryption key must be at least 32 bytes")
        return v

    _INSECURE_DEFAULTS = frozenset(
        {
            "change-me-in-production",
            "change-me-32-byte-key-for-prod!!",
        }
    )

    @model_validator(mode="after")
    def _reject_insecure_defaults_in_production(self) -> Settings:
        if self.environment != Environment.PRODUCTION:
            return self
        violations: list[str] = []
        if self.jwt_secret in self._INSECURE_DEFAULTS:
            violations.append("JWT_SECRET")
        if self.csrf_secret in self._INSECURE_DEFAULTS:
            violations.append("CSRF_SECRET")
        if self.encryption_key in self._INSECURE_DEFAULTS:
            violations.append("ENCRYPTION_KEY")
        if violations:
            raise ValueError(
                f"Production environment requires real secrets for: "
                f"{', '.join(violations)}. "
                f"Set them via environment variables or .env file."
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
