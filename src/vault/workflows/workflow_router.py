"""
Workflow Router — Maps document types to workflow agents and dispatches execution.

Single entry point for the vault pipeline. Receives a document + LibrarianDecision,
selects the correct workflow, executes it, and handles errors gracefully.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.vault.workflows.base_workflow import (
    BaseWorkflow,
    LibrarianDecision,
    WorkflowResult,
)
from src.vault.workflows.change_order_workflow import ChangeOrderWorkflow
from src.vault.workflows.coi_workflow import COIWorkflow
from src.vault.workflows.general_workflow import GeneralWorkflow
from src.vault.workflows.invoice_workflow import InvoiceWorkflow
from src.vault.workflows.permit_workflow import PermitWorkflow
from src.vault.workflows.rfi_workflow import RFIWorkflow
from src.vault.workflows.schedule_workflow import ScheduleWorkflow
from src.vault.workflows.submittal_workflow import SubmittalWorkflow

# ── Document Type → Workflow Mapping ────────────────────────

DOCUMENT_TYPE_TO_WORKFLOW: dict[str, type[BaseWorkflow]] = {
    "RFI": RFIWorkflow,
    "SUBMITTAL": SubmittalWorkflow,
    "INVOICE": InvoiceWorkflow,
    "CHANGE_ORDER": ChangeOrderWorkflow,
    "COI": COIWorkflow,
    "CERTIFICATE_OF_INSURANCE": COIWorkflow,
    "PERMIT": PermitWorkflow,
    "SCHEDULE": ScheduleWorkflow,
    # General / catch-all types
    "PLANS_DRAWINGS": GeneralWorkflow,
    "SPECIFICATIONS": GeneralWorkflow,
    "PHOTO_PROGRESS": GeneralWorkflow,
    "DAILY_REPORT": GeneralWorkflow,
    "MEETING_MINUTES": GeneralWorkflow,
    "CLOSEOUT": GeneralWorkflow,
    "TRANSMITTAL": GeneralWorkflow,
    "UNKNOWN": GeneralWorkflow,
}

# Singleton workflow instances (stateless between calls — reset on each execute)
_workflow_instances: dict[str, BaseWorkflow] = {}


def _get_workflow(document_type: str) -> BaseWorkflow:
    """Get or create a workflow instance for the given document type."""
    doc_type_upper = document_type.upper()
    workflow_cls = DOCUMENT_TYPE_TO_WORKFLOW.get(doc_type_upper, GeneralWorkflow)

    # Cache by class name so all general types share one instance
    cls_name = workflow_cls.__name__
    if cls_name not in _workflow_instances:
        _workflow_instances[cls_name] = workflow_cls()
    return _workflow_instances[cls_name]


async def execute_workflow(
    document: dict[str, Any],
    decision: LibrarianDecision,
    project_id: str,
    user_id: str,
) -> WorkflowResult:
    """
    Execute the appropriate workflow for a document based on its LibrarianDecision.

    This is the primary entry point for the vault workflow engine. It:
    1. Resolves the correct workflow class from the document type
    2. Executes the workflow
    3. Handles any unrecoverable errors gracefully

    Never crashes — on failure, returns a WorkflowResult with success=False
    and flags the document for human review.
    """
    doc_type = decision.document_type
    doc_id = document.get("id", "unknown")

    try:
        workflow = _get_workflow(doc_type)
        logger.info(
            f"Dispatching {doc_type} → {workflow.workflow_name} workflow",
            document_id=doc_id,
            project_id=project_id,
        )

        result = await workflow.execute(document, decision, project_id, user_id)

        if result.success:
            logger.info(
                f"Workflow completed: {workflow.workflow_name}",
                document_id=doc_id,
                actions={len(result.actions_taken)},
            )
        else:
            logger.warning(
                f"Workflow completed with errors: {workflow.workflow_name}",
                document_id=doc_id,
                error=result.error_message,
            )

        return result

    except Exception as e:
        logger.error(
            f"Workflow router error for {doc_type}",
            document_id=doc_id,
            error=str(e),
            exc_info=True,
        )
        return WorkflowResult(
            success=False,
            error_message=f"Workflow execution failed: {str(e)}",
            next_steps=[
                "Document flagged for human review due to workflow failure",
                f"Error: {str(e)[:200]}",
            ],
        )
