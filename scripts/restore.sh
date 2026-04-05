#!/usr/bin/env bash
set -euo pipefail

# Nexus Notebook 11 LM — Postgres Restore
# Usage: ./scripts/restore.sh <dump_file_path>

if [ $# -lt 1 ]; then
  echo "Usage: $0 <dump_file_path>"
  echo "Example: $0 deploy/backups/nexus_20260405_120000.dump"
  exit 1
fi

DUMP_FILE="$1"

if [ ! -f "$DUMP_FILE" ]; then
  echo "ERROR: File not found: ${DUMP_FILE}"
  exit 1
fi

FILE_SIZE=$(ls -lh "$DUMP_FILE" | awk '{print $5}')
echo "=== Nexus Postgres Restore ==="
echo "Source: ${DUMP_FILE} (${FILE_SIZE})"
echo ""
echo "WARNING: This will overwrite the current database."
echo -n "Type CONFIRM to proceed: "
read -r CONFIRM

if [ "$CONFIRM" != "CONFIRM" ]; then
  echo "Aborted."
  exit 1
fi

echo ""
echo "Restoring database..."

docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_restore \
    --clean \
    --if-exists \
    --no-owner \
    --no-privileges \
    -U nexus \
    -d nexus_notebook_11 \
  < "$DUMP_FILE"

RESTORE_EXIT=$?

if [ $RESTORE_EXIT -ne 0 ] && [ $RESTORE_EXIT -ne 1 ]; then
  echo "ERROR: pg_restore failed with exit code ${RESTORE_EXIT}."
  echo "Note: exit code 1 is acceptable (warnings about pre-existing objects)."
  exit 1
fi

echo ""
echo "Restore complete. Verifying row counts..."
echo ""

docker compose -f deploy/docker-compose.yml exec -T postgres \
  psql -U nexus -d nexus_notebook_11 -t -A -c "
    SELECT 'users: '     || COUNT(*) FROM users
    UNION ALL
    SELECT 'sources: '   || COUNT(*) FROM sources
    UNION ALL
    SELECT 'notebooks: ' || COUNT(*) FROM notebooks;
  "

echo ""
echo "Restore verified successfully."
exit 0
