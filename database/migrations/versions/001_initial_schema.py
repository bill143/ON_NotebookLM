"""Initial schema — applies 001_initial.sql

Revision ID: 001_initial
Revises: None
Create Date: 2026-03-29
"""
from typing import Sequence, Union
from pathlib import Path

from alembic import op

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Path to the raw SQL file
SQL_FILE = Path(__file__).parent.parent.parent / "schema" / "001_initial.sql"


def _split_statements(sql: str) -> list[str]:
    """Split SQL into statements: drop full-line comments, then split on
    semicolons outside $$-quoted bodies.

    The previous "split on ';' and skip fragments starting with '--'" approach
    silently dropped every statement that followed a comment banner (which is
    nearly all of them) and broke plpgsql functions — fresh databases ended up
    with no tables at all.
    """
    lines = [ln for ln in sql.splitlines() if not ln.lstrip().startswith("--")]
    cleaned = "\n".join(lines)

    statements: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(cleaned):
        if cleaned.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = cleaned[i]
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def upgrade() -> None:
    """Apply the full initial schema from 001_initial.sql."""
    sql_content = SQL_FILE.read_text(encoding="utf-8")
    for stmt in _split_statements(sql_content):
        op.execute(stmt + ";")


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    tables = [
        "prompt_deployments", "prompt_test_cases", "prompt_versions",
        "review_records", "flashcards",
        "chat_messages", "sessions",
        "usage_records", "budget_limits",
        "source_embeddings", "artifacts", "notes",
        "notebook_sources", "sources", "notebooks",
        "default_models", "ai_credentials", "ai_models",
        "audit_logs", "tenants",
    ]
    for table in tables:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")

    # Drop custom types
    op.execute("DROP TYPE IF EXISTS source_type CASCADE;")
    op.execute("DROP TYPE IF EXISTS artifact_type CASCADE;")
    op.execute("DROP TYPE IF EXISTS processing_status CASCADE;")
    op.execute("DROP TYPE IF EXISTS prompt_status CASCADE;")

    # Drop extensions
    op.execute("DROP EXTENSION IF EXISTS pgvector CASCADE;")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm CASCADE;")
