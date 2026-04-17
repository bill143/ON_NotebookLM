"""
006_vault_foundation — Document Vault tables for construction document management.

Adds 9 tables: vault_documents, rfi_records, submittal_records, invoice_records,
change_order_records, coi_records, permit_records, vault_workflow_log, vault_deadline_reminders.

All tables are tenant-scoped with RLS policies.
Soft-delete applied to vault_documents only.

Revision ID: 006_vault_foundation
Revises: 005_batch2_routers
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "006_vault_foundation"
down_revision = "005_batch2_routers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── vault_documents ────────────────────────────────────────
    op.create_table(
        "vault_documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by", UUID(as_uuid=True), nullable=False),
        sa.Column("original_filename", sa.Text, nullable=False),
        sa.Column("stored_filename", sa.Text, nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_size", sa.BigInteger, nullable=True),
        sa.Column("mime_type", sa.Text, nullable=True),
        sa.Column("document_type", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("librarian_decision", JSONB, nullable=True),
        sa.Column("processing_status", sa.Text, nullable=True, server_default="PENDING"),
        sa.Column("requires_human_review", sa.Boolean, nullable=True, server_default=sa.text("false")),
        sa.Column("human_reviewed_by", UUID(as_uuid=True), nullable=True),
        sa.Column("human_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("human_override_type", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["human_reviewed_by"], ["users.id"]),
    )
    op.create_index("idx_vault_documents_tenant", "vault_documents", ["tenant_id"])
    op.create_index("idx_vault_documents_project", "vault_documents", ["project_id"])
    op.create_index("idx_vault_documents_type", "vault_documents", ["document_type"])
    op.create_index("idx_vault_documents_status", "vault_documents", ["processing_status"])
    op.create_index("idx_vault_documents_created", "vault_documents", ["created_at"])

    # ── rfi_records ────────────────────────────────────────────
    op.create_table(
        "rfi_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rfi_number", sa.Text, nullable=False),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("discipline", sa.Text, nullable=True),
        sa.Column("spec_section", sa.Text, nullable=True),
        sa.Column("submitted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_to", UUID(as_uuid=True), nullable=True),
        sa.Column("date_submitted", sa.Date, nullable=True),
        sa.Column("date_required", sa.Date, nullable=True),
        sa.Column("status", sa.Text, nullable=True, server_default="OPEN"),
        sa.Column("is_potential_scope_change", sa.Boolean, nullable=True, server_default=sa.text("false")),
        sa.Column("scope_change_notes", sa.Text, nullable=True),
        sa.Column("response_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("response_date", sa.Date, nullable=True),
        sa.Column("distribution_list", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_to"], ["users.id"]),
        sa.ForeignKeyConstraint(["response_document_id"], ["vault_documents.id"]),
        sa.UniqueConstraint("tenant_id", "project_id", "rfi_number", name="uq_rfi_tenant_project_number"),
    )
    op.create_index("idx_rfi_records_tenant", "rfi_records", ["tenant_id"])
    op.create_index("idx_rfi_records_project", "rfi_records", ["project_id"])

    # ── submittal_records ──────────────────────────────────────
    op.create_table(
        "submittal_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("submittal_number", sa.Text, nullable=False),
        sa.Column("spec_section", sa.Text, nullable=True),
        sa.Column("trade", sa.Text, nullable=True),
        sa.Column("revision", sa.Integer, nullable=True, server_default="0"),
        sa.Column("submitted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("assigned_reviewer", UUID(as_uuid=True), nullable=True),
        sa.Column("date_submitted", sa.Date, nullable=True),
        sa.Column("date_required", sa.Date, nullable=True),
        sa.Column("status", sa.Text, nullable=True, server_default="SUBMITTED"),
        sa.Column("review_notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["assigned_reviewer"], ["users.id"]),
    )
    op.create_index("idx_submittal_records_tenant", "submittal_records", ["tenant_id"])
    op.create_index("idx_submittal_records_project", "submittal_records", ["project_id"])

    # ── invoice_records ────────────────────────────────────────
    op.create_table(
        "invoice_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.Text, nullable=False),
        sa.Column("vendor_name", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("period_start", sa.Date, nullable=True),
        sa.Column("period_end", sa.Date, nullable=True),
        sa.Column("date_received", sa.Date, nullable=True),
        sa.Column("date_due", sa.Date, nullable=True),
        sa.Column("status", sa.Text, nullable=True, server_default="RECEIVED"),
        sa.Column("date_paid", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
    )
    op.create_index("idx_invoice_records_tenant", "invoice_records", ["tenant_id"])
    op.create_index("idx_invoice_records_project", "invoice_records", ["project_id"])

    # ── change_order_records ───────────────────────────────────
    op.create_table(
        "change_order_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("co_number", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("reason_code", sa.Text, nullable=True),
        sa.Column("is_owner_directed", sa.Boolean, nullable=True, server_default=sa.text("false")),
        sa.Column("is_potential", sa.Boolean, nullable=True, server_default=sa.text("false")),
        sa.Column("status", sa.Text, nullable=True, server_default="PENDING"),
        sa.Column("submitted_by", UUID(as_uuid=True), nullable=True),
        sa.Column("date_submitted", sa.Date, nullable=True),
        sa.Column("date_approved", sa.Date, nullable=True),
        sa.Column("approved_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
    )
    op.create_index("idx_change_order_records_tenant", "change_order_records", ["tenant_id"])
    op.create_index("idx_change_order_records_project", "change_order_records", ["project_id"])

    # ── coi_records ────────────────────────────────────────────
    op.create_table(
        "coi_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("insured_name", sa.Text, nullable=False),
        sa.Column("policy_number", sa.Text, nullable=True),
        sa.Column("insurer_name", sa.Text, nullable=True),
        sa.Column("coverage_types", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("effective_date", sa.Date, nullable=True),
        sa.Column("expiration_date", sa.Date, nullable=False),
        sa.Column("meets_requirements", sa.Boolean, nullable=True),
        sa.Column("deficiency_notes", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=True, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
    )
    op.create_index("idx_coi_records_tenant", "coi_records", ["tenant_id"])
    op.create_index("idx_coi_records_project", "coi_records", ["project_id"])

    # ── permit_records ─────────────────────────────────────────
    op.create_table(
        "permit_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("permit_number", sa.Text, nullable=False),
        sa.Column("permit_type", sa.Text, nullable=True),
        sa.Column("issuing_authority", sa.Text, nullable=True),
        sa.Column("issue_date", sa.Date, nullable=True),
        sa.Column("expiration_date", sa.Date, nullable=True),
        sa.Column("status", sa.Text, nullable=True, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
    )
    op.create_index("idx_permit_records_tenant", "permit_records", ["tenant_id"])
    op.create_index("idx_permit_records_project", "permit_records", ["project_id"])

    # ── vault_workflow_log ─────────────────────────────────────
    op.create_table(
        "vault_workflow_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("vault_document_id", UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_type", sa.Text, nullable=True),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("details", JSONB, nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("performed_by", sa.Text, nullable=True, server_default="LIBRARIAN_AI"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["vault_document_id"], ["vault_documents.id"]),
    )
    op.create_index("idx_vault_workflow_log_tenant", "vault_workflow_log", ["tenant_id"])
    op.create_index("idx_vault_workflow_log_document", "vault_workflow_log", ["vault_document_id"])

    # ── vault_deadline_reminders ───────────────────────────────
    op.create_table(
        "vault_deadline_reminders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("related_record_id", UUID(as_uuid=True), nullable=False),
        sa.Column("related_record_type", sa.Text, nullable=False),
        sa.Column("reminder_type", sa.Text, nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recipient_user_ids", JSONB, nullable=True, server_default=sa.text("'[]'::jsonb")),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=True, server_default="PENDING"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_vault_deadline_reminders_tenant", "vault_deadline_reminders", ["tenant_id"])
    op.create_index("idx_vault_deadline_reminders_scheduled", "vault_deadline_reminders", ["scheduled_for"])

    # ── RLS Policies ───────────────────────────────────────────
    rls_tables = [
        "vault_documents",
        "rfi_records",
        "submittal_records",
        "invoice_records",
        "change_order_records",
        "coi_records",
        "permit_records",
        "vault_workflow_log",
        "vault_deadline_reminders",
    ]
    for table in rls_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"USING (tenant_id = current_setting('app.tenant_id')::uuid)"
        )

    # ── updated_at Triggers ────────────────────────────────────
    # Reuses the existing update_updated_at() function from 001_initial.sql
    updated_at_tables = [
        "vault_documents",
        "rfi_records",
        "submittal_records",
        "invoice_records",
        "change_order_records",
        "coi_records",
        "permit_records",
    ]
    for table in updated_at_tables:
        op.execute(
            f"CREATE TRIGGER tr_{table}_updated "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION update_updated_at()"
        )


def downgrade() -> None:
    # Drop in reverse dependency order
    tables = [
        "vault_deadline_reminders",
        "vault_workflow_log",
        "permit_records",
        "coi_records",
        "change_order_records",
        "invoice_records",
        "submittal_records",
        "rfi_records",
        "vault_documents",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
