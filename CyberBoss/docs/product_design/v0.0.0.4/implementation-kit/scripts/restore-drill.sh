#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

R2_REMOTE="${CB_R2_REMOTE:-}"
RESTORE_ROOT="${CB_RESTORE_ROOT:-/var/lib/cyberboss/restore-tests}"
SNAPSHOT=""
TARGET=""
NETWORK_DISABLED=0

while (($#)); do
  case "$1" in
    --snapshot) SNAPSHOT="${2:-}"; shift 2 ;;
    --target) TARGET="${2:-}"; shift 2 ;;
    --network-disabled) NETWORK_DISABLED=1; shift ;;
    *) echo "RESTORE=STOP unknown_arg:$1"; exit 2 ;;
  esac
done

[[ -n "$SNAPSHOT" ]] || { echo 'RESTORE=STOP snapshot_required'; exit 2; }
[[ -n "$TARGET" ]] || TARGET="$RESTORE_ROOT/$(date -u +%Y%m%dT%H%M%SZ)"
case "$TARGET" in "$RESTORE_ROOT"/*) ;; *) echo 'RESTORE=STOP target_outside_restore_root'; exit 2;; esac
[[ ! -e "$TARGET" ]] || { echo 'RESTORE=STOP target_exists'; exit 2; }

for cmd in sqlite3 tar zstd sha256sum; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "RESTORE=STOP missing:$cmd"; exit 2; }
done
mkdir -p "$TARGET"

ARCHIVE="$TARGET/snapshot.tar.zst"
SHA_FILE="$ARCHIVE.sha256"
if [[ -f "$SNAPSHOT" ]]; then
  cp -- "$SNAPSHOT" "$ARCHIVE"
  cp -- "${SNAPSHOT}.sha256" "$SHA_FILE"
else
  [[ -n "$R2_REMOTE" ]] || { echo 'RESTORE=STOP r2_remote_unconfigured'; exit 2; }
  command -v rclone >/dev/null 2>&1 || { echo 'RESTORE=STOP missing:rclone'; exit 2; }
  KEY="$SNAPSHOT"
  [[ "$KEY" == *:* ]] || KEY="${R2_REMOTE%/}/${SNAPSHOT#/}"
  rclone copyto "$KEY" "$ARCHIVE"
  rclone copyto "${KEY}.sha256" "$SHA_FILE"
fi

EXPECTED="$(awk '{print $1}' "$SHA_FILE")"
ACTUAL="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
[[ -n "$EXPECTED" && "$EXPECTED" == "$ACTUAL" ]] || { echo 'RESTORE=FAIL hash_mismatch'; exit 1; }

mkdir -p "$TARGET/extracted"
zstd -q -dc "$ARCHIVE" | tar -C "$TARGET/extracted" -xf -
DB="$TARGET/extracted/runtime.db"
[[ -r "$DB" ]] || { echo 'RESTORE=FAIL runtime_db_missing'; exit 1; }
INTEGRITY="$(sqlite3 "$DB" 'PRAGMA integrity_check;' 2>/dev/null || true)"
[[ "$INTEGRITY" == "ok" ]] || { echo "RESTORE=FAIL sqlite_integrity:$INTEGRITY"; exit 1; }

JOBS="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM jobs;' 2>/dev/null || echo 0)"
EVENTS="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM job_events;' 2>/dev/null || echo 0)"
OUTBOX="$(sqlite3 "$DB" 'SELECT COUNT(*) FROM outbox_messages;' 2>/dev/null || echo 0)"

cat > "$TARGET/restore-report.txt" <<REPORT
restore=PASS
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
archive_sha256=$ACTUAL
sqlite_integrity=$INTEGRITY
jobs=$JOBS
job_events=$EVENTS
outbox=$OUTBOX
network_disabled=$NETWORK_DISABLED
promoted=false
REPORT

printf 'RESTORE=PASS\nTARGET=%s\nSHA256=%s\nJOBS=%s\nEVENTS=%s\nOUTBOX=%s\nPROMOTED=false\n' \
  "$TARGET" "$ACTUAL" "$JOBS" "$EVENTS" "$OUTBOX"
