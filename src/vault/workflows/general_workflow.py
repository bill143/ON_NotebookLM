"""
General Workflow — Catch-All Document Processing Agent.

Handles document types without specialized workflows:
PLANS_DRAWINGS, SPECIFICATIONS, PHOTO_PROGRESS, DAILY_REPORT,
MEETING_MINUTES, CLOSEOUT, TRANSMITTAL, UNKNOWN.

Provides filing, organization, basic notification, and human-review flagging.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.vault.workflows.base_workflow import (
    BaseWorkflow,
    LibrarianDecision,
    NotificationChannel,
    Urgency,
    WorkflowResult,
)

# Document type → notification target role
DOCUMENT_TYPE_NOTIFY: dict[str, str] = {
    "PLANS_DRAWINGS": "project_manager",
    "SPECIFICATIONS": "project_manager",
    "PHOTO_PROGRESS": "superintendent",
    "DAILY_REPORT": "project_manager",
    "MEETING_MINUTES": "project_manager",
    "CLOSEOUT": "project_manager",
    "TRANSMITTAL": "project_manager",
    "UNKNOWN": "project_manager",
}

# Document type → project folder path
DOCUMENT_TYPE_FOLDER: dict[str, str] = {
    "PLANS_DRAWINGS": "Drawings",
    "SPECIFICATIONS": "Specifications",
    "PHOTO_PROGRESS": "Photos/Progress",
    "DAILY_REPORT": "Reports/Daily",
    "MEETING_MINUTES": "Meeting Minutes",
    "CLOSEOUT": "Closeout",
    "TRANSMITTAL": "Transmittals",
    "UNKNOWN": "Unsorted",
}


class GeneralWorkflow(BaseWorkflow):
    """Workflow agent for general / catch-all document types."""

    workflow_name = "general"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            return await self._process_general(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"General workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _process_general(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        metadata = decision.metadata
        doc_type = decision.document_type.upper()
        next_steps: list[str] = []

        # 1. Determine folder and file document
        folder = DOCUMENT_TYPE_FOLDER.get(doc_type, "Unsorted")
        doc_record = {
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "document_type": doc_type,
            "title": metadata.get("title", document.get("title", "Untitled")),
            "folder_path": f"{project_id}/{folder}",
            "filed_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(doc_record)
        self._record_action("file_document", {
            "document_type": doc_type,
            "folder": folder,
        })

        # 2. Notify relevant party
        notify_role = DOCUMENT_TYPE_NOTIFY.get(doc_type, "project_manager")
        recipient = metadata.get(notify_role, metadata.get("project_manager", user_id))

        await self.notify(
            recipients=[recipient],
            subject=f"New {doc_type.replace('_', ' ').title()} Filed — {doc_record['title']}",
            message=(
                f"A new document has been filed in the project vault.\n\n"
                f"Type: {doc_type.replace('_', ' ').title()}\n"
                f"Title: {doc_record['title']}\n"
                f"Folder: {folder}\n"
                f"Filed By: {user_id}"
            ),
            channel=NotificationChannel.IN_APP,
            urgency=Urgency.LOW,
        )

        # 3. Handle UNKNOWN type — flag for human review
        if doc_type == "UNKNOWN":
            self._record_action("flag_for_human_review", {
                "reason": "Document type could not be determined",
            })
            pm = metadata.get("project_manager", user_id)
            await self.notify(
                recipients=[pm],
                subject=f"Unclassified Document Requires Review — {doc_record['title']}",
                message=(
                    f"A document was uploaded but could not be automatically classified.\n\n"
                    f"Title: {doc_record['title']}\n"
                    f"Confidence: {decision.confidence_score:.0%}\n\n"
                    f"Please review and classify this document manually."
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH,
            )
            next_steps.append("Awaiting human classification")

        # 4. Handle requires_human_review flag from Librarian
        if decision.requires_human_review and doc_type != "UNKNOWN":
            self._record_action("flag_for_human_review", {
                "reason": "Librarian flagged for review",
                "confidence": decision.confidence_score,
            })
            next_steps.append("Document flagged for human review by Librarian AI")

        await self.create_log_entry(
            action="document_filed",
            details={"document_type": doc_type, "folder": folder},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        if not next_steps:
            next_steps.append(f"Document filed in {folder}")

        return self._build_result(success=True, next_steps=next_steps)
