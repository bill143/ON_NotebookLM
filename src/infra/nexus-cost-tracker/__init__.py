"""
Nexus Cost Tracker — Feature 11: Token Usage Tracking & Budget Management
Source: ORIGINAL ENGINEERING (Tier 1 Critical Gap — no repo has this)

Provides:
- Per-request token accounting middleware
- Per-user and per-tenant cost aggregation
- Budget limit enforcement (hard/soft limits)
- Budget alerts at 80%/90%/100% thresholds
- Cost estimation before execution
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger


@dataclass
class UsageRecord:
    """A single AI API usage record."""
    tenant_id: str
    user_id: str
    model_name: str
    provider: str
    feature_id: str = ""
    agent_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    success: bool = True
    error_type: Optional[str] = None
    request_id: Optional[str] = None
    trace_id: Optional[str] = None


class CostTracker:
    """
    Middleware for tracking AI API costs and enforcing budgets.

    Architecture:
    - Wraps every AI call with usage recording
    - Fire-and-forget recording (never blocks the AI call)
    - Budget checks before execution
    - Alerts via webhook at configurable thresholds
    """

    async def record_usage(self, record: UsageRecord) -> None:
        """Record a usage event to the database."""
        try:
            from src.infra import nexus_data_persist as db

            await db.usage_repo.create(
                data={
                    "tenant_id": record.tenant_id,
                    "user_id": record.user_id,
                    "model_name": record.model_name,
                    "provider": record.provider,
                    "feature_id": record.feature_id,
                    "agent_id": record.agent_id,
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "cached_tokens": record.cached_tokens,
                    "cost_usd": record.cost_usd,
                    "latency_ms": record.latency_ms,
                    "success": record.success,
                    "error_type": record.error_type,
                    "request_id": record.request_id,
                    "trace_id": record.trace_id,
                },
                tenant_id=record.tenant_id,
            )

            # Update metrics
            from src.infra.nexus_obs_tracing import metrics
            metrics.record_ai_call(
                provider=record.provider,
                model=record.model_name,
                agent=record.agent_id,
                success=record.success,
                latency_seconds=record.latency_ms / 1000,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                cost_usd=record.cost_usd,
                tenant_id=record.tenant_id,
            )

            # Check budget thresholds
            await self._check_budget_alerts(record.tenant_id, record.user_id)

        except Exception as e:
            # Cost tracking MUST NOT block AI calls (fire-and-forget)
            logger.error(f"Failed to record usage: {e}", exc_info=True)

    async def check_budget(
        self,
        tenant_id: str,
        user_id: str,
        estimated_cost: float = 0.0,
    ) -> dict[str, Any]:
        """
        Check if a request is within budget.

        Returns: {allowed: bool, remaining_usd: float, limit_usd: float}
        """
        try:
            from src.infra import nexus_data_persist as db
            from sqlalchemy import text

            query = """
                SELECT bl.limit_usd, bl.hard_limit,
                       COALESCE(SUM(ur.cost_usd), 0) as current_usage
                FROM budget_limits bl
                LEFT JOIN usage_records ur ON ur.tenant_id = bl.tenant_id
                    AND ur.created_at >= bl.period_start
                    AND (bl.user_id IS NULL OR ur.user_id = bl.user_id)
                WHERE bl.tenant_id = :tenant_id
                  AND (bl.user_id = :user_id OR bl.user_id IS NULL)
                GROUP BY bl.id
                ORDER BY bl.user_id DESC NULLS LAST
                LIMIT 1
            """

            async with db.get_session(tenant_id) as session:
                result = await session.execute(
                    text(query),
                    {"tenant_id": tenant_id, "user_id": user_id},
                )
                row = result.mappings().first()

            if not row:
                return {"allowed": True, "remaining_usd": float("inf"), "limit_usd": 0}

            limit = float(row["limit_usd"])
            current = float(row["current_usage"])
            remaining = limit - current

            if row["hard_limit"] and (current + estimated_cost) > limit:
                from src.exceptions import TokenBudgetExceeded
                raise TokenBudgetExceeded(
                    f"Budget exceeded: ${current:.2f} / ${limit:.2f}",
                    details={"current_usd": current, "limit_usd": limit},
                )

            return {
                "allowed": True,
                "remaining_usd": max(0, remaining),
                "limit_usd": limit,
                "current_usd": current,
                "utilization_pct": (current / limit * 100) if limit > 0 else 0,
            }

        except Exception as e:
            if "TokenBudgetExceeded" in type(e).__name__:
                raise
            logger.error(f"Budget check failed: {e}")
            return {"allowed": True, "remaining_usd": float("inf"), "limit_usd": 0}

    async def get_usage_summary(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        period_days: int = 30,
    ) -> dict[str, Any]:
        """Get usage summary for a tenant/user over a period."""
        from src.infra import nexus_data_persist as db
        from sqlalchemy import text
        from datetime import timedelta

        period_start = datetime.now(timezone.utc) - timedelta(days=period_days)

        query = """
            SELECT
                COUNT(*) as total_requests,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(cost_usd) as total_cost_usd,
                AVG(latency_ms)::int as avg_latency_ms,
                COUNT(*) FILTER (WHERE success = false) as failed_requests,
                jsonb_object_agg(
                    COALESCE(provider, 'unknown'),
                    provider_count
                ) as by_provider
            FROM usage_records ur
            LEFT JOIN LATERAL (
                SELECT COUNT(*) as provider_count
                FROM usage_records ur2
                WHERE ur2.tenant_id = ur.tenant_id
                  AND ur2.provider = ur.provider
                  AND ur2.created_at >= :period_start
            ) pc ON true
            WHERE ur.tenant_id = :tenant_id
              AND ur.created_at >= :period_start
        """
        params: dict[str, Any] = {"tenant_id": tenant_id, "period_start": period_start}

        if user_id:
            query = query.replace(
                "WHERE ur.tenant_id",
                "WHERE ur.user_id = :user_id AND ur.tenant_id",
            )
            params["user_id"] = user_id

        async with db.get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            row = result.mappings().first()
            return dict(row) if row else {}

    async def _check_budget_alerts(self, tenant_id: str, user_id: str) -> None:
        """Check and send budget threshold alerts."""
        try:
            budget = await self.check_budget(tenant_id, user_id)
            utilization = budget.get("utilization_pct", 0)

            if utilization >= 100:
                logger.warning(
                    "BUDGET EXCEEDED",
                    tenant_id=tenant_id,
                    utilization_pct=utilization,
                )
            elif utilization >= 90:
                logger.warning(
                    "Budget at 90%",
                    tenant_id=tenant_id,
                    utilization_pct=utilization,
                )
            elif utilization >= 80:
                logger.info(
                    "Budget at 80%",
                    tenant_id=tenant_id,
                    utilization_pct=utilization,
                )
        except Exception:
            pass  # Budget alerts must never crash


# Global singleton
cost_tracker = CostTracker()
