"""
Change Order Workflow — Change Order Processing Agent.

Handles construction change order lifecycle:
- CO record creation with sequential numbering
- Owner-directed vs contractor-initiated classification
- Budget impact calculation and tracking
- PM → Owner approval chain
- Contract value update on execution
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

CO_STATUSES = [
    "DRAFT",
    "PENDING_PM_REVIEW",
    "PENDING_OWNER_APPROVAL",
    "APPROVED",
    "EXECUTED",
    "REJECTED",
    "VOID",
]


class ChangeOrderWorkflow(BaseWorkflow):
    """Workflow agent for construction change order documents."""

    workflow_name = "change_order"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            is_execution = decision.metadata.get("is_execution", False)
            if is_execution:
                return await self._handle_execution(document, decision, project_id, user_id)
            return await self._handle_new_co(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"Change Order workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _handle_new_co(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        metadata = decision.metadata
        co_sequence = metadata.get("co_sequence", 1)
        co_number = f"CO-{co_sequence:03d}"

        # Classify origin
        is_owner_directed = metadata.get("is_owner_directed", False)
        origin = "Owner-Directed" if is_owner_directed else "Contractor-Initiated"

        amount = metadata.get("amount", 0.0)
        schedule_impact_days = metadata.get("schedule_impact_days", 0)
        original_contract_value = metadata.get("original_contract_value", 0.0)
        current_contract_value = metadata.get("current_contract_value", original_contract_value)

        # Budget impact
        new_contract_value = current_contract_value + amount
        budget_impact_pct = (amount / current_contract_value * 100) if current_contract_value else 0

        co_record = {
            "id": str(uuid.uuid4()),
            "co_number": co_number,
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "description": metadata.get("description", document.get("title", "Change Order")),
            "origin": origin,
            "amount": amount,
            "schedule_impact_days": schedule_impact_days,
            "original_contract_value": original_contract_value,
            "current_contract_value": current_contract_value,
            "new_contract_value": new_contract_value,
            "budget_impact_pct": round(budget_impact_pct, 2),
            "status": "PENDING_PM_REVIEW",
            "created_by": user_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self._records.append(co_record)
        self._record_action("create_change_order", {
            "co_number": co_number,
            "origin": origin,
            "amount": amount,
        })

        # Budget tracking update
        self._records.append({
            "type": "budget_update",
            "co_number": co_number,
            "project_id": project_id,
            "amount": amount,
            "new_contract_value": new_contract_value,
            "budget_impact_pct": round(budget_impact_pct, 2),
        })
        self._record_action("update_budget_tracking", {
            "new_contract_value": new_contract_value,
            "impact_pct": round(budget_impact_pct, 2),
        })

        # Route to PM for review
        pm = metadata.get("project_manager", user_id)
        await self.notify(
            recipients=[pm],
            subject=f"Change Order for Review — {co_number}",
            message=(
                f"A new Change Order requires your review.\n\n"
                f"CO Number: {co_number}\n"
                f"Origin: {origin}\n"
                f"Description: {co_record['description']}\n"
                f"Amount: ${amount:,.2f}\n"
                f"Schedule Impact: {schedule_impact_days} days\n"
                f"Current Contract Value: ${current_contract_value:,.2f}\n"
                f"Proposed New Value: ${new_contract_value:,.2f} ({budget_impact_pct:+.1f}%)"
            ),
            channel=NotificationChannel.BOTH,
            urgency=Urgency.HIGH,
        )
        self._record_action("route_to_pm", {"pm": pm})

        await self.create_log_entry(
            action="change_order_created",
            details={"co_number": co_number, "origin": origin, "amount": amount},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=[
                f"Pending PM review — {co_number}",
                "After PM approval, route to Owner for final approval",
            ],
        )

    async def _handle_execution(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        """Handle an executed (approved) change order — update contract value."""
        metadata = decision.metadata
        co_number = metadata.get("co_number", "CO-000")
        amount = metadata.get("amount", 0.0)
        current_contract_value = metadata.get("current_contract_value", 0.0)
        new_contract_value = current_contract_value + amount

        self._records.append({
            "type": "co_execution",
            "co_number": co_number,
            "status": "EXECUTED",
            "executed_date": datetime.now(UTC).isoformat(),
            "amount": amount,
            "new_contract_value": new_contract_value,
        })
        self._record_action("execute_change_order", {
            "co_number": co_number,
            "new_contract_value": new_contract_value,
        })

        # Update contract value record
        self._records.append({
            "type": "contract_value_update",
            "project_id": project_id,
            "previous_value": current_contract_value,
            "new_value": new_contract_value,
            "reason": f"Change Order {co_number} executed",
        })
        self._record_action("update_contract_value", {"new_value": new_contract_value})

        # Notify all parties
        parties = metadata.get("notification_list", [])
        if parties:
            await self.notify(
                recipients=parties,
                subject=f"Change Order Executed — {co_number}",
                message=(
                    f"Change Order {co_number} has been fully executed.\n\n"
                    f"Amount: ${amount:,.2f}\n"
                    f"New Contract Value: ${new_contract_value:,.2f}\n"
                    f"Executed Date: {datetime.now(UTC).strftime('%B %d, %Y')}"
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.NORMAL,
            )
            self._record_action("notify_all_parties", {"count": len(parties)})

        await self.create_log_entry(
            action="change_order_executed",
            details={"co_number": co_number, "new_contract_value": new_contract_value},
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        return self._build_result(
            success=True,
            next_steps=[f"Contract value updated to ${new_contract_value:,.2f}"],
        )
