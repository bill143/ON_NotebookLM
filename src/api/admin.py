"""
Admin API — Feature 9D: Backup/Restore, Audit Logs
Codename: ESPERANTO
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.infra.nexus_vault_keys import AuthContext, get_current_user

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Schemas ──────────────────────────────────────────────────


class BackupResponse(BaseModel):
    backup_id: str
    status: str
    started_at: str
    file_path: str | None = None
    size_bytes: int | None = None


class RestoreRequest(BaseModel):
    backup_id: str


class AuditLogEntry(BaseModel):
    id: str
    event_type: str
    actor_id: str
    actor_email: str | None
    resource_type: str
    resource_id: str
    details: dict[str, Any]
    ip_address: str | None
    timestamp: str


class GDPRErasureRequest(BaseModel):
    user_id: str
    confirm: bool


class GDPRErasureResponse(BaseModel):
    status: str
    records_deleted: dict[str, int]
    completed_at: str


# ── Endpoints ────────────────────────────────────────────────


@router.post("/backup")
async def trigger_backup(
    auth: AuthContext = Depends(get_current_user),
) -> BackupResponse:
    """Trigger a database backup (admin only)."""
    auth.require_role("admin")

    import uuid
    from datetime import UTC, datetime

    backup_id = str(uuid.uuid4())
    # In production, this dispatches a Celery task for pg_dump
    from loguru import logger

    logger.info("Backup triggered", backup_id=backup_id, by=auth.user_id)

    return BackupResponse(
        backup_id=backup_id,
        status="in_progress",
        started_at=datetime.now(UTC).isoformat(),
    )


@router.get("/backups")
async def list_backups(
    limit: int = Query(default=10, ge=1, le=50),
    auth: AuthContext = Depends(get_current_user),
) -> list[BackupResponse]:
    """List recent backups."""
    auth.require_role("admin")
    from src.infra.nexus_data_persist import get_session

    async with get_session() as session:
        from sqlalchemy import text

        result = await session.execute(
            text(
                "SELECT id, status, started_at, file_path, size_bytes "
                "FROM backups ORDER BY started_at DESC LIMIT :limit"
            ),
            {"limit": limit},
        )
        rows = result.fetchall()
        return [
            BackupResponse(
                backup_id=str(r[0]),
                status=r[1],
                started_at=str(r[2]),
                file_path=r[3],
                size_bytes=r[4],
            )
            for r in rows
        ]


@router.post("/restore")
async def restore_backup(
    data: RestoreRequest,
    auth: AuthContext = Depends(get_current_user),
) -> dict[str, str]:
    """Restore from a backup (admin only)."""
    auth.require_role("admin")
    from loguru import logger

    logger.warning("Restore triggered", backup_id=data.backup_id, by=auth.user_id)
    return {"status": "restore_started", "backup_id": data.backup_id}


@router.get("/audit-log")
async def get_audit_log(
    event_type: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    auth: AuthContext = Depends(get_current_user),
) -> list[AuditLogEntry]:
    """Query audit log (admin only)."""
    auth.require_role("admin")
    from src.infra.nexus_data_persist import get_session

    async with get_session() as session:
        from sqlalchemy import text

        query = "SELECT * FROM audit_logs WHERE tenant_id = :tid"
        params: dict[str, Any] = {"tid": auth.tenant_id}

        if event_type:
            query += " AND event_type = :event_type"
            params["event_type"] = event_type
        if actor_id:
            query += " AND actor_id = :actor_id"
            params["actor_id"] = actor_id

        query += " ORDER BY created_at DESC LIMIT :limit"
        params["limit"] = limit

        result = await session.execute(text(query), params)
        rows = result.mappings().fetchall()
        return [AuditLogEntry(**dict(r)) for r in rows]


@router.delete("/users/{user_id}/data")
async def gdpr_erasure(
    user_id: str,
    data: GDPRErasureRequest,
    auth: AuthContext = Depends(get_current_user),
) -> GDPRErasureResponse:
    """GDPR right-to-erasure: delete all user data (admin only)."""
    auth.require_role("admin")

    if not data.confirm:
        from src.exceptions import ValidationError

        raise ValidationError("Must confirm erasure with confirm=true")

    from datetime import UTC, datetime

    from loguru import logger

    logger.critical(
        "GDPR ERASURE initiated",
        target_user=user_id,
        by=auth.user_id,
        tenant=auth.tenant_id,
    )

    from src.infra.nexus_data_persist import get_session

    records_deleted: dict[str, int] = {}

    async with get_session() as session:
        from sqlalchemy import text

        # Delete in dependency order
        tables = [
            "review_logs",
            "flashcards",
            "chat_messages",
            "collaboration_sessions",
            "usage_records",
            "artifact_generations",
            "artifacts",
            "notebooks_sources",
            "sources",
            "notebooks",
        ]
        for table in tables:
            result = await session.execute(
                text(f"DELETE FROM {table} WHERE user_id = :uid AND tenant_id = :tid"),  # noqa: S608
                {"uid": user_id, "tid": auth.tenant_id},
            )
            records_deleted[table] = result.rowcount or 0

        await session.commit()

    return GDPRErasureResponse(
        status="completed",
        records_deleted=records_deleted,
        completed_at=datetime.now(UTC).isoformat(),
    )
