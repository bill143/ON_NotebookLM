"""
Nexus Vault — FastAPI Router for the Intelligent Document Vault
Codename: ESPERANTO

Endpoints:
- POST   /vault/upload           — Upload and classify a document
- GET    /vault/status/{id}      — Check processing status
- GET    /vault/queue/{project}  — List all queued documents for a project
- POST   /vault/approve/{id}     — Human approval for low-confidence docs
- POST   /vault/reject/{id}      — Reject and override classification
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from loguru import logger

from src.exceptions import FileTooLargeError, NotFoundError, ValidationError
from src.infra.nexus_obs_tracing import traced
from src.infra.nexus_vault_keys import AuthContext, get_current_user
from src.vault.document_types import (
    DocumentStatus,
    VaultApproveRequest,
    VaultDocumentResponse,
    VaultRejectRequest,
    VaultUploadResponse,
)

router = APIRouter(prefix="/vault", tags=["Vault"])

MAX_FILE_SIZE_MB = 200  # Construction files can be large


# ── Repository Access ───────────────────────────────────────


def _get_vault_repo():
    """Lazy import to avoid circular deps at module level."""
    from src.infra.nexus_data_persist import BaseRepository

    return BaseRepository("vault_documents")


# ── Upload Endpoint ─────────────────────────────────────────


@router.post("/upload", response_model=VaultUploadResponse, status_code=201)
@traced("vault.upload")
async def upload_document(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    title: str | None = Form(None),
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Upload a construction document for AI classification."""
    from src.infra.nexus_vault_keys import rate_limiter

    rate_limiter.check(f"vault_upload:{auth.user_id}", max_requests=20, window_seconds=60)

    # Validate file
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise FileTooLargeError(f"File too large: {size_mb:.1f}MB (max {MAX_FILE_SIZE_MB}MB)")

    if not file.filename:
        raise ValidationError("Filename is required")

    # Persist file to storage
    from src.config import get_settings

    settings = get_settings()

    content_hash = hashlib.sha256(content).hexdigest()[:16]
    safe_filename = f"{content_hash}_{file.filename}"
    vault_dir = Path(settings.storage_local_path) / "vault" / auth.tenant_id / project_id
    vault_dir.mkdir(parents=True, exist_ok=True)
    file_path = vault_dir / safe_filename
    file_path.write_bytes(content)

    # Create vault document record
    repo = _get_vault_repo()
    record = await repo.create(
        data={
            "project_id": project_id,
            "user_id": auth.user_id,
            "filename": file.filename,
            "file_size_bytes": len(content),
            "mime_type": file.content_type,
            "status": DocumentStatus.PENDING.value,
            "title": title or file.filename,
            "file_path": str(file_path),
        },
        tenant_id=auth.tenant_id,
    )

    document_id = record["id"]

    # Enqueue async classification
    from src.worker import classify_vault_document

    classify_vault_document.delay(document_id, auth.tenant_id)

    logger.info(
        f"Vault document queued: {file.filename}",
        document_id=document_id,
        project_id=project_id,
    )

    return {
        "id": document_id,
        "filename": file.filename,
        "status": DocumentStatus.PENDING.value,
        "message": "Document queued for classification",
    }


# ── Status Endpoint ─────────────────────────────────────────


@router.get("/status/{document_id}", response_model=VaultDocumentResponse)
@traced("vault.status")
async def get_document_status(
    document_id: str,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Get the processing status and classification result for a document."""
    repo = _get_vault_repo()
    record = await repo.get_by_id(document_id, auth.tenant_id)

    if not record:
        raise NotFoundError(f"Vault document '{document_id}' not found")

    return _format_response(record)


# ── Queue Endpoint ──────────────────────────────────────────


@router.get("/queue/{project_id}", response_model=list[VaultDocumentResponse])
@traced("vault.queue")
async def get_project_queue(
    project_id: str,
    auth: AuthContext = Depends(get_current_user),
    status: str | None = Query(None, description="Filter by status"),
    limit: int = Query(50, le=100),
    offset: int = 0,
) -> list[dict[str, Any]]:
    """List all vault documents for a project."""
    repo = _get_vault_repo()
    filters: dict[str, Any] = {"project_id": project_id}
    if status:
        filters["status"] = status

    records = await repo.list_all(
        auth.tenant_id,
        limit=limit,
        offset=offset,
        filters=filters,
        order_by="created_at DESC",
    )

    return [_format_response(r) for r in records]


# ── Approve Endpoint ────────────────────────────────────────


@router.post("/approve/{document_id}", response_model=VaultDocumentResponse)
@traced("vault.approve")
async def approve_document(
    document_id: str,
    body: VaultApproveRequest | None = None,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Approve a classified document (human review step)."""
    repo = _get_vault_repo()
    record = await repo.get_by_id(document_id, auth.tenant_id)

    if not record:
        raise NotFoundError(f"Vault document '{document_id}' not found")

    update_data: dict[str, Any] = {
        "status": DocumentStatus.APPROVED.value,
        "reviewed_by": auth.user_id,
    }

    if body and body.document_type_override:
        update_data["document_type"] = body.document_type_override.value
    if body and body.notes:
        update_data["review_notes"] = body.notes

    updated = await repo.update(document_id, update_data, auth.tenant_id)
    if not updated:
        raise NotFoundError(f"Vault document '{document_id}' not found")

    logger.info(
        f"Vault document approved: {document_id}",
        reviewed_by=auth.user_id,
        override=bool(body and body.document_type_override),
    )

    return _format_response(updated)


# ── Reject Endpoint ─────────────────────────────────────────


@router.post("/reject/{document_id}", response_model=VaultDocumentResponse)
@traced("vault.reject")
async def reject_document(
    document_id: str,
    body: VaultRejectRequest,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, Any]:
    """Reject a classification and provide the correct document type."""
    repo = _get_vault_repo()
    record = await repo.get_by_id(document_id, auth.tenant_id)

    if not record:
        raise NotFoundError(f"Vault document '{document_id}' not found")

    update_data: dict[str, Any] = {
        "status": DocumentStatus.REJECTED.value,
        "document_type": body.correct_document_type.value,
        "reviewed_by": auth.user_id,
        "review_notes": body.notes or f"Reclassified to {body.correct_document_type.value}",
    }

    updated = await repo.update(document_id, update_data, auth.tenant_id)
    if not updated:
        raise NotFoundError(f"Vault document '{document_id}' not found")

    logger.info(
        f"Vault document rejected: {document_id}",
        reviewed_by=auth.user_id,
        correct_type=body.correct_document_type.value,
    )

    return _format_response(updated)


# ── Response Formatter ──────────────────────────────────────


def _format_response(record: dict[str, Any]) -> dict[str, Any]:
    """Format a DB record into VaultDocumentResponse shape."""
    return {
        "id": str(record.get("id", "")),
        "project_id": str(record.get("project_id", "")),
        "filename": record.get("filename", ""),
        "status": record.get("status", DocumentStatus.PENDING.value),
        "document_type": record.get("document_type"),
        "confidence_score": record.get("confidence_score"),
        "requires_human_review": record.get("requires_human_review", False),
        "metadata": record.get("classification_metadata", {}),
        "title": record.get("title"),
        "created_at": str(record["created_at"]) if record.get("created_at") else None,
        "classified_at": str(record["classified_at"]) if record.get("classified_at") else None,
    }
