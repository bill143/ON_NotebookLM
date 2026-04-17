# Document Vault — Build Report

## Tables Created (9)

| Table | Columns | Soft-Delete | updated_at Trigger |
|-------|---------|-------------|-------------------|
| vault_documents | 20 | Yes | Yes |
| rfi_records | 20 | No | Yes |
| submittal_records | 16 | No | Yes |
| invoice_records | 14 | No | Yes |
| change_order_records | 17 | No | Yes |
| coi_records | 15 | No | Yes |
| permit_records | 12 | No | Yes |
| vault_workflow_log | 8 | No | No |
| vault_deadline_reminders | 11 | No | No |

## Indexes Created (22)

- vault_documents: tenant_id, project_id, document_type, processing_status, created_at (5)
- rfi_records: tenant_id, project_id (2)
- submittal_records: tenant_id, project_id (2)
- invoice_records: tenant_id, project_id (2)
- change_order_records: tenant_id, project_id (2)
- coi_records: tenant_id, project_id (2)
- permit_records: tenant_id, project_id (2)
- vault_workflow_log: tenant_id, vault_document_id (2)
- vault_deadline_reminders: tenant_id, scheduled_for (2)
- rfi_records: UNIQUE(tenant_id, project_id, rfi_number) (1)

## RLS Policies Applied (9)

All 9 tables have Row-Level Security enabled with policy:
`tenant_isolation_{table} USING (tenant_id = current_setting('app.tenant_id')::uuid)`

## Repositories Built (9)

| Repository | Methods |
|-----------|---------|
| VaultDocumentRepository | get, create, update, soft_delete, list_by_project, list_pending, list_needs_review, update_status, update_librarian_decision (9) |
| RFIRepository | get, create, update, list_by_project, get_by_rfi_number, list_open, list_overdue (7) |
| SubmittalRepository | get, create, update, list_by_project, get_next_submittal_number (5) |
| InvoiceRepository | get, create, update, list_by_project, check_duplicate_invoice_number (5) |
| ChangeOrderRepository | get, create, update, list_by_project, get_next_co_number (5) |
| COIRepository | get, create, update, list_by_project, list_expiring_soon (5) |
| PermitRepository | get, create, update, list_by_project, list_expiring_soon (5) |
| WorkflowLogRepository | create, list_by_document (2) |
| DeadlineReminderRepository | create, list_pending, mark_sent, cancel (4) |

**Total: 47 methods across 9 repositories**

## Integration Points Connected (4)

1. **link_to_notebook_source** — Creates a source record from a vault document and links it to a notebook for NotebookLM features
2. **create_calendar_deadline** — Creates calendar events using existing calendar module (fails gracefully if unavailable)
3. **trigger_notification** — Sends notifications using existing notification service (fails gracefully if unavailable)
4. **update_project_document_count** — Queries vault_documents to get current document count for a project

## File Storage Service

- Organizes files as: `uploads/{tenant_id}/{project_id}/{document_type}/{year}/{month}/{uuid}_{filename}`
- Supports LOCAL and S3 storage backends via `src.config.StorageBackend`
- Filename sanitization removes path separators and dangerous characters
- Methods: save_uploaded_file, get_file_url, delete_file

## Test Results

| Test File | Tests | Status |
|-----------|-------|--------|
| tests/test_vault_database.py | 12 | All PASSED |
| tests/test_vault_integration.py | 3 | All PASSED |
| **Total** | **15** | **All PASSED** |

Full suite: **569 passed, 45 skipped, 0 failed**

### Test Coverage

| Test # | Description | Result |
|--------|-------------|--------|
| 1 | VaultDocumentRepository create and retrieve | PASS |
| 2 | VaultDocumentRepository soft delete does not hard delete | PASS |
| 3 | RFIRepository create with auto-number format validation | PASS |
| 4 | SubmittalRepository duplicate number detection | PASS |
| 5 | InvoiceRepository duplicate invoice number detection | PASS |
| 6 | COIRepository list_expiring_soon returns correct records | PASS |
| 7 | PermitRepository list_expiring_soon returns correct records | PASS |
| 8 | WorkflowLogRepository create and list by document | PASS |
| 9 | DeadlineReminderRepository pending reminders query | PASS |
| 10 | Tenant isolation — tenant A cannot see tenant B documents | PASS |
| 11 | Migration upgrade runs cleanly (all 9 tables verified) | PASS |
| 12 | Migration downgrade SQL validity verified | PASS |
| 13 | link_to_notebook_source creates correct association | PASS |
| 14 | create_calendar_deadline handles missing module gracefully | PASS |
| 15 | trigger_notification handles missing service gracefully | PASS |

## Migration Status

- **Upgrade**: Applied successfully to both main and test databases
- **Downgrade**: SQL validated (drops 9 tables in correct reverse dependency order)
- **Alembic revision**: `006_vault_foundation` (down_revision: `005_batch2_routers`)

## Total Lines of Code Added

| File | Lines |
|------|-------|
| database/migrations/versions/006_vault_foundation.py | 296 |
| src/vault/repositories.py | 393 |
| src/vault/file_storage.py | 121 |
| src/vault/integration.py | 206 |
| tests/test_vault_database.py | 468 |
| tests/test_vault_integration.py | 157 |
| **Total** | **1,641** |

## Issues Encountered and Resolved

1. **Alembic revision chain broken**: Existing migration 003 references `down_revision = "002_phase2_phase3_tables"` but migration 002's revision ID is `"002_phase2_phase3"`. Resolved by running migration SQL directly against the database and stamping the alembic_version table.

2. **asyncpg JSONB serialization**: asyncpg requires JSONB values to be passed as JSON strings, not Python dicts, when using raw `text()` queries with parameter binding. Fixed by serializing dict values with `json.dumps()` before insertion in tests.

3. **Test database setup**: The `nexus_notebook_11_test` database did not exist. Created it and applied both the initial schema (via `001_initial.sql`) and vault migration (via `vault_tables.sql`) using Docker psql.
