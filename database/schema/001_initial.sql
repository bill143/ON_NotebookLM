-- ============================================================
-- Nexus Notebook 11 LM — Initial Schema Migration (001)
-- Codename: ESPERANTO
-- Date: 2026-03-29
-- Target: PostgreSQL 15+ with pgvector
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgvector";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================
-- TENANT & USER TABLES
-- ============================================================

CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    plan VARCHAR(50) NOT NULL DEFAULT 'free',
    settings JSONB DEFAULT '{}',
    max_users INTEGER DEFAULT 5,
    max_storage_mb INTEGER DEFAULT 1024,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_tenants_slug ON tenants(slug) WHERE deleted_at IS NULL;

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(320) NOT NULL,
    display_name VARCHAR(255),
    avatar_url TEXT,
    role VARCHAR(50) NOT NULL DEFAULT 'member',
    auth_provider_id VARCHAR(255) UNIQUE,
    preferences JSONB DEFAULT '{}',
    last_login_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    UNIQUE(tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_auth ON users(auth_provider_id);

-- ============================================================
-- NOTEBOOKS
-- ============================================================

CREATE TABLE notebooks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    name VARCHAR(500) NOT NULL,
    description TEXT DEFAULT '',
    icon VARCHAR(10) DEFAULT '📓',
    color VARCHAR(7) DEFAULT '#6366f1',
    archived BOOLEAN DEFAULT FALSE,
    pinned BOOLEAN DEFAULT FALSE,
    tags TEXT[] DEFAULT '{}',
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_notebooks_tenant_user ON notebooks(tenant_id, user_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_notebooks_archived ON notebooks(archived) WHERE deleted_at IS NULL;

-- ============================================================
-- SOURCES
-- ============================================================

CREATE TYPE source_status AS ENUM ('pending', 'processing', 'ready', 'error', 'archived');
CREATE TYPE source_type AS ENUM (
    'pdf', 'url', 'youtube', 'audio', 'image', 'text',
    'markdown', 'docx', 'csv', 'google_doc', 'google_slide',
    'google_sheet', 'pasted_text', 'upload'
);

CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title VARCHAR(1000),
    source_type source_type NOT NULL DEFAULT 'text',
    status source_status NOT NULL DEFAULT 'pending',
    asset_url TEXT,
    asset_file_path TEXT,
    asset_mime_type VARCHAR(255),
    asset_size_bytes BIGINT,
    full_text TEXT,
    summary TEXT,
    topics TEXT[] DEFAULT '{}',
    word_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    language VARCHAR(10) DEFAULT 'en',
    processing_error TEXT,
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_sources_tenant ON sources(tenant_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_sources_status ON sources(tenant_id, status);
CREATE INDEX idx_sources_fulltext ON sources USING gin(to_tsvector('english', COALESCE(full_text, '')));

CREATE TABLE notebook_sources (
    notebook_id UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (notebook_id, source_id)
);

-- ============================================================
-- SOURCE EMBEDDINGS (pgvector)
-- ============================================================

CREATE TABLE source_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER DEFAULT 0,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_embeddings_source ON source_embeddings(source_id);
CREATE INDEX idx_embeddings_vector ON source_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- SOURCE INSIGHTS
-- ============================================================

CREATE TABLE source_insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    insight_type VARCHAR(100) NOT NULL,
    title VARCHAR(500),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_insights_source ON source_insights(source_id);

-- ============================================================
-- NOTES
-- ============================================================

CREATE TABLE notes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    notebook_id UUID REFERENCES notebooks(id) ON DELETE SET NULL,
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    title VARCHAR(1000),
    content TEXT,
    note_type VARCHAR(10) DEFAULT 'human',
    pinned BOOLEAN DEFAULT FALSE,
    tags TEXT[] DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_notes_notebook ON notes(notebook_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_notes_source ON notes(source_id);

-- ============================================================
-- ARTIFACTS (generated outputs)
-- ============================================================

CREATE TYPE artifact_type AS ENUM (
    'audio', 'video', 'report', 'quiz', 'flashcard_deck',
    'mind_map', 'infographic', 'slide_deck', 'data_table',
    'summary', 'transcript', 'podcast'
);
CREATE TYPE artifact_status AS ENUM ('queued', 'processing', 'completed', 'failed', 'cancelled');

CREATE TABLE artifacts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    notebook_id UUID REFERENCES notebooks(id) ON DELETE SET NULL,
    user_id UUID NOT NULL REFERENCES users(id),
    title VARCHAR(1000) NOT NULL,
    artifact_type artifact_type NOT NULL,
    status artifact_status NOT NULL DEFAULT 'queued',
    content TEXT,
    storage_url TEXT,
    storage_size_bytes BIGINT,
    format VARCHAR(50),
    duration_seconds FLOAT,
    generation_config JSONB DEFAULT '{}',
    error_message TEXT,
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_artifacts_notebook ON artifacts(notebook_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_artifacts_user ON artifacts(user_id, created_at DESC);
CREATE INDEX idx_artifacts_status ON artifacts(tenant_id, status);

CREATE TABLE artifact_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    artifact_id UUID NOT NULL REFERENCES artifacts(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    content TEXT,
    storage_url TEXT,
    changelog TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(artifact_id, version)
);

-- ============================================================
-- SESSIONS & CHAT
-- ============================================================

CREATE TYPE session_type AS ENUM ('chat', 'research', 'audio', 'generation');

CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    notebook_id UUID REFERENCES notebooks(id) ON DELETE SET NULL,
    session_type session_type NOT NULL DEFAULT 'chat',
    title VARCHAR(500),
    model_override VARCHAR(255),
    context_config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sessions_notebook ON sessions(notebook_id);
CREATE INDEX idx_sessions_user ON sessions(user_id, created_at DESC);

CREATE TABLE chat_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    citations JSONB DEFAULT '[]',
    token_count_input INTEGER DEFAULT 0,
    token_count_output INTEGER DEFAULT 0,
    model_used VARCHAR(255),
    latency_ms INTEGER,
    turn_number INTEGER NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_session ON chat_messages(session_id, turn_number);

-- ============================================================
-- FLASHCARDS & SPACED REPETITION (FSRS)
-- ============================================================

CREATE TABLE flashcards (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    notebook_id UUID REFERENCES notebooks(id) ON DELETE SET NULL,
    source_id UUID REFERENCES sources(id) ON DELETE SET NULL,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    tags TEXT[] DEFAULT '{}',
    difficulty_level INTEGER DEFAULT 1,
    auto_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_flashcards_notebook ON flashcards(notebook_id);

CREATE TABLE review_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    flashcard_id UUID NOT NULL REFERENCES flashcards(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    difficulty FLOAT NOT NULL DEFAULT 0.3,
    stability FLOAT NOT NULL DEFAULT 1.0,
    retrievability FLOAT NOT NULL DEFAULT 1.0,
    due_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_review_at TIMESTAMPTZ,
    review_count INTEGER DEFAULT 0,
    lapses INTEGER DEFAULT 0,
    rating INTEGER CHECK (rating BETWEEN 1 AND 4),
    elapsed_days FLOAT DEFAULT 0,
    scheduled_days FLOAT DEFAULT 0,
    state INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_reviews_due ON review_records(user_id, due_at);
CREATE INDEX idx_reviews_flashcard ON review_records(flashcard_id);

-- ============================================================
-- AI MODELS & CREDENTIALS (Esperanto Pattern — ADR-1)
-- ============================================================

CREATE TYPE model_type AS ENUM ('chat', 'embedding', 'tts', 'stt', 'vision', 'reranker');

CREATE TABLE ai_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    model_type model_type NOT NULL,
    model_id_string VARCHAR(500) NOT NULL,
    is_local BOOLEAN DEFAULT FALSE,
    base_url TEXT,
    max_tokens INTEGER,
    supports_streaming BOOLEAN DEFAULT TRUE,
    supports_function_calling BOOLEAN DEFAULT FALSE,
    cost_per_1k_input NUMERIC(10,6) DEFAULT 0,
    cost_per_1k_output NUMERIC(10,6) DEFAULT 0,
    config JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_models_type ON ai_models(model_type, is_active);
CREATE INDEX idx_models_provider ON ai_models(provider);

CREATE TABLE ai_credentials (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    provider VARCHAR(100) NOT NULL,
    credential_name VARCHAR(255) NOT NULL,
    encrypted_key TEXT NOT NULL,
    key_prefix VARCHAR(10),
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_credentials_provider ON ai_credentials(tenant_id, provider);

CREATE TABLE default_models (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    task_type VARCHAR(100) NOT NULL,
    model_id UUID NOT NULL REFERENCES ai_models(id),
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(tenant_id, task_type, priority)
);

-- ============================================================
-- COST & USAGE TRACKING
-- ============================================================

CREATE TABLE usage_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    request_id VARCHAR(255),
    trace_id VARCHAR(255),
    model_name VARCHAR(255) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    feature_id VARCHAR(10),
    agent_id VARCHAR(100),
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER DEFAULT 0,
    cost_usd NUMERIC(10,6) DEFAULT 0,
    latency_ms INTEGER,
    success BOOLEAN DEFAULT TRUE,
    error_type VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_usage_tenant_date ON usage_records(tenant_id, created_at);
CREATE INDEX idx_usage_user ON usage_records(user_id, created_at);
CREATE INDEX idx_usage_model ON usage_records(model_name, created_at);

CREATE TABLE budget_limits (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id),
    period VARCHAR(20) NOT NULL DEFAULT 'monthly',
    limit_usd NUMERIC(10,2) NOT NULL,
    alert_threshold_pct INTEGER DEFAULT 80,
    hard_limit BOOLEAN DEFAULT FALSE,
    current_usage_usd NUMERIC(10,2) DEFAULT 0,
    period_start TIMESTAMPTZ NOT NULL DEFAULT date_trunc('month', NOW()),
    notified_at_80 BOOLEAN DEFAULT FALSE,
    notified_at_90 BOOLEAN DEFAULT FALSE,
    notified_at_100 BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- PROMPT VERSIONING
-- ============================================================

CREATE TYPE prompt_status AS ENUM ('draft', 'active', 'deprecated', 'archived');

CREATE TABLE prompt_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    namespace VARCHAR(100) NOT NULL,
    version VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    variables JSONB DEFAULT '[]',
    model_target VARCHAR(255),
    max_tokens INTEGER,
    temperature FLOAT DEFAULT 0.7,
    status prompt_status NOT NULL DEFAULT 'draft',
    parent_version_id UUID REFERENCES prompt_versions(id),
    changelog TEXT,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deployed_at TIMESTAMPTZ,
    avg_latency_ms FLOAT,
    avg_token_cost FLOAT,
    quality_score FLOAT,
    invocation_count INTEGER DEFAULT 0,
    UNIQUE(namespace, name, version)
);
CREATE INDEX idx_prompts_active ON prompt_versions(namespace, name) WHERE status = 'active';

CREATE TABLE prompt_test_cases (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_version_id UUID NOT NULL REFERENCES prompt_versions(id) ON DELETE CASCADE,
    test_name VARCHAR(255) NOT NULL,
    input_variables JSONB NOT NULL,
    expected_output_criteria JSONB NOT NULL,
    pass_threshold FLOAT NOT NULL DEFAULT 0.8,
    last_run_at TIMESTAMPTZ,
    last_run_result VARCHAR(20),
    last_run_score FLOAT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE prompt_deployments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_version_id UUID NOT NULL REFERENCES prompt_versions(id),
    environment VARCHAR(20) NOT NULL,
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deployed_by UUID REFERENCES users(id),
    rolled_back_at TIMESTAMPTZ,
    rollback_reason TEXT
);

-- ============================================================
-- PLUGIN REGISTRY
-- ============================================================

CREATE TABLE plugin_registry (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    author VARCHAR(255),
    manifest JSONB NOT NULL,
    permissions TEXT[] DEFAULT '{}',
    status VARCHAR(20) DEFAULT 'active',
    config JSONB DEFAULT '{}',
    installed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- SYNC QUEUE (Local-First)
-- ============================================================

CREATE TYPE sync_status AS ENUM ('pending', 'synced', 'conflict', 'failed');

CREATE TABLE sync_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    device_id VARCHAR(255) NOT NULL,
    operation VARCHAR(20) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    record_id UUID NOT NULL,
    payload JSONB NOT NULL,
    status sync_status DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 5,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    synced_at TIMESTAMPTZ
);
CREATE INDEX idx_sync_pending ON sync_queue(tenant_id, device_id, status) WHERE status = 'pending';

-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    user_id UUID,
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id UUID,
    details JSONB DEFAULT '{}',
    ip_address INET,
    user_agent TEXT,
    severity VARCHAR(20) DEFAULT 'info',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_tenant_date ON audit_logs(tenant_id, created_at);
CREATE INDEX idx_audit_action ON audit_logs(action, created_at);

-- ============================================================
-- ROW-LEVEL SECURITY
-- ============================================================

ALTER TABLE notebooks ENABLE ROW LEVEL SECURITY;
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE source_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE flashcards ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_records ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_notebooks ON notebooks USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_sources ON sources USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_embeddings ON source_embeddings USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_notes ON notes USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_artifacts ON artifacts USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_sessions ON sessions USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_flashcards ON flashcards USING (tenant_id = current_setting('app.tenant_id')::uuid);
CREATE POLICY tenant_usage ON usage_records USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- ============================================================
-- FUNCTIONS
-- ============================================================

CREATE OR REPLACE FUNCTION resolve_prompt(
    p_namespace VARCHAR, p_name VARCHAR, p_version VARCHAR DEFAULT NULL
) RETURNS TABLE(prompt_id UUID, content TEXT, version VARCHAR, variables JSONB, model_target VARCHAR, max_tokens INTEGER, temperature FLOAT) AS $$
BEGIN
    IF p_version IS NOT NULL THEN
        RETURN QUERY SELECT pv.id, pv.content, pv.version, pv.variables, pv.model_target, pv.max_tokens, pv.temperature
        FROM prompt_versions pv
        WHERE pv.namespace = p_namespace AND pv.name = p_name AND pv.version = p_version;
    ELSE
        RETURN QUERY SELECT pv.id, pv.content, pv.version, pv.variables, pv.model_target, pv.max_tokens, pv.temperature
        FROM prompt_versions pv
        WHERE pv.namespace = p_namespace AND pv.name = p_name AND pv.status = 'active'
        ORDER BY pv.deployed_at DESC NULLS LAST LIMIT 1;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION vector_search(
    p_query_embedding vector(1536),
    p_source_ids UUID[],
    p_limit INTEGER DEFAULT 10,
    p_min_score FLOAT DEFAULT 0.5
) RETURNS TABLE(chunk_id UUID, source_id UUID, content TEXT, score FLOAT) AS $$
BEGIN
    RETURN QUERY
    SELECT se.id, se.source_id, se.content,
           1 - (se.embedding <=> p_query_embedding) as similarity
    FROM source_embeddings se
    WHERE se.source_id = ANY(p_source_ids)
      AND 1 - (se.embedding <=> p_query_embedding) >= p_min_score
    ORDER BY se.embedding <=> p_query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers
CREATE TRIGGER tr_tenants_updated BEFORE UPDATE ON tenants FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_users_updated BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_notebooks_updated BEFORE UPDATE ON notebooks FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_sources_updated BEFORE UPDATE ON sources FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_notes_updated BEFORE UPDATE ON notes FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_artifacts_updated BEFORE UPDATE ON artifacts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER tr_sessions_updated BEFORE UPDATE ON sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at();
