"""
Submittal Workflow — Submittal Processing Agent.

Handles shop drawing / product data submittal lifecycle:
- Submittal log creation with spec-section numbering
- Design team reviewer assignment by spec section
- 21-day review period tracking
- Approval / Rejection / Revise & Resubmit routing
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

# ── Spec Section → Design Reviewer Mapping ──────────────────

SPEC_SECTION_REVIEWERS: dict[str, str] = {
    "03": "structural_engineer",  # Concrete
    "04": "structural_engineer",  # Masonry
    "05": "structural_engineer",  # Metals
    "06": "architect",            # Wood/Plastics
    "07": "architect",            # Thermal/Moisture
    "08": "architect",            # Openings
    "09": "architect",            # Finishes
    "15": "mep_engineer",         # Mechanical (legacy)
    "16": "mep_engineer",         # Electrical (legacy)
    "21": "mep_engineer",         # Fire Suppression
    "22": "mep_engineer",         # Plumbing
    "23": "mep_engineer",         # HVAC
    "26": "mep_engineer",         # Electrical
    "27": "mep_engineer",         # Communications
    "28": "mep_engineer",         # Safety/Security
    "31": "civil_engineer",       # Earthwork
    "32": "civil_engineer",       # Exterior Improvements
    "33": "civil_engineer",       # Utilities
}

DEFAULT_SUBMITTAL_REVIEW_DAYS = 21

SUBMITTAL_STATUSES = [
    "SUBMITTED",
    "UNDER_REVIEW",
    "APPROVED",
    "APPROVED_AS_NOTED",
    "REJECTED",
    "REVISE_AND_RESUBMIT",
]


class SubmittalWorkflow(BaseWorkflow):
    """Workflow agent for construction submittal documents."""

    workflow_name = "submittal"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            is_review_action = decision.metadata.get("is_review_action", False)
            if is_review_action:
                return await self._handle_review_action(document, decision, project_id, user_id)
            return await self._handle_new_submittal(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"Submittal workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _handle_new_submittal(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        """Process a newly uploaded submittal."""
        metadata = decision.metadata
        spec_section = metadata.get("spec_section", "00")
        revision = metadata.get("revision", 0)
        submittal_number = f"SUB-{spec_section}-{revision:02d}"

        # Assign reviewer based on spec section prefix (first 2 digits)
        section_prefix = spec_section[:2] if len(spec_section) >= 2 else spec_section
        reviewer = SPEC_SECTION_REVIEWERS.get(section_prefix, "architect")

        due_date = datetime.now(UTC) + timedelta(days=DEFAULT_SUBMITTAL_REVIEW_DAYS)

        submittal_record = {
            "id": str(uuid.uuid4()),
            "submittal_number": submittal_number,
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "spec_section": spec_section,
            "revision": revision,
            "title": metadata.get("title", document.get("title", "Untitled Submittal")),
            "status": "SUBMITTED",
            "reviewer": reviewer,
            "submitter": user_id,
            "submitted_date": datetime.now(UTC).isoformat(),
            "due_date": due_date.isoformat(),
        }
        self._records.append(submittal_record)
        self._record_action("create_submittal", {
            "submittal_number": submittal_number,
            "spec_section": spec_section,
            "reviewer": reviewer,
        })

        # Add to submittal log
        self._records.append({
            "type": "submittal_log_entry",
            "submittal_number": submittal_number,
            "spec_section": spec_section,
            "revision": revision,
            "status": "SUBMITTED",
            "date": datetime.now(UTC).isoformat(),
        })
        self._record_action("add_to_submittal_log", {"submittal_number": submittal_number})

        # Notify reviewer
        await self.notify(
            recipients=[reviewer],
            subject=f"Submittal Assigned — {submittal_number}",
            message=(
                f"A new submittal has been assigned for your review.\n\n"
                f"Submittal: {submittal_number}\n"
                f"Spec Section: {spec_section}\n"
                f"Title: {submittal_record['title']}\n"
                f"Review Due: {due_date.strftime('%B %d, %Y')}"
            ),
            channel=NotificationChannel.BOTH,
            urgency=Urgency.NORMAL,
        )
        self._record_action("notify_reviewer", {"reviewer": reviewer})

        # Schedule deadline reminders (same chain as RFI)
        await self.schedule_reminder(
            deadline=due_date,
            recipient=reviewer,
            message=f"Submittal {submittal_number} review due",
            reminder_offsets_days=[2, 0],
            project_id=project_id,
            document_id=submittal_record["id"],
        )
        self._record_action("schedule_reminders", {"submittal_number": submittal_number})

        await self.create_log_entry(
            action="submittal_created",
            details={"submittal_number": submittal_number, "spec_section": spec_section},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=[
                f"Awaiting review from {reviewer} by {due_date.strftime('%Y-%m-%d')}",
            ],
        )

    async def _handle_review_action(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        """Process a review action (approve/reject/revise) on a submittal."""
        metadata = decision.metadata
        submittal_number = metadata.get("submittal_number", "UNKNOWN")
        action = metadata.get("review_action", "APPROVED").upper()
        submitter = metadata.get("submitter", "")
        comments = metadata.get("review_comments", "")

        self._record_action("update_submittal_status", {
            "submittal_number": submittal_number,
            "status": action,
        })

        self._records.append({
            "type": "submittal_status_update",
            "submittal_number": submittal_number,
            "status": action,
            "reviewed_by": user_id,
            "review_date": datetime.now(UTC).isoformat(),
            "comments": comments,
        })

        if action in ("APPROVED", "APPROVED_AS_NOTED"):
            await self.notify(
                recipients=[submitter] if submitter else [],
                subject=f"Submittal {action.replace('_', ' ').title()} — {submittal_number}",
                message=(
                    f"Submittal {submittal_number} has been {action.replace('_', ' ').lower()}.\n\n"
                    f"Comments: {comments or 'None'}"
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.NORMAL,
            )

        elif action in ("REJECTED", "REVISE_AND_RESUBMIT"):
            new_rev = metadata.get("revision", 0) + 1
            await self.notify(
                recipients=[submitter] if submitter else [],
                subject=f"Submittal {action.replace('_', ' ').title()} — {submittal_number}",
                message=(
                    f"Submittal {submittal_number} has been {action.replace('_', ' ').lower()}.\n\n"
                    f"Comments: {comments}\n"
                    f"Please resubmit as revision {new_rev:02d}."
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH,
            )
            self._records.append({
                "type": "revision_increment",
                "submittal_number": submittal_number,
                "new_revision": new_rev,
            })

        # Update submittal log
        self._records.append({
            "type": "submittal_log_entry",
            "submittal_number": submittal_number,
            "status": action,
            "reviewed_by": user_id,
            "date": datetime.now(UTC).isoformat(),
        })

        await self.create_log_entry(
            action="submittal_reviewed",
            details={"submittal_number": submittal_number, "result": action},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=[f"Submittal {submittal_number} — {action}"],
        )
