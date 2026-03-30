"""
Nexus Celery Worker — Async Task Engine for Artifact Generation
Codename: ESPERANTO

Handles long-running AI tasks outside the request cycle:
- Source processing (extract → embed → transform)
- Artifact generation (summaries, podcasts, quizzes)
- Batch embedding jobs
- Scheduled flashcard generation
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from celery import Celery, signals
from loguru import logger

from src.config import get_settings

settings = get_settings()

# ── Celery App ───────────────────────────────────────────────

celery_app = Celery(
    "nexus",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,       # 10 min hard limit
    task_soft_time_limit=540,  # 9 min soft limit
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    # Queue routing
    task_routes={
        "nexus.tasks.process_source": {"queue": "source_processing"},
        "nexus.tasks.generate_artifact": {"queue": "artifact_generation"},
        "nexus.tasks.batch_embed": {"queue": "embedding"},
    },
    task_default_queue="default",
)


# ── Lifecycle Hooks ──────────────────────────────────────────

@signals.worker_init.connect
def on_worker_init(**kwargs: Any) -> None:
    """Initialize database and logging when worker starts."""
    from src.infra.nexus_obs_tracing import setup_logging
    setup_logging(settings.log_level.value, settings.log_format)
    logger.info("Celery worker starting — initializing database")

    # Initialize async DB pool for the worker
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    from src.infra.nexus_data_persist import init_database
    loop.run_until_complete(init_database())
    logger.info("Celery worker ready")


@signals.worker_shutdown.connect
def on_worker_shutdown(**kwargs: Any) -> None:
    """Clean up database connections on worker shutdown."""
    loop = asyncio.get_event_loop()
    from src.infra.nexus_data_persist import close_database
    loop.run_until_complete(close_database())
    logger.info("Celery worker shutdown complete")


# ── Helper ───────────────────────────────────────────────────

def run_async(coro):
    """Run an async function from a sync Celery task."""
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ── Tasks ────────────────────────────────────────────────────

@celery_app.task(
    name="nexus.tasks.process_source",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def process_source(self, source_id: str, tenant_id: str) -> dict:
    """
    Full source processing pipeline:
    1. Extract content from source
    2. Generate embeddings
    3. Create insights/summary
    """
    logger.info(f"Processing source: {source_id}", task_id=self.request.id)

    async def _process():
        from src.core.nexus_source_ingest import source_processor
        from src.agents.nexus_agent_embed import vectorize_source
        from src.agents.nexus_agent_orchestrator import ChainState

        # Step 1: Extract and process source content
        result = await source_processor.process_source(source_id, tenant_id)

        # Step 2: Vectorize the processed source
        if result["status"] == "ready":
            from src.infra.nexus_data_persist import sources_repo

            source = await sources_repo.get_by_id(source_id, tenant_id)
            if source and source.get("full_text"):
                embed_state = ChainState(
                    tenant_id=tenant_id,
                    user_id="system",
                    inputs={
                        "source_id": source_id,
                        "source_content": source["full_text"],
                    },
                )
                embed_result = await vectorize_source(embed_state)
                result["chunks"] = embed_result.get("chunks", 0)

        return result

    return run_async(_process())


@celery_app.task(
    name="nexus.tasks.generate_artifact",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def generate_artifact(self, artifact_id: str, tenant_id: str) -> dict:
    """
    Generate an artifact (summary, quiz, podcast, flashcards).
    Routes to the appropriate agent chain based on artifact_type.
    """
    logger.info(f"Generating artifact: {artifact_id}", task_id=self.request.id)

    async def _generate():
        from src.infra.nexus_data_persist import artifacts_repo, notebooks_repo, sources_repo, get_session
        from src.agents.nexus_agent_orchestrator import ChainState, ChainStep, CompensationStrategy, chain_executor, AgentRegistry
        from src.agents.nexus_agent_content import (
            generate_summary, generate_quiz, generate_podcast_script, generate_flashcards,
        )
        from src.agents.nexus_agent_voice import synthesize_dialogue
        from src.infra.nexus_obs_tracing import metrics
        from sqlalchemy import text

        # 1. Get artifact record
        artifact = await artifacts_repo.get_by_id(artifact_id, tenant_id)
        if not artifact:
            raise ValueError(f"Artifact {artifact_id} not found")

        # Update status to processing
        await artifacts_repo.update(artifact_id, {"status": "processing"}, tenant_id)
        metrics.active_generations.labels(artifact_type=artifact["artifact_type"]).inc()

        try:
            # 2. Get source content from notebook
            notebook_id = artifact.get("notebook_id")
            source_content = ""

            if notebook_id:
                async with get_session(tenant_id) as session:
                    result = await session.execute(
                        text("""
                            SELECT s.full_text FROM sources s
                            JOIN notebook_sources ns ON s.id = ns.source_id
                            WHERE ns.notebook_id = :nid AND s.deleted_at IS NULL AND s.full_text IS NOT NULL
                        """),
                        {"nid": notebook_id},
                    )
                    rows = result.mappings().all()
                    source_content = "\n\n---\n\n".join(
                        row["full_text"][:20000] for row in rows
                    )

            if not source_content:
                await artifacts_repo.update(
                    artifact_id,
                    {"status": "error", "content": "No source content available"},
                    tenant_id,
                )
                return {"status": "error", "reason": "No source content"}

            # 3. Build chain state
            state = ChainState(
                tenant_id=tenant_id,
                user_id=artifact.get("user_id", "system"),
                inputs={
                    "source_content": source_content,
                    "generation_config": artifact.get("generation_config", {}),
                    "num_questions": artifact.get("generation_config", {}).get("num_questions", 10),
                    "num_cards": artifact.get("generation_config", {}).get("num_cards", 20),
                },
            )

            # 4. Route to appropriate generator
            artifact_type = artifact["artifact_type"]
            result_content = ""
            result_data: dict = {}

            if artifact_type == "summary":
                result_data = await generate_summary(state)
                result_content = result_data.get("summary", "")

            elif artifact_type == "quiz":
                result_data = await generate_quiz(state)
                import json
                result_content = json.dumps(result_data.get("quiz", {}), indent=2)

            elif artifact_type == "flashcard":
                result_data = await generate_flashcards(state)
                import json
                result_content = json.dumps(result_data.get("flashcards", []), indent=2)

                # Save flashcards to flashcards table
                from src.infra.nexus_data_persist import flashcards_repo
                for card in result_data.get("flashcards", []):
                    await flashcards_repo.create(
                        data={
                            "notebook_id": notebook_id,
                            "source_id": None,
                            "front": card.get("front", ""),
                            "back": card.get("back", ""),
                            "tags": card.get("tags", []),
                        },
                        tenant_id=tenant_id,
                    )

            elif artifact_type in ("audio", "podcast"):
                # Step 1: Generate script
                script_data = await generate_podcast_script(state)
                state.outputs["script_generator"] = script_data

                # Step 2: Synthesize audio
                audio_data = await synthesize_dialogue(state)

                # Save audio file
                import os
                storage_path = f"storage/artifacts/{tenant_id}/{artifact_id}.mp3"
                os.makedirs(os.path.dirname(storage_path), exist_ok=True)
                with open(storage_path, "wb") as f:
                    f.write(audio_data.get("audio_data", b""))

                result_content = script_data.get("script", "")
                result_data = {
                    "storage_url": storage_path,
                    "duration_seconds": audio_data.get("duration_seconds", 0),
                    "segment_count": audio_data.get("segment_count", 0),
                }

            elif artifact_type == "report":
                result_data = await generate_summary(state)
                result_content = result_data.get("summary", "")

            else:
                result_data = await generate_summary(state)
                result_content = result_data.get("summary", "")

            # 5. Update artifact with results
            update_data = {
                "status": "completed",
                "content": result_content,
                "completed_at": datetime.now(timezone.utc),
            }
            if result_data.get("storage_url"):
                update_data["storage_url"] = result_data["storage_url"]
            if result_data.get("duration_seconds"):
                update_data["duration_seconds"] = result_data["duration_seconds"]

            await artifacts_repo.update(artifact_id, update_data, tenant_id)
            logger.info(f"Artifact generated: {artifact_id} ({artifact_type})")

            return {"status": "completed", "artifact_id": artifact_id, "type": artifact_type}

        except Exception as e:
            await artifacts_repo.update(
                artifact_id,
                {"status": "error", "content": f"Generation failed: {str(e)[:500]}"},
                tenant_id,
            )
            logger.error(f"Artifact generation failed: {artifact_id}", error=str(e))
            raise

        finally:
            metrics.active_generations.labels(artifact_type=artifact["artifact_type"]).dec()

    return run_async(_generate())


@celery_app.task(
    name="nexus.tasks.batch_embed",
    bind=True,
    max_retries=2,
)
def batch_embed(self, source_ids: list[str], tenant_id: str) -> dict:
    """Batch embedding job for multiple sources."""
    logger.info(f"Batch embedding: {len(source_ids)} sources")

    async def _batch():
        from src.agents.nexus_agent_embed import vectorize_source
        from src.agents.nexus_agent_orchestrator import ChainState
        from src.infra.nexus_data_persist import sources_repo

        results = {"success": 0, "failed": 0, "total_chunks": 0}

        for source_id in source_ids:
            try:
                source = await sources_repo.get_by_id(source_id, tenant_id)
                if source and source.get("full_text"):
                    state = ChainState(
                        tenant_id=tenant_id,
                        user_id="system",
                        inputs={
                            "source_id": source_id,
                            "source_content": source["full_text"],
                        },
                    )
                    result = await vectorize_source(state)
                    results["success"] += 1
                    results["total_chunks"] += result.get("chunks", 0)
            except Exception as e:
                results["failed"] += 1
                logger.error(f"Embedding failed for {source_id}: {e}")

        return results

    return run_async(_batch())


@celery_app.task(name="nexus.tasks.generate_flashcards_scheduled")
def generate_flashcards_scheduled(notebook_id: str, tenant_id: str, user_id: str) -> dict:
    """Scheduled flashcard generation from new sources."""

    async def _gen():
        from src.agents.nexus_agent_content import generate_flashcards
        from src.agents.nexus_agent_orchestrator import ChainState
        from src.infra.nexus_data_persist import get_session
        from sqlalchemy import text

        # Get source content
        async with get_session(tenant_id) as session:
            result = await session.execute(
                text("""
                    SELECT s.full_text FROM sources s
                    JOIN notebook_sources ns ON s.id = ns.source_id
                    WHERE ns.notebook_id = :nid AND s.deleted_at IS NULL AND s.full_text IS NOT NULL
                    ORDER BY s.created_at DESC LIMIT 3
                """),
                {"nid": notebook_id},
            )
            rows = result.mappings().all()

        source_content = "\n\n".join(row["full_text"][:10000] for row in rows)

        state = ChainState(
            tenant_id=tenant_id,
            user_id=user_id,
            inputs={"source_content": source_content, "num_cards": 10},
        )
        return await generate_flashcards(state)

    return run_async(_gen())


# ── Beat Schedule (Periodic Tasks) ───────────────────────────

celery_app.conf.beat_schedule = {
    "health-check": {
        "task": "nexus.tasks.health_check",
        "schedule": 300.0,  # Every 5 minutes
    },
}


@celery_app.task(name="nexus.tasks.health_check")
def health_check() -> dict:
    """Worker health check heartbeat."""
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}
