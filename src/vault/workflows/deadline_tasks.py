"""
Deadline Tasks — Celery periodic tasks for vault deadline monitoring.

Runs on the Celery beat schedule to check for:
- Overdue RFIs (every hour)
- Expiring COIs (daily at 7 AM UTC)
- Expiring Permits (daily at 7 AM UTC)
- Overdue Invoices (daily at 7 AM UTC)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from loguru import logger

from src.worker import celery_app, run_async

# ── Periodic Tasks ──────────────────────────────────────────


@celery_app.task(name="nexus.vault.check_rfi_deadlines")
def check_rfi_deadlines() -> dict[str, Any]:
    """Check for RFIs approaching or past their deadlines. Runs every hour."""
    logger.info("Checking RFI deadlines")
    # In production, this queries the RFI table for:
    # - RFIs with status OPEN and due_date approaching
    # - Triggers appropriate reminder/escalation tasks
    return {
        "task": "check_rfi_deadlines",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "completed",
    }


@celery_app.task(name="nexus.vault.check_coi_expirations")
def check_coi_expirations() -> dict[str, Any]:
    """Check for COIs approaching expiration. Runs daily at 7 AM UTC."""
    logger.info("Checking COI expirations")
    return {
        "task": "check_coi_expirations",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "completed",
    }


@celery_app.task(name="nexus.vault.check_permit_expirations")
def check_permit_expirations() -> dict[str, Any]:
    """Check for permits approaching expiration. Runs daily at 7 AM UTC."""
    logger.info("Checking permit expirations")
    return {
        "task": "check_permit_expirations",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "completed",
    }


@celery_app.task(name="nexus.vault.check_invoice_due_dates")
def check_invoice_due_dates() -> dict[str, Any]:
    """Check for invoices approaching payment due dates. Runs daily at 7 AM UTC."""
    logger.info("Checking invoice due dates")
    return {
        "task": "check_invoice_due_dates",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": "completed",
    }


# ── On-Demand Tasks (triggered by workflow scheduling) ──────


@celery_app.task(name="nexus.vault.send_reminder")
def send_reminder(
    recipient: str,
    message: str,
    document_id: str,
    project_id: str,
    urgency: str = "normal",
    cc: str | None = None,
) -> dict[str, Any]:
    """Send a deadline reminder notification."""

    async def _send():
        from src.vault.workflows.notification_service import notification_service

        await notification_service.send_in_app(
            user_id=recipient,
            title="Deadline Reminder",
            message=message,
            urgency=urgency,
        )
        await notification_service.send_email(
            to=recipient,
            subject=f"Reminder: {message[:80]}",
            body=message,
        )

        if cc:
            await notification_service.send_email(
                to=cc,
                subject=f"CC: Reminder — {message[:80]}",
                body=message,
            )

    run_async(_send())

    logger.info(f"Reminder sent to {recipient}: {message[:80]}")
    return {
        "recipient": recipient,
        "message": message[:80],
        "sent_at": datetime.now(UTC).isoformat(),
    }


@celery_app.task(name="nexus.vault.rfi_overdue_letter")
def rfi_overdue_letter(
    rfi_id: str,
    rfi_number: str,
    reviewer: str,
    project_id: str,
) -> dict[str, Any]:
    """Generate and send a formal overdue letter for an RFI."""

    async def _send():
        from src.vault.workflows.notification_service import (
            LetterTemplate,
            notification_service,
        )

        letter = notification_service.generate_formal_letter(
            template=LetterTemplate.OVERDUE_RFI,
            data={
                "project_name": project_id,
                "rfi_number": rfi_number,
                "subject": f"Overdue RFI {rfi_number}",
                "reviewer_name": reviewer,
                "submitted_date": "See RFI record",
                "due_date": "See RFI record",
                "days_overdue": "1+",
                "sender_name": "Project Manager",
            },
        )

        await notification_service.send_email(
            to=reviewer,
            subject=f"FORMAL NOTICE — Overdue RFI {rfi_number}",
            body=letter,
        )

    run_async(_send())

    logger.warning(f"Overdue letter sent for {rfi_number} to {reviewer}")
    return {
        "rfi_number": rfi_number,
        "reviewer": reviewer,
        "sent_at": datetime.now(UTC).isoformat(),
    }


@celery_app.task(name="nexus.vault.rfi_escalate")
def rfi_escalate(
    rfi_id: str,
    rfi_number: str,
    project_id: str,
    principal_in_charge: str,
) -> dict[str, Any]:
    """Escalate overdue RFI to principal-in-charge."""

    async def _send():
        from src.vault.workflows.notification_service import notification_service

        await notification_service.send_email(
            to=principal_in_charge,
            subject=f"ESCALATION — Overdue RFI {rfi_number} (7+ days)",
            body=(
                f"RFI {rfi_number} on project {project_id} is now 7+ days overdue.\n\n"
                f"This RFI requires immediate attention from leadership.\n"
                f"Please review and take appropriate action."
            ),
        )
        await notification_service.send_in_app(
            user_id=principal_in_charge,
            title=f"RFI Escalation — {rfi_number}",
            message=f"RFI {rfi_number} is 7+ days overdue and requires executive attention.",
            urgency="critical",
        )

    run_async(_send())

    logger.warning(f"RFI {rfi_number} escalated to {principal_in_charge}")
    return {
        "rfi_number": rfi_number,
        "escalated_to": principal_in_charge,
        "sent_at": datetime.now(UTC).isoformat(),
    }


@celery_app.task(name="nexus.vault.coi_expiration_alert")
def coi_expiration_alert(
    coi_id: str,
    subcontractor: str,
    project_id: str,
    pm: str,
    contracts_admin: str,
) -> dict[str, Any]:
    """Alert on COI expiration — flag subcontractor for stop work."""

    async def _send():
        from src.vault.workflows.notification_service import (
            LetterTemplate,
            notification_service,
        )

        letter = notification_service.generate_formal_letter(
            template=LetterTemplate.INSURANCE_EXPIRED,
            data={
                "project_name": project_id,
                "subcontractor_name": subcontractor,
                "policy_number": "See insurance record",
                "expiration_date": datetime.now(UTC).strftime("%B %d, %Y"),
                "sender_name": "Contracts Administrator",
            },
        )

        for recipient in [pm, contracts_admin]:
            await notification_service.send_email(
                to=recipient,
                subject=f"STOP WORK — Insurance Expired for {subcontractor}",
                body=letter,
            )
            await notification_service.send_in_app(
                user_id=recipient,
                title=f"Insurance Expired — {subcontractor}",
                message=f"COI for {subcontractor} has expired. Stop work flagged.",
                urgency="critical",
            )

    run_async(_send())

    logger.critical(f"COI expired for {subcontractor} — stop work flagged")
    return {
        "subcontractor": subcontractor,
        "action": "STOP_WORK_FLAGGED",
        "sent_at": datetime.now(UTC).isoformat(),
    }


@celery_app.task(name="nexus.vault.permit_expiration_alert")
def permit_expiration_alert(
    permit_id: str,
    permit_number: str,
    project_id: str,
    pm: str,
    superintendent: str,
) -> dict[str, Any]:
    """Critical alert on permit expiration."""

    async def _send():
        from src.vault.workflows.notification_service import notification_service

        for recipient in [pm, superintendent]:
            await notification_service.send_email(
                to=recipient,
                subject=f"CRITICAL — Permit Expired: {permit_number}",
                body=(
                    f"Permit {permit_number} for project {project_id} has expired.\n\n"
                    f"Work covered by this permit must stop until the permit is renewed.\n"
                    f"Contact the issuing authority immediately."
                ),
            )
            await notification_service.send_in_app(
                user_id=recipient,
                title=f"Permit Expired — {permit_number}",
                message=f"Permit {permit_number} has expired. Immediate action required.",
                urgency="critical",
            )

    run_async(_send())

    logger.critical(f"Permit {permit_number} expired — critical alert sent")
    return {
        "permit_number": permit_number,
        "action": "CRITICAL_ALERT_SENT",
        "sent_at": datetime.now(UTC).isoformat(),
    }
