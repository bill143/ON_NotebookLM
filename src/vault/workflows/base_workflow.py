"""
Base Workflow — Abstract foundation for all document workflow agents.

Every construction document workflow inherits from BaseWorkflow and implements
execute() with domain-specific logic. Shared plumbing — notifications, logging,
deadline scheduling — lives here.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

# ── Shared Models ───────────────────────────────────────────


class Urgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class NotificationChannel(str, Enum):
    EMAIL = "email"
    IN_APP = "in_app"
    BOTH = "both"


class ActionRecord(BaseModel):
    """Single action taken during workflow execution."""
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NotificationRecord(BaseModel):
    """Record of a notification sent."""
    recipient: str
    channel: NotificationChannel
    subject: str
    urgency: Urgency = Urgency.NORMAL
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LogEntry(BaseModel):
    """Audit log entry for a workflow action."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: str
    document_id: str
    project_id: str
    user_id: str
    action: str
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReminderSchedule(BaseModel):
    """A scheduled reminder for deadline tracking."""
    deadline: datetime
    recipient: str
    message: str
    reminder_offsets_days: list[int] = Field(default_factory=list)
    project_id: str
    document_id: str
    document_type: str


class WorkflowResult(BaseModel):
    """Result returned by every workflow execution."""
    success: bool
    actions_taken: list[ActionRecord] = Field(default_factory=list)
    notifications_sent: list[NotificationRecord] = Field(default_factory=list)
    records_created: list[dict[str, Any]] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    error_message: str | None = None


# ── LibrarianDecision (contract from Terminal 1) ────────────


class LibrarianDecision(BaseModel):
    """Output from the Librarian AI — determines document type and routing."""
    document_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 0.0
    routing_instructions: dict[str, Any] = Field(default_factory=dict)
    workflow_triggers: list[str] = Field(default_factory=list)
    requires_human_review: bool = False


# ── Abstract Base ───────────────────────────────────────────


class BaseWorkflow(ABC):
    """Abstract base class for all document workflow agents."""

    workflow_name: str = "base"

    def __init__(self) -> None:
        self._actions: list[ActionRecord] = []
        self._notifications: list[NotificationRecord] = []
        self._records: list[dict[str, Any]] = []

    @abstractmethod
    async def execute(
        self,
        document: dict[str, Any],
        decision: LibrarianDecision,
        project_id: str,
        user_id: str,
    ) -> WorkflowResult:
        """Execute the workflow for a given document and librarian decision."""
        ...

    def _record_action(self, action: str, details: dict[str, Any] | None = None) -> None:
        """Record an action taken during this workflow run."""
        record = ActionRecord(action=action, details=details or {})
        self._actions.append(record)
        logger.info(
            f"[{self.workflow_name}] {action}",
            **{k: str(v) for k, v in (details or {}).items()},
        )

    def _record_notification(
        self,
        recipient: str,
        channel: NotificationChannel,
        subject: str,
        urgency: Urgency = Urgency.NORMAL,
    ) -> None:
        """Record a notification sent."""
        self._notifications.append(
            NotificationRecord(
                recipient=recipient,
                channel=channel,
                subject=subject,
                urgency=urgency,
            )
        )

    async def notify(
        self,
        recipients: list[str],
        message: str,
        channel: NotificationChannel = NotificationChannel.BOTH,
        urgency: Urgency = Urgency.NORMAL,
        subject: str = "",
    ) -> None:
        """Send notifications to a list of recipients."""
        from src.vault.workflows.notification_service import notification_service

        for recipient in recipients:
            if channel in (NotificationChannel.EMAIL, NotificationChannel.BOTH):
                await notification_service.send_email(
                    to=recipient,
                    subject=subject or message[:80],
                    body=message,
                )
            if channel in (NotificationChannel.IN_APP, NotificationChannel.BOTH):
                await notification_service.send_in_app(
                    user_id=recipient,
                    title=subject or message[:80],
                    message=message,
                    urgency=urgency,
                )
            self._record_notification(recipient, channel, subject or message[:80], urgency)

    async def create_log_entry(
        self,
        action: str,
        details: dict[str, Any],
        document_id: str = "",
        project_id: str = "",
        user_id: str = "",
    ) -> LogEntry:
        """Create an audit log entry for this workflow action."""
        entry = LogEntry(
            workflow_type=self.workflow_name,
            document_id=document_id,
            project_id=project_id,
            user_id=user_id,
            action=action,
            details=details,
        )
        logger.info(
            f"[{self.workflow_name}] LOG: {action}",
            document_id=document_id,
            project_id=project_id,
        )
        return entry

    async def schedule_reminder(
        self,
        deadline: datetime,
        recipient: str,
        message: str,
        reminder_offsets_days: list[int],
        project_id: str = "",
        document_id: str = "",
    ) -> ReminderSchedule:
        """Schedule deadline reminders via Celery. Offsets are days before deadline."""
        from src.worker import celery_app

        reminder = ReminderSchedule(
            deadline=deadline,
            recipient=recipient,
            message=message,
            reminder_offsets_days=reminder_offsets_days,
            project_id=project_id,
            document_id=document_id,
            document_type=self.workflow_name,
        )

        for offset in reminder_offsets_days:
            fire_at = deadline - timedelta(days=offset)
            if fire_at > datetime.now(UTC):
                celery_app.send_task(
                    "nexus.vault.send_reminder",
                    args=[recipient, message, document_id, project_id],
                    eta=fire_at,
                )
                logger.debug(
                    f"Scheduled reminder T-{offset}d for {document_id}",
                    fire_at=fire_at.isoformat(),
                )

        return reminder

    def _build_result(
        self,
        success: bool = True,
        next_steps: list[str] | None = None,
        error_message: str | None = None,
    ) -> WorkflowResult:
        """Build the final WorkflowResult from accumulated state."""
        return WorkflowResult(
            success=success,
            actions_taken=self._actions,
            notifications_sent=self._notifications,
            records_created=self._records,
            next_steps=next_steps or [],
            error_message=error_message,
        )

    def _reset(self) -> None:
        """Reset accumulated state for a fresh run."""
        self._actions = []
        self._notifications = []
        self._records = []
