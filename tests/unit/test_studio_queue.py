"""
Unit Tests — Nexus Studio Queue (Artifact Generation Engine)
"""

from __future__ import annotations

import time

from src.core.nexus_studio_queue import (
    ARTIFACT_PIPELINES,
    STEP_REGISTRY,
    ArtifactType,
    GenerationJob,
    GenerationStep,
    JobStatus,
    StepExecutors,
    StudioQueue,
)

# ── Module Importability ────────────────────────────────────


class TestModuleImport:
    def test_studio_queue_module_importable(self):
        import src.core.nexus_studio_queue as mod

        assert hasattr(mod, "StudioQueue")
        assert hasattr(mod, "studio_queue")

    def test_all_public_classes_importable(self):
        from src.core.nexus_studio_queue import (
            ArtifactType,
            GenerationJob,
            GenerationStep,
            JobStatus,
            StudioQueue,
        )

        assert all(
            cls is not None
            for cls in [
                ArtifactType,
                GenerationJob,
                GenerationStep,
                JobStatus,
                StepExecutors,
                StudioQueue,
            ]
        )


# ── ArtifactType Enum ───────────────────────────────────────


class TestArtifactType:
    def test_artifact_types_defined(self):
        expected = {
            "summary",
            "podcast",
            "quiz",
            "flashcard",
            "study_guide",
            "timeline",
            "faq",
            "briefing",
            "slide_deck",
            "video",
            "mind_map",
            "infographic",
        }
        actual = {member.value for member in ArtifactType}
        assert actual == expected

    def test_artifact_type_count(self):
        assert len(ArtifactType) == 12

    def test_artifact_type_is_string_enum(self):
        assert isinstance(ArtifactType.PODCAST, str)
        assert ArtifactType.PODCAST == "podcast"


# ── JobStatus Enum ──────────────────────────────────────────


class TestJobStatus:
    def test_job_status_values(self):
        assert JobStatus.QUEUED == "queued"
        assert JobStatus.RUNNING == "running"
        assert JobStatus.COMPLETE == "complete"
        assert JobStatus.FAILED == "failed"
        assert JobStatus.CANCELLED == "cancelled"
        assert JobStatus.PARTIAL == "partial"

    def test_job_status_count(self):
        assert len(JobStatus) == 6


# ── GenerationStep ──────────────────────────────────────────


class TestGenerationStep:
    def test_generation_step_defaults(self):
        step = GenerationStep(step_id="1_gather", name="gather_sources")
        assert step.status == JobStatus.QUEUED
        assert step.progress_pct == 0.0
        assert step.output is None
        assert step.error is None
        assert step.started_at is None
        assert step.completed_at is None
        assert step.retries == 0
        assert step.max_retries == 2

    def test_generation_step_custom_retries(self):
        step = GenerationStep(step_id="2_gen", name="generate_content", max_retries=5)
        assert step.max_retries == 5

    def test_generation_step_status_transitions(self):
        step = GenerationStep(step_id="s1", name="step")
        step.status = JobStatus.RUNNING
        step.started_at = time.time()
        assert step.status == JobStatus.RUNNING
        step.status = JobStatus.COMPLETE
        step.completed_at = time.time()
        assert step.status == JobStatus.COMPLETE


# ── GenerationJob ───────────────────────────────────────────


class TestGenerationJob:
    def _make_job(self, **overrides):
        defaults = {
            "job_id": "job-001",
            "artifact_id": "art-001",
            "artifact_type": ArtifactType.SUMMARY,
            "notebook_id": "nb-001",
            "tenant_id": "t-1",
            "user_id": "u-1",
        }
        defaults.update(overrides)
        return GenerationJob(**defaults)

    def test_generation_job_defaults(self):
        job = self._make_job()
        assert job.status == JobStatus.QUEUED
        assert job.steps == []
        assert job.config == {}
        assert job.result is None
        assert job.error is None
        assert job.progress_pct == 0.0

    def test_generation_job_to_dict(self):
        job = self._make_job()
        d = job.to_dict()
        assert d["job_id"] == "job-001"
        assert d["artifact_type"] == "summary"
        assert d["status"] == "queued"
        assert isinstance(d["steps"], list)

    def test_generation_job_to_dict_with_steps(self):
        job = self._make_job()
        job.steps = [
            GenerationStep(step_id="1_gather", name="gather_sources"),
            GenerationStep(step_id="2_gen", name="generate_content"),
        ]
        d = job.to_dict()
        assert len(d["steps"]) == 2
        assert d["steps"][0]["name"] == "gather_sources"
        assert d["steps"][1]["status"] == "queued"

    def test_generation_job_config(self):
        job = self._make_job(config={"style": "conversational"})
        assert job.config["style"] == "conversational"


# ── Pipeline Definitions ────────────────────────────────────


class TestPipelineDefinitions:
    def test_pipeline_step_definitions(self):
        """Every ArtifactType has a pipeline entry."""
        for art_type in ArtifactType:
            assert art_type in ARTIFACT_PIPELINES, f"Missing pipeline for {art_type}"

    def test_all_pipelines_start_with_gather(self):
        for art_type, steps in ARTIFACT_PIPELINES.items():
            assert steps[0] == "gather_sources", (
                f"{art_type} pipeline should start with gather_sources"
            )

    def test_podcast_pipeline_has_audio_steps(self):
        pipeline = ARTIFACT_PIPELINES[ArtifactType.PODCAST]
        assert "generate_script" in pipeline
        assert "synthesize_audio_segments" in pipeline
        assert "assemble_audio" in pipeline

    def test_quiz_pipeline_has_questions(self):
        pipeline = ARTIFACT_PIPELINES[ArtifactType.QUIZ]
        assert "generate_questions" in pipeline
        assert "validate_answers" in pipeline

    def test_flashcard_pipeline_has_concepts(self):
        pipeline = ARTIFACT_PIPELINES[ArtifactType.FLASHCARD]
        assert "extract_key_concepts" in pipeline
        assert "generate_cards" in pipeline

    def test_pipeline_lengths_vary(self):
        summary_len = len(ARTIFACT_PIPELINES[ArtifactType.SUMMARY])
        podcast_len = len(ARTIFACT_PIPELINES[ArtifactType.PODCAST])
        assert summary_len < podcast_len


# ── Step Registry ───────────────────────────────────────────


class TestStepRegistry:
    def test_step_registry_covers_all_pipeline_steps(self):
        """Every step name used in any pipeline is in STEP_REGISTRY."""
        all_step_names = set()
        for steps in ARTIFACT_PIPELINES.values():
            all_step_names.update(steps)

        for name in all_step_names:
            assert name in STEP_REGISTRY, f"Step '{name}' missing from STEP_REGISTRY"

    def test_step_registry_values_are_callable(self):
        for name, fn in STEP_REGISTRY.items():
            assert callable(fn), f"STEP_REGISTRY['{name}'] is not callable"

    def test_step_registry_count(self):
        assert len(STEP_REGISTRY) >= 12


# ── StudioQueue ─────────────────────────────────────────────


class TestStudioQueue:
    def test_studio_queue_init(self):
        sq = StudioQueue(max_concurrent=5)
        assert sq._jobs == {}
        assert sq.stats == {}

    def test_studio_queue_get_job_missing_returns_none(self):
        sq = StudioQueue()
        assert sq.get_job("nonexistent") is None

    def test_studio_queue_get_jobs_for_artifact_empty(self):
        sq = StudioQueue()
        assert sq.get_jobs_for_artifact("art-x") == []
