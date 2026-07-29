#!/usr/bin/env bash
set -euo pipefail
db="${CYBERBOSS_DB_PATH:-/var/lib/cyberboss/runtime.sqlite3}"
root="${CYBERBOSS_BACKUP_ROOT:-/var/lib/cyberboss/backups}"
mkdir -p "$root"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"; plain="$root/.runtime-$stamp.sqlite3"; out="$root/runtime-$stamp.cbbackup"
/opt/cyberboss-cloud/current/starter_kit/scripts/sqlite_snapshot.py --source "$db" --output "$plain"
/usr/bin/node /opt/cyberboss-cloud/current/starter_kit/scripts/snapshot-crypto.js encrypt "$plain" "$out" >/dev/null
rm -f "$plain"
chmod 0600 "$out"
printf '%s\n' "$out"
