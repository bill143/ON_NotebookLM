"""Unit tests for nexus_cost_tracker — usage recording, budget checks, alerts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.nexus_cost_tracker import (
    CostTracker,
    UsageRecord,
    cost_tracker,
)

# ── UsageRecord dataclass ────────────────────────────────────


class TestUsageRecord:
    def test_required_fields(self):
        rec = UsageRecord(
            tenant_id="t1",
            user_id="u1",
            model_name="gpt-4o",
            provider="openai",
        )
        assert rec.tenant_id == "t1"
        assert rec.user_id == "u1"
        assert rec.model_name == "gpt-4o"
        assert rec.provider == "openai"

    def test_default_values(self):
        rec = UsageRecord(tenant_id="t", user_id="u", model_name="m", provider="p")
        assert rec.feature_id == ""
        assert rec.agent_id == ""
        assert rec.input_tokens == 0
        assert rec.output_tokens == 0
        assert rec.cached_tokens == 0
        assert rec.cost_usd == 0.0
        assert rec.latency_ms == 0.0
        assert rec.success is True
        assert rec.error_type is None
        assert rec.request_id is None
        assert rec.trace_id is None

    def test_custom_values(self):
        rec = UsageRecord(
            tenant_id="t",
            user_id="u",
            model_name="claude-3",
            provider="anthropic",
            feature_id="1A",
            agent_id="summary",
            input_tokens=500,
            output_tokens=200,
            cost_usd=0.01,
            latency_ms=300,
            success=False,
            error_type="timeout",
        )
        assert rec.input_tokens == 500
        assert rec.output_tokens == 200
        assert rec.cost_usd == 0.01
        assert rec.success is False
        assert rec.error_type == "timeout"


# ── CostTracker instantiation ───────────────────────────────


class TestCostTrackerInit:
    def test_is_class(self):
        tracker = CostTracker()
        assert isinstance(tracker, CostTracker)

    def test_global_singleton(self):
        assert isinstance(cost_tracker, CostTracker)


# ── record_usage (mocked DB) ────────────────────────────────


class TestRecordUsage:
    @pytest.mark.asyncio
    async def test_record_usage_calls_db(self):
        tracker = CostTracker()
        rec = UsageRecord(tenant_id="t1", user_id="u1", model_name="gpt-4o", provider="openai")

        mock_repo = MagicMock()
        mock_repo.create = AsyncMock()

        mock_metrics = MagicMock()
        mock_metrics.record_ai_call = MagicMock()

        with patch("src.infra.nexus_data_persist.usage_repo", mock_repo):
            with patch("src.infra.nexus_obs_tracing.metrics", mock_metrics):
                with patch.object(tracker, "_check_budget_alerts", new_callable=AsyncMock):
                    await tracker.record_usage(rec)

        mock_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_usage_does_not_raise_on_failure(self):
        tracker = CostTracker()
        rec = UsageRecord(tenant_id="t1", user_id="u1", model_name="m", provider="p")

        mock_repo = MagicMock()
        mock_repo.create = AsyncMock(side_effect=Exception("DB down"))
        with patch("src.infra.nexus_data_persist.usage_repo", mock_repo):
            await tracker.record_usage(rec)


# ── check_budget (mocked DB) ────────────────────────────────


class TestCheckBudget:
    @pytest.mark.asyncio
    async def test_no_budget_row_returns_allowed(self):
        tracker = CostTracker()

        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = None

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.infra.nexus_data_persist") as mock_db:
            mock_db.get_session.return_value = mock_session
            result = await tracker.check_budget("t1", "u1")

        assert result["allowed"] is True
        assert result["remaining_usd"] == float("inf")

    @pytest.mark.asyncio
    async def test_within_budget(self):
        tracker = CostTracker()

        mock_row = {"limit_usd": 100.0, "current_usage": 50.0, "hard_limit": True}
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.infra.nexus_data_persist") as mock_db:
            mock_db.get_session.return_value = mock_session
            result = await tracker.check_budget("t1", "u1", estimated_cost=10.0)

        assert result["allowed"] is True
        assert result["remaining_usd"] == 50.0
        assert result["utilization_pct"] == 50.0

    @pytest.mark.asyncio
    async def test_budget_exceeded_raises(self):
        from src.exceptions import TokenBudgetExceeded

        tracker = CostTracker()

        mock_row = {"limit_usd": 100.0, "current_usage": 95.0, "hard_limit": True}
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.infra.nexus_data_persist") as mock_db:
            mock_db.get_session.return_value = mock_session
            with pytest.raises(TokenBudgetExceeded, match="Budget exceeded"):
                await tracker.check_budget("t1", "u1", estimated_cost=10.0)

    @pytest.mark.asyncio
    async def test_soft_limit_allows(self):
        tracker = CostTracker()

        mock_row = {"limit_usd": 100.0, "current_usage": 95.0, "hard_limit": False}
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = mock_row

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("src.infra.nexus_data_persist") as mock_db:
            mock_db.get_session.return_value = mock_session
            result = await tracker.check_budget("t1", "u1", estimated_cost=10.0)

        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_db_error_returns_allowed(self):
        tracker = CostTracker()

        with patch("src.infra.nexus_data_persist") as mock_db:
            mock_db.get_session.side_effect = Exception("Connection refused")
            result = await tracker.check_budget("t1", "u1")

        assert result["allowed"] is True


# ── _check_budget_alerts ─────────────────────────────────────


class TestCheckBudgetAlerts:
    @pytest.mark.asyncio
    async def test_alerts_do_not_raise(self):
        tracker = CostTracker()
        with patch.object(
            tracker,
            "check_budget",
            new_callable=AsyncMock,
            return_value={"utilization_pct": 85},
        ):
            await tracker._check_budget_alerts("t1", "u1")

    @pytest.mark.asyncio
    async def test_alert_check_failure_swallowed(self):
        tracker = CostTracker()
        with patch.object(
            tracker,
            "check_budget",
            new_callable=AsyncMock,
            side_effect=Exception("alert fail"),
        ):
            await tracker._check_budget_alerts("t1", "u1")
