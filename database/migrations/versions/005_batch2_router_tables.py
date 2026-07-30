"""
005_batch2_router_tables — Add tables for brain, plugins, local-sync, prompts, admin routers.

Revision ID: 005_batch2_routers
Revises: 004_hnsw_index_migration
Create Date: 2026-04-15
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "005_batch2_routers"
down_revision = "004_hnsw_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 001_initial.sql also creates some of these (e.g. audit_logs,
    # prompt_versions) — skip tables that already exist so the chain
    # works on fresh databases.
    inspector = sa.inspect(op.get_bind())
    existing = set(inspector.get_table_names())

    if "backups" not in existing:
        _create_backups()
    if "audit_logs" not in existing:
        _create_audit_logs()
    if "plugin_registry" not in existing:
        _create_plugin_registry()
    if "sync_queue" not in existing:
        _create_sync_queue()
    if "prompt_versions" not in existing:
        _create_prompt_versions()
    if "prompt_test_cases" not in existing:
        _create_prompt_test_cases()


def _create_backups() -> None:
    op.create_table(
        "backups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="in_progress"),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("size_bytes", sa.BigInteger, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
    )


def _create_audit_logs() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("details", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_audit_logs_tenant", "audit_logs", ["tenant_id"])
    op.create_index("idx_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("idx_audit_logs_created", "audit_logs", ["created_at"])


def _create_plugin_registry() -> None:
    op.create_table(
        "plugin_registry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("author", sa.String(255), nullable=True),
        sa.Column("manifest", JSONB, nullable=True),
        sa.Column("permissions", JSONB, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("config", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("installed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_plugin_registry_name", "plugin_registry", ["tenant_id", "name"], unique=True)


def _create_sync_queue() -> None:
    op.create_table(
        "sync_queue",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(50), nullable=False),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("record_id", sa.String(255), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_sync_queue_tenant_status", "sync_queue", ["tenant_id", "status"])


def _create_prompt_versions() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("variables", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model_target", sa.String(255), nullable=True),
        sa.Column("max_tokens", sa.Integer, nullable=True),
        sa.Column("temperature", sa.Float, nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column("parent_version_id", UUID(as_uuid=True), nullable=True),
        sa.Column("changelog", sa.Text, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("avg_latency_ms", sa.Float, nullable=True),
        sa.Column("avg_token_cost", sa.Float, nullable=True),
        sa.Column("quality_score", sa.Float, nullable=True),
    )
    op.create_index("idx_prompt_versions_ns_name", "prompt_versions", ["namespace", "name"])
    op.create_index("idx_prompt_versions_status", "prompt_versions", ["status"])


def _create_prompt_test_cases() -> None:
    op.create_table(
        "prompt_test_cases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("prompt_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("input_variables", JSONB, nullable=False),
        sa.Column("expected_output_criteria", JSONB, nullable=False),
        sa.Column("pass_threshold", sa.Float, nullable=False, server_default="0.8"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_result", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("prompt_test_cases")
    op.drop_table("prompt_versions")
    op.drop_table("sync_queue")
    op.drop_table("plugin_registry")
    op.drop_table("audit_logs")
    op.drop_table("backups")
