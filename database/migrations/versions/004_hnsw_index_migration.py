"""Replace IVFFlat vector index with HNSW and add tenant composite index.

IVFFlat with lists=100 degrades above ~10K rows and requires manual tuning.
HNSW maintains recall quality at any scale without list-count management.

Both indexes are created/dropped with CONCURRENTLY for zero-downtime operation.
Alembic must run this migration outside a transaction block to allow
CREATE INDEX CONCURRENTLY (autocommit=True via op.execute with execution_options).

Revision ID: 004_hnsw_index
Revises: 003_argon2_salt
Create Date: 2026-04-05
"""

from alembic import op

revision = "004_hnsw_index"
down_revision = "003_argon2_salt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # DROP the existing IVFFlat index.
    # Cannot use CONCURRENTLY for DROP INDEX inside a transaction, so we
    # use IF EXISTS to be idempotent across partial runs.
    op.execute("DROP INDEX IF EXISTS idx_embeddings_vector")

    # CREATE the HNSW index CONCURRENTLY (zero-downtime).
    # m=16 gives good recall/speed balance; ef_construction=200 is the
    # pgvector team's recommended default for production workloads.
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embeddings_hnsw "
        "ON source_embeddings "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 200)"
    )

    # ADD a composite tenant index for RLS-filtered ANN queries.
    # Without this, every RLS-scoped vector search requires a sequential
    # bitmap filter on tenant_id.
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embeddings_tenant "
        "ON source_embeddings (tenant_id, source_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_embeddings_tenant")
    op.execute("DROP INDEX IF EXISTS idx_embeddings_hnsw")

    # Restore the original IVFFlat index.
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_embeddings_vector "
        "ON source_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) "
        "WITH (lists = 100)"
    )
