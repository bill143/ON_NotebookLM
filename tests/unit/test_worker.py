"""Unit tests for Celery worker — task dispatch, routing, config."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.worker import (
    celery_app,
    generate_artifact,
    health_check,
    on_worker_init,
    on_worker_shutdown,
    run_async,
)


class TestCeleryConfig:
    def test_broker_configured(self):
        assert celery_app.conf.broker_url is not None

    def test_task_serializer_json(self):
        assert celery_app.conf.task_serializer == "json"

    def test_task_time_limit(self):
        assert celery_app.conf.task_time_limit == 600

    def test_soft_time_limit(self):
        assert celery_app.conf.task_soft_time_limit == 540

    def test_late_ack_enabled(self):
        assert celery_app.conf.task_acks_late is True

    def test_reject_on_worker_lost(self):
        assert celery_app.conf.task_reject_on_worker_lost is True

    def test_result_expires(self):
        assert celery_app.conf.result_expires == 3600

    def test_prefetch_multiplier(self):
        assert celery_app.conf.worker_prefetch_multiplier == 1

    def test_max_tasks_per_child(self):
        assert celery_app.conf.worker_max_tasks_per_child == 100


class TestTaskRouting:
    def test_process_source_queue(self):
        routes = celery_app.conf.task_routes
        assert routes["nexus.tasks.process_source"]["queue"] == "source_processing"

    def test_generate_artifact_queue(self):
        routes = celery_app.conf.task_routes
        assert routes["nexus.tasks.generate_artifact"]["queue"] == "artifact_generation"

    def test_batch_embed_queue(self):
        routes = celery_app.conf.task_routes
        assert routes["nexus.tasks.batch_embed"]["queue"] == "embedding"

    def test_default_queue(self):
        assert celery_app.conf.task_default_queue == "default"


class TestBeatSchedule:
    def test_health_check_scheduled(self):
        schedule = celery_app.conf.beat_schedule
        assert "health-check" in schedule
        assert schedule["health-check"]["task"] == "nexus.tasks.health_check"
        assert schedule["health-check"]["schedule"] == 300.0


class TestRunAsync:
    def test_run_async_executes_coroutine(self):
        async def sample():
            return 42

        result = run_async(sample())
        assert result == 42

    def test_run_async_propagates_exceptions(self):
        async def failing():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            run_async(failing())

    def test_run_async_recreates_loop_when_closed(self):
        async def sample():
            return 7

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.close()
        assert run_async(sample()) == 7


class TestHealthCheckTask:
    def test_health_check_returns_status(self):
        out = health_check.run()
        assert out["status"] == "healthy"
        assert "timestamp" in out


class TestProcessSourceTask:
    def test_process_source_not_ready_skips_embed(self):
        proc = AsyncMock(return_value={"status": "pending"})
        with patch(
            "src.core.nexus_source_ingest.source_processor.process_source",
            proc,
        ):
            from src.worker import process_source

            out = process_source.run("s1", "t1")
        assert out["status"] == "pending"
        proc.assert_awaited()

    def test_process_source_ready_without_full_text(self):
        proc = AsyncMock(return_value={"status": "ready"})
        with (
            patch(
                "src.core.nexus_source_ingest.source_processor.process_source",
                proc,
            ),
            patch(
                "src.infra.nexus_data_persist.sources_repo.get_by_id",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            from src.worker import process_source

            out = process_source.run("s2", "t1")
        assert out["status"] == "ready"
        assert "chunks" not in out

    def test_process_source_ready_vectorizes(self):
        proc = AsyncMock(return_value={"status": "ready"})
        src = {"full_text": "hello world content"}
        with (
            patch(
                "src.core.nexus_source_ingest.source_processor.process_source",
                proc,
            ),
            patch(
                "src.infra.nexus_data_persist.sources_repo.get_by_id",
                new_callable=AsyncMock,
                return_value=src,
            ),
            patch(
                "src.agents.nexus_agent_embed.vectorize_source",
                new_callable=AsyncMock,
                return_value={"chunks": 4},
            ),
        ):
            from src.worker import process_source

            out = process_source.run("s3", "t1")
        assert out["status"] == "ready"
        assert out["chunks"] == 4


class TestBatchEmbedTask:
    def test_batch_embed_counts_success_and_failure(self):
        async def get_src(_sid, _tid):
            if _sid == "ok":
                return {"full_text": "text"}
            if _sid == "bad":
                raise RuntimeError("db")
            return None

        with (
            patch(
                "src.infra.nexus_data_persist.sources_repo.get_by_id",
                new_callable=AsyncMock,
                side_effect=get_src,
            ),
            patch(
                "src.agents.nexus_agent_embed.vectorize_source",
                new_callable=AsyncMock,
                return_value={"chunks": 2},
            ),
        ):
            from src.worker import batch_embed

            out = batch_embed.run(["ok", "skip", "bad"], "t1")
        assert out["success"] == 1
        assert out["failed"] == 1
        assert out["total_chunks"] == 2


class TestGenerateFlashcardsScheduled:
    def test_scheduled_flashcards_runs_pipeline(self):
        @asynccontextmanager
        async def fake_session(_tenant=None):
            mock_s = AsyncMock()
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = [{"full_text": "abc" * 50}]
            mock_s.execute = AsyncMock(return_value=mock_result)
            yield mock_s

        with (
            patch("src.infra.nexus_data_persist.get_session", fake_session),
            patch(
                "src.agents.nexus_agent_content.generate_flashcards",
                new_callable=AsyncMock,
                return_value={"cards": [{"q": "1"}]},
            ),
        ):
            from src.worker import generate_flashcards_scheduled

            out = generate_flashcards_scheduled.run("nb1", "t1", "u1")
        assert "cards" in out


class TestWorkerInitHook:
    def test_on_worker_init_sets_up_loop_and_db(self):
        mock_loop = MagicMock()
        mock_loop.run_until_complete = MagicMock()
        mock_init = AsyncMock()
        with (
            patch("src.worker.asyncio.new_event_loop", return_value=mock_loop),
            patch("src.worker.asyncio.set_event_loop"),
            patch("src.infra.nexus_data_persist.init_database", mock_init),
        ):
            on_worker_init()
        mock_loop.run_until_complete.assert_called_once()


class TestWorkerShutdownHook:
    def test_on_worker_shutdown_closes_db(self):
        mock_loop = MagicMock()
        mock_loop.run_until_complete = MagicMock()
        with (
            patch("src.worker.asyncio.get_event_loop", return_value=mock_loop),
            patch("src.infra.nexus_data_persist.close_database", new_callable=AsyncMock),
        ):
            on_worker_shutdown()
        mock_loop.run_until_complete.assert_called_once()


class TestGenerateArtifactTask:
    def test_generate_artifact_missing_record_raises(self):
        with patch(
            "src.infra.nexus_data_persist.artifacts_repo.get_by_id",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="not found"):
                generate_artifact.run("missing", "t1")

    def test_generate_artifact_no_source_content(self):
        artifact = {
            "id": "a1",
            "notebook_id": "nb1",
            "artifact_type": "summary",
            "user_id": "u1",
            "generation_config": {},
        }

        @asynccontextmanager
        async def empty_session(_tenant=None):
            mock_s = AsyncMock()
            mock_result = MagicMock()
            mock_result.mappings.return_value.all.return_value = []
            mock_s.execute = AsyncMock(return_value=mock_result)
            yield mock_s

        mock_metrics = MagicMock()
        mock_metrics.labels.return_value = MagicMock(inc=MagicMock())

        with (
            patch(
                "src.infra.nexus_data_persist.artifacts_repo.get_by_id",
                new_callable=AsyncMock,
                return_value=artifact,
            ),
            patch(
                "src.infra.nexus_data_persist.artifacts_repo.update",
                new_callable=AsyncMock,
            ),
            patch("src.infra.nexus_data_persist.get_session", empty_session),
            patch(
                "src.infra.nexus_obs_tracing.metrics.active_generations",
                mock_metrics,
            ),
        ):
            out = generate_artifact.run("a1", "t1")
        assert out["status"] == "error"
        assert out["reason"] == "No source content"
