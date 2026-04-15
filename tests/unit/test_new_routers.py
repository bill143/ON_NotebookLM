"""Unit tests for new routers: plugins, local, prompts, admin."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin import router as admin_router
from src.api.local import (
    ConflictResolution,
    FeatureAvailability,
    LocalModelInfo,
    SyncStatusResponse,
    router as local_router,
)
from src.api.plugins import (
    PluginInstallRequest,
    PluginResponse,
    PluginToggleRequest,
    router as plugins_router,
)
from src.api.prompts import (
    PromptCreate,
    PromptResponse,
    PromptRollbackRequest,
    PromptTestCase,
    router as prompts_router,
)


# ── Plugin Schemas ───────────────────────────────────────────


class TestPluginSchemas:
    def test_plugin_install_request(self):
        req = PluginInstallRequest(name="my-plugin")
        assert req.version == "latest"
        assert req.permissions == []

    def test_plugin_response(self):
        pr = PluginResponse(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
            author="Test",
            enabled=True,
            permissions=["read:notebooks"],
            installed_at="2026-01-01T00:00:00",
        )
        assert pr.enabled

    def test_plugin_toggle(self):
        pt = PluginToggleRequest(enabled=False)
        assert not pt.enabled


# ── Local Schemas ────────────────────────────────────────────


class TestLocalSchemas:
    def test_local_model_info(self):
        lm = LocalModelInfo(
            name="llama3:8b",
            size_gb=4.7,
            quantization="Q4_K_M",
            capabilities=["chat", "embedding"],
            status="available",
        )
        assert lm.provider == "ollama"

    def test_sync_status(self):
        ss = SyncStatusResponse(
            mode="online",
            pending_operations=0,
            conflicts=0,
            queue_size=0,
        )
        assert ss.mode == "online"

    def test_feature_availability(self):
        fa = FeatureAvailability(
            feature="chat",
            online=True,
            offline=True,
        )
        assert fa.degraded_note is None

    def test_conflict_resolution(self):
        cr = ConflictResolution(strategy="local_wins")
        assert cr.strategy == "local_wins"


# ── Prompt Schemas ───────────────────────────────────────────


class TestPromptSchemas:
    def test_prompt_create(self):
        pc = PromptCreate(
            namespace="chat",
            name="system",
            content="You are a helpful assistant.",
        )
        assert pc.variables == []
        assert pc.changelog == ""

    def test_prompt_create_with_vars(self):
        pc = PromptCreate(
            namespace="research",
            name="grounding",
            content="Research {{ topic }} with depth {{ depth }}",
            variables=["topic", "depth"],
            model_target="gpt-4",
            temperature=0.3,
        )
        assert len(pc.variables) == 2

    def test_prompt_rollback_request(self):
        rr = PromptRollbackRequest(target_version="1.0.0")
        assert rr.target_version == "1.0.0"

    def test_prompt_test_case(self):
        tc = PromptTestCase(
            input_variables={"topic": "AI"},
            expected_criteria={"contains": "artificial intelligence"},
            pass_threshold=0.9,
        )
        assert tc.pass_threshold == 0.9


# ── Router Registration ─────────────────────────────────────


class TestRouterRegistration:
    @pytest.fixture()
    def app(self):
        app = FastAPI()
        app.include_router(plugins_router, prefix="/api/v1")
        app.include_router(local_router, prefix="/api/v1")
        app.include_router(prompts_router, prefix="/api/v1")
        app.include_router(admin_router, prefix="/api/v1")
        return app

    def test_plugins_router_prefix(self):
        assert plugins_router.prefix == "/plugins"

    def test_local_router_prefix(self):
        assert local_router.prefix == "/local"

    def test_prompts_router_prefix(self):
        assert prompts_router.prefix == "/prompts"

    def test_admin_router_prefix(self):
        assert admin_router.prefix == "/admin"

    def _assert_route_exists(self, app, method, path):
        """Route exists if response is anything other than 404/405."""
        client = TestClient(app, raise_server_exceptions=False)
        fn = getattr(client, method)
        r = fn(path)
        assert r.status_code in (401, 403, 422, 500), (
            f"{method.upper()} {path} returned {r.status_code}"
        )

    def test_plugin_routes_exist(self, app):
        self._assert_route_exists(app, "get", "/api/v1/plugins")

    def test_local_routes_exist(self, app):
        self._assert_route_exists(app, "get", "/api/v1/local/models")

    def test_prompts_routes_exist(self, app):
        self._assert_route_exists(app, "get", "/api/v1/prompts")

    def test_admin_routes_exist(self, app):
        self._assert_route_exists(app, "get", "/api/v1/admin/audit-log")

    def test_admin_backup_route_exists(self, app):
        self._assert_route_exists(app, "post", "/api/v1/admin/backup")

    def test_local_sync_route_exists(self, app):
        self._assert_route_exists(app, "get", "/api/v1/local/sync/status")

    def test_local_features_route_exists(self, app):
        self._assert_route_exists(app, "get", "/api/v1/local/features")
