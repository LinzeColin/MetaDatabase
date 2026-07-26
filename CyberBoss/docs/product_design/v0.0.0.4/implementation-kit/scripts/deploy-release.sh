#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$EUID" -eq 0 ]] || { echo 'DEPLOY=STOP root_required'; exit 2; }
COMMIT=""
ARTIFACT=""
CHECKSUM=""
while (($#)); do
  case "$1" in
    --commit) COMMIT="${2:-}"; shift 2 ;;
    --artifact) ARTIFACT="${2:-}"; shift 2 ;;
    --checksum) CHECKSUM="${2:-}"; shift 2 ;;
    *) echo "DEPLOY=STOP unknown_arg:$1"; exit 2 ;;
  esac
done
[[ "$COMMIT" =~ ^[0-9a-fA-F]{7,40}$ ]] || { echo 'DEPLOY=STOP valid_commit_required'; exit 2; }
[[ -r "$ARTIFACT" ]] || { echo 'DEPLOY=STOP artifact_unreadable'; exit 2; }
[[ -r "$CHECKSUM" ]] || { echo 'DEPLOY=STOP checksum_unreadable'; exit 2; }

APP_ROOT="${CB_APP_ROOT:-/opt/cyberboss-cloud}"
APP_USER="${CB_APP_USER:-cyberboss}"
APP_GROUP="${CB_APP_GROUP:-cyberboss}"
SERVICE="${CB_SYSTEMD_SERVICE:-cyberboss-cloud.service}"
INCOMING_ROOT="${CB_INCOMING_ROOT:-/var/lib/cyberboss/incoming}"
RELEASE="$APP_ROOT/releases/$COMMIT"
CURRENT="$APP_ROOT/current"
PREVIOUS="$APP_ROOT/previous"

INCOMING_REAL="$(realpath "$INCOMING_ROOT")"
ARTIFACT_REAL="$(realpath "$ARTIFACT")"
CHECKSUM_REAL="$(realpath "$CHECKSUM")"
case "$ARTIFACT_REAL" in
  "$INCOMING_REAL"/*) ;;
  *) echo 'DEPLOY=STOP artifact_outside_incoming_root'; exit 2 ;;
esac
case "$CHECKSUM_REAL" in
  "$INCOMING_REAL"/*) ;;
  *) echo 'DEPLOY=STOP checksum_outside_incoming_root'; exit 2 ;;
esac

EXPECTED_SHA="$(awk 'NF {print $1; exit}' "$CHECKSUM_REAL")"
[[ "$EXPECTED_SHA" =~ ^[0-9a-fA-F]{64}$ ]] || { echo 'DEPLOY=STOP checksum_invalid'; exit 2; }
ACTUAL_SHA="$(sha256sum "$ARTIFACT_REAL" | awk '{print $1}')"
[[ "${ACTUAL_SHA,,}" == "${EXPECTED_SHA,,}" ]] || { echo 'DEPLOY=FAIL artifact_hash_mismatch'; exit 1; }

[[ ! -e "$RELEASE" ]] || { echo 'DEPLOY=STOP release_exists'; exit 2; }
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0755 "$APP_ROOT/releases"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0755 "$RELEASE"

DEPLOYED=0
cleanup_incomplete_release() {
  if (( DEPLOYED == 0 )) && [[ -d "$RELEASE" ]]; then
    rm -rf -- "$RELEASE"
  fi
}
trap cleanup_incomplete_release EXIT

runuser -u "$APP_USER" -- tar --extract --zstd --file "$ARTIFACT_REAL" \
  --directory "$RELEASE" --no-same-owner --no-same-permissions
[[ -r "$RELEASE/release-manifest.json" ]] || { echo 'DEPLOY=FAIL release_manifest_missing'; exit 1; }
ACTUAL="$(
  node -e "
    const fs = require('node:fs');
    const value = JSON.parse(fs.readFileSync(process.argv[1], 'utf8')).commit;
    if (typeof value !== 'string') process.exit(2);
    process.stdout.write(value);
  " "$RELEASE/release-manifest.json"
)"
[[ "$ACTUAL" == "$COMMIT" || "$ACTUAL" == "$COMMIT"* ]] || { echo 'DEPLOY=FAIL commit_mismatch'; exit 1; }

runuser -u "$APP_USER" -- bash -lc "cd '$RELEASE' && npm ci && npm test"

# Back up before migration/deploy when a runtime DB already exists. Missing R2 credentials do not block: local verified snapshot is allowed and R2 remains activation_pending.
if [[ -r "${CB_RUNTIME_DB:-/var/lib/cyberboss/runtime.db}" ]]; then
  CB_BACKUP_ALLOW_LOCAL_ONLY=true "$RELEASE/implementation-kit/scripts/backup-runtime.sh"
fi

if [[ -n "${CB_MIGRATE_COMMAND:-}" && "${CB_MIGRATE_COMMAND}" != "true" ]]; then
  runuser -u "$APP_USER" -- bash -lc "cd '$RELEASE' && ${CB_MIGRATE_COMMAND}"
fi

if [[ -L "$CURRENT" ]]; then
  OLD="$(readlink -f "$CURRENT")"
  ln -sfn "$OLD" "$PREVIOUS"
fi
ln -sfn "$RELEASE" "$CURRENT"
systemctl restart "$SERVICE"

if ! "$CURRENT/implementation-kit/scripts/wait-ready.sh"; then
  if [[ -L "$PREVIOUS" ]]; then
    ln -sfn "$(readlink -f "$PREVIOUS")" "$CURRENT"
    systemctl restart "$SERVICE"
  fi
  echo 'DEPLOY=FAIL health_check_rollback_attempted'
  exit 1
fi

DEPLOYED=1
printf 'DEPLOY=PASS\nCOMMIT=%s\nPREVIOUS=%s\n' "$ACTUAL" "$(readlink -f "$PREVIOUS" 2>/dev/null || echo none)"
