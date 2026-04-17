"""
Tests for Vault Integration Layer — notebook linking, calendar, notifications.

3 test cases covering integration with existing NEXUS modules.
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://nexus:nexus_dev_2024@localhost:5432/nexus_notebook_11_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-bytes-long!!!")
os.environ.setdefault("CSRF_SECRET", "test-csrf-secret-32-bytes!!!!!!!")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-32-bytes!!!!")

from sqlalchemy import text

from src.infra.nexus_data_persist import close_database, get_session, init_database
from src.vault.integration import (
    create_calendar_deadline,
    link_to_notebook_source,
    trigger_notification,
)
from src.vault.repositories import VaultDocumentRepository

TENANT_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "22222222-2222-2222-2222-222222222222"
NOTEBOOK_ID = "44444444-4444-4444-4444-444444444444"
PROJECT_ID = "55555555-5555-5555-5555-555555555555"


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Initialize database and ensure test principals exist."""
    try:
        await init_database()
    except Exception:
        pytest.skip("Database not available")

    # Ensure tenant, user, and notebook exist
    async with get_session() as session:
        await session.execute(
            text("""
                INSERT INTO tenants (id, name, slug, plan, created_at, updated_at)
                VALUES (:tid, 'Integration Test Tenant', 'nexus-integration-test', 'free', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"tid": TENANT_ID},
        )
        await session.execute(
            text("""
                INSERT INTO users (id, tenant_id, email, display_name, role, created_at, updated_at)
                VALUES (:uid, :tid, 'integration-user@test.local', 'Integration User', 'member', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"uid": USER_ID, "tid": TENANT_ID},
        )
        await session.execute(
            text("""
                INSERT INTO notebooks (id, tenant_id, user_id, name, created_at, updated_at)
                VALUES (:nid, :tid, :uid, 'Vault Integration Test Notebook', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """),
            {"nid": NOTEBOOK_ID, "tid": TENANT_ID, "uid": USER_ID},
        )

    yield

    # Cleanup
    async with get_session() as session:
        await session.execute(
            text("DELETE FROM notebook_sources WHERE notebook_id = :nid"),
            {"nid": NOTEBOOK_ID},
        )
        await session.execute(
            text("DELETE FROM vault_documents WHERE tenant_id = :tid"),
            {"tid": TENANT_ID},
        )

    await close_database()


# ── Test 13: link_to_notebook_source creates association ─────


@pytest.mark.asyncio
async def test_link_to_notebook_source():
    doc_repo = VaultDocumentRepository()
    doc = await doc_repo.create({
        "project_id": PROJECT_ID,
        "uploaded_by": USER_ID,
        "original_filename": "integration-test.pdf",
        "stored_filename": f"{uuid.uuid4().hex[:12]}_integration-test.pdf",
        "file_path": f"uploads/{TENANT_ID}/{PROJECT_ID}/RFI/2026/04/test.pdf",
        "mime_type": "application/pdf",
    }, tenant_id=TENANT_ID)

    result = await link_to_notebook_source(doc["id"], NOTEBOOK_ID, TENANT_ID)
    assert result is not None
    assert result["notebook_id"] == NOTEBOOK_ID
    assert result["vault_document_id"] == doc["id"]
    assert "source_id" in result

    # Verify the source was actually created and linked
    async with get_session(TENANT_ID) as session:
        ns_result = await session.execute(
            text("SELECT 1 FROM notebook_sources WHERE notebook_id = :nid AND source_id = :sid"),
            {"nid": NOTEBOOK_ID, "sid": result["source_id"]},
        )
        assert ns_result.first() is not None


# ── Test 14: create_calendar_deadline handles missing module ─


@pytest.mark.asyncio
async def test_calendar_deadline_missing_module():
    """Should return None gracefully when calendar module doesn't exist."""
    from datetime import date

    result = await create_calendar_deadline(
        title="RFI Response Due",
        due_date=date.today(),
        project_id=PROJECT_ID,
        assignee_id=USER_ID,
        reminder_days=[7, 3, 1],
        tenant_id=TENANT_ID,
    )
    # Calendar module doesn't exist — should return None without crashing
    assert result is None


# ── Test 15: trigger_notification handles missing service ────


@pytest.mark.asyncio
async def test_notification_missing_service():
    """Should return False gracefully when notification service doesn't exist."""
    result = await trigger_notification(
        user_id=USER_ID,
        title="Document Processed",
        message="Your RFI has been classified",
        urgency="normal",
        action_url="/vault/documents/123",
        tenant_id=TENANT_ID,
    )
    # Notification module doesn't exist — should return False without crashing
    assert result is False
