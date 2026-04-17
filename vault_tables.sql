-- Vault Foundation Tables for test DB

CREATE TABLE IF NOT EXISTS vault_documents (
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
CREATE INDEX IF NOT EXISTS idx_vault_documents_tenant ON vault_documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vault_documents_project ON vault_documents(project_id);
CREATE INDEX IF NOT EXISTS idx_vault_documents_type ON vault_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_vault_documents_status ON vault_documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_vault_documents_created ON vault_documents(created_at);

CREATE TABLE IF NOT EXISTS rfi_records (
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
CREATE INDEX IF NOT EXISTS idx_rfi_records_tenant ON rfi_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rfi_records_project ON rfi_records(project_id);

CREATE TABLE IF NOT EXISTS submittal_records (
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
CREATE INDEX IF NOT EXISTS idx_submittal_records_tenant ON submittal_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_submittal_records_project ON submittal_records(project_id);

CREATE TABLE IF NOT EXISTS invoice_records (
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
CREATE INDEX IF NOT EXISTS idx_invoice_records_tenant ON invoice_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_invoice_records_project ON invoice_records(project_id);

CREATE TABLE IF NOT EXISTS change_order_records (
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
CREATE INDEX IF NOT EXISTS idx_change_order_records_tenant ON change_order_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_change_order_records_project ON change_order_records(project_id);

CREATE TABLE IF NOT EXISTS coi_records (
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
CREATE INDEX IF NOT EXISTS idx_coi_records_tenant ON coi_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_coi_records_project ON coi_records(project_id);

CREATE TABLE IF NOT EXISTS permit_records (
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
CREATE INDEX IF NOT EXISTS idx_permit_records_tenant ON permit_records(tenant_id);
CREATE INDEX IF NOT EXISTS idx_permit_records_project ON permit_records(project_id);

CREATE TABLE IF NOT EXISTS vault_workflow_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    vault_document_id UUID REFERENCES vault_documents(id),
    workflow_type TEXT,
    action TEXT NOT NULL,
    details JSONB DEFAULT '{}',
    performed_by TEXT DEFAULT 'LIBRARIAN_AI',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_vault_workflow_log_tenant ON vault_workflow_log(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vault_workflow_log_document ON vault_workflow_log(vault_document_id);

CREATE TABLE IF NOT EXISTS vault_deadline_reminders (
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
CREATE INDEX IF NOT EXISTS idx_vault_deadline_reminders_tenant ON vault_deadline_reminders(tenant_id);
CREATE INDEX IF NOT EXISTS idx_vault_deadline_reminders_scheduled ON vault_deadline_reminders(scheduled_for);

-- RLS Policies
ALTER TABLE vault_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_vault_documents ON vault_documents USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE rfi_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_rfi_records ON rfi_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE submittal_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_submittal_records ON submittal_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE invoice_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_invoice_records ON invoice_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE change_order_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_change_order_records ON change_order_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE coi_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_coi_records ON coi_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE permit_records ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_permit_records ON permit_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE vault_workflow_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_vault_workflow_log ON vault_workflow_log USING (tenant_id = current_setting('app.tenant_id')::uuid);

ALTER TABLE vault_deadline_reminders ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_vault_deadline_reminders ON vault_deadline_reminders USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- updated_at Triggers
CREATE TRIGGER tr_vault_documents_updated BEFORE UPDATE ON vault_documents FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_rfi_records_updated BEFORE UPDATE ON rfi_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_submittal_records_updated BEFORE UPDATE ON submittal_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_invoice_records_updated BEFORE UPDATE ON invoice_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_change_order_records_updated BEFORE UPDATE ON change_order_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_coi_records_updated BEFORE UPDATE ON coi_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_permit_records_updated BEFORE UPDATE ON permit_records FOR EACH ROW EXECUTE FUNCTION update_updated_at();
