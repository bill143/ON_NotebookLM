"""Add argon2_salt column to ai_credentials for Argon2id KDF.

Revision ID: 003_argon2_salt
Revises: 002_phase2_phase3_tables
Create Date: 2026-04-05
"""

from alembic import op
import sqlalchemy as sa

revision = "003_argon2_salt"
down_revision = "002_phase2_phase3_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_credentials",
        sa.Column("argon2_salt", sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_credentials", "argon2_salt")
