"""
COI Workflow — Certificate of Insurance Processing Agent.

Handles insurance certificate lifecycle:
- Policy detail extraction and tracking
- Coverage verification against project minimums
- Expiration date monitoring with multi-stage reminders
- Stop-work flagging on expiration
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from loguru import logger

from src.vault.workflows.base_workflow import (
    BaseWorkflow,
    LibrarianDecision,
    NotificationChannel,
    Urgency,
    WorkflowResult,
)

# Default minimum coverage requirements (can be overridden per project)
DEFAULT_MIN_COVERAGE: dict[str, float] = {
    "general_liability": 1_000_000.0,
    "auto_liability": 1_000_000.0,
    "workers_comp": 500_000.0,
    "umbrella": 2_000_000.0,
}

EXPIRATION_REMINDER_OFFSETS_DAYS = [60, 30, 14, 7, 0]


class COIWorkflow(BaseWorkflow):
    """Workflow agent for Certificate of Insurance documents."""

    workflow_name = "coi"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            return await self._process_coi(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"COI workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _process_coi(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        metadata = decision.metadata
        next_steps: list[str] = []

        # 1. Extract policy details
        subcontractor = metadata.get("subcontractor", metadata.get("insured_name", "Unknown"))
        policy_number = metadata.get("policy_number", "")
        carrier = metadata.get("insurance_carrier", "")

        expiration_str = metadata.get("expiration_date", "")
        if expiration_str:
            expiration_date = datetime.fromisoformat(expiration_str).replace(tzinfo=UTC)
        else:
            # Default: 1 year from now if not extracted
            expiration_date = datetime.now(UTC) + timedelta(days=365)

        coverage_amounts: dict[str, float] = metadata.get("coverage_amounts", {})

        self._record_action("extract_policy_details", {
            "subcontractor": subcontractor,
            "policy_number": policy_number,
            "carrier": carrier,
            "expiration_date": expiration_date.isoformat(),
        })

        # 2. Verify coverage meets project minimums
        min_requirements = metadata.get("min_coverage_requirements", DEFAULT_MIN_COVERAGE)
        insufficient_coverage: list[dict[str, Any]] = []

        for coverage_type, min_amount in min_requirements.items():
            actual = coverage_amounts.get(coverage_type, 0.0)
            if actual < min_amount:
                insufficient_coverage.append({
                    "type": coverage_type,
                    "required": min_amount,
                    "actual": actual,
                    "shortfall": min_amount - actual,
                })

        if insufficient_coverage:
            self._record_action("flag_insufficient_coverage", {
                "subcontractor": subcontractor,
                "gaps": insufficient_coverage,
            })

            pm = metadata.get("project_manager", user_id)
            contracts_admin = metadata.get("contracts_admin", user_id)
            gap_details = "\n".join(
                f"  - {g['type']}: Required ${g['required']:,.0f}, Actual ${g['actual']:,.0f} "
                f"(shortfall ${g['shortfall']:,.0f})"
                for g in insufficient_coverage
            )
            await self.notify(
                recipients=[pm, contracts_admin],
                subject=f"Insufficient Insurance Coverage — {subcontractor}",
                message=(
                    f"The COI submitted by {subcontractor} does not meet project minimum "
                    f"requirements.\n\nCoverage Gaps:\n{gap_details}\n\n"
                    f"Please request an updated COI with adequate coverage."
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH,
            )
            next_steps.append("Request updated COI with adequate coverage")

        # 3. Create or update insurance tracking record
        coi_record = {
            "id": str(uuid.uuid4()),
            "subcontractor": subcontractor,
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "policy_number": policy_number,
            "carrier": carrier,
            "expiration_date": expiration_date.isoformat(),
            "coverage_amounts": coverage_amounts,
            "coverage_adequate": len(insufficient_coverage) == 0,
            "status": "ACTIVE",
            "created_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(coi_record)
        self._record_action("create_insurance_record", {
            "subcontractor": subcontractor,
            "policy_number": policy_number,
            "expiration_date": expiration_date.isoformat(),
        })

        # 4. Schedule expiration reminders at 60, 30, 14, 7, and 0 days
        pm = metadata.get("project_manager", user_id)
        contracts_admin = metadata.get("contracts_admin", user_id)

        for offset in EXPIRATION_REMINDER_OFFSETS_DAYS:
            fire_at = expiration_date - timedelta(days=offset)
            if fire_at > datetime.now(UTC):
                from src.worker import celery_app

                if offset == 0:
                    # Day of expiration — critical alert with stop-work flag
                    celery_app.send_task(
                        "nexus.vault.coi_expiration_alert",
                        args=[coi_record["id"], subcontractor, project_id, pm, contracts_admin],
                        eta=fire_at,
                    )
                else:
                    celery_app.send_task(
                        "nexus.vault.send_reminder",
                        args=[
                            contracts_admin,
                            f"COI for {subcontractor} expires in {offset} days "
                            f"(Policy: {policy_number})",
                            coi_record["id"],
                            project_id,
                        ],
                        eta=fire_at,
                    )

        self._record_action("schedule_expiration_reminders", {
            "expiration_date": expiration_date.isoformat(),
            "reminders_at_days": EXPIRATION_REMINDER_OFFSETS_DAYS,
        })

        await self.create_log_entry(
            action="coi_processed",
            details={
                "subcontractor": subcontractor,
                "policy_number": policy_number,
                "coverage_adequate": len(insufficient_coverage) == 0,
            },
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        if not next_steps:
            next_steps.append(
                f"COI active — monitoring expiration {expiration_date.strftime('%Y-%m-%d')}"
            )

        return self._build_result(success=True, next_steps=next_steps)
