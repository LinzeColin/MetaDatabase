#!/usr/bin/env bash
set -Eeuo pipefail

MODE=check
RELEASE_ID=
while (($#)); do
  case "$1" in
    --check)
      MODE=check
      shift
      ;;
    --apply)
      MODE=apply
      shift
      ;;
    --release-id)
      (($# >= 2)) || { echo 'INSTALL=FAIL missing_release_id'; exit 2; }
      RELEASE_ID="$2"
      shift 2
      ;;
    *)
      echo "INSTALL=FAIL unknown_arg:$1"
      exit 2
      ;;
  esac
done

[[ "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'INSTALL=FAIL release_id_must_be_full_lowercase_git_sha'
  exit 2
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
UNIT_SOURCE="$KIT_ROOT/systemd/cyberboss-cloud.service"
JOURNAL_SOURCE="$KIT_ROOT/config/cyberboss-journald.conf"
ENV_SOURCE="$KIT_ROOT/config/cyberboss.env.example"
WORKSPACES_SOURCE="$KIT_ROOT/config/workspaces.json.example"

USER_NAME=cyberboss
GROUP_NAME=cyberboss
APP_ROOT=/opt/cyberboss-cloud
STATE_ROOT=/var/lib/cyberboss
WORKSPACE_ROOT=/srv/cyberboss-workspaces
CONFIG_ROOT=/etc/cyberboss
UNIT_PATH=/etc/systemd/system/cyberboss-cloud.service
DROPIN_PATH=/etc/systemd/system/cyberboss-cloud.service.d/20-resource-profile.conf
JOURNAL_DIR=/etc/systemd/journald@cyberboss.conf.d
JOURNAL_PATH="$JOURNAL_DIR/20-limits.conf"
RELEASE_PATH="$APP_ROOT/releases/$RELEASE_ID"

fail() {
  echo "INSTALL=FAIL $1"
  exit "${2:-1}"
}

hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$1" | awk '{print $1}'
  else
    fail 'sha256_tool_missing' 2
  fi
}

for path in \
  "$UNIT_SOURCE" "$JOURNAL_SOURCE" "$ENV_SOURCE" "$WORKSPACES_SOURCE" \
  "$SCRIPT_DIR/select-resource-profile.sh" "$SCRIPT_DIR/resource_profile.py"; do
  [[ -f "$path" ]] || fail "source_missing:$(basename "$path")" 2
done
for directive in \
  'User=cyberboss' \
  'Group=cyberboss' \
  'KillMode=control-group' \
  'ExecStart=/usr/bin/flock -n /var/lib/cyberboss/locks/bridge.lock' \
  'LogNamespace=cyberboss' \
  'ProtectSystem=strict' \
  'ReadWritePaths=/var/lib/cyberboss /srv/cyberboss-workspaces'; do
  grep -Fq "$directive" "$UNIT_SOURCE" || fail "unit_contract_missing:$directive" 2
done
grep -Fq '@CB_MAX_LOG_BYTES@' "$JOURNAL_SOURCE" ||
  fail 'journal_template_missing_log_cap_placeholder' 2

if [[ "$MODE" == check ]]; then
  printf 'INSTALL_CHECK=PASS release_id=%s live_commands=false persistent_writes=false\n' \
    "$RELEASE_ID"
  exit 0
fi

[[ "$EUID" -eq 0 ]] || fail 'root_required_for_apply' 2
for command in \
  awk cat chmod chown cut find flock getent grep groupadd install ln mv \
  python3 readlink sed stat systemctl systemd-analyze tail useradd; do
  command -v "$command" >/dev/null 2>&1 || fail "required_command_missing:$command" 2
done
if ! command -v sha256sum >/dev/null 2>&1 &&
  ! command -v shasum >/dev/null 2>&1; then
  fail 'sha256_tool_missing' 2
fi
[[ -d /run/systemd/system ]] || fail 'systemd_runtime_unavailable' 2

if systemctl is-active --quiet cyberboss-cloud.service; then
  fail 'existing_unit_active'
fi
if systemctl is-enabled --quiet cyberboss-cloud.service 2>/dev/null; then
  fail 'existing_unit_enabled'
fi

if getent group "$GROUP_NAME" >/dev/null 2>&1; then
  [[ "$(getent group "$GROUP_NAME" | cut -d: -f3)" != 0 ]] ||
    fail 'group_gid_must_not_be_root'
else
  groupadd --system "$GROUP_NAME"
fi

if getent passwd "$USER_NAME" >/dev/null 2>&1; then
  IFS=: read -r _ _ user_uid user_gid _ user_home user_shell < <(
    getent passwd "$USER_NAME"
  )
  [[ "$user_uid" != 0 ]] || fail 'user_uid_must_not_be_root'
  [[ "$user_gid" == "$(getent group "$GROUP_NAME" | cut -d: -f3)" ]] ||
    fail 'existing_user_group_mismatch'
  [[ "$user_home" == "$STATE_ROOT" ]] || fail 'existing_user_home_mismatch'
  [[ "$user_shell" == /usr/sbin/nologin || "$user_shell" == /sbin/nologin ]] ||
    fail 'existing_user_shell_mismatch'
else
  useradd --system --gid "$GROUP_NAME" --home-dir "$STATE_ROOT" \
    --shell /usr/sbin/nologin "$USER_NAME"
fi

install -d -o root -g root -m 0755 "$APP_ROOT" "$APP_ROOT/releases"
install -d -o root -g "$GROUP_NAME" -m 0750 "$APP_ROOT/shared"
install -d -o "$USER_NAME" -g "$GROUP_NAME" -m 0750 \
  "$STATE_ROOT" "$STATE_ROOT/locks" "$STATE_ROOT/status" "$STATE_ROOT/tmp" \
  "$STATE_ROOT/snapshots" "$STATE_ROOT/restore-tests" \
  "$STATE_ROOT/canonical-spool" "$STATE_ROOT/incoming" "$WORKSPACE_ROOT"
install -d -o root -g root -m 0700 "$STATE_ROOT/install-backups"
install -d -o root -g "$GROUP_NAME" -m 0750 "$CONFIG_ROOT"
install -d -o root -g root -m 0700 "$CONFIG_ROOT/credentials"

if [[ ! -e "$CONFIG_ROOT/cyberboss.env" ]]; then
  install -o root -g root -m 0600 "$ENV_SOURCE" "$CONFIG_ROOT/cyberboss.env"
  echo 'ACTION_REQUIRED=replace_environment_placeholders_before_runtime_activation'
else
  [[ -f "$CONFIG_ROOT/cyberboss.env" && ! -L "$CONFIG_ROOT/cyberboss.env" ]] ||
    fail 'existing_environment_file_not_regular'
  chown root:root "$CONFIG_ROOT/cyberboss.env"
  chmod 0600 "$CONFIG_ROOT/cyberboss.env"
fi
if [[ ! -e "$CONFIG_ROOT/workspaces.json" ]]; then
  install -o root -g "$GROUP_NAME" -m 0640 \
    "$WORKSPACES_SOURCE" "$CONFIG_ROOT/workspaces.json"
else
  [[ -f "$CONFIG_ROOT/workspaces.json" && ! -L "$CONFIG_ROOT/workspaces.json" ]] ||
    fail 'existing_workspace_config_not_regular'
  chown root:"$GROUP_NAME" "$CONFIG_ROOT/workspaces.json"
  chmod 0640 "$CONFIG_ROOT/workspaces.json"
fi

RELEASE_EXISTS=false
if [[ -e "$RELEASE_PATH" ]]; then
  [[ -d "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]] ||
    fail 'existing_release_not_directory'
  RELEASE_EXISTS=true
  for path in \
    "$CONFIG_ROOT/resource-profile.env" "$DROPIN_PATH" "$JOURNAL_PATH"; do
    [[ -f "$path" && ! -L "$path" ]] ||
      fail "existing_release_support_file_invalid:$path"
  done
else
  "$SCRIPT_DIR/select-resource-profile.sh" \
    --write "$CONFIG_ROOT/resource-profile.env" \
    --systemd-dropin "$DROPIN_PATH" >/dev/null
  chown root:root "$CONFIG_ROOT/resource-profile.env" "$DROPIN_PATH"
  chmod 0600 "$CONFIG_ROOT/resource-profile.env"
  chmod 0644 "$DROPIN_PATH"
fi

LOG_CAP="$(
  awk -F= '$1 == "CB_MAX_LOG_BYTES" {gsub(/[^0-9]/, "", $2); print $2}' \
    "$CONFIG_ROOT/resource-profile.env"
)"
[[ "$LOG_CAP" =~ ^[1-9][0-9]*$ ]] || fail 'resource_profile_log_cap_invalid'
grep -Fxq 'CB_RESOURCE_ACTIVATION_SAFE=true' "$CONFIG_ROOT/resource-profile.env" ||
  fail 'resource_profile_not_activation_safe'
grep -Fxq 'CB_RESOURCE_GUARD_STATE=recover' "$CONFIG_ROOT/resource-profile.env" ||
  fail 'resource_profile_not_recover'
if [[ "$RELEASE_EXISTS" == false ]]; then
  install -d -o root -g root -m 0755 "$JOURNAL_DIR"
  JOURNAL_TMP="$JOURNAL_DIR/.20-limits.conf.$$.tmp"
  trap 'rm -f -- "$JOURNAL_TMP"' EXIT
  sed "s/@CB_MAX_LOG_BYTES@/$LOG_CAP/g" "$JOURNAL_SOURCE" >"$JOURNAL_TMP"
  grep -Fq '@CB_MAX_LOG_BYTES@' "$JOURNAL_TMP" &&
    fail 'journal_log_cap_substitution_failed'
  install -o root -g root -m 0644 "$JOURNAL_TMP" "$JOURNAL_PATH"
  rm -f -- "$JOURNAL_TMP"
fi

UNIT_HASH="$(hash_file "$UNIT_SOURCE")"
JOURNAL_HASH="$(hash_file "$JOURNAL_PATH")"
DROPIN_HASH="$(hash_file "$DROPIN_PATH")"
if [[ "$RELEASE_EXISTS" == true ]]; then
  python3 - "$RELEASE_PATH/install-layout.json" "$RELEASE_ID" \
    "$UNIT_HASH" "$JOURNAL_HASH" "$DROPIN_HASH" "$LOG_CAP" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = {
    "schema_version": 1,
    "kind": "cb100-host-layout",
    "release_id": sys.argv[2],
    "unit_sha256": sys.argv[3],
    "journald_sha256": sys.argv[4],
    "resource_dropin_sha256": sys.argv[5],
    "max_log_bytes": int(sys.argv[6]),
    "unit_enabled": False,
    "runtime_installed": False,
    "network_routes_created": 0,
}
try:
    value = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as error:
    raise SystemExit(f"INSTALL=FAIL existing_release_manifest_invalid:{type(error).__name__}")
for key, expected_value in expected.items():
    if value.get(key) != expected_value:
        raise SystemExit(f"INSTALL=FAIL existing_release_mismatch:{key}")
print("RELEASE_IDEMPOTENCY=PASS")
PY
  [[ "$(hash_file "$RELEASE_PATH/systemd/cyberboss-cloud.service")" == "$UNIT_HASH" ]] ||
    fail 'existing_release_unit_hash_mismatch'
  [[ "$(hash_file "$RELEASE_PATH/systemd/cyberboss-journald.conf")" == "$JOURNAL_HASH" ]] ||
    fail 'existing_release_journal_hash_mismatch'
  [[ "$(hash_file "$RELEASE_PATH/systemd/20-resource-profile.conf")" == "$DROPIN_HASH" ]] ||
    fail 'existing_release_dropin_hash_mismatch'
else
  STAGING="$APP_ROOT/releases/.cb100-$RELEASE_ID-$$"
  [[ "$STAGING" == "$APP_ROOT/releases/.cb100-"* ]] ||
    fail 'unsafe_staging_path'
  cleanup_staging() {
    if [[ -d "$STAGING" ]]; then
      find "$STAGING" -depth -delete
    fi
  }
  trap 'cleanup_staging; rm -f -- "$JOURNAL_TMP"' EXIT
  install -d -o root -g root -m 0755 \
    "$STAGING/systemd" "$STAGING/implementation-kit/scripts"
  install -o root -g root -m 0644 \
    "$UNIT_SOURCE" "$STAGING/systemd/cyberboss-cloud.service"
  install -o root -g root -m 0644 \
    "$JOURNAL_PATH" "$STAGING/systemd/cyberboss-journald.conf"
  install -o root -g root -m 0644 \
    "$DROPIN_PATH" "$STAGING/systemd/20-resource-profile.conf"
  cat >"$STAGING/implementation-kit/scripts/run-cyberboss.sh" <<'SCRIPT'
#!/usr/bin/env bash
set -Eeuo pipefail
[[ "${CB_LAYOUT_RELEASE_KIND:-cb100-host-layout}" == cb100-host-layout ]] || {
  echo 'CB100_STAGING_PROBE=FAIL invalid_release_kind'
  exit 2
}
echo 'CB100_STAGING_PROBE=READY network_listeners=0 runtime_adapters=0'
exec /usr/bin/tail -f /dev/null
SCRIPT
  chmod 0555 "$STAGING/implementation-kit/scripts/run-cyberboss.sh"
  python3 - "$STAGING/install-layout.json" "$RELEASE_ID" \
    "$UNIT_HASH" "$JOURNAL_HASH" "$DROPIN_HASH" "$LOG_CAP" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
value = {
    "schema_version": 1,
    "kind": "cb100-host-layout",
    "release_id": sys.argv[2],
    "unit_sha256": sys.argv[3],
    "journald_sha256": sys.argv[4],
    "resource_dropin_sha256": sys.argv[5],
    "max_log_bytes": int(sys.argv[6]),
    "app_user": "cyberboss",
    "app_group": "cyberboss",
    "unit": "cyberboss-cloud.service",
    "unit_enabled": False,
    "runtime_installed": False,
    "network_routes_created": 0,
}
path.write_text(
    json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
PY
  chown -R root:root "$STAGING"
  find "$STAGING" -type d -exec chmod 0555 {} +
  find "$STAGING" -type f ! -path '*/run-cyberboss.sh' -exec chmod 0444 {} +
  mv "$STAGING" "$RELEASE_PATH"
  trap 'rm -f -- "$JOURNAL_TMP"' EXIT
  echo 'RELEASE_CREATE=PASS'
fi

PREVIOUS_CURRENT=absent
if [[ -e "$APP_ROOT/current" || -L "$APP_ROOT/current" ]]; then
  [[ -L "$APP_ROOT/current" ]] || fail 'current_pointer_not_symlink'
  PREVIOUS_CURRENT="$(readlink "$APP_ROOT/current")"
fi
CURRENT_BACKUP="$STATE_ROOT/install-backups/cb100-previous-current"
if [[ ! -e "$CURRENT_BACKUP" ]]; then
  CURRENT_BACKUP_TMP="$STATE_ROOT/install-backups/.cb100-previous-current-$$"
  printf '%s\n' "$PREVIOUS_CURRENT" >"$CURRENT_BACKUP_TMP"
  chown root:root "$CURRENT_BACKUP_TMP"
  chmod 0600 "$CURRENT_BACKUP_TMP"
  mv -T "$CURRENT_BACKUP_TMP" "$CURRENT_BACKUP"
else
  [[ -f "$CURRENT_BACKUP" && ! -L "$CURRENT_BACKUP" ]] ||
    fail 'existing_current_backup_not_regular'
  [[ "$(stat -c '%U:%G:%a' "$CURRENT_BACKUP")" == root:root:600 ]] ||
    fail 'existing_current_backup_mode_mismatch'
fi
CURRENT_TMP="$APP_ROOT/.current-$RELEASE_ID-$$"
ln -s "releases/$RELEASE_ID" "$CURRENT_TMP"
mv -Tf "$CURRENT_TMP" "$APP_ROOT/current"

install -o root -g root -m 0644 \
  "$RELEASE_PATH/systemd/cyberboss-cloud.service" "$UNIT_PATH"
systemctl daemon-reload
systemd-analyze verify "$UNIT_PATH" >/dev/null
systemctl is-active --quiet cyberboss-cloud.service &&
  fail 'unit_must_remain_inactive'
systemctl is-enabled --quiet cyberboss-cloud.service 2>/dev/null &&
  fail 'unit_must_remain_disabled'

printf 'INSTALL=PASS\nRELEASE_ID=%s\nUSER=%s\nAPP_ROOT=%s\nSTATE_ROOT=%s\n' \
  "$RELEASE_ID" "$USER_NAME" "$APP_ROOT" "$STATE_ROOT"
printf 'WORKSPACE_ROOT=%s\nUNIT_ENABLED=false\nUNIT_ACTIVE=false\n' "$WORKSPACE_ROOT"
printf 'RUNTIME_INSTALLED=false\nNETWORK_ROUTES_CREATED=0\n'
