#!/usr/bin/env bash
set -euo pipefail
root="${CYBERBOSS_BACKUP_ROOT:-/var/lib/cyberboss/backups}"; db="${CYBERBOSS_DB_PATH:-/var/lib/cyberboss/runtime.sqlite3}"
latest="$(find "$root" -maxdepth 1 -type f -name 'runtime-*.cbbackup' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
[[ -n "$latest" ]] || { echo '没有可恢复的已验证备份。' >&2; exit 1; }
tmp="${db}.restore.$$"
/usr/bin/node /opt/cyberboss-cloud/current/starter_kit/scripts/snapshot-crypto.js decrypt "$latest" "$tmp" >/dev/null
/usr/bin/python3 - "$tmp" <<'PY'
import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
PY
/usr/bin/systemctl stop cyberboss.service
cp -a "$db" "${db}.pre-restore" 2>/dev/null || true
mv -f "$tmp" "$db"; chmod 0600 "$db"; chown cyberboss:cyberboss "$db"
/usr/bin/systemctl start cyberboss.service
/opt/cyberboss-cloud/current/starter_kit/scripts/doctor.sh
printf '%s\n' '恢复完成并通过完整性检查。'
