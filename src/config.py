"""
Nexus Notebook 11 LM — Application Configuration
Codename: ESPERANTO

Centralized configuration using pydantic-settings.
All secrets loaded from environment variables (never hardcoded — ADR-5, Tier 4 Security).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
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
    host: str = "0.0.0.0"
    port: int = 8000

    # ── Database ─────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://nexus:password@localhost:5432/nexus_notebook_11"
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_echo: bool = False

    # ── Authentication (Supabase SSR — ADR-5) ────────────────
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    csrf_secret: str = "change-me-in-production"

    # ── AI Providers (ADR-1 — Esperanto Pattern) ─────────────
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None

    # ── Local Models (ADR-7) ─────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    kokoro_tts_base_url: str = "http://localhost:8880"

    # ── TTS Providers (ADR-4) ────────────────────────────────
    elevenlabs_api_key: Optional[str] = None
    edge_tts_enabled: bool = True

    # ── Storage ──────────────────────────────────────────────
    storage_backend: StorageBackend = StorageBackend.LOCAL
    storage_local_path: str = "./storage"
    s3_bucket: Optional[str] = None
    s3_region: Optional[str] = None

    # ── Redis (Caching) ──────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 3600

    # ── Observability (Feature 13) ───────────────────────────
    log_level: LogLevel = LogLevel.INFO
    log_format: str = "json"
    sentry_dsn: Optional[str] = None
    otel_exporter_endpoint: Optional[str] = None
    otel_service_name: str = "nexus-notebook-11"

    # ── Cost Tracking (Feature 11) ───────────────────────────
    cost_tracking_enabled: bool = True
    budget_alert_webhook: Optional[str] = None

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
