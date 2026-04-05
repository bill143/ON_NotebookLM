"""
Nexus Test Fixtures — Shared test infrastructure for integration tests.

Provides:
- Async test client with FastAPI TestClient
- Test database session with automatic cleanup
- Auth fixture generating valid test JWT tokens
- Factory fixtures for notebooks, sources, artifacts
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Ensure tests default to an isolated local test stack.
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus_dev_2024@localhost:5432/nexus_notebook_11_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-bytes-long!!!")
os.environ.setdefault("CSRF_SECRET", "test-csrf-secret-32-bytes!!!!!!!")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-bytes!!!!")

from src.config import Environment, Settings
from src.infra.nexus_data_persist import close_database, init_database
from src.main import app

# ── Settings Override ────────────────────────────────────────
# Fixed UUIDs: JWT `tid` / RLS `app.tenant_id` must cast to PostgreSQL uuid;
# artifacts and sessions reference `users` and `notebooks` by FK.

TEST_TENANT_ID = "11111111-1111-1111-1111-111111111111"
TEST_USER_ID = "22222222-2222-2222-2222-222222222222"
TEST_ADMIN_ID = "33333333-3333-3333-3333-333333333333"
TEST_NOTEBOOK_ID = "44444444-4444-4444-4444-444444444444"


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


async def ensure_integration_principals() -> None:
    """Insert tenant, users, and notebook for API FK/RLS (idempotent)."""
    from sqlalchemy import text

    from src.infra.nexus_data_persist import get_session

    async with get_session() as session:
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, slug, plan, created_at, updated_at)
                VALUES (:tid, 'Integration Test Tenant', 'nexus-integration-test', 'free', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"tid": TEST_TENANT_ID},
        )
        await session.execute(
            text("""
                INSERT INTO users (id, tenant_id, email, display_name, role, created_at, updated_at)
                VALUES (:uid, :tid, 'integration-user@test.local', 'Integration User', 'member', NOW(), NOW())
                ON CONFLICT (tenant_id, email) DO NOTHING
            """),
            {"uid": TEST_USER_ID, "tid": TEST_TENANT_ID},
        )
        await session.execute(
            text("""
                INSERT INTO users (id, tenant_id, email, display_name, role, created_at, updated_at)
                VALUES (:aid, :tid, 'integration-admin@test.local', 'Integration Admin', 'admin', NOW(), NOW())
                ON CONFLICT (tenant_id, email) DO NOTHING
            """),
            {"aid": TEST_ADMIN_ID, "tid": TEST_TENANT_ID},
        )
        await session.execute(
            text("""
                INSERT INTO notebooks (id, tenant_id, user_id, name, created_at, updated_at)
                VALUES (:nid, :tid, :uid, 'Integration Test Notebook', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"nid": TEST_NOTEBOOK_ID, "tid": TEST_TENANT_ID, "uid": TEST_USER_ID},
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
    try:
        await init_database()
        await ensure_integration_principals()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(
            "Integration services unavailable. Start Docker services first "
            "(`docker compose -f deploy/docker-compose.yml up -d postgres redis`). "
            f"Details: {exc}"
        )

    # Avoid requiring a live Celery broker for artifact creation in tests.
    with patch("src.worker.generate_artifact.delay", MagicMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    await close_database()


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


def make_source_text_data(
    content: str = "This is test content for embedding.", **overrides
) -> dict:
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


def make_artifact_data(
    notebook_id: str | None = None,
    artifact_type: str = "summary",
    **overrides,
) -> dict:
    """Create artifact request data."""
    data = {
        "notebook_id": notebook_id or TEST_NOTEBOOK_ID,
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
