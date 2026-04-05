"""
Nexus Data Persistence — Feature 9: Database Engine & Repository Pattern
Source: Repo #7 (database/repository.py — SurrealDB async pattern)
Adapted: PostgreSQL + SQLAlchemy async with pgvector

Provides:
- Async connection pool management
- Base repository pattern for all domain models
- Tenant-scoped query enforcement
- Transaction management with retry logic
"""

from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, TypeVar

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Environment, get_settings
from src.exceptions import DatabaseError, TransactionConflictError

T = TypeVar("T")

# ── Engine & Session Factory ─────────────────────────────────

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_database() -> None:
    """Initialize the database engine and session factory."""
    global _engine, _session_factory

    settings = get_settings()
    connect_args: dict[str, Any] = {}
    if settings.environment == Environment.TESTING and settings.database_url.startswith(
        "postgresql+asyncpg"
    ):
        # Fail fast when Postgres is down (local integration runs / CI), instead of long TCP hangs.
        connect_args["timeout"] = 10

    _engine = create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        echo=settings.database_echo,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args=connect_args,
    )
    _session_factory = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    logger.info("Database engine initialized", pool_size=settings.database_pool_size)


async def close_database() -> None:
    """Close the database engine and release connections."""
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Database engine closed")


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get the session factory (must call init_database first)."""
    if _session_factory is None:
        raise DatabaseError("Database not initialized. Call init_database() first.")
    return _session_factory


@asynccontextmanager
async def get_session(tenant_id: str | None = None):
    """
    Get a database session with optional tenant context.

    If tenant_id is provided, sets the app.tenant_id session variable
    for PostgreSQL Row-Level Security enforcement.

    Safety guardrails applied to every session:
    - statement_timeout: 30 s — prevents runaway queries from holding
      connections indefinitely (vector search, full-text, AI-generated SQL).
    - idle_in_transaction_session_timeout: 60 s — auto-kills sessions that
      open a transaction and then stall (e.g. awaiting an external API call
      inside a ``async with get_session()`` block).
    """
    factory = get_session_factory()
    session = factory()

    try:
        await session.execute(text("SET LOCAL statement_timeout = '30000'"))
        await session.execute(text("SET LOCAL idle_in_transaction_session_timeout = '60000'"))

        if tenant_id:
            await session.execute(
                text("SET LOCAL app.tenant_id = :tid"),
                {"tid": tenant_id},
            )

        yield session
        await session.commit()
    except Exception as e:
        await session.rollback()
        error_str = str(e).lower()
        if "conflict" in error_str or "serialization" in error_str:
            raise TransactionConflictError(
                "Transaction conflict — please retry",
                original_error=e,
            ) from e
        raise DatabaseError(str(e), original_error=e) from e
    finally:
        await session.close()


# ── Base Repository ──────────────────────────────────────────

_SAFE_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_SAFE_ORDER_BY = re.compile(
    r"^[a-z_][a-z0-9_]*\s*(?:ASC|DESC)?$",
    re.IGNORECASE,
)


def _validate_identifier(name: str) -> str:
    """Reject anything that isn't a simple column name."""
    if not _SAFE_IDENTIFIER.match(name):
        raise DatabaseError(f"Invalid identifier: {name!r}")
    return name


def _validate_order_clause(clause: str) -> str:
    """Validate an ORDER BY clause like 'created_at DESC'."""
    for part in clause.split(","):
        if not _SAFE_ORDER_BY.match(part.strip()):
            raise DatabaseError(f"Invalid order_by clause: {clause!r}")
    return clause


class BaseRepository:
    """
    Base repository providing CRUD operations for any domain model.

    Pattern source: Repo #7, database/repository.py
    - Async context-managed sessions
    - Automatic tenant scoping
    - Timestamp management
    - Soft delete support
    """

    def __init__(self, table_name: str) -> None:
        _validate_identifier(table_name)
        self.table_name = table_name

    async def create(
        self,
        data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new record."""
        record_id = str(uuid.uuid4())
        now = datetime.now(UTC)

        data["id"] = record_id
        data["created_at"] = now
        data["updated_at"] = now
        if tenant_id:
            data["tenant_id"] = tenant_id

        data = {k: v for k, v in data.items() if v is not None}

        for key in data:
            _validate_identifier(key)

        columns = ", ".join(data.keys())
        placeholders = ", ".join(f":{k}" for k in data.keys())

        async with get_session(tenant_id) as session:
            await session.execute(
                text(
                    f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"  # noqa: S608 — table_name validated by _validate_identifier; values use :param binding
                ),
                data,
            )
            logger.debug(f"Created record in {self.table_name}", record_id=record_id)

        return {**data, "id": record_id}

    async def get_by_id(
        self,
        record_id: str,
        tenant_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Get a single record by ID."""
        query = f"SELECT * FROM {self.table_name} WHERE id = :id"  # noqa: S608 — table_name validated at __init__
        params: dict[str, Any] = {"id": record_id}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        query += " AND deleted_at IS NULL"

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            row = result.mappings().first()
            return dict(row) if row else None

    async def list_all(
        self,
        tenant_id: str | None = None,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at DESC",
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """List records with pagination and filtering."""
        _validate_order_clause(order_by)

        query = f"SELECT * FROM {self.table_name} WHERE deleted_at IS NULL"  # noqa: S608 — table_name validated at __init__
        params: dict[str, Any] = {"limit": limit, "offset": offset}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        if filters:
            for key, value in filters.items():
                _validate_identifier(key)
                query += f" AND {key} = :{key}"
                params[key] = value

        query += f" ORDER BY {order_by} LIMIT :limit OFFSET :offset"

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            return [dict(row) for row in result.mappings().all()]

    async def update(
        self,
        record_id: str,
        data: dict[str, Any],
        tenant_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Update a record by ID."""
        data["updated_at"] = datetime.now(UTC)
        data.pop("id", None)
        data.pop("created_at", None)

        for key in data:
            _validate_identifier(key)

        set_clause = ", ".join(f"{k} = :{k}" for k in data.keys())
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = :id"  # noqa: S608 — table_name validated at __init__
        params = {**data, "id": record_id}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        query += " RETURNING *"

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            row = result.mappings().first()
            if row:
                logger.debug(f"Updated record in {self.table_name}", record_id=record_id)
                return dict(row)
            return None

    async def soft_delete(
        self,
        record_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Soft delete a record by setting deleted_at."""
        now = datetime.now(UTC)
        query = f"UPDATE {self.table_name} SET deleted_at = :now, updated_at = :now WHERE id = :id AND deleted_at IS NULL"  # noqa: S608 — table_name validated at __init__
        params: dict[str, Any] = {"id": record_id, "now": now}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            deleted = result.rowcount > 0
            if deleted:
                logger.info(f"Soft deleted from {self.table_name}", record_id=record_id)
            return deleted

    async def hard_delete(
        self,
        record_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Permanently delete a record."""
        query = f"DELETE FROM {self.table_name} WHERE id = :id"  # noqa: S608 — table_name validated at __init__
        params: dict[str, Any] = {"id": record_id}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            return result.rowcount > 0

    async def count(
        self,
        tenant_id: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> int:
        """Count records with optional filtering."""
        query = f"SELECT COUNT(*) as cnt FROM {self.table_name} WHERE deleted_at IS NULL"  # noqa: S608 — table_name validated at __init__
        params: dict[str, Any] = {}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        if filters:
            for key, value in filters.items():
                _validate_identifier(key)
                query += f" AND {key} = :{key}"
                params[key] = value

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            row = result.mappings().first()
            return row["cnt"] if row else 0

    async def exists(
        self,
        record_id: str,
        tenant_id: str | None = None,
    ) -> bool:
        """Check if a record exists."""
        query = f"SELECT 1 FROM {self.table_name} WHERE id = :id AND deleted_at IS NULL"  # noqa: S608 — table_name validated at __init__
        params: dict[str, Any] = {"id": record_id}

        if tenant_id:
            query += " AND tenant_id = :tenant_id"
            params["tenant_id"] = tenant_id

        async with get_session(tenant_id) as session:
            result = await session.execute(text(query), params)
            return result.first() is not None


# ── Specialized Repositories ─────────────────────────────────


class NotebookRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("notebooks")

    async def get_with_sources(self, notebook_id: str, tenant_id: str) -> dict | None:
        query = """
            SELECT n.*,
                   COALESCE(json_agg(
                       json_build_object('id', s.id, 'title', s.title, 'source_type', s.source_type, 'status', s.status)
                   ) FILTER (WHERE s.id IS NOT NULL), '[]') as sources,
                   COUNT(DISTINCT ns.source_id) as source_count
            FROM notebooks n
            LEFT JOIN notebook_sources ns ON n.id = ns.notebook_id
            LEFT JOIN sources s ON ns.source_id = s.id AND s.deleted_at IS NULL
            WHERE n.id = :notebook_id AND n.tenant_id = :tenant_id AND n.deleted_at IS NULL
            GROUP BY n.id
        """
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query), {"notebook_id": notebook_id, "tenant_id": tenant_id}
            )
            row = result.mappings().first()
            return dict(row) if row else None

    async def cascade_delete_preview(self, notebook_id: str, tenant_id: str) -> dict[str, int]:
        """Preview what would be deleted (Repo #7 pattern)."""
        counts: dict[str, int] = {}
        queries = {
            "sources": "SELECT COUNT(*) as cnt FROM notebook_sources WHERE notebook_id = :id",
            "notes": "SELECT COUNT(*) as cnt FROM notes WHERE notebook_id = :id AND deleted_at IS NULL",
            "artifacts": "SELECT COUNT(*) as cnt FROM artifacts WHERE notebook_id = :id AND deleted_at IS NULL",
            "sessions": "SELECT COUNT(*) as cnt FROM sessions WHERE notebook_id = :id",
        }
        async with get_session(tenant_id) as session:
            for name, query in queries.items():
                result = await session.execute(text(query), {"id": notebook_id})
                row = result.mappings().first()
                counts[name] = row["cnt"] if row else 0
        return counts


class SourceRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("sources")

    async def vector_search(
        self,
        query_embedding: list[float],
        source_ids: list[str],
        tenant_id: str,
        limit: int = 10,
        min_score: float = 0.5,
    ) -> list[dict[str, Any]]:
        """Semantic vector search across source embeddings."""
        query = """
            SELECT se.id, se.source_id, se.content, se.chunk_index,
                   1 - (se.embedding <=> :embedding::vector) as score
            FROM source_embeddings se
            WHERE se.source_id = ANY(:source_ids)
              AND se.tenant_id = :tenant_id
              AND 1 - (se.embedding <=> :embedding::vector) >= :min_score
            ORDER BY se.embedding <=> :embedding::vector
            LIMIT :limit
        """
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {
                    "embedding": str(query_embedding),
                    "source_ids": source_ids,
                    "tenant_id": tenant_id,
                    "min_score": min_score,
                    "limit": limit,
                },
            )
            return [dict(row) for row in result.mappings().all()]

    async def text_search(
        self,
        query_text: str,
        tenant_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Full-text search across source content."""
        query = """
            SELECT id, title, source_type,
                   ts_rank(to_tsvector('english', COALESCE(full_text, '')), plainto_tsquery(:query)) as rank
            FROM sources
            WHERE tenant_id = :tenant_id
              AND deleted_at IS NULL
              AND to_tsvector('english', COALESCE(full_text, '')) @@ plainto_tsquery(:query)
            ORDER BY rank DESC
            LIMIT :limit
        """
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"query": query_text, "tenant_id": tenant_id, "limit": limit},
            )
            return [dict(row) for row in result.mappings().all()]


class ArtifactRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("artifacts")

    async def get_queue(self, tenant_id: str, status: str = "queued") -> list[dict]:
        return await self.list_all(
            tenant_id,
            filters={"status": status},
            order_by="created_at ASC",
        )


class SessionRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("sessions")


class UsageRepository(BaseRepository):
    def __init__(self) -> None:
        super().__init__("usage_records")

    async def get_usage_summary(self, tenant_id: str, period_start: datetime) -> dict[str, Any]:
        query = """
            SELECT
                COUNT(*) as total_requests,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                SUM(cost_usd) as total_cost_usd,
                AVG(latency_ms) as avg_latency_ms
            FROM usage_records
            WHERE tenant_id = :tenant_id
              AND created_at >= :period_start
        """
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text(query),
                {"tenant_id": tenant_id, "period_start": period_start},
            )
            row = result.mappings().first()
            return dict(row) if row else {}


# ── Repository Registry ──────────────────────────────────────

notebooks_repo = NotebookRepository()
sources_repo = SourceRepository()
artifacts_repo = ArtifactRepository()
sessions_repo = SessionRepository()
usage_repo = UsageRepository()
notes_repo = BaseRepository("notes")
flashcards_repo = BaseRepository("flashcards")
audit_repo = BaseRepository("audit_logs")
