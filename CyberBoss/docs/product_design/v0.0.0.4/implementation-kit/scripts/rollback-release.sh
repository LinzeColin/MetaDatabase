#!/usr/bin/env bash
set -Eeuo pipefail
[[ "$EUID" -eq 0 ]] || { echo 'ROLLBACK=STOP root_required'; exit 2; }

APP_ROOT="${CB_APP_ROOT:-/opt/cyberboss-cloud}"
SERVICE="${CB_SYSTEMD_SERVICE:-cyberboss-cloud.service}"
CURRENT="$APP_ROOT/current"
PREVIOUS="$APP_ROOT/previous"
[[ -L "$PREVIOUS" ]] || { echo 'ROLLBACK=STOP previous_missing'; exit 2; }
TARGET="$(readlink -f "$PREVIOUS")"
[[ -d "$TARGET" ]] || { echo 'ROLLBACK=STOP previous_target_missing'; exit 2; }
OLD="$(readlink -f "$CURRENT" 2>/dev/null || true)"
ln -sfn "$TARGET" "$CURRENT"
systemctl restart "$SERVICE"
if ! "$CURRENT/implementation-kit/scripts/wait-ready.sh"; then
  [[ -n "$OLD" && -d "$OLD" ]] && ln -sfn "$OLD" "$CURRENT" && systemctl restart "$SERVICE"
  echo 'ROLLBACK=FAIL previous_unhealthy_reverted_to_original'
  exit 1
fi
ln -sfn "$OLD" "$PREVIOUS"
printf 'ROLLBACK=PASS\nACTIVE=%s\nPREVIOUS=%s\n' "$TARGET" "$OLD"
