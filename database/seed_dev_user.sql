-- Development seed: fixed tenant + user for DEV_AUTO_LOGIN (see src/config.py).
-- Idempotent — safe to run repeatedly. Never run in production.
INSERT INTO tenants (id, name, slug, plan)
VALUES ('00000000-0000-0000-0000-000000000001', 'Local Development', 'local-dev', 'free')
ON CONFLICT (id) DO NOTHING;

INSERT INTO users (id, tenant_id, email, display_name, role)
VALUES (
    '00000000-0000-0000-0000-000000000002',
    '00000000-0000-0000-0000-000000000001',
    'dev@localhost',
    'Local Developer',
    'owner'
)
ON CONFLICT (id) DO NOTHING;
