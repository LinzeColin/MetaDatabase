#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

DB="${CB_RUNTIME_DB:-/var/lib/cyberboss/runtime.db}"
OUT_DIR="${CB_BACKUP_LOCAL_DIR:-/var/lib/cyberboss/snapshots}"
R2_REMOTE="${CB_R2_REMOTE:-}"
APP_ROOT="${CB_APP_ROOT:-/opt/cyberboss-cloud}"
CANONICAL_LAST_OBJECT_FILE="${CB_CANONICAL_LAST_OBJECT_FILE:-/var/lib/cyberboss/status/canonical-last-object.sha256}"
INCLUDE_WECHAT="${CB_BACKUP_INCLUDE_WECHAT_STATE:-false}"
ALLOW_LOCAL_ONLY="${CB_BACKUP_ALLOW_LOCAL_ONLY:-true}"
MAX_LOCAL="${CB_BACKUP_LOCAL_KEEP_COUNT:-3}"

for cmd in sqlite3 tar zstd sha256sum date; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "BACKUP=FAIL missing:$cmd"; exit 2; }
done
[[ -r "$DB" ]] || { echo "BACKUP=FAIL db_unreadable:$DB"; exit 2; }
[[ "$INCLUDE_WECHAT" != "true" ]] || { echo 'BACKUP=FAIL wechat_state_requires_separate_encrypted_design'; exit 2; }

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ID="cyberboss-${STAMP}-$$"
mkdir -p "$OUT_DIR"
WORK="$(mktemp -d "$OUT_DIR/.${ID}.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

SNAP_DB="$WORK/runtime.db"
sqlite3 "$DB" ".timeout 10000" ".backup '$SNAP_DB'"
[[ "$(sqlite3 "$SNAP_DB" 'PRAGMA integrity_check;' 2>/dev/null)" == "ok" ]] || { echo 'BACKUP=FAIL sqlite_integrity'; exit 1; }

APP_COMMIT="$(
  node -e "
    const fs = require('node:fs');
    try {
      const m = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
      process.stdout.write(typeof m.commit === 'string' ? m.commit : 'unknown');
    } catch { process.stdout.write('unknown'); }
  " "$APP_ROOT/current/release-manifest.json" 2>/dev/null || echo unknown
)"
CANONICAL_OBJECT_SHA256="not_verified"
if [[ -e "$CANONICAL_LAST_OBJECT_FILE" ]]; then
  [[ -r "$CANONICAL_LAST_OBJECT_FILE" ]] || { echo 'BACKUP=FAIL canonical_object_hash_unreadable'; exit 2; }
  CANONICAL_OBJECT_SHA256="$(head -n 1 "$CANONICAL_LAST_OBJECT_FILE" | tr -d '[:space:]')"
  [[ "$CANONICAL_OBJECT_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo 'BACKUP=FAIL canonical_object_hash_invalid'
    exit 2
  }
fi
SCHEMA_VERSION="$(sqlite3 "$SNAP_DB" 'SELECT COALESCE(MAX(version),0) FROM schema_migrations;' 2>/dev/null || echo unknown)"

cat > "$WORK/manifest.txt" <<MANIFEST
snapshot_id=$ID
created_at=$STAMP
app_commit=$APP_COMMIT
canonical_object_sha256=$CANONICAL_OBJECT_SHA256
schema_version=$SCHEMA_VERSION
include_wechat_state=false
MANIFEST

ARCHIVE="$OUT_DIR/${ID}.tar.zst"
tar -C "$WORK" -cf - runtime.db manifest.txt | zstd -q -T1 -3 -o "$ARCHIVE"
SHA="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
printf '%s  %s\n' "$SHA" "$(basename "$ARCHIVE")" > "${ARCHIVE}.sha256"

R2_STATE="activation_pending"
REMOTE_SHA=""
if [[ -n "$R2_REMOTE" ]] && command -v rclone >/dev/null 2>&1 && [[ "$R2_REMOTE" != REPLACE_* ]]; then
  REMOTE_KEY="${R2_REMOTE%/}/$(basename "$ARCHIVE")"
  rclone copyto "$ARCHIVE" "$REMOTE_KEY" --immutable --retries 3 --low-level-retries 5
  rclone copyto "${ARCHIVE}.sha256" "${REMOTE_KEY}.sha256" --immutable --retries 3 --low-level-retries 5
  REMOTE_SHA="$(rclone cat "${REMOTE_KEY}.sha256" | awk '{print $1}')"
  [[ "$REMOTE_SHA" == "$SHA" ]] || { echo 'BACKUP=FAIL remote_hash_mismatch'; exit 1; }
  R2_STATE="verified"
elif [[ "$ALLOW_LOCAL_ONLY" != "true" ]]; then
  echo 'BACKUP=FAIL r2_activation_required'
  exit 2
fi

# Count-based local retention; never waits for an age window.
mapfile -t archives < <(find "$OUT_DIR" -maxdepth 1 -type f -name 'cyberboss-*.tar.zst' -printf '%T@ %p\n' | sort -nr | awk '{print $2}')
if ((${#archives[@]} > MAX_LOCAL)); then
  for old in "${archives[@]:MAX_LOCAL}"; do
    rm -f -- "$old" "${old}.sha256"
  done
fi

printf 'BACKUP=PASS\nSNAPSHOT_ID=%s\nLOCAL_SHA256=%s\nR2_STATE=%s\nR2_SHA256=%s\nCANONICAL_OBJECT_SHA256=%s\nOCI_STATE=%s\n' \
  "$ID" "$SHA" "$R2_STATE" "${REMOTE_SHA:-not_verified}" "$CANONICAL_OBJECT_SHA256" "${CB_OCI_STATE:-activation_pending}"
