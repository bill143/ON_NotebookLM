"""
002_phase2_phase3_tables — Add research, export, collaboration, and studio tables.

Revision ID: 002_phase2_phase3
Revises: 001_initial
Create Date: 2026-03-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "002_phase2_phase3"
down_revision = None  # Chain to 001_initial if exists
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Research Sessions ────────────────────────────────
    op.create_table(
        "research_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notebook_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(500), nullable=False, server_default="Untitled Research"),
        sa.Column("turn_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("checkpoint_data", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_research_sessions_notebook", "research_sessions", ["notebook_id"])
    op.create_index("idx_research_sessions_user", "research_sessions", ["user_id"])

    # ── Research Turns ───────────────────────────────────
    op.create_table(
        "research_turns",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("research_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_number", sa.Integer, nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("citations", JSONB, nullable=True),
        sa.Column("follow_up_questions", JSONB, nullable=True),
        sa.Column("model_used", sa.String(100), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("token_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_research_turns_session", "research_turns", ["session_id", "turn_number"])

    # ── Export Jobs ───────────────────────────────────────
    op.create_table(
        "export_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_id", UUID(as_uuid=True), nullable=True),
        sa.Column("notebook_id", UUID(as_uuid=True), nullable=True),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("storage_url", sa.Text, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Studio Queue Jobs ────────────────────────────────
    op.create_table(
        "studio_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notebook_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("artifact_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("progress_pct", sa.Float, nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(200), nullable=True),
        sa.Column("generation_config", JSONB, nullable=True),
        sa.Column("result_data", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_studio_jobs_notebook", "studio_jobs", ["notebook_id"])
    op.create_index("idx_studio_jobs_status", "studio_jobs", ["status"])

    # ── Collaboration Presence ───────────────────────────
    op.create_table(
        "collab_presence",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notebook_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("cursor_position", JSONB, nullable=True),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_collab_presence_notebook", "collab_presence", ["notebook_id"])

    # ── Flashcards (FSRS) ────────────────────────────────
    op.create_table(
        "flashcards",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("notebook_id", UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("front", sa.Text, nullable=False),
        sa.Column("back", sa.Text, nullable=False),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("state", sa.Integer, nullable=False, server_default="0"),
        sa.Column("difficulty", sa.Float, nullable=False, server_default="0"),
        sa.Column("stability", sa.Float, nullable=False, server_default="0"),
        sa.Column("due_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_review", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_flashcards_due", "flashcards", ["user_id", "due_at"])
    op.create_index("idx_flashcards_notebook", "flashcards", ["notebook_id"])

    # ── Video/Slide Artifacts Metadata ───────────────────
    op.create_table(
        "media_artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("artifact_id", UUID(as_uuid=True), nullable=False),
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("slide_count", sa.Integer, nullable=True),
        sa.Column("resolution", sa.String(20), nullable=True),
        sa.Column("file_format", sa.String(10), nullable=True),
        sa.Column("storage_url", sa.Text, nullable=True),
        sa.Column("thumbnail_url", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("media_artifacts")
    op.drop_table("flashcards")
    op.drop_table("collab_presence")
    op.drop_table("studio_jobs")
    op.drop_table("export_jobs")
    op.drop_table("research_turns")
    op.drop_table("research_sessions")
