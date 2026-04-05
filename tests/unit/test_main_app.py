"""Unit tests for FastAPI app wiring (mocked lifespan / DB)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.infra.nexus_vault_keys import create_access_token


@pytest_asyncio.fixture
async def app_client() -> AsyncClient:
    with (
        patch(
            "src.infra.nexus_obs_tracing.setup_logging",
            MagicMock(),
        ),
        patch(
            "src.infra.nexus_data_persist.init_database",
            new_callable=AsyncMock,
        ),
        patch(
            "src.infra.nexus_data_persist.close_database",
            new_callable=AsyncMock,
        ),
        patch(
            "src.infra.nexus_ws_broker.ws_broker.connect",
            new_callable=AsyncMock,
        ),
        patch(
            "src.infra.nexus_ws_broker.ws_broker.disconnect",
            new_callable=AsyncMock,
        ),
    ):
        from src.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_health_live(app_client: AsyncClient) -> None:
    r = await app_client.get("/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_health_startup_when_engine_none(app_client: AsyncClient) -> None:
    with patch("src.infra.nexus_data_persist._engine", None):
        r = await app_client.get("/health/startup")
    assert r.status_code == 503
    assert r.json()["status"] == "starting"


@pytest.mark.asyncio
async def test_health_startup_when_engine_set(app_client: AsyncClient) -> None:
    fake_engine = object()
    with patch("src.infra.nexus_data_persist._engine", fake_engine):
        r = await app_client.get("/health/startup")
    assert r.status_code == 200
    assert r.json()["status"] == "started"


@pytest.mark.asyncio
async def test_metrics_endpoint(app_client: AsyncClient) -> None:
    r = await app_client.get("/metrics")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/plain")


@pytest.mark.asyncio
async def test_api_v1_root(app_client: AsyncClient) -> None:
    r = await app_client.get("/api/v1")
    assert r.status_code == 200
    body = r.json()
    assert "service" in body
    assert "version" in body
    assert body.get("codename") == "ESPERANTO"


@pytest.mark.asyncio
async def test_request_middleware_skips_invalid_bearer_trace(app_client: AsyncClient) -> None:
    """Invalid JWT on optional tracing path should not break the request."""
    r = await app_client.get(
        "/health/live",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_request_middleware_parses_valid_bearer_for_trace(app_client: AsyncClient) -> None:
    tok = create_access_token("trace-user", "trace-tenant", ["member"])
    r = await app_client.get("/health/live", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.headers.get("X-Trace-ID")


@pytest.mark.asyncio
async def test_lifespan_initializes_sentry_when_dsn_set() -> None:
    from src.main import lifespan

    mock_settings = MagicMock()
    mock_settings.sentry_dsn = "https://examplePublicKey@o0.ingest.sentry.io/0"
    mock_settings.app_name = "Nexus"
    mock_settings.app_version = "0.1.0"
    mock_settings.environment.value = "development"
    mock_settings.log_level.value = "INFO"
    mock_settings.log_format = "text"

    with (
        patch("src.main.get_settings", return_value=mock_settings),
        patch("src.infra.nexus_obs_tracing.setup_logging", MagicMock()),
        patch("src.infra.nexus_data_persist.init_database", new_callable=AsyncMock),
        patch("src.infra.nexus_data_persist.close_database", new_callable=AsyncMock),
        patch("src.infra.nexus_ws_broker.ws_broker.connect", new_callable=AsyncMock),
        patch("src.infra.nexus_ws_broker.ws_broker.disconnect", new_callable=AsyncMock),
        patch("sentry_sdk.init") as sentry_init,
    ):
        app = MagicMock()
        async with lifespan(app):
            pass
    sentry_init.assert_called_once()


@pytest.mark.asyncio
async def test_nexus_error_handler_returns_json() -> None:
    from src.exceptions import AuthError
    from src.main import nexus_error_handler

    req = MagicMock()
    req.url.path = "/demo"
    resp = await nexus_error_handler(req, AuthError("no access"))
    assert resp.status_code == 401
    assert "error" in resp.body.decode()


@pytest.mark.asyncio
async def test_unhandled_error_handler_masks_internals() -> None:
    from src.main import unhandled_error_handler

    req = MagicMock()
    req.method = "GET"
    req.url.path = "/boom"
    resp = await unhandled_error_handler(req, RuntimeError("secret internals"))
    assert resp.status_code == 500
    body = resp.body.decode()
    assert "secret" not in body
    assert "INTERNAL_ERROR" in body


@pytest.mark.asyncio
async def test_health_ready_ok_when_db_ping_succeeds(app_client: AsyncClient) -> None:
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()

    @asynccontextmanager
    async def ok_session(_tenant_id: str | None = None):
        yield mock_session

    with patch("src.infra.nexus_data_persist.get_session", ok_session):
        r = await app_client.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_degraded_without_db(app_client: AsyncClient) -> None:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def failing_cm():
        msg = "no db"
        raise RuntimeError(msg)
        yield MagicMock()  # pragma: no cover

    def mock_get_session(*_a: object, **_kw: object):
        return failing_cm()

    with patch("src.infra.nexus_data_persist.get_session", mock_get_session):
        r = await app_client.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert "database" in body["checks"]
