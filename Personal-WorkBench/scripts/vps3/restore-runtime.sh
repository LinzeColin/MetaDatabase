#!/usr/bin/env bash
set -euo pipefail
: "${DATABASE_URL:?DATABASE_URL is required}"
backup="${1:?usage: bash scripts/vps3/restore-runtime.sh /path/to/backup.dump}"
test -f "$backup"
pg_restore --clean --if-exists --no-owner --dbname "$DATABASE_URL" "$backup"
echo "restore_complete=$backup"
