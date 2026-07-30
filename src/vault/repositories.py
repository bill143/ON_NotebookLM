"""
Vault Repositories — Data access layer for the Document Vault module.

Follows the BaseRepository pattern from src.infra.nexus_data_persist.
Each repository provides domain-specific query methods beyond base CRUD.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from loguru import logger
from sqlalchemy import text

from src.infra.nexus_data_persist import (
    BaseRepository,
    _stringify_uuids,
    get_session,
)

# ── VaultDocumentRepository ────────────────────────────────────


class VaultDocumentRepository(BaseRepository):
    """Repository for vault_documents — the core document table with soft-delete."""

    def __init__(self) -> None:
        super().__init__("vault_documents")
        # Override: vault_documents supports soft-delete
        self._has_soft_delete = True

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def soft_delete(self, record_id: str, tenant_id: str | None = None) -> bool:
        """Soft delete by setting deleted_at."""
        now = datetime.now(UTC)
        query = (
            "UPDATE vault_documents SET deleted_at = :now, updated_at = :now "
            "WHERE id = :id AND deleted_at IS NULL"
        )
        params: dict[str, Any] = {"id": record_id, "now": now}
        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id
        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            deleted = result.rowcount > 0
            if deleted:
                logger.info("Soft deleted vault_document", record_id=record_id)
            return deleted

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def list_pending(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self.list_all(tenant_id, filters={"processing_status": "PENDING"})

    async def list_needs_review(self, tenant_id: str) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM vault_documents "
            "WHERE tenant_id = :tenant_id AND requires_human_review = true "
            "AND human_reviewed_at IS NULL AND deleted_at IS NULL "
            "ORDER BY created_at ASC"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), {"tenant_id": tenant_id})
            return [_stringify_uuids(dict(row)) for row in result.mappings().all()]

    async def update_status(
        self, record_id: str, status: str, tenant_id: str
    ) -> dict[str, Any] | None:
        return await self.update(record_id, {"processing_status": status}, tenant_id)

    async def update_librarian_decision(
        self,
        record_id: str,
        decision: dict[str, Any],
        document_type: str,
        confidence: float,
        tenant_id: str,
    ) -> dict[str, Any] | None:
        return await self.update(
            record_id,
            {
                "librarian_decision": decision,
                "document_type": document_type,
                "confidence_score": confidence,
                "processing_status": "CLASSIFIED",
            },
            tenant_id,
        )


# ── RFIRepository ──────────────────────────────────────────────


class RFIRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("rfi_records")

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def get_by_rfi_number(
        self, rfi_number: str, project_id: str, tenant_id: str
    ) -> dict[str, Any] | None:
        query = (
            "SELECT * FROM rfi_records "
            "WHERE rfi_number = :rfi_number AND project_id = :project_id "
            "AND tenant_id = :tenant_id"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"rfi_number": rfi_number, "project_id": project_id, "tenant_id": tenant_id},
            )
            row = result.mappings().first()
            return _stringify_uuids(dict(row)) if row else None

    async def list_open(self, tenant_id: str) -> list[dict[str, Any]]:
        return await self.list_all(tenant_id, filters={"status": "OPEN"})

    async def list_overdue(self, tenant_id: str) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM rfi_records "
            "WHERE tenant_id = :tenant_id AND status = 'OPEN' "
            "AND date_required < :today "
            "ORDER BY date_required ASC"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"tenant_id": tenant_id, "today": date.today()}
            )
            return [_stringify_uuids(dict(row)) for row in result.mappings().all()]


# ── SubmittalRepository ────────────────────────────────────────


class SubmittalRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("submittal_records")

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def get_next_submittal_number(self, project_id: str, tenant_id: str) -> str:
        query = (
            "SELECT COUNT(*) as cnt FROM submittal_records "
            "WHERE project_id = :project_id AND tenant_id = :tenant_id"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"project_id": project_id, "tenant_id": tenant_id}
            )
            row = result.mappings().first()
            count = row["cnt"] if row else 0
            return f"SUB-{count + 1:04d}"


# ── InvoiceRepository ─────────────────────────────────────────


class InvoiceRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("invoice_records")

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def check_duplicate_invoice_number(
        self, invoice_number: str, project_id: str, tenant_id: str
    ) -> bool:
        query = (
            "SELECT 1 FROM invoice_records "
            "WHERE invoice_number = :invoice_number AND project_id = :project_id "
            "AND tenant_id = :tenant_id LIMIT 1"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"invoice_number": invoice_number, "project_id": project_id, "tenant_id": tenant_id},
            )
            return result.first() is not None


# ── ChangeOrderRepository ─────────────────────────────────────


class ChangeOrderRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("change_order_records")

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def get_next_co_number(self, project_id: str, tenant_id: str) -> str:
        query = (
            "SELECT COUNT(*) as cnt FROM change_order_records "
            "WHERE project_id = :project_id AND tenant_id = :tenant_id"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"project_id": project_id, "tenant_id": tenant_id}
            )
            row = result.mappings().first()
            count = row["cnt"] if row else 0
            return f"CO-{count + 1:04d}"


# ── COIRepository ──────────────────────────────────────────────


class COIRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("coi_records")

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def list_expiring_soon(
        self, tenant_id: str, days_ahead: int = 30
    ) -> list[dict[str, Any]]:
        cutoff = date.today() + timedelta(days=days_ahead)
        query = (
            "SELECT * FROM coi_records "
            "WHERE tenant_id = :tenant_id AND status = 'ACTIVE' "
            "AND expiration_date <= :cutoff AND expiration_date >= :today "
            "ORDER BY expiration_date ASC"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"tenant_id": tenant_id, "cutoff": cutoff, "today": date.today()},
            )
            return [_stringify_uuids(dict(row)) for row in result.mappings().all()]


# ── PermitRepository ───────────────────────────────────────────


class PermitRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("permit_records")

    async def get(self, record_id: str, tenant_id: str) -> dict[str, Any] | None:
        return await self.get_by_id(record_id, tenant_id)

    async def list_by_project(
        self, project_id: str, tenant_id: str, *, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        return await self.list_all(
            tenant_id, limit=limit, offset=offset, filters={"project_id": project_id}
        )

    async def list_expiring_soon(
        self, tenant_id: str, days_ahead: int = 30
    ) -> list[dict[str, Any]]:
        cutoff = date.today() + timedelta(days=days_ahead)
        query = (
            "SELECT * FROM permit_records "
            "WHERE tenant_id = :tenant_id AND status = 'ACTIVE' "
            "AND expiration_date <= :cutoff AND expiration_date >= :today "
            "ORDER BY expiration_date ASC"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"tenant_id": tenant_id, "cutoff": cutoff, "today": date.today()},
            )
            return [_stringify_uuids(dict(row)) for row in result.mappings().all()]


# ── WorkflowLogRepository ─────────────────────────────────────


class WorkflowLogRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("vault_workflow_log")
        self._has_updated_at = False

    async def list_by_document(
        self, vault_document_id: str, tenant_id: str
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM vault_workflow_log "
            "WHERE vault_document_id = :vault_document_id AND tenant_id = :tenant_id "
            "ORDER BY created_at ASC"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"vault_document_id": vault_document_id, "tenant_id": tenant_id},
            )
            return [_stringify_uuids(dict(row)) for row in result.mappings().all()]


# ── DeadlineReminderRepository ─────────────────────────────────


class DeadlineReminderRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("vault_deadline_reminders")
        self._has_updated_at = False

    async def list_pending(self, tenant_id: str) -> list[dict[str, Any]]:
        query = (
            "SELECT * FROM vault_deadline_reminders "
            "WHERE tenant_id = :tenant_id AND status = 'PENDING' "
            "AND scheduled_for <= :now "
            "ORDER BY scheduled_for ASC"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"tenant_id": tenant_id, "now": datetime.now(UTC)}
            )
            return [_stringify_uuids(dict(row)) for row in result.mappings().all()]

    async def mark_sent(self, record_id: str, tenant_id: str) -> bool:
        now = datetime.now(UTC)
        query = (
            "UPDATE vault_deadline_reminders SET status = 'SENT', sent_at = :now "
            "WHERE id = :id AND tenant_id = :tenant_id AND status = 'PENDING' "
            "RETURNING id"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"id": record_id, "tenant_id": tenant_id, "now": now}
            )
            return result.first() is not None

    async def cancel(self, record_id: str, tenant_id: str) -> bool:
        query = (
            "UPDATE vault_deadline_reminders SET status = 'CANCELLED' "
            "WHERE id = :id AND tenant_id = :tenant_id AND status = 'PENDING' "
            "RETURNING id"
        )
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"id": record_id, "tenant_id": tenant_id}
            )
            return result.first() is not None


# ── Repository Registry ───────────────────────────────────────

vault_documents_repo = VaultDocumentRepository()
rfi_repo = RFIRepository()
submittal_repo = SubmittalRepository()
invoice_repo = InvoiceRepository()
change_order_repo = ChangeOrderRepository()
coi_repo = COIRepository()
permit_repo = PermitRepository()
workflow_log_repo = WorkflowLogRepository()
deadline_reminder_repo = DeadlineReminderRepository()
