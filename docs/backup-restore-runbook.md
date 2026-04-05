# Backup & Restore Runbook — Nexus Notebook 11 LM

> **RPO**: 1 hour (automated hourly dumps + continuous WAL archiving)
> **RTO**: 30 minutes (restore from most recent dump + WAL replay)
> **Last updated**: 2026-04-05

---

## 1. Automated Backup Schedule

The `nexus-backup` sidecar container runs continuously and performs:

| Action | Frequency | Retention |
|--------|-----------|-----------|
| `pg_dump -Fc` (full dump) | Every 60 minutes | 7 days (auto-pruned) |
| WAL archiving (`archive_command`) | Continuous (per WAL segment) | Manual pruning |

Backup files are stored at `deploy/backups/`:
- `nexus_YYYYMMDD_HHMMSS.dump` — hourly full dumps
- `wal/` — continuous WAL archive segments

### Verify automated backups are running

```bash
docker compose -f deploy/docker-compose.yml logs nexus-backup --tail=5
ls -lht deploy/backups/*.dump | head -5
```

---

## 2. Manual Backup Procedure

For ad-hoc backups before deployments, migrations, or maintenance:

```bash
# Default output: deploy/backups/manual_<timestamp>.dump
./scripts/backup.sh

# Custom output path
./scripts/backup.sh /path/to/my-backup.dump
```

The script:
1. Runs `pg_dump -Fc` via `docker compose exec`
2. Prints file size on completion
3. Returns exit code 0 on success, 1 on failure

**Always run a manual backup before**:
- Alembic migrations
- Schema changes
- Bulk data operations
- Major version upgrades

---

## 3. Full Restore Procedure

```bash
./scripts/restore.sh deploy/backups/nexus_20260405_120000.dump
```

The script:
1. Requires explicit `CONFIRM` to proceed
2. Runs `pg_restore --clean --if-exists`
3. Verifies row counts for `users`, `sources`, `notebooks`
4. Returns exit code 0 on success

### Post-restore checklist

- [ ] Verify `GET /health/ready` returns `{"status": "ready"}`
- [ ] Verify row counts match expected values
- [ ] Restart API and worker containers: `docker compose restart nexus-api nexus-worker`
- [ ] Check application logs for database errors
- [ ] Verify a test query works: `GET /api/v1/notebooks`

---

## 4. Point-in-Time Recovery (PITR) via WAL

WAL archiving is enabled on the `postgres` service with:

```
wal_level=replica
archive_mode=on
archive_command='cp %p /backups/wal/%f'
```

### PITR procedure

1. **Stop the database**: `docker compose stop postgres`

2. **Replace the data directory** with the base backup:
   ```bash
   docker compose run --rm -v nexus-pgdata:/var/lib/postgresql/data \
     postgres:16-alpine sh -c "rm -rf /var/lib/postgresql/data/*"
   pg_restore -D /var/lib/postgresql/data deploy/backups/nexus_<timestamp>.dump
   ```

3. **Create recovery signal file**:
   ```bash
   cat > recovery.signal <<EOF
   restore_command = 'cp /backups/wal/%f %p'
   recovery_target_time = '2026-04-05 14:30:00 UTC'
   EOF
   ```

4. **Start postgres**: `docker compose up -d postgres`
   PostgreSQL will replay WAL segments up to the target time.

5. **Verify**: `SELECT pg_is_in_recovery();` returns `false` after recovery completes.

---

## 5. Disaster Recovery Scenarios

### Scenario A — Corrupted database
1. Stop all services: `docker compose down`
2. Restore from latest dump: `./scripts/restore.sh deploy/backups/<latest>.dump`
3. Start services: `docker compose up -d`
4. Verify via health checks

### Scenario B — Accidental data deletion
1. Identify the time before deletion from audit logs
2. Perform PITR to that timestamp (Section 4)
3. Export recovered data and merge into production

### Scenario C — Complete infrastructure loss
1. Provision new Docker host
2. Clone repository
3. Copy backup files from off-site storage
4. Run: `docker compose up -d postgres redis`
5. Restore: `./scripts/restore.sh <backup_file>`
6. Start remaining services: `docker compose up -d`

---

## 6. Monthly Restore Test Checklist

Perform on the first Monday of each month:

- [ ] Create a fresh manual backup: `./scripts/backup.sh`
- [ ] Spin up a test database container:
      `docker run --name nexus-restore-test -e POSTGRES_PASSWORD=test -d postgres:16-alpine`
- [ ] Restore the backup into the test container
- [ ] Verify row counts match production
- [ ] Verify a sample query returns correct data
- [ ] Destroy the test container: `docker rm -f nexus-restore-test`
- [ ] Record test date and result in this section:

| Date | Backup File | Rows Verified | Result | Tester |
|------|-------------|---------------|--------|--------|
| | | | | |

---

## 7. Off-site Backup (Recommended)

For production, copy dumps to off-site storage daily:

```bash
# Example: AWS S3
aws s3 sync deploy/backups/ s3://nexus-backups/daily/ \
  --exclude "wal/*" \
  --storage-class STANDARD_IA
```

Configure as a cron job or add an S3 sync step to the backup sidecar.

---

## 8. Emergency Contacts

| Role | Contact | When to Escalate |
|------|---------|-----------------|
| On-call engineer | [Slack: #nexus-oncall] | Any backup failure or restore needed |
| Database admin | [Bill Asmar] | PITR, corruption, schema recovery |
| Infrastructure lead | [Bill Asmar] | Complete infrastructure loss |
