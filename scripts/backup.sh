#!/usr/bin/env bash
set -euo pipefail

# Nexus Notebook 11 LM — Manual Postgres Backup
# Usage: ./scripts/backup.sh [output_path]

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEFAULT_PATH="deploy/backups/manual_${TIMESTAMP}.dump"
OUTPUT_PATH="${1:-$DEFAULT_PATH}"

echo "=== Nexus Postgres Backup ==="
echo "Output: ${OUTPUT_PATH}"
echo ""

mkdir -p "$(dirname "$OUTPUT_PATH")"

docker compose -f deploy/docker-compose.yml exec -T postgres \
  pg_dump -U nexus -d nexus_notebook_11 -Fc \
  > "$OUTPUT_PATH"

if [ $? -ne 0 ]; then
  echo "ERROR: pg_dump failed."
  rm -f "$OUTPUT_PATH"
  exit 1
fi

FILE_SIZE=$(ls -lh "$OUTPUT_PATH" | awk '{print $5}')
echo "Backup complete: ${OUTPUT_PATH} (${FILE_SIZE})"
exit 0
