# Secret Rotation Runbook — Nexus Notebook 11 LM

> **Target**: Zero-downtime rotation for every secret in the system.
> **Audience**: Platform engineers and on-call SREs.
> **Last updated**: 2026-04-05

---

## 1. JWT_SECRET Rotation

JWT_SECRET signs all user access tokens. Rotating it invalidates every
in-flight session unless you run a grace period that accepts both keys.

### Procedure

1. **Generate new secret** (minimum 32 bytes, cryptographically random):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

2. **Deploy with dual-accept** — set a new env var `JWT_SECRET_PREVIOUS`
   to the current value and `JWT_SECRET` to the new value.  Update
   `verify_token()` to try the new key first, then fall back to
   `JWT_SECRET_PREVIOUS`:
   ```python
   try:
       return jwt.decode(token, settings.jwt_secret, ...)
   except JWTError:
       if settings.jwt_secret_previous:
           return jwt.decode(token, settings.jwt_secret_previous, ...)
       raise
   ```
   Add `jwt_secret_previous: Optional[str] = None` to `Settings`.

3. **Deploy the updated code** to all API containers.  Wait for traffic
   to confirm both old and new tokens are accepted (monitor 401 rate).

4. **Wait one full token lifetime** (default: 60 minutes) so all old
   tokens expire naturally.

5. **Remove `JWT_SECRET_PREVIOUS`** from the environment.  Deploy.

### Estimated downtime: **Zero**
### Rollback: Set `JWT_SECRET` back to the old value and redeploy.
### Verification:
- `curl -H "Authorization: Bearer <old_token>" /health/ready` → 200 during grace, 401 after
- `curl -H "Authorization: Bearer <new_token>" /health/ready` → 200

---

## 2. ENCRYPTION_KEY Rotation

ENCRYPTION_KEY derives AES-256 keys (via Argon2id) for encrypting
stored AI provider credentials in `ai_credentials.encrypted_key`.

### Procedure

1. **Generate new key** (minimum 32 characters):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

2. **Deploy with dual-key support** — set `ENCRYPTION_KEY` to the new
   value and `ENCRYPTION_KEY_PREVIOUS` to the old value.  Update
   `decrypt_credential()` to try the new key first and fall back:
   ```python
   try:
       return _decrypt_with_key(settings.encryption_key, encrypted, salt)
   except Exception:
       if settings.encryption_key_previous:
           return _decrypt_with_key(settings.encryption_key_previous, encrypted, salt)
       raise
   ```
   Add `encryption_key_previous: Optional[str] = None` to `Settings`.

3. **Run the re-encryption migration**:
   ```bash
   python -m scripts.reencrypt_credentials
   ```
   This script reads each row from `ai_credentials`, decrypts with the
   appropriate key (trying new first, then old), then re-encrypts with
   the new key + fresh Argon2id salt, and writes back.

4. **Verify** all credentials decrypt successfully:
   ```bash
   python -c "
   from src.agents.nexus_model_layer import model_manager
   import asyncio
   asyncio.run(model_manager.get_credential('openai'))
   "
   ```

5. **Remove `ENCRYPTION_KEY_PREVIOUS`** from the environment.  Deploy.

### Estimated downtime: **Zero**
### Rollback: Revert `ENCRYPTION_KEY` to the old value, redeploy. Old
ciphertexts are still readable because the re-encryption script only
writes after successful decrypt.
### Verification:
- `GET /api/v1/models` returns models with valid credential lookups
- No `ProviderAuthError` in logs

---

## 3. CSRF_SECRET Rotation

CSRF_SECRET is used to generate per-session CSRF tokens. The token
includes `int(time.time() // 3600)` so tokens rotate hourly.

### Procedure

1. **Generate new secret**:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Set `CSRF_SECRET`** to the new value in the environment.

3. **Deploy.** Existing CSRF tokens become invalid, but since they
   rotate hourly anyway and are only checked on state-changing
   endpoints, the impact window is < 1 hour.

4. If zero-impact is required, add `CSRF_SECRET_PREVIOUS` support
   identical to the JWT pattern above.

### Estimated downtime: **Zero** (< 1 hour of CSRF validation misses
for users with cached tokens, which auto-heal on next page load).
### Rollback: Set `CSRF_SECRET` back to the old value and redeploy.
### Verification:
- Submit a form via the frontend; confirm no 403 CSRF errors

---

## 4. POSTGRES_PASSWORD Rotation

The database password is used by the API server, Celery workers, and
Celery beat to connect to PostgreSQL.

### Procedure

1. **Create the new password in PostgreSQL** (via superuser):
   ```sql
   ALTER USER nexus WITH PASSWORD 'new_secure_password_here';
   ```

2. **Update the `.env` / environment** with the new
   `POSTGRES_PASSWORD` and the corresponding `DATABASE_URL`:
   ```
   POSTGRES_PASSWORD=new_secure_password_here
   DATABASE_URL=postgresql+asyncpg://nexus:new_secure_password_here@postgres:5432/nexus_notebook_11
   ```

3. **Rolling restart** each service one at a time:
   ```bash
   # API server (drains existing pool via pool_pre_ping=True)
   docker compose up -d --no-deps nexus-api

   # Workers
   docker compose up -d --no-deps nexus-worker

   # Beat
   docker compose up -d --no-deps nexus-beat
   ```
   SQLAlchemy's `pool_pre_ping=True` detects stale connections and
   replaces them automatically on the next query.

4. **Verify** each service:
   ```bash
   curl http://localhost:8000/health/ready   # API
   docker compose exec nexus-worker celery -A src.worker inspect ping  # Worker
   ```

5. **Update monitoring** — if the Postgres exporter uses the old
   password, update `DATA_SOURCE_NAME` in docker-compose and restart
   `postgres-exporter`.

### Estimated downtime: **Zero** (rolling restart with pre-ping).
### Rollback: `ALTER USER nexus WITH PASSWORD 'old_password';` and
redeploy with old env vars.
### Verification:
- `GET /health/ready` returns `{"status": "ready", "checks": {"database": "ok"}}`
- No `DatabaseError` in API or worker logs

---

## Rotation Schedule (Recommended)

| Secret | Rotation Frequency | Trigger |
|--------|-------------------|---------|
| JWT_SECRET | Every 90 days | Calendar reminder |
| ENCRYPTION_KEY | Every 180 days or on suspected compromise | Calendar + incident |
| CSRF_SECRET | Every 90 days | Calendar reminder |
| POSTGRES_PASSWORD | Every 90 days | Calendar reminder |
| AI provider API keys | Per-provider policy | Provider dashboard |

---

## Emergency Rotation (Suspected Compromise)

If a secret is suspected compromised:

1. **Immediately** generate and deploy the new secret using the
   dual-key procedure above.
2. **Do not** wait for the grace period — accept that some in-flight
   requests may fail.
3. **Audit** the `audit_logs` table for unusual activity during the
   compromise window.
4. **Notify** affected tenants if credential data may have been
   exposed.
5. **File an incident report** in the team wiki.
