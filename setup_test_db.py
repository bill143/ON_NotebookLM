"""Create test database and apply full schema + vault migration."""

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


MAIN_DB_URL = "postgresql+asyncpg://nexus:nexus_dev_2024@localhost:5432/nexus_notebook_11"
TEST_DB_URL = "postgresql+asyncpg://nexus:nexus_dev_2024@localhost:5432/nexus_notebook_11_test"
TEST_DB_NAME = "nexus_notebook_11_test"


async def create_test_database():
    """Create the test database if it doesn't exist."""
    engine = create_async_engine(MAIN_DB_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_NAME},
        )
        if result.first() is None:
            await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
            print(f"Created database {TEST_DB_NAME}")
        else:
            print(f"Database {TEST_DB_NAME} already exists")
    await engine.dispose()


async def apply_schema():
    """Apply the initial schema as a single block."""
    engine = create_async_engine(TEST_DB_URL)

    async with engine.begin() as conn:
        # Check if tenants table already exists
        result = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'tenants'"
        ))
        if result.first() is not None:
            print("Schema already applied, skipping initial schema")
            await engine.dispose()
            return

    # Read the initial schema SQL and execute as one big block
    schema_file = Path("database/schema/001_initial.sql")
    schema_sql = schema_file.read_text(encoding="utf-8")

    async with engine.begin() as conn:
        # Extensions first - need superuser or at least CREATE permission
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        except Exception:
            print("Warning: pgvector extension not available - skipping")
        try:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception:
            print("Warning: pg_trgm extension not available - skipping")

    # Now run the full schema (excluding extension lines) as one transaction
    async with engine.begin() as conn:
        # Filter out extension lines and run everything else
        lines = schema_sql.split("\n")
        filtered = []
        for line in lines:
            stripped = line.strip().upper()
            if stripped.startswith("CREATE EXTENSION"):
                continue
            filtered.append(line)
        clean_sql = "\n".join(filtered)

        # Execute the whole thing at once
        await conn.execute(text(clean_sql))
        print("Applied initial schema to test DB")

    await engine.dispose()


async def apply_vault_migration():
    """Apply the vault tables to the test database."""
    engine = create_async_engine(TEST_DB_URL)

    async with engine.begin() as conn:
        # Check if vault tables already exist
        result = await conn.execute(text(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'vault_documents'"
        ))
        if result.first() is not None:
            print("Vault tables already exist in test DB")
            await engine.dispose()
            return

        # Create all vault tables
        await conn.execute(text("""
            CREATE TABLE vault_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id),
                project_id UUID NOT NULL,
                uploaded_by UUID NOT NULL REFERENCES users(id),
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size BIGINT,
                mime_type TEXT,
                document_type TEXT,
                confidence_score DECIMAL(4,3),
                librarian_decision JSONB,
                processing_status TEXT DEFAULT 'PENDING',
                requires_human_review BOOLEAN DEFAULT false,
                human_reviewed_by UUID REFERENCES users(id),
                human_reviewed_at TIMESTAMPTZ,
                human_override_type TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                deleted_at TIMESTAMPTZ
            );
            CREATE INDEX idx_vault_documents_tenant ON vault_documents(tenant_id);
            CREATE INDEX idx_vault_documents_project ON vault_documents(project_id);
            CREATE INDEX idx_vault_documents_type ON vault_documents(document_type);
            CREATE INDEX idx_vault_documents_status ON vault_documents(processing_status);
            CREATE INDEX idx_vault_documents_created ON vault_documents(created_at);

            CREATE TABLE rfi_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                project_id UUID NOT NULL,
                rfi_number TEXT NOT NULL,
                subject TEXT NOT NULL,
                discipline TEXT,
                spec_section TEXT,
                submitted_by UUID REFERENCES users(id),
                assigned_to UUID REFERENCES users(id),
                date_submitted DATE,
                date_required DATE,
                status TEXT DEFAULT 'OPEN',
                is_potential_scope_change BOOLEAN DEFAULT false,
                scope_change_notes TEXT,
                response_document_id UUID REFERENCES vault_documents(id),
                response_date DATE,
                distribution_list JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(tenant_id, project_id, rfi_number)
            );
            CREATE INDEX idx_rfi_records_tenant ON rfi_records(tenant_id);
            CREATE INDEX idx_rfi_records_project ON rfi_records(project_id);

            CREATE TABLE submittal_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                project_id UUID NOT NULL,
                submittal_number TEXT NOT NULL,
                spec_section TEXT,
                trade TEXT,
                revision INTEGER DEFAULT 0,
                submitted_by UUID REFERENCES users(id),
                assigned_reviewer UUID REFERENCES users(id),
                date_submitted DATE,
                date_required DATE,
                status TEXT DEFAULT 'SUBMITTED',
                review_notes TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_submittal_records_tenant ON submittal_records(tenant_id);
            CREATE INDEX idx_submittal_records_project ON submittal_records(project_id);

            CREATE TABLE invoice_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                project_id UUID NOT NULL,
                invoice_number TEXT NOT NULL,
                vendor_name TEXT,
                amount DECIMAL(14,2),
                period_start DATE,
                period_end DATE,
                date_received DATE,
                date_due DATE,
                status TEXT DEFAULT 'RECEIVED',
                date_paid DATE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_invoice_records_tenant ON invoice_records(tenant_id);
            CREATE INDEX idx_invoice_records_project ON invoice_records(project_id);

            CREATE TABLE change_order_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                project_id UUID NOT NULL,
                co_number TEXT NOT NULL,
                description TEXT,
                amount DECIMAL(14,2),
                reason_code TEXT,
                is_owner_directed BOOLEAN DEFAULT false,
                is_potential BOOLEAN DEFAULT false,
                status TEXT DEFAULT 'PENDING',
                submitted_by UUID REFERENCES users(id),
                date_submitted DATE,
                date_approved DATE,
                approved_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_change_order_records_tenant ON change_order_records(tenant_id);
            CREATE INDEX idx_change_order_records_project ON change_order_records(project_id);

            CREATE TABLE coi_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                project_id UUID NOT NULL,
                insured_name TEXT NOT NULL,
                policy_number TEXT,
                insurer_name TEXT,
                coverage_types JSONB DEFAULT '[]',
                effective_date DATE,
                expiration_date DATE NOT NULL,
                meets_requirements BOOLEAN,
                deficiency_notes TEXT,
                status TEXT DEFAULT 'ACTIVE',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_coi_records_tenant ON coi_records(tenant_id);
            CREATE INDEX idx_coi_records_project ON coi_records(project_id);

            CREATE TABLE permit_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                project_id UUID NOT NULL,
                permit_number TEXT NOT NULL,
                permit_type TEXT,
                issuing_authority TEXT,
                issue_date DATE,
                expiration_date DATE,
                status TEXT DEFAULT 'ACTIVE',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_permit_records_tenant ON permit_records(tenant_id);
            CREATE INDEX idx_permit_records_project ON permit_records(project_id);

            CREATE TABLE vault_workflow_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                vault_document_id UUID REFERENCES vault_documents(id),
                workflow_type TEXT,
                action TEXT NOT NULL,
                details JSONB DEFAULT '{}',
                performed_by TEXT DEFAULT 'LIBRARIAN_AI',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_vault_workflow_log_tenant ON vault_workflow_log(tenant_id);
            CREATE INDEX idx_vault_workflow_log_document ON vault_workflow_log(vault_document_id);

            CREATE TABLE vault_deadline_reminders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL,
                related_record_id UUID NOT NULL,
                related_record_type TEXT NOT NULL,
                reminder_type TEXT NOT NULL,
                scheduled_for TIMESTAMPTZ NOT NULL,
                sent_at TIMESTAMPTZ,
                recipient_user_ids JSONB DEFAULT '[]',
                message TEXT,
                status TEXT DEFAULT 'PENDING',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX idx_vault_deadline_reminders_tenant ON vault_deadline_reminders(tenant_id);
            CREATE INDEX idx_vault_deadline_reminders_scheduled ON vault_deadline_reminders(scheduled_for);
        """))
        print("Created all 9 vault tables in test DB")

        # RLS
        rls_tables = [
            "vault_documents", "rfi_records", "submittal_records", "invoice_records",
            "change_order_records", "coi_records", "permit_records",
            "vault_workflow_log", "vault_deadline_reminders",
        ]
        for table in rls_tables:
            await conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            await conn.execute(text(
                f"CREATE POLICY tenant_isolation_{table} ON {table} "
                f"USING (tenant_id = current_setting('app.tenant_id')::uuid)"
            ))
        print("Applied RLS to all 9 tables in test DB")

        # updated_at triggers
        updated_at_tables = [
            "vault_documents", "rfi_records", "submittal_records", "invoice_records",
            "change_order_records", "coi_records", "permit_records",
        ]
        for table in updated_at_tables:
            await conn.execute(text(
                f"CREATE TRIGGER tr_{table}_updated "
                f"BEFORE UPDATE ON {table} "
                f"FOR EACH ROW EXECUTE FUNCTION update_updated_at()"
            ))
        print("Applied updated_at triggers to 7 tables in test DB")

    await engine.dispose()


async def main():
    await create_test_database()
    await apply_schema()
    await apply_vault_migration()
    print("\nTest database setup complete!")


if __name__ == "__main__":
    asyncio.run(main())
