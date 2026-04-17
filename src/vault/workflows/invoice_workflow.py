"""
Invoice Workflow — Invoice Processing Agent.

Handles construction invoice lifecycle:
- Invoice record creation with validation
- Contract value / remaining balance checks
- Duplicate invoice detection
- Accounting routing and NET 30 payment tracking
- G702/G703 pay application format detection
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

DEFAULT_PAYMENT_TERMS_DAYS = 30
PAYMENT_REMINDER_OFFSET_DAYS = 5

INVOICE_STATUSES = [
    "RECEIVED",
    "UNDER_REVIEW",
    "APPROVED",
    "PAID",
    "DISPUTED",
]


class InvoiceWorkflow(BaseWorkflow):
    """Workflow agent for construction invoice documents."""

    workflow_name = "invoice"

    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        self._reset()

        try:
            return await self._process_invoice(document, decision, project_id, user_id)
        except Exception as e:
            logger.error(f"Invoice workflow failed: {e}", document_id=document.get("id"))
            self._record_action("workflow_error", {"error": str(e)})
            return self._build_result(
                success=False,
                error_message=str(e),
                next_steps=["Flag document for human review"],
            )

    async def _process_invoice(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        metadata = decision.metadata
        invoice_number = metadata.get("invoice_number", f"INV-{uuid.uuid4().hex[:8].upper()}")
        vendor = metadata.get("vendor", "Unknown Vendor")
        amount = metadata.get("amount", 0.0)
        contract_value = metadata.get("contract_value", 0.0)
        amount_previously_billed = metadata.get("amount_previously_billed", 0.0)

        flags: list[str] = []
        next_steps: list[str] = []

        # 1. Create invoice record
        payment_due_date = datetime.now(UTC) + timedelta(days=DEFAULT_PAYMENT_TERMS_DAYS)
        invoice_record = {
            "id": str(uuid.uuid4()),
            "invoice_number": invoice_number,
            "project_id": project_id,
            "document_id": document.get("id", ""),
            "vendor": vendor,
            "amount": amount,
            "status": "RECEIVED",
            "received_date": datetime.now(UTC).isoformat(),
            "payment_due_date": payment_due_date.isoformat(),
            "created_by": user_id,
        }
        self._records.append(invoice_record)
        self._record_action("create_invoice_record", {
            "invoice_number": invoice_number,
            "vendor": vendor,
            "amount": amount,
        })

        # 2. Validate against contract value
        if contract_value > 0:
            remaining_balance = contract_value - amount_previously_billed
            if amount > remaining_balance:
                flags.append("EXCEEDS_CONTRACT_BALANCE")
                self._record_action("flag_exceeds_contract", {
                    "invoice_amount": amount,
                    "remaining_balance": remaining_balance,
                    "contract_value": contract_value,
                })
                pm = metadata.get("project_manager", user_id)
                await self.notify(
                    recipients=[pm],
                    subject=f"Invoice Exceeds Contract Balance — {invoice_number}",
                    message=(
                        f"Invoice {invoice_number} from {vendor} for ${amount:,.2f} exceeds "
                        f"the remaining contract balance of ${remaining_balance:,.2f}.\n\n"
                        f"Contract Value: ${contract_value:,.2f}\n"
                        f"Previously Billed: ${amount_previously_billed:,.2f}\n"
                        f"This Invoice: ${amount:,.2f}\n\n"
                        f"Please review before approving."
                    ),
                    channel=NotificationChannel.BOTH,
                    urgency=Urgency.HIGH,
                )
                next_steps.append("PM review required — invoice exceeds remaining balance")

        # 3. Duplicate invoice detection
        existing_invoices = metadata.get("existing_invoice_numbers", [])
        if invoice_number in existing_invoices:
            flags.append("DUPLICATE_INVOICE")
            self._record_action("flag_duplicate_invoice", {"invoice_number": invoice_number})
            await self.notify(
                recipients=[metadata.get("accounting_contact", user_id)],
                subject=f"Duplicate Invoice Detected — {invoice_number}",
                message=(
                    f"Invoice {invoice_number} from {vendor} appears to be a duplicate.\n"
                    f"Please verify before processing."
                ),
                channel=NotificationChannel.BOTH,
                urgency=Urgency.HIGH,
            )
            next_steps.append("Verify duplicate invoice")

        # 4. Route to accounting
        accounting = metadata.get("accounting_contact", "accounting")
        await self.notify(
            recipients=[accounting],
            subject=f"New Invoice for Review — {invoice_number}",
            message=(
                f"A new invoice has been received and requires review.\n\n"
                f"Invoice: {invoice_number}\n"
                f"Vendor: {vendor}\n"
                f"Amount: ${amount:,.2f}\n"
                f"Payment Due: {payment_due_date.strftime('%B %d, %Y')}\n"
                f"{'Flags: ' + ', '.join(flags) if flags else 'No flags.'}"
            ),
            channel=NotificationChannel.BOTH,
            urgency=Urgency.NORMAL,
        )
        self._record_action("route_to_accounting", {"accounting": accounting})

        # 5. Schedule NET 30 payment reminder
        reminder_date = payment_due_date - timedelta(days=PAYMENT_REMINDER_OFFSET_DAYS)
        if reminder_date > datetime.now(UTC):
            await self.schedule_reminder(
                deadline=payment_due_date,
                recipient=accounting,
                message=f"Invoice {invoice_number} payment due in {PAYMENT_REMINDER_OFFSET_DAYS} days",
                reminder_offsets_days=[PAYMENT_REMINDER_OFFSET_DAYS],
                project_id=project_id,
                document_id=invoice_record["id"],
            )
            self._record_action("schedule_payment_reminder", {
                "due_date": payment_due_date.isoformat(),
            })

        # 6. G702/G703 detection
        is_pay_app = metadata.get("is_pay_application", False)
        pay_app_keywords = ["g702", "g703", "application for payment", "schedule of values"]
        doc_title = document.get("title", "").lower()
        if is_pay_app or any(kw in doc_title for kw in pay_app_keywords):
            self._records.append({
                "type": "g702_g703_log_entry",
                "invoice_number": invoice_number,
                "project_id": project_id,
                "vendor": vendor,
                "amount": amount,
                "period": metadata.get("billing_period", ""),
                "date": datetime.now(UTC).isoformat(),
            })
            self._record_action("create_pay_app_log_entry", {"invoice_number": invoice_number})
            next_steps.append("G702/G703 pay application logged")

        invoice_record["flags"] = flags

        await self.create_log_entry(
            action="invoice_received",
            details={
                "invoice_number": invoice_number,
                "vendor": vendor,
                "amount": amount,
                "flags": flags,
            },
            document_id=document.get("id", ""),
            project_id=project_id,
            user_id=user_id,
        )

        if not next_steps:
            next_steps.append(f"Awaiting accounting review, payment due {payment_due_date.strftime('%Y-%m-%d')}")

        return self._build_result(success=True, next_steps=next_steps)
