"""
Integration-only pytest hooks:
- Module-scoped HTTP client (one DB pool per test file).
- Stub LLM provisioning so tests pass without API keys.

Set NEXUS_INTEGRATION_REAL_LLM=1 to call the real model stack (requires credentials + network).
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.agents.nexus_model_layer import AIResponse
from src.infra.nexus_data_persist import close_database, init_database
from src.main import app


class _StubLLM:
    async def generate(self, messages: list, temperature: float = 0.7) -> AIResponse:
        return AIResponse(
            content="Integration stub reply.",
            model="stub-llm",
            provider="stub",
            input_tokens=3,
            output_tokens=5,
            latency_ms=0.0,
            cost_usd=0.0,
        )


@pytest.fixture(autouse=True)
def _stub_llm_for_integration_tests() -> None:
    if os.environ.get("NEXUS_INTEGRATION_REAL_LLM") == "1":
        yield
        return

    async def _provision(*args, **kwargs):
        return _StubLLM()

    with patch(
        "src.agents.nexus_model_layer.model_manager.provision_llm",
        new=AsyncMock(side_effect=_provision),
    ):
        yield


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """One shared async client + DB pool per integration test module."""
    from tests.conftest import ensure_integration_principals

    try:
        await init_database()
        await ensure_integration_principals()
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(
            "Integration services unavailable. Start Docker services first "
            "(`docker compose -f deploy/docker-compose.yml up -d postgres redis`). "
            f"Details: {exc}"
        )

    with patch("src.worker.generate_artifact.delay", MagicMock()):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    await close_database()
