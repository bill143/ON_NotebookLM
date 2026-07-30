"""Add sessions.checkpoint_data for research session persistence.

nexus_research_grounding stores research state (turns, citations, total_tokens)
in this column; without it every /api/v1/research/sessions call fails with
UndefinedColumnError.

Revision ID: 007_sessions_checkpoint_data
Revises: 006_vault_foundation
"""

from alembic import op

revision = "007_sessions_checkpoint_data"
down_revision = "006_vault_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS checkpoint_data JSONB DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS checkpoint_data")
