"""
Nexus Test Fixtures — Shared test infrastructure for integration tests.

Provides:
- Async test client with FastAPI TestClient
- Test database session with automatic cleanup
- Auth fixture generating valid test JWT tokens
- Factory fixtures for notebooks, sources, artifacts
"""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.config import Settings, Environment
from src.main import app


# ── Settings Override ────────────────────────────────────────

TEST_TENANT_ID = "test-tenant-001"
TEST_USER_ID = "test-user-001"
TEST_ADMIN_ID = "test-admin-001"


def get_test_settings() -> Settings:
    """Return settings configured for testing."""
    return Settings(
        environment=Environment.TESTING,
        database_url="postgresql+asyncpg://nexus:nexus_dev_2024@localhost:5432/nexus_notebook_11_test",
        jwt_secret="test-jwt-secret-32-bytes-long!!!",
        csrf_secret="test-csrf-secret-32-bytes!!!!!!!",
        encryption_key="test-encryption-key-32-bytes!!!!",
        log_level="DEBUG",
        log_format="text",
        redis_url="redis://localhost:6379/1",
    )


# ── Auth Helpers ─────────────────────────────────────────────

def make_auth_token(
    user_id: str = TEST_USER_ID,
    tenant_id: str = TEST_TENANT_ID,
    roles: list[str] | None = None,
) -> str:
    """Generate a valid JWT token for testing."""
    from src.infra.nexus_vault_keys import create_access_token

    return create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        roles=roles or ["member"],
        expires_minutes=60,
    )


def make_admin_token() -> str:
    """Generate an admin JWT token."""
    return make_auth_token(
        user_id=TEST_ADMIN_ID,
        roles=["admin", "member"],
    )


def auth_headers(user_id: str = TEST_USER_ID, roles: list[str] | None = None) -> dict:
    """Return Authorization headers for test requests."""
    token = make_auth_token(user_id=user_id, roles=roles)
    return {"Authorization": f"Bearer {token}"}


def admin_headers() -> dict:
    """Return admin Authorization headers."""
    token = make_admin_token()
    return {"Authorization": f"Bearer {token}"}


# ── Fixtures ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client for FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def user_headers() -> dict:
    """Standard user auth headers."""
    return auth_headers()


@pytest.fixture
def admin_auth_headers() -> dict:
    """Admin auth headers."""
    return admin_headers()


# ── Factory Helpers ──────────────────────────────────────────

def make_notebook_data(name: str = "Test Notebook", **overrides) -> dict:
    """Create notebook request data."""
    data = {
        "name": name,
        "description": "A test notebook",
        "icon": "📓",
        "color": "#6366f1",
        "tags": ["test"],
    }
    data.update(overrides)
    return data


def make_source_text_data(content: str = "This is test content for embedding.", **overrides) -> dict:
    """Create text source request data."""
    data = {
        "content": content,
        "title": "Test Source",
        "source_type": "pasted_text",
    }
    data.update(overrides)
    return data


def make_source_url_data(url: str = "https://example.com/article", **overrides) -> dict:
    """Create URL source request data."""
    data = {
        "url": url,
        "title": "Example Article",
        "source_type": "url",
    }
    data.update(overrides)
    return data


def make_artifact_data(notebook_id: str, artifact_type: str = "summary", **overrides) -> dict:
    """Create artifact request data."""
    data = {
        "notebook_id": notebook_id,
        "title": f"Test {artifact_type}",
        "artifact_type": artifact_type,
        "generation_config": {},
    }
    data.update(overrides)
    return data


def make_chat_data(content: str = "What is this about?", **overrides) -> dict:
    """Create chat message request data."""
    data = {
        "content": content,
        "stream": False,
    }
    data.update(overrides)
    return data


def make_model_data(
    name: str = "test-model",
    provider: str = "openai",
    model_type: str = "chat",
    **overrides,
) -> dict:
    """Create model registration data."""
    data = {
        "name": name,
        "provider": provider,
        "model_type": model_type,
        "model_id_string": f"test-{name}",
        "is_local": False,
        "max_tokens": 4096,
        "cost_per_1k_input": 0.001,
        "cost_per_1k_output": 0.002,
    }
    data.update(overrides)
    return data
