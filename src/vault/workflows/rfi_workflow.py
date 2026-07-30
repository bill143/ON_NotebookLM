"""
RFI Workflow — Request for Information Processing Agent.

The most critical construction document workflow. Handles:
- RFI creation with auto-incremented numbering
- Discipline-based reviewer assignment
- Distribution list management
- Deadline tracking with escalation chain
- Response processing with scope change detection
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

# ── Discipline → Reviewer Mapping ──────────────────────────

DISCIPLINE_REVIEWERS: dict[str, str] = {
    "structural": "structural_engineer",
    "mep": "mep_engineer",
    "mechanical": "mep_engineer",
    "electrical": "mep_engineer",
    "plumbing": "mep_engineer",
    "civil": "civil_engineer",
    "architectural": "architect",
    "landscape": "landscape_architect",
    "geotechnical": "geotechnical_engineer",
    "environmental": "environmental_consultant",
}

DEFAULT_RFI_REVIEW_DAYS = 14
OVERDUE_LETTER_DAY = 1  # days after deadline
ESCALATION_DAY = 7  # days after deadline


class RFIWorkflow(BaseWorkflow):
    """Workflow agent for Request for Information documents."""

    workflow_name = "rfi"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            # Determine if this is a new RFI or a response to an existing one
            is_response = "response" in decision.workflow_triggers or decision.metadata.get(
                "is_response", False
            )

            if is_response:
                return await self._handle_response(document, decision, project_id, user_id)
            return await self._handle_new_rfi(document, decision, project_id, user_id)

        except Exception as e:
            logger.error(f"RFI workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _handle_new_rfi(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        """Process a newly uploaded RFI document."""
        metadata = decision.metadata
        project_code = metadata.get("project_code", project_id[:8].upper())

        # 1. Generate RFI number
        rfi_sequence = metadata.get("rfi_sequence", 1)
        rfi_number = f"RFI-{project_code}-{rfi_sequence:04d}"
        self._record_action("generate_rfi_number", {"rfi_number": rfi_number})

        # 2. Create RFI record
        discipline = metadata.get("discipline", "architectural").lower()
        reviewer = DISCIPLINE_REVIEWERS.get(discipline, "architect")
        submitter = metadata.get("submitter", user_id)

        # Due date: 14 calendar days unless extracted from document
        due_date_str = metadata.get("due_date")
        if due_date_str:
            due_date = datetime.fromisoformat(due_date_str).replace(tzinfo=UTC)
        else:
            due_date = datetime.now(UTC) + timedelta(days=DEFAULT_RFI_REVIEW_DAYS)

        rfi_record = {
            "id": str(uuid.uuid4()),
            "rfi_number": rfi_number,
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "subject": metadata.get("subject", document.get("title", "Untitled RFI")),
            "discipline": discipline,
            "submitter": submitter,
            "reviewer": reviewer,
            "status": "OPEN",
            "submitted_date": datetime.now(UTC).isoformat(),
            "due_date": due_date.isoformat(),
            "created_by": user_id,
        }
        self._records.append(rfi_record)
        self._record_action("create_rfi_record", {"rfi_number": rfi_number, "reviewer": reviewer})

        # 3. Distribute to all parties on distribution list
        distribution_list = metadata.get("distribution_list", [])
        if distribution_list:
            await self.notify(
                recipients=distribution_list,
                subject=f"New RFI Issued — {rfi_number}: {rfi_record['subject']}",
                message=(
                    f"A new Request for Information has been issued.\n\n"
                    f"RFI Number: {rfi_number}\n"
                    f"Subject: {rfi_record['subject']}\n"
                    f"Discipline: {discipline.title()}\n"
                    f"Due Date: {due_date.strftime('%B %d, %Y')}\n"
                    f"Assigned Reviewer: {reviewer}"
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.NORMAL,
            )
            self._record_action(
                "distribute_rfi", {"recipients_count": len(distribution_list)}
            )

        # 4. Notify submitter confirming receipt
        await self.notify(
            recipients=[submitter],
            subject=f"RFI Received — {rfi_number}",
            message=(
                f"Your Request for Information has been received and logged.\n\n"
                f"RFI Number: {rfi_number}\n"
                f"Subject: {rfi_record['subject']}\n"
                f"Response Due: {due_date.strftime('%B %d, %Y')}\n"
                f"Assigned Reviewer: {reviewer}"
            ),
            channel=NotificationChannel.BOTH,
            urgency=Urgency.NORMAL,
        )
        self._record_action("notify_submitter", {"submitter": submitter})

        # 5. Notify reviewer with deadline
        await self.notify(
            recipients=[reviewer],
            subject=f"RFI Assigned — {rfi_number}: {rfi_record['subject']}",
            message=(
                f"You have been assigned to review the following RFI.\n\n"
                f"RFI Number: {rfi_number}\n"
                f"Subject: {rfi_record['subject']}\n"
                f"Discipline: {discipline.title()}\n"
                f"Submitted By: {submitter}\n"
                f"Response Due: {due_date.strftime('%B %d, %Y')}\n\n"
                f"Please provide your response before the deadline."
            ),
            channel=NotificationChannel.BOTH,
            urgency=Urgency.HIGH,
        )
        self._record_action("notify_reviewer", {"reviewer": reviewer})

        # 6. Schedule deadline reminders via Celery
        await self._schedule_rfi_reminders(
            rfi_number=rfi_number,
            rfi_id=rfi_record["id"],
            reviewer=reviewer,
            project_id=project_id,
            due_date=due_date,
            pm=metadata.get("project_manager", user_id),
            pic=metadata.get("principal_in_charge", ""),
        )

        # 7. Log entry
        await self.create_log_entry(
            action="rfi_created",
            details={"rfi_number": rfi_number, "discipline": discipline, "reviewer": reviewer},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=[
                f"Awaiting response from {reviewer} by {due_date.strftime('%Y-%m-%d')}",
                "Deadline reminders scheduled at T-2, T-0, T+1, T+7",
            ],
        )

    async def _handle_response(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        """Process an RFI response document linked to an existing RFI."""
        metadata = decision.metadata
        rfi_number = metadata.get("rfi_number", "UNKNOWN")
        rfi_id = metadata.get("rfi_id", "")

        # 1. Update RFI status
        self._record_action("update_rfi_status", {"rfi_number": rfi_number, "status": "RESPONDED"})
        self._records.append({
            "type": "rfi_status_update",
            "rfi_id": rfi_id,
            "rfi_number": rfi_number,
            "status": "RESPONDED",
            "responded_date": datetime.now(UTC).isoformat(),
            "response_document_id": document.get("id", ""),
        })

        # 2. Distribute response to all original recipients
        distribution_list = metadata.get("distribution_list", [])
        if distribution_list:
            await self.notify(
                recipients=distribution_list,
                subject=f"RFI Response Received — {rfi_number}",
                message=(
                    f"A response has been received for {rfi_number}.\n\n"
                    f"Subject: {metadata.get('subject', 'N/A')}\n"
                    f"Responded By: {user_id}\n"
                    f"Response Date: {datetime.now(UTC).strftime('%B %d, %Y')}"
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.NORMAL,
            )
            self._record_action("distribute_response", {"recipients_count": len(distribution_list)})

        # 3. Check for scope change
        scope_change_detected = metadata.get("scope_change_detected", False)
        scope_change_keywords = ["change", "additional", "extra", "modify", "revision", "scope"]
        response_text = metadata.get("response_text", "").lower()
        if not scope_change_detected and any(kw in response_text for kw in scope_change_keywords):
            scope_change_detected = True

        if scope_change_detected:
            pco_record = {
                "id": str(uuid.uuid4()),
                "type": "potential_change_order",
                "rfi_number": rfi_number,
                "project_id": project_id,
                "description": metadata.get("scope_change_description", "Scope change identified from RFI response"),
                "created_at": datetime.now(UTC).isoformat(),
            }
            self._records.append(pco_record)
            self._record_action("create_potential_change_order", {"rfi_number": rfi_number})

            pm = metadata.get("project_manager", user_id)
            await self.notify(
                recipients=[pm],
                subject=f"\u26a0\ufe0f Potential Change Order Identified — RFI {rfi_number}",
                message=(
                    f"The response to {rfi_number} indicates a potential scope change.\n\n"
                    f"Description: {pco_record['description']}\n"
                    f"A Change Order may be required. Please review the RFI response."
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH,
            )
            self._record_action("notify_pm_scope_change", {"pm": pm})

        # 4. Check if RFI references submittals
        if metadata.get("references_submittals", False):
            submittal_ref = metadata.get("submittal_reference", "")
            self._records.append({
                "type": "submittal_log_entry",
                "rfi_number": rfi_number,
                "submittal_reference": submittal_ref,
                "note": f"Referenced in RFI {rfi_number} response",
                "created_at": datetime.now(UTC).isoformat(),
            })
            self._record_action("create_submittal_log_entry", {"submittal_reference": submittal_ref})

        # 5. Close RFI workflow
        self._record_action("close_rfi", {"rfi_number": rfi_number})

        await self.create_log_entry(
            action="rfi_response_processed",
            details={"rfi_number": rfi_number, "scope_change": scope_change_detected},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=["RFI closed"]
            + (["Review Potential Change Order"] if scope_change_detected else []),
        )

    async def _schedule_rfi_reminders(
        self,
        rfi_number: str,
        rfi_id: str,
        reviewer: str,
        project_id: str,
        due_date: datetime,
        pm: str,
        pic: str,
    ) -> None:
        """Schedule the full RFI deadline reminder chain."""
        from src.worker import celery_app

        # T-2 days: reminder to reviewer
        t_minus_2 = due_date - timedelta(days=2)
        if t_minus_2 > datetime.now(UTC):
            celery_app.send_task(
                "nexus.vault.send_reminder",
                args=[
                    reviewer,
                    f"RFI {rfi_number} response due in 2 days",
                    rfi_id,
                    project_id,
                ],
                eta=t_minus_2,
            )

        # T-0 days: urgent reminder to reviewer AND PM
        if due_date > datetime.now(UTC):
            celery_app.send_task(
                "nexus.vault.send_reminder",
                args=[
                    reviewer,
                    f"RFI {rfi_number} response due TODAY",
                    rfi_id,
                    project_id,
                ],
                kwargs={"urgency": "critical", "cc": pm},
                eta=due_date,
            )

        # T+1 day: generate and send formal overdue letter
        t_plus_1 = due_date + timedelta(days=OVERDUE_LETTER_DAY)
        if t_plus_1 > datetime.now(UTC):
            celery_app.send_task(
                "nexus.vault.rfi_overdue_letter",
                args=[rfi_id, rfi_number, reviewer, project_id],
                eta=t_plus_1,
            )

        # T+7 days: escalate to principal-in-charge
        t_plus_7 = due_date + timedelta(days=ESCALATION_DAY)
        if t_plus_7 > datetime.now(UTC):
            celery_app.send_task(
                "nexus.vault.rfi_escalate",
                args=[rfi_id, rfi_number, project_id, pic],
                eta=t_plus_7,
            )

        self._record_action("schedule_reminders", {
            "rfi_number": rfi_number,
            "due_date": due_date.isoformat(),
            "reminders": ["T-2", "T-0", "T+1 overdue_letter", "T+7 escalation"],
        })
