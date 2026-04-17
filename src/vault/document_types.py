"""
Nexus Vault — Document Type Definitions & Pydantic Models
Codename: ESPERANTO

Enums and models for the Intelligent Document Vault:
- DocumentType enum (21 construction document categories)
- LibrarianDecision — AI classification result
- VaultUploadRequest / VaultDocument — upload lifecycle
- WorkflowTrigger / RoutingInstruction — downstream routing
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Document Type Enum ──────────────────────────────────────


class DocumentType(str, Enum):
    """Construction document classification categories."""

    RFI = "rfi"
    SUBMITTAL = "submittal"
    SCHEDULE = "schedule"
    PLANS_DRAWINGS = "plans_drawings"
    SPECIFICATIONS = "specifications"
    INVOICE = "invoice"
    CHANGE_ORDER = "change_order"
    PERMIT = "permit"
    COI = "coi"
    DAILY_REPORT = "daily_report"
    SAFETY_DOCUMENT = "safety_document"
    PAY_APPLICATION = "pay_application"
    LIEN_WAIVER = "lien_waiver"
    MEETING_MINUTES = "meeting_minutes"
    BIM_MODEL = "bim_model"
    PHOTO_PROGRESS = "photo_progress"
    GEOTECHNICAL = "geotechnical"
    SURVEY = "survey"
    CLOSEOUT = "closeout"
    TRANSMITTAL = "transmittal"
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    """Processing status for vault documents."""

    PENDING = "pending"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    AWAITING_REVIEW = "awaiting_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ERROR = "error"


# ── Workflow & Routing Models ───────────────────────────────


class WorkflowTrigger(BaseModel):
    """A downstream workflow action triggered by document classification."""

    trigger_type: str = Field(
        ...,
        description="Workflow type: review_cycle, deadline_tracking, cost_impact, notification",
    )
    target_roles: list[str] = Field(
        default_factory=list,
        description="Roles that should be notified or assigned",
    )
    urgency: str = Field(default="normal", description="low | normal | high | critical")
    parameters: dict[str, Any] = Field(default_factory=dict)


class RoutingInstruction(BaseModel):
    """Where and how to route a classified document."""

    destination: str = Field(
        ...,
        description="Target module or queue: rfi_tracker, submittal_log, cost_control, etc.",
    )
    action: str = Field(
        default="create",
        description="Action to take: create, update, link, notify",
    )
    priority: int = Field(default=0, description="Routing priority (0 = normal)")
    parameters: dict[str, Any] = Field(default_factory=dict)


# ── Librarian Decision ──────────────────────────────────────


class LibrarianDecision(BaseModel):
    """
    Output from the Librarian AI — determines document type and routing.

    This is the primary output of the classification engine. Every uploaded
    document receives a LibrarianDecision that drives downstream workflows.
    """

    document_type: DocumentType = DocumentType.UNKNOWN
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted metadata specific to the document type",
    )
    confidence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="AI confidence in the classification (0.0–1.0)",
    )
    routing_instructions: list[RoutingInstruction] = Field(default_factory=list)
    workflow_triggers: list[WorkflowTrigger] = Field(default_factory=list)
    requires_human_review: bool = Field(
        default=False,
        description="True when confidence < 0.75 or ambiguous classification",
    )


# ── Upload & Document Models ────────────────────────────────


class VaultUploadRequest(BaseModel):
    """Request model for document upload to the vault."""

    project_id: str = Field(..., description="Project UUID the document belongs to")
    title: str | None = Field(default=None, description="Optional user-supplied title")
    description: str | None = Field(default=None, description="Optional description")
    tags: list[str] = Field(default_factory=list)


class VaultDocument(BaseModel):
    """Full vault document record with classification results."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    tenant_id: str
    user_id: str
    filename: str
    file_size_bytes: int = 0
    mime_type: str | None = None
    status: DocumentStatus = DocumentStatus.PENDING
    decision: LibrarianDecision | None = None
    title: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    file_path: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    classified_at: datetime | None = None
    reviewed_by: str | None = None
    review_notes: str | None = None


# ── Response Models ─────────────────────────────────────────


class VaultUploadResponse(BaseModel):
    """Response after a document upload."""

    id: str
    filename: str
    status: DocumentStatus
    message: str = "Document queued for classification"


class VaultDocumentResponse(BaseModel):
    """API response model for vault documents."""

    id: str
    project_id: str
    filename: str
    status: DocumentStatus
    document_type: DocumentType | None = None
    confidence_score: float | None = None
    requires_human_review: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None
    created_at: str | None = None
    classified_at: str | None = None


class VaultApproveRequest(BaseModel):
    """Request to approve a classified document."""

    document_type_override: DocumentType | None = Field(
        default=None,
        description="Override the AI classification if incorrect",
    )
    notes: str | None = None


class VaultRejectRequest(BaseModel):
    """Request to reject and re-classify a document."""

    correct_document_type: DocumentType = Field(
        ...,
        description="The correct document type for re-classification",
    )
    notes: str | None = None
