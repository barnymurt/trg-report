#!/usr/bin/env bash
# Backup script — runs nightly via cron / Task Scheduler.
# Snapshots Qdrant, audit DB, and document store to a local backup directory
# which is then synced to the user's cloud (iCloud/OneDrive/Drive).
#
# Usage:
#   bash infra/scripts/backup.sh                  # backup to ./backups
#   BACKUP_PATH=/path/to/cloud bash infra/scripts/backup.sh
#
# Cron entry (Linux/macOS):
#   0 2 * * * cd /path/to/trg && bash infra/scripts/backup.sh
#
# Task Scheduler (Windows) — create a task that runs this script daily at 02:00.

set -euo pipefail

# ─── Configuration ────────────────────────────────────────────────────

BACKUP_PATH="${BACKUP_PATH:-./backups}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_PATH}/${TIMESTAMP}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "${BACKUP_DIR}"

echo "[backup] ${TIMESTAMP} — writing to ${BACKUP_DIR}"

# ─── Qdrant snapshot ──────────────────────────────────────────────────
# Note: snapshots require Qdrant to be running.

if curl -sf http://localhost:6333/health >/dev/null 2>&1; then
  echo "[backup] snapshotting Qdrant…"
  SNAPSHOT_NAME="trg-${TIMESTAMP}"
  # Create a snapshot for every collection (one per project)
  for collection in $(curl -sf http://localhost:6333/collections | jq -r '.result.collections[].name'); do
    echo "  - ${collection}"
    curl -sf -X POST "http://localhost:6333/collections/${collection}/snapshots" \
      -H "Content-Type: application/json" \
      -d "{\"snapshot_name\": \"${SNAPSHOT_NAME}-${collection}\"}" \
      >/dev/null || echo "    (failed for ${collection})"
  done

  # Download all snapshots
  mkdir -p "${BACKUP_DIR}/qdrant"
  for collection in $(curl -sf http://localhost:6333/collections | jq -r '.result.collections[].name'); do
    SNAP_URL="http://localhost:6333/collections/${collection}/snapshots/${SNAPSHOT_NAME}-${collection}"
    curl -sf "${SNAP_URL}" -o "${BACKUP_DIR}/qdrant/${SNAPSHOT_NAME}-${collection}.snapshot" \
      || echo "    (download failed for ${collection})"
  done
else
  echo "[backup] Qdrant not running — skipping snapshot"
fi

# ─── Audit DB ─────────────────────────────────────────────────────────

if [ -f "${REPO_ROOT}/data/audit.db" ]; then
  echo "[backup] copying audit.db…"
  cp "${REPO_ROOT}/data/audit.db" "${BACKUP_DIR}/audit.db"
  # Use sqlite3 for safe hot backup if available
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "${REPO_ROOT}/data/audit.db" ".backup '${BACKUP_DIR}/audit.db.hot'"
  fi
fi

# ─── Documents ────────────────────────────────────────────────────────

if [ -d "${REPO_ROOT}/data/documents" ]; then
  echo "[backup] copying documents…"
  rsync -a "${REPO_ROOT}/data/documents/" "${BACKUP_DIR}/documents/"
fi

# ─── Config (agents, whitelists) ──────────────────────────────────────

if [ -d "${REPO_ROOT}/data/agent-config" ]; then
  echo "[backup] copying agent config…"
  rsync -a "${REPO_ROOT}/data/agent-config/" "${BACKUP_DIR}/agent-config/"
fi

# ─── Manifest ─────────────────────────────────────────────────────────

cat > "${BACKUP_DIR}/manifest.json" <<EOF
{
  "timestamp": "${TIMESTAMP}",
  "repo_root": "${REPO_ROOT}",
  "contents": [
    "qdrant/",
    "audit.db",
    "documents/",
    "agent-config/"
  ]
}
EOF

# ─── Compress ─────────────────────────────────────────────────────────

echo "[backup] compressing…"
tar -czf "${BACKUP_DIR}.tar.gz" -C "${BACKUP_PATH}" "${TIMESTAMP}"
rm -rf "${BACKUP_DIR}"

# ─── Retention ────────────────────────────────────────────────────────

echo "[backup] pruning backups older than ${RETENTION_DAYS} days…"
find "${BACKUP_PATH}" -maxdepth 1 -name "*.tar.gz" -mtime +${RETENTION_DAYS} -delete

echo "[backup] done → ${BACKUP_DIR}.tar.gz"
