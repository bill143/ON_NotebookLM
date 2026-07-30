-- Migration 002: add sessions.checkpoint_data
-- nexus_research_grounding persists research session state (turns, citations,
-- total_tokens) in this column; without it every /api/v1/research/sessions
-- call fails with UndefinedColumnError. 001_initial.sql only runs on fresh
-- volumes, so existing databases need this applied manually:
--   docker exec deploy-postgres-1 psql -U nexus -d nexus_notebook_11 -f /backups/../002... (or via stdin)

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS checkpoint_data JSONB DEFAULT '{}';
