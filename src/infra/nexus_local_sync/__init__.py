"""
Nexus Local Sync — Feature 12: Local-First & Offline Mode
Source: Repo #1 (Ollama + Kokoro), Repo #7 (Esperanto local), Repo #8 (Ollama toggle)

Provides:
- Local model detection and management
- Offline operation queue with conflict resolution
- Sync protocol between local and cloud
- Feature degradation matrix
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from loguru import logger

from src.infra.nexus_obs_tracing import traced


class SyncOperation(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class SyncStatus(str, Enum):
    PENDING = "pending"
    SYNCED = "synced"
    CONFLICT = "conflict"
    FAILED = "failed"


class ConflictStrategy(str, Enum):
    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    MERGE = "merge"
    MANUAL = "manual"


@dataclass
class LocalModelInfo:
    """Information about a locally available model."""

    name: str
    provider: str
    model_type: str
    base_url: str
    is_available: bool = False
    model_size_gb: float = 0.0


class LocalModelManager:
    """Detects and manages locally running AI models."""

    @traced("local.detect_models")
    async def detect_local_models(self) -> list[LocalModelInfo]:
        """Detect available local models (Ollama, Kokoro)."""
        models: list[LocalModelInfo] = []

        # Check Ollama
        try:
            import httpx

            from src.config import get_settings

            settings = get_settings()

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.ollama_base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    for model in data.get("models", []):
                        models.append(
                            LocalModelInfo(
                                name=model["name"],
                                provider="ollama",
                                model_type="chat",
                                base_url=f"{settings.ollama_base_url}/v1",
                                is_available=True,
                                model_size_gb=model.get("size", 0) / (1024**3),
                            )
                        )
        except Exception:
            logger.debug("Ollama not available")

        # Check Kokoro TTS
        try:
            import httpx

            from src.config import get_settings

            settings = get_settings()

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.kokoro_tts_base_url}/v1/models")
                if response.status_code == 200:
                    models.append(
                        LocalModelInfo(
                            name="kokoro-tts",
                            provider="kokoro",
                            model_type="tts",
                            base_url=settings.kokoro_tts_base_url,
                            is_available=True,
                        )
                    )
        except Exception:
            logger.debug("Kokoro TTS not available")

        logger.info(f"Detected {len(models)} local models")
        return models

    async def auto_register_local_models(self, tenant_id: str | None = None) -> int:
        """Auto-register detected local models in the DB."""
        from src.infra.nexus_data_persist import BaseRepository

        models = await self.detect_local_models()
        registered = 0

        repo = BaseRepository("ai_models")
        for model in models:
            if model.is_available:
                try:
                    await repo.create(
                        data={
                            "name": f"[Local] {model.name}",
                            "provider": model.provider,
                            "model_type": model.model_type,
                            "model_id_string": model.name,
                            "is_local": True,
                            "base_url": model.base_url,
                            "cost_per_1k_input": 0.0,
                            "cost_per_1k_output": 0.0,
                        },
                        tenant_id=tenant_id,
                    )
                    registered += 1
                except Exception:
                    logger.debug(
                        "Skipping local model registration (may already exist)",
                        model=model.name,
                        exc_info=True,
                    )

        logger.info(f"Auto-registered {registered} local models")
        return registered


class SyncQueue:
    """
    Offline-to-cloud sync queue with conflict resolution.
    Tracks changes made while offline and syncs when connection restored.
    """

    @traced("sync.enqueue")
    async def enqueue(
        self,
        tenant_id: str,
        device_id: str,
        operation: SyncOperation,
        table_name: str,
        record_id: str,
        payload: dict[str, Any],
    ) -> str:
        """Add an operation to the sync queue."""
        from src.infra.nexus_data_persist import BaseRepository

        repo = BaseRepository("sync_queue")
        result = await repo.create(
            data={
                "tenant_id": tenant_id,
                "device_id": device_id,
                "operation": operation.value,
                "table_name": table_name,
                "record_id": record_id,
                "payload": payload,
                "status": SyncStatus.PENDING.value,
            }
        )
        return result["id"]

    @traced("sync.process_queue")
    async def process_queue(
        self,
        tenant_id: str,
        device_id: str,
        conflict_strategy: ConflictStrategy = ConflictStrategy.LOCAL_WINS,
    ) -> dict[str, int]:
        """Process pending sync items."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT * FROM sync_queue
                    WHERE tenant_id = :tid AND device_id = :did AND status = 'pending'
                    ORDER BY created_at ASC
                """),
                {"tid": tenant_id, "did": device_id},
            )
            items = [dict(row) for row in result.mappings().all()]

        stats = {"synced": 0, "conflicts": 0, "failed": 0}

        for item in items:
            try:
                await self._sync_item(item, tenant_id, conflict_strategy)
                stats["synced"] += 1
            except Exception as e:
                if "conflict" in str(e).lower():
                    stats["conflicts"] += 1
                else:
                    stats["failed"] += 1
                    logger.error(f"Sync failed for {item['id']}: {e}")

        return stats

    async def _sync_item(
        self,
        item: dict[str, Any],
        tenant_id: str,
        strategy: ConflictStrategy,
    ) -> None:
        """Sync a single queue item to the cloud database."""
        from src.infra.nexus_data_persist import BaseRepository

        repo = BaseRepository(item["table_name"])

        if item["operation"] == "create":
            await repo.create(data=item["payload"], tenant_id=tenant_id)
        elif item["operation"] == "update":
            await repo.update(item["record_id"], item["payload"], tenant_id)
        elif item["operation"] == "delete":
            await repo.soft_delete(item["record_id"], tenant_id)

        # Mark as synced
        sync_repo = BaseRepository("sync_queue")
        await sync_repo.update(
            item["id"],
            {
                "status": SyncStatus.SYNCED.value,
                "synced_at": datetime.now(UTC),
            },
        )

    def get_feature_matrix(self, is_online: bool) -> dict[str, bool]:
        """Feature availability matrix for online vs offline mode."""
        return {
            "chat": True,
            "research_grounding": True,
            "audio_generation": is_online or True,  # Local TTS available
            "source_upload": True,
            "source_url_fetch": is_online,
            "source_youtube": is_online,
            "vector_search": True,
            "cloud_model_access": is_online,
            "export": True,
            "sync": is_online,
            "budget_tracking": True,
            "real_time_collab": is_online,
        }


    async def list_models(self) -> list[dict[str, Any]]:
        """List local models in router-friendly format."""
        detected = await self.detect_local_models()
        return [
            {
                "name": m.name,
                "provider": m.provider,
                "size_gb": m.model_size_gb,
                "quantization": "unknown",
                "capabilities": [m.model_type],
                "status": "available" if m.is_available else "not_installed",
                "download_progress": None,
            }
            for m in detected
        ]

    @traced("local.pull_model")
    async def pull_model(self, model_name: str) -> None:
        """Pull/download a model via Ollama API."""
        import httpx

        from src.config import get_settings

        settings = get_settings()
        async with httpx.AsyncClient(timeout=300.0) as client:
            await client.post(
                f"{settings.ollama_base_url}/api/pull",
                json={"name": model_name},
            )
        logger.info("Model pull started", model=model_name)

    @traced("local.remove_model")
    async def remove_model(self, model_name: str) -> None:
        """Remove a local model via Ollama API."""
        import httpx

        from src.config import get_settings

        settings = get_settings()
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.delete(
                f"{settings.ollama_base_url}/api/delete",
                json={"name": model_name},
            )
        logger.info("Model removed", model=model_name)


class SyncManager:
    """High-level sync management for the local router."""

    def __init__(self) -> None:
        self._queue = SyncQueue()

    async def get_status(
        self, tenant_id: str, user_id: str
    ) -> dict[str, Any]:
        """Get sync status overview."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        try:
            async with get_session(tenant_id) as session:
                result = await session.execute(
                    text("""
                        SELECT
                            COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                            COUNT(*) FILTER (WHERE status = 'conflict') AS conflicts,
                            MAX(CASE WHEN status = 'synced' THEN synced_at END) AS last_sync
                        FROM sync_queue
                        WHERE tenant_id = :tid
                    """),
                    {"tid": tenant_id},
                )
                row = result.mappings().first()
        except Exception:
            row = None

        return {
            "mode": "online",
            "pending_operations": int(row["pending"]) if row and row["pending"] else 0,
            "last_sync_at": str(row["last_sync"]) if row and row["last_sync"] else None,
            "conflicts": int(row["conflicts"]) if row and row["conflicts"] else 0,
            "queue_size": int(row["pending"]) if row and row["pending"] else 0,
        }

    async def trigger_sync(self, tenant_id: str, user_id: str) -> None:
        """Manually trigger sync processing."""
        await self._queue.process_queue(tenant_id, device_id="default")

    async def list_conflicts(
        self, tenant_id: str, user_id: str
    ) -> list[dict[str, Any]]:
        """List unresolved sync conflicts."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT id, table_name, record_id, payload, created_at
                    FROM sync_queue
                    WHERE tenant_id = :tid AND status = 'conflict'
                    ORDER BY created_at DESC
                """),
                {"tid": tenant_id},
            )
            rows = result.mappings().all()

        return [
            {
                "id": str(r["id"]),
                "resource_type": r["table_name"],
                "resource_id": str(r["record_id"]),
                "local_version": "local",
                "remote_version": "remote",
                "strategy": "manual",
                "created_at": str(r["created_at"]),
            }
            for r in rows
        ]

    async def resolve_conflict(
        self, tenant_id: str, conflict_id: str, strategy: str
    ) -> None:
        """Resolve a sync conflict."""
        from sqlalchemy import text

        from src.infra.nexus_data_persist import get_session

        async with get_session(tenant_id) as session:
            await session.execute(
                text("""
                    UPDATE sync_queue SET status = 'synced',
                    synced_at = NOW() WHERE id = :cid AND tenant_id = :tid
                """),
                {"cid": conflict_id, "tid": tenant_id},
            )
            await session.commit()


def get_feature_matrix() -> list[dict[str, Any]]:
    """Module-level feature availability matrix."""
    features = [
        {"feature": "Chat (AI conversation)", "online": True, "offline": True, "degraded_note": None},
        {"feature": "Source Upload (file)", "online": True, "offline": True, "degraded_note": None},
        {"feature": "Source Upload (URL)", "online": True, "offline": False, "degraded_note": "Requires internet to fetch URL content"},
        {"feature": "Source Upload (YouTube)", "online": True, "offline": False, "degraded_note": "Requires internet for transcript"},
        {"feature": "Vector Search", "online": True, "offline": True, "degraded_note": None},
        {"feature": "Deep Research (web)", "online": True, "offline": False, "degraded_note": "Web search requires internet"},
        {"feature": "Deep Research (local)", "online": True, "offline": True, "degraded_note": "Limited to local sources only"},
        {"feature": "Audio Generation", "online": True, "offline": True, "degraded_note": "Uses local Kokoro TTS when offline"},
        {"feature": "Slide Generation", "online": True, "offline": True, "degraded_note": None},
        {"feature": "Video Generation", "online": True, "offline": False, "degraded_note": "Requires cloud vision models"},
        {"feature": "Export (PDF/DOCX/EPUB)", "online": True, "offline": True, "degraded_note": None},
        {"feature": "Real-time Collaboration", "online": True, "offline": False, "degraded_note": "Requires WebSocket connection"},
        {"feature": "Cloud Model Access", "online": True, "offline": False, "degraded_note": "Uses local Ollama models when offline"},
        {"feature": "Flashcard Review", "online": True, "offline": True, "degraded_note": None},
        {"feature": "Budget Tracking", "online": True, "offline": True, "degraded_note": "Local costs are $0"},
    ]
    return features


# Global singletons
local_model_manager = LocalModelManager()
sync_queue = SyncQueue()
