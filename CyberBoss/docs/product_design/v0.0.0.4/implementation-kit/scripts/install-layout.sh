#!/usr/bin/env bash
set -Eeuo pipefail

[[ "$EUID" -eq 0 ]] || { echo 'INSTALL=FAIL root_required'; exit 2; }
ENABLE=0
START=0
while (($#)); do
  case "$1" in
    --enable) ENABLE=1; shift ;;
    --start) ENABLE=1; START=1; shift ;;
    *) echo "INSTALL=FAIL unknown_arg:$1"; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
USER_NAME="${CB_APP_USER:-cyberboss}"
GROUP_NAME="${CB_APP_GROUP:-cyberboss}"
APP_ROOT="${CB_APP_ROOT:-/opt/cyberboss-cloud}"
STATE_ROOT="${CYBERBOSS_STATE_DIR:-/var/lib/cyberboss}"
WORKSPACE_ROOT="${CYBERBOSS_WORKSPACE_ROOT:-/srv/cyberboss-workspaces}"
CONFIG_ROOT="/etc/cyberboss"

getent group "$GROUP_NAME" >/dev/null 2>&1 || groupadd --system "$GROUP_NAME"
id "$USER_NAME" >/dev/null 2>&1 || useradd --system --gid "$GROUP_NAME" --home-dir "$STATE_ROOT" --shell /usr/sbin/nologin "$USER_NAME"

install -d -o root -g root -m 0755 "$APP_ROOT" "$APP_ROOT/releases"
install -d -o root -g "$GROUP_NAME" -m 0750 "$APP_ROOT/shared"
install -d -o "$USER_NAME" -g "$GROUP_NAME" -m 0750 \
  "$STATE_ROOT" "$STATE_ROOT/locks" "$STATE_ROOT/status" "$STATE_ROOT/tmp" \
  "$STATE_ROOT/snapshots" "$STATE_ROOT/restore-tests" "$STATE_ROOT/canonical-spool" \
  "$STATE_ROOT/incoming"
install -d -o "$USER_NAME" -g "$GROUP_NAME" -m 0750 "$WORKSPACE_ROOT"
install -d -o root -g "$GROUP_NAME" -m 0750 "$CONFIG_ROOT" "$CONFIG_ROOT/credentials"

if [[ ! -e "$CONFIG_ROOT/cyberboss.env" ]]; then
  install -o root -g "$GROUP_NAME" -m 0640 "$KIT_ROOT/config/cyberboss.env.example" "$CONFIG_ROOT/cyberboss.env"
  echo 'ACTION_REQUIRED=edit_/etc/cyberboss/cyberboss.env_and_replace_placeholders'
fi
if [[ ! -e "$CONFIG_ROOT/workspaces.json" ]]; then
  install -o root -g "$GROUP_NAME" -m 0640 "$KIT_ROOT/config/workspaces.json.example" "$CONFIG_ROOT/workspaces.json"
  echo 'ACTION_REQUIRED=verify_/etc/cyberboss/workspaces.json'
fi

for unit in "$KIT_ROOT"/systemd/*.{service,timer}; do
  [[ -e "$unit" ]] || continue
  install -o root -g root -m 0644 "$unit" "/etc/systemd/system/$(basename "$unit")"
done

"$SCRIPT_DIR/select-resource-profile.sh" \
  --write "$CONFIG_ROOT/resource-profile.env" \
  --systemd-dropin /etc/systemd/system/cyberboss-cloud.service.d/20-resource-profile.conf >/dev/null
systemctl daemon-reload

if (( ENABLE )); then
  systemctl enable cyberboss-cloud.service cyberboss-status.timer cyberboss-backup.timer cyberboss-selfheal.timer
fi
if (( START )); then
  if grep -Eq 'REPLACE_' "$CONFIG_ROOT/cyberboss.env"; then
    echo 'INSTALL=ACTIVATION_PENDING unresolved_environment_placeholders; units_installed_not_started'
    exit 0
  fi
  systemctl start cyberboss-cloud.service cyberboss-status.timer cyberboss-backup.timer cyberboss-selfheal.timer
fi

printf 'INSTALL=PASS\nUSER=%s\nAPP_ROOT=%s\nSTATE_ROOT=%s\nWORKSPACE_ROOT=%s\nENABLED=%s\nSTARTED=%s\n' \
  "$USER_NAME" "$APP_ROOT" "$STATE_ROOT" "$WORKSPACE_ROOT" "$ENABLE" "$START"
