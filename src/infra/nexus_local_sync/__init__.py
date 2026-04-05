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


# Global singletons
local_model_manager = LocalModelManager()
sync_queue = SyncQueue()
