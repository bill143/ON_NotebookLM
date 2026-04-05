"""
Integration Tests — Artifacts, Chat, Models, Health APIs
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.conftest import (
    TEST_NOTEBOOK_ID,
    make_artifact_data,
    make_chat_data,
    make_model_data,
)

# ── Artifacts Tests ──────────────────────────────────────────


@pytest.mark.asyncio
class TestArtifactsAPI:
    async def test_create_artifact(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/artifacts — queues artifact generation."""
        data = make_artifact_data(artifact_type="summary")

        response = await client.post(
            "/api/v1/artifacts",
            json=data,
            headers=user_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "queued"
        assert body["artifact_type"] == "summary"

    async def test_list_artifacts(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/artifacts — lists user artifacts."""
        response = await client.get(
            "/api/v1/artifacts",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_list_artifacts_filter(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/artifacts?status=queued — filters by status."""
        response = await client.get(
            "/api/v1/artifacts?status=queued",
            headers=user_headers,
        )

        assert response.status_code == 200

    async def test_cancel_artifact(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/artifacts/:id/cancel — cancels generation."""
        create_resp = await client.post(
            "/api/v1/artifacts",
            json=make_artifact_data(artifact_type="quiz"),
            headers=user_headers,
        )
        artifact_id = create_resp.json()["id"]

        response = await client.post(
            f"/api/v1/artifacts/{artifact_id}/cancel",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    async def test_queue_status(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/artifacts/queue/status — returns queue counts."""
        response = await client.get(
            "/api/v1/artifacts/queue/status",
            headers=user_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert "queued" in body
        assert "processing" in body

    async def test_create_podcast_artifact_with_presets(
        self, client: AsyncClient, user_headers: dict
    ):
        """POST /api/v1/artifacts — accepts validated podcast preset config."""
        response = await client.post(
            "/api/v1/artifacts",
            json={
                "notebook_id": TEST_NOTEBOOK_ID,
                "title": "Podcast with Presets",
                "artifact_type": "podcast",
                "generation_config": {
                    "format": "deep_dive",
                    "length": "long",
                    "language": "English",
                    "speaker_profile": "interviewer_guest",
                    "speech_rate": 1.1,
                },
            },
            headers=user_headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["artifact_type"] == "podcast"

    async def test_create_podcast_artifact_rejects_invalid_presets(
        self, client: AsyncClient, user_headers: dict
    ):
        """POST /api/v1/artifacts — rejects invalid podcast preset values."""
        response = await client.post(
            "/api/v1/artifacts",
            json={
                "notebook_id": TEST_NOTEBOOK_ID,
                "title": "Podcast Invalid",
                "artifact_type": "podcast",
                "generation_config": {
                    "format": "unsupported",
                    "length": "very_long",
                    "speaker_profile": "unknown",
                    "speech_rate": 2.0,
                },
            },
            headers=user_headers,
        )

        assert response.status_code == 422

    async def test_get_podcast_preset_catalog(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/artifacts/podcast/presets — returns preset metadata."""
        response = await client.get(
            "/api/v1/artifacts/podcast/presets",
            headers=user_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert "default" in body
        assert "formats" in body
        assert "speaker_profiles" in body


# ── Chat Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestChatAPI:
    async def test_send_message(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/chat — sends chat message."""
        data = make_chat_data(content="Explain machine learning in simple terms")

        response = await client.post(
            "/api/v1/chat",
            json=data,
            headers=user_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert "session_id" in body
        assert "content" in body
        assert body["turn_number"] >= 1

    async def test_send_empty_message(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/chat — rejects empty message."""
        response = await client.post(
            "/api/v1/chat",
            json={"content": ""},
            headers=user_headers,
        )

        assert response.status_code == 422

    async def test_list_sessions(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/chat/sessions — lists chat sessions."""
        response = await client.get(
            "/api/v1/chat/sessions",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_get_session_messages(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/chat/sessions/:id/messages — returns 200."""
        response = await client.get(
            "/api/v1/chat/sessions/00000000-0000-0000-0000-000000000099/messages",
            headers=user_headers,
        )

        assert response.status_code == 200


# ── Models Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestModelsAPI:
    async def test_list_models(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/models — lists registered models."""
        response = await client.get(
            "/api/v1/models",
            headers=user_headers,
        )

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_register_model_requires_admin(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/models — rejects non-admin users."""
        data = make_model_data(name="test-model")

        response = await client.post(
            "/api/v1/models",
            json=data,
            headers=user_headers,
        )

        assert response.status_code == 403

    async def test_register_model_as_admin(self, client: AsyncClient, admin_auth_headers: dict):
        """POST /api/v1/models — allows admin registration."""
        data = make_model_data(name="admin-test-model")

        response = await client.post(
            "/api/v1/models",
            json=data,
            headers=admin_auth_headers,
        )

        assert response.status_code == 201

    async def test_store_credential_requires_admin(self, client: AsyncClient, user_headers: dict):
        """POST /api/v1/models/credentials — rejects non-admin."""
        response = await client.post(
            "/api/v1/models/credentials",
            json={"provider": "openai", "credential_name": "test", "api_key": "sk-test"},
            headers=user_headers,
        )

        assert response.status_code == 403

    async def test_usage_summary(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/models/usage/summary — returns usage data."""
        response = await client.get(
            "/api/v1/models/usage/summary",
            headers=user_headers,
        )

        assert response.status_code == 200

    async def test_budget_check(self, client: AsyncClient, user_headers: dict):
        """GET /api/v1/models/usage/budget — returns budget status."""
        response = await client.get(
            "/api/v1/models/usage/budget",
            headers=user_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert "allowed" in body


# ── Health Tests ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestHealthAPI:
    async def test_liveness(self, client: AsyncClient):
        """GET /health/live — returns alive status."""
        response = await client.get("/health/live")

        assert response.status_code == 200
        assert response.json()["status"] == "alive"

    async def test_readiness(self, client: AsyncClient):
        """GET /health/ready — checks service readiness."""
        response = await client.get("/health/ready")

        assert response.status_code in (200, 503)
        body = response.json()
        assert "status" in body
        assert "checks" in body

    async def test_startup(self, client: AsyncClient):
        """GET /health/startup — checks startup status."""
        response = await client.get("/health/startup")

        assert response.status_code in (200, 503)

    async def test_metrics(self, client: AsyncClient):
        """GET /metrics — returns Prometheus metrics."""
        response = await client.get("/metrics")

        assert response.status_code == 200
        assert "nexus_" in response.text or "# HELP" in response.text

    async def test_api_root(self, client: AsyncClient):
        """GET /api/v1 — returns service info."""
        response = await client.get("/api/v1")

        assert response.status_code == 200
        body = response.json()
        assert body["codename"] == "ESPERANTO"
        assert "version" in body
