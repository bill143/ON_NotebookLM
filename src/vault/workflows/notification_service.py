"""
Centralized Notification Service — Email, In-App, and Formal Letter Generation.

All outbound communication from vault workflows flows through this service.
External calls (SMTP, push) are isolated here for easy mocking in tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


# ── Letter Templates ────────────────────────────────────────


class LetterTemplate(str, Enum):
    OVERDUE_RFI = "overdue_rfi"
    INSURANCE_EXPIRED = "insurance_expired"
    SCOPE_CHANGE_NOTICE = "scope_change_notice"


_LETTER_TEMPLATES: dict[LetterTemplate, str] = {
    LetterTemplate.OVERDUE_RFI: """
O'NEILL CONTRACTORS, INC.
FORMAL NOTICE — OVERDUE REQUEST FOR INFORMATION

Date: {date}
Project: {project_name}
RFI Number: {rfi_number}
Subject: {subject}

Dear {reviewer_name},

This letter serves as formal notice that the above-referenced Request for Information
(RFI) submitted on {submitted_date} with a response deadline of {due_date} remains
unanswered as of the date of this letter.

The response is now {days_overdue} day(s) overdue. Failure to respond in a timely
manner may result in project delays and associated costs.

Please provide your response immediately. If you require additional time or
clarification, contact the undersigned at your earliest convenience.

Respectfully,
{sender_name}
Project Manager
O'Neill Contractors, Inc.
""",
    LetterTemplate.INSURANCE_EXPIRED: """
O'NEILL CONTRACTORS, INC.
NOTICE OF EXPIRED INSURANCE COVERAGE

Date: {date}
Project: {project_name}
Subcontractor: {subcontractor_name}
Policy Number: {policy_number}

Dear {subcontractor_name},

This notice is to inform you that the Certificate of Insurance (COI) on file for
the above-referenced project has expired as of {expiration_date}.

Per the terms of your subcontract agreement, you are required to maintain active
insurance coverage for the duration of the project. Work under your subcontract
is hereby SUSPENDED until a valid, updated COI is provided.

Please submit an updated Certificate of Insurance immediately to avoid further
project impact.

Respectfully,
{sender_name}
Contracts Administrator
O'Neill Contractors, Inc.
""",
    LetterTemplate.SCOPE_CHANGE_NOTICE: """
O'NEILL CONTRACTORS, INC.
POTENTIAL CHANGE ORDER NOTICE

Date: {date}
Project: {project_name}
RFI Reference: {rfi_number}
Subject: {subject}

Dear {recipient_name},

During the review of the above-referenced RFI, a potential scope change has been
identified that may result in a change to the contract value and/or schedule.

Description of Potential Change:
{change_description}

Estimated Impact: {estimated_impact}

A formal Change Order proposal will follow pending further evaluation. Please
review the attached RFI response for details.

Respectfully,
{sender_name}
Project Manager
O'Neill Contractors, Inc.
""",
}


# ── Models ──────────────────────────────────────────────────


class EmailMessage(BaseModel):
    to: str
    subject: str
    body: str
    attachments: list[str] = Field(default_factory=list)
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class InAppMessage(BaseModel):
    user_id: str
    title: str
    message: str
    urgency: str = "normal"
    action_url: str | None = None
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Service ─────────────────────────────────────────────────


class NotificationService:
    """Centralized notification dispatch for all vault workflows."""

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        attachments: list[str] | None = None,
    ) -> EmailMessage:
        """Send an email notification. In production, delegates to SMTP/SES."""
        msg = EmailMessage(
            to=to,
            subject=subject,
            body=body,
            attachments=attachments or [],
        )
        # Production: delegate to email provider (SES, SendGrid, etc.)
        # For now, log and return the message record
        logger.info(f"EMAIL → {to}: {subject}")
        return msg

    async def send_in_app(
        self,
        user_id: str,
        title: str,
        message: str,
        urgency: Any = "normal",
        action_url: str | None = None,
    ) -> InAppMessage:
        """Send an in-app notification via WebSocket broker."""
        urgency_str = urgency.value if hasattr(urgency, "value") else str(urgency)
        msg = InAppMessage(
            user_id=user_id,
            title=title,
            message=message,
            urgency=urgency_str,
            action_url=action_url,
        )
        logger.info(f"IN-APP → {user_id}: {title} [{urgency_str}]")
        return msg

    def generate_formal_letter(
        self,
        template: LetterTemplate,
        data: dict[str, Any],
    ) -> str:
        """Generate a formal letter from a template. Returns rendered text."""
        tmpl = _LETTER_TEMPLATES.get(template)
        if not tmpl:
            raise ValueError(f"Unknown letter template: {template}")
        # Fill in defaults for missing keys to avoid KeyError
        defaults = {
            "date": datetime.now(UTC).strftime("%B %d, %Y"),
        }
        merged = {**defaults, **data}
        try:
            return tmpl.format(**merged)
        except KeyError as e:
            logger.error(f"Letter template missing key: {e}", template=template.value)
            raise


# Singleton
notification_service = NotificationService()
