"""
Permit Workflow — Permit Processing Agent.

Handles construction permit lifecycle:
- Permit record creation with number and issuing authority
- Expiration tracking with multi-stage reminders (90, 60, 30, 14, 7 days)
- Work activity linking
- Critical expiration alerts to PM and Superintendent
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

PERMIT_EXPIRATION_REMINDER_OFFSETS_DAYS = [90, 60, 30, 14, 7]


class PermitWorkflow(BaseWorkflow):
    """Workflow agent for construction permit documents."""

    workflow_name = "permit"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            return await self._process_permit(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"Permit workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _process_permit(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        metadata = decision.metadata

        permit_number = metadata.get("permit_number", f"PRM-{uuid.uuid4().hex[:8].upper()}")
        issuing_authority = metadata.get("issuing_authority", "")
        permit_type = metadata.get("permit_type", "General")
        work_activities = metadata.get("work_activities", [])

        expiration_str = metadata.get("expiration_date", "")
        if expiration_str:
            expiration_date = datetime.fromisoformat(expiration_str).replace(tzinfo=UTC)
        else:
            expiration_date = datetime.now(UTC) + timedelta(days=365)

        # 1. Create permit record
        permit_record = {
            "id": str(uuid.uuid4()),
            "permit_number": permit_number,
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "permit_type": permit_type,
            "issuing_authority": issuing_authority,
            "expiration_date": expiration_date.isoformat(),
            "work_activities": work_activities,
            "status": "ACTIVE",
            "created_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(permit_record)
        self._record_action("create_permit_record", {
            "permit_number": permit_number,
            "permit_type": permit_type,
            "issuing_authority": issuing_authority,
        })

        # 2. Link to relevant work activities
        if work_activities:
            for activity in work_activities:
                self._records.append({
                    "type": "permit_activity_link",
                    "permit_id": permit_record["id"],
                    "activity": activity,
                })
            self._record_action("link_work_activities", {
                "permit_number": permit_number,
                "activities": work_activities,
            })

        # 3. Schedule expiration reminders
        pm = metadata.get("project_manager", user_id)
        superintendent = metadata.get("superintendent", user_id)

        from src.worker import celery_app

        for offset in PERMIT_EXPIRATION_REMINDER_OFFSETS_DAYS:
            fire_at = expiration_date - timedelta(days=offset)
            if fire_at > datetime.now(UTC):
                celery_app.send_task(
                    "nexus.vault.send_reminder",
                    args=[
                        pm,
                        f"Permit {permit_number} ({permit_type}) expires in {offset} days",
                        permit_record["id"],
                        project_id,
                    ],
                    eta=fire_at,
                )

        # Day-of expiration: critical alert
        if expiration_date > datetime.now(UTC):
            celery_app.send_task(
                "nexus.vault.permit_expiration_alert",
                args=[permit_record["id"], permit_number, project_id, pm, superintendent],
                eta=expiration_date,
            )

        self._record_action("schedule_expiration_reminders", {
            "permit_number": permit_number,
            "expiration_date": expiration_date.isoformat(),
        })

        # 4. Notify PM
        await self.notify(
            recipients=[pm],
            subject=f"Permit Logged — {permit_number} ({permit_type})",
            message=(
                f"A new permit has been logged for the project.\n\n"
                f"Permit Number: {permit_number}\n"
                f"Type: {permit_type}\n"
                f"Issuing Authority: {issuing_authority}\n"
                f"Expiration: {expiration_date.strftime('%B %d, %Y')}\n"
                f"Linked Activities: {', '.join(work_activities) if work_activities else 'None'}"
            ),
            channel=NotificationChannel.BOTH,
            urgency=Urgency.NORMAL,
        )

        await self.create_log_entry(
            action="permit_logged",
            details={"permit_number": permit_number, "permit_type": permit_type},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=[
                f"Permit active — monitoring expiration {expiration_date.strftime('%Y-%m-%d')}",
            ],
        )
