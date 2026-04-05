"""Unit tests for nexus_data_persist — BaseRepository, session management."""

from __future__ import annotations

from src.infra.nexus_data_persist import (
    ArtifactRepository,
    BaseRepository,
    NotebookRepository,
    SessionRepository,
    SourceRepository,
    UsageRepository,
    artifacts_repo,
    audit_repo,
    flashcards_repo,
    notebooks_repo,
    notes_repo,
    sessions_repo,
    sources_repo,
    usage_repo,
)


class TestBaseRepository:
    def test_init_sets_table_name(self):
        repo = BaseRepository("my_table")
        assert repo.table_name == "my_table"

    def test_notes_repo_table(self):
        assert notes_repo.table_name == "notes"

    def test_flashcards_repo_table(self):
        assert flashcards_repo.table_name == "flashcards"

    def test_audit_repo_table(self):
        assert audit_repo.table_name == "audit_logs"


class TestSpecializedRepositories:
    def test_notebook_repo_table(self):
        assert notebooks_repo.table_name == "notebooks"
        assert isinstance(notebooks_repo, NotebookRepository)

    def test_source_repo_table(self):
        assert sources_repo.table_name == "sources"
        assert isinstance(sources_repo, SourceRepository)

    def test_artifact_repo_table(self):
        assert artifacts_repo.table_name == "artifacts"
        assert isinstance(artifacts_repo, ArtifactRepository)

    def test_session_repo_table(self):
        assert sessions_repo.table_name == "sessions"
        assert isinstance(sessions_repo, SessionRepository)

    def test_usage_repo_table(self):
        assert usage_repo.table_name == "usage_records"
        assert isinstance(usage_repo, UsageRepository)


class TestRepositoryMethods:
    """Test that repository public methods exist and have correct signatures."""

    def test_create_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.create)

    def test_get_by_id_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.get_by_id)

    def test_list_all_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.list_all)

    def test_update_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.update)

    def test_soft_delete_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.soft_delete)

    def test_hard_delete_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.hard_delete)

    def test_count_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.count)

    def test_exists_method_exists(self):
        repo = BaseRepository("test")
        assert callable(repo.exists)


class TestSourceRepositoryMethods:
    def test_vector_search_exists(self):
        assert callable(sources_repo.vector_search)

    def test_text_search_exists(self):
        assert callable(sources_repo.text_search)


class TestNotebookRepositoryMethods:
    def test_get_with_sources_exists(self):
        assert callable(notebooks_repo.get_with_sources)

    def test_cascade_delete_preview_exists(self):
        assert callable(notebooks_repo.cascade_delete_preview)
