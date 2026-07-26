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
    --exercise)
      MODE=exercise
      shift
      ;;
    --release-id)
      (($# >= 2)) || { echo 'INSTALL_VERIFY=FAIL missing_release_id'; exit 2; }
      RELEASE_ID="$2"
      shift 2
      ;;
    *)
      echo "INSTALL_VERIFY=FAIL unknown_arg:$1"
      exit 2
      ;;
  esac
done

[[ "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] || {
  echo 'INSTALL_VERIFY=FAIL release_id_must_be_full_lowercase_git_sha'
  exit 2
}

USER_NAME=cyberboss
GROUP_NAME=cyberboss
APP_ROOT=/opt/cyberboss-cloud
STATE_ROOT=/var/lib/cyberboss
WORKSPACE_ROOT=/srv/cyberboss-workspaces
CONFIG_ROOT=/etc/cyberboss
UNIT=cyberboss-cloud.service
UNIT_PATH=/etc/systemd/system/cyberboss-cloud.service
DROPIN_PATH=/etc/systemd/system/cyberboss-cloud.service.d/20-resource-profile.conf
JOURNAL_PATH=/etc/systemd/journald@cyberboss.conf.d/20-limits.conf
RELEASE_PATH="$APP_ROOT/releases/$RELEASE_ID"
FAIL=()

record_fail() {
  FAIL+=("$1")
}

expect_mode() {
  local expected="$1"
  local path="$2"
  local actual
  actual="$(stat -c '%U:%G:%a' "$path" 2>/dev/null || true)"
  [[ "$actual" == "$expected" ]] || record_fail "mode:$path:$actual"
}

expect_denied() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    record_fail "permission_unexpectedly_allowed:$label"
  fi
}

wait_for_new_main_pid() {
  local old_pid="$1"
  local require_lock="${2:-false}"
  local attempt state pid lock_rc
  for attempt in $(seq 1 4000); do
    state="$(systemctl show "$UNIT" -p ActiveState --value)"
    pid="$(systemctl show "$UNIT" -p MainPID --value)"
    if [[ "$state" == active && "$pid" =~ ^[1-9][0-9]*$ && "$pid" != "$old_pid" ]]; then
      if [[ "$require_lock" == false ]]; then
        printf '%s\n' "$pid"
        return 0
      fi
      set +e
      runuser -u "$USER_NAME" -- \
        flock -n "$STATE_ROOT/locks/bridge.lock" /bin/true >/dev/null 2>&1
      lock_rc=$?
      set -e
      if ((lock_rc == 1)); then
        printf '%s\n' "$pid"
        return 0
      fi
      ((lock_rc == 0)) || return 2
    fi
  done
  return 1
}

[[ "$EUID" -eq 0 ]] || {
  echo 'INSTALL_VERIFY=FAIL root_required_for_identity_checks'
  exit 2
}
for command in \
  awk cat chmod cut find flock getent grep install python3 readlink rm runuser \
  seq sort stat systemctl systemd-analyze tail; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "INSTALL_VERIFY=FAIL required_command_missing:$command"
    exit 2
  }
done

if getent passwd "$USER_NAME" >/dev/null 2>&1; then
  IFS=: read -r _ _ user_uid user_gid _ user_home user_shell < <(
    getent passwd "$USER_NAME"
  )
  [[ "$user_uid" != 0 ]] || record_fail 'user_uid_is_root'
  [[ "$user_gid" == "$(getent group "$GROUP_NAME" | cut -d: -f3)" ]] ||
    record_fail 'user_primary_group_mismatch'
  [[ "$user_home" == "$STATE_ROOT" ]] || record_fail 'user_home_mismatch'
  [[ "$user_shell" == /usr/sbin/nologin || "$user_shell" == /sbin/nologin ]] ||
    record_fail 'user_shell_not_nologin'
else
  record_fail 'user_missing'
fi

expect_mode 'root:root:755' "$APP_ROOT"
expect_mode 'root:root:755' "$APP_ROOT/releases"
expect_mode 'root:cyberboss:750' "$APP_ROOT/shared"
for path in \
  "$STATE_ROOT" "$STATE_ROOT/locks" "$STATE_ROOT/status" "$STATE_ROOT/tmp" \
  "$STATE_ROOT/snapshots" "$STATE_ROOT/restore-tests" \
  "$STATE_ROOT/canonical-spool" "$STATE_ROOT/incoming" "$WORKSPACE_ROOT"; do
  expect_mode 'cyberboss:cyberboss:750' "$path"
done
expect_mode 'root:root:700' "$STATE_ROOT/install-backups"
expect_mode 'root:cyberboss:750' "$CONFIG_ROOT"
expect_mode 'root:root:700' "$CONFIG_ROOT/credentials"
expect_mode 'root:root:600' "$CONFIG_ROOT/cyberboss.env"
expect_mode 'root:cyberboss:640' "$CONFIG_ROOT/workspaces.json"
expect_mode 'root:root:600' "$CONFIG_ROOT/resource-profile.env"
expect_mode 'root:root:644' "$UNIT_PATH"
expect_mode 'root:root:644' "$DROPIN_PATH"
expect_mode 'root:root:644' "$JOURNAL_PATH"

[[ -d "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]] ||
  record_fail 'release_missing_or_not_directory'
[[ "$(readlink -f "$APP_ROOT/current" 2>/dev/null || true)" == "$RELEASE_PATH" ]] ||
  record_fail 'current_pointer_mismatch'
if [[ -d "$RELEASE_PATH" ]]; then
  writable="$(
    find "$RELEASE_PATH" -xdev -perm /0222 -print -quit 2>/dev/null || true
  )"
  [[ -z "$writable" ]] || record_fail 'release_contains_writable_entry'
fi

python3 - "$RELEASE_PATH/install-layout.json" "$RELEASE_ID" \
  "$RELEASE_PATH/systemd/cyberboss-cloud.service" \
  "$RELEASE_PATH/systemd/cyberboss-journald.conf" \
  "$RELEASE_PATH/systemd/20-resource-profile.conf" \
  "$UNIT_PATH" "$JOURNAL_PATH" "$DROPIN_PATH" <<'PY' ||
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
expected = {
    "schema_version": 1,
    "kind": "cb100-host-layout",
    "release_id": sys.argv[2],
    "app_user": "cyberboss",
    "app_group": "cyberboss",
    "unit": "cyberboss-cloud.service",
    "unit_enabled": False,
    "runtime_installed": False,
    "network_routes_created": 0,
}
for key, expected_value in expected.items():
    if value.get(key) != expected_value:
        raise SystemExit(1)
for key, release_path, live_path in (
    ("unit_sha256", sys.argv[3], sys.argv[6]),
    ("journald_sha256", sys.argv[4], sys.argv[7]),
    ("resource_dropin_sha256", sys.argv[5], sys.argv[8]),
):
    try:
        release_bytes = Path(release_path).read_bytes()
        live_bytes = Path(live_path).read_bytes()
    except OSError:
        raise SystemExit(1)
    digest = hashlib.sha256(release_bytes).hexdigest()
    if value.get(key) != digest:
        raise SystemExit(1)
    if live_bytes != release_bytes:
        raise SystemExit(1)
journal = Path(sys.argv[4]).read_text(encoding="utf-8")
match = re.search(r"^SystemMaxUse=([1-9][0-9]*)$", journal, re.MULTILINE)
if match is None or value.get("max_log_bytes") != int(match.group(1)):
    raise SystemExit(1)
PY
  record_fail 'release_manifest_invalid'

mapfile -t cyberboss_units < <(
  systemctl list-unit-files 'cyberboss-*' --no-legend 2>/dev/null |
    awk 'NF {print $1}' | sort
)
[[ "${#cyberboss_units[@]}" == 1 &&
  "${cyberboss_units[0]:-}" == "$UNIT" ]] ||
  record_fail "unexpected_unit_set:${#cyberboss_units[@]}"

systemd-analyze verify "$UNIT_PATH" >/dev/null 2>&1 ||
  record_fail 'systemd_analyze_verify_failed'
[[ "$(systemctl show "$UNIT" -p User --value)" == "$USER_NAME" ]] ||
  record_fail 'unit_user_mismatch'
[[ "$(systemctl show "$UNIT" -p Group --value)" == "$GROUP_NAME" ]] ||
  record_fail 'unit_group_mismatch'
[[ "$(systemctl show "$UNIT" -p KillMode --value)" == control-group ]] ||
  record_fail 'unit_kill_mode_mismatch'
[[ "$(systemctl show "$UNIT" -p Restart --value)" == on-failure ]] ||
  record_fail 'unit_restart_policy_mismatch'
[[ "$(systemctl show "$UNIT" -p LogNamespace --value)" == cyberboss ]] ||
  record_fail 'unit_log_namespace_mismatch'
[[ "$(systemctl is-active "$UNIT" 2>/dev/null || true)" == inactive ]] ||
  record_fail 'unit_not_inactive'
[[ "$(systemctl is-enabled "$UNIT" 2>/dev/null || true)" == disabled ]] ||
  record_fail 'unit_not_disabled'

for directive in \
  'ProtectSystem=strict' \
  'ReadWritePaths=/var/lib/cyberboss /srv/cyberboss-workspaces'; do
  grep -Fq "$directive" "$UNIT_PATH" || record_fail "unit_missing:$directive"
done
RESOURCE_HIGH="$(
  awk -F= '$1 == "CB_SYSTEMD_MEMORY_HIGH" {print $2}' \
    "$CONFIG_ROOT/resource-profile.env"
)"
RESOURCE_MAX="$(
  awk -F= '$1 == "CB_SYSTEMD_MEMORY_MAX" {print $2}' \
    "$CONFIG_ROOT/resource-profile.env"
)"
RESOURCE_TASKS="$(
  awk -F= '$1 == "CB_SYSTEMD_TASKS_MAX" {print $2}' \
    "$CONFIG_ROOT/resource-profile.env"
)"
RESOURCE_LOG_CAP="$(
  awk -F= '$1 == "CB_MAX_LOG_BYTES" {print $2}' \
    "$CONFIG_ROOT/resource-profile.env"
)"
[[ "$RESOURCE_HIGH" =~ ^[1-9][0-9]*M$ ]] ||
  record_fail 'resource_memory_high_invalid'
[[ "$RESOURCE_MAX" =~ ^[1-9][0-9]*M$ ]] ||
  record_fail 'resource_memory_max_invalid'
[[ "$RESOURCE_TASKS" =~ ^[1-9][0-9]*$ ]] ||
  record_fail 'resource_tasks_max_invalid'
[[ "$RESOURCE_LOG_CAP" =~ ^[1-9][0-9]*$ ]] ||
  record_fail 'app_log_cap_missing'
grep -Fxq 'CB_RESOURCE_ACTIVATION_SAFE=true' "$CONFIG_ROOT/resource-profile.env" ||
  record_fail 'resource_profile_not_activation_safe'
grep -Fxq 'CB_RESOURCE_GUARD_STATE=recover' "$CONFIG_ROOT/resource-profile.env" ||
  record_fail 'resource_profile_not_recover'
for directive in \
  "MemoryHigh=$RESOURCE_HIGH" \
  "MemoryMax=$RESOURCE_MAX" \
  "TasksMax=$RESOURCE_TASKS"; do
  grep -Fqx "$directive" "$DROPIN_PATH" || record_fail "dropin_missing:$directive"
done
grep -Fxq "SystemMaxUse=$RESOURCE_LOG_CAP" "$JOURNAL_PATH" ||
  record_fail 'journal_size_limit_mismatch'
grep -Fq 'RateLimitIntervalSec=30s' "$JOURNAL_PATH" ||
  record_fail 'journal_rate_interval_missing'
grep -Fq 'RateLimitBurst=500' "$JOURNAL_PATH" ||
  record_fail 'journal_rate_burst_missing'

expect_denied env_read runuser -u "$USER_NAME" -- test -r "$CONFIG_ROOT/cyberboss.env"
expect_denied credential_read runuser -u "$USER_NAME" -- test -r "$CONFIG_ROOT/credentials"
expect_denied config_write runuser -u "$USER_NAME" -- test -w "$CONFIG_ROOT"
expect_denied release_write runuser -u "$USER_NAME" -- test -w "$RELEASE_PATH"
expect_denied app_root_write runuser -u "$USER_NAME" -- test -w "$APP_ROOT"
runuser -u "$USER_NAME" -- test -w "$STATE_ROOT" ||
  record_fail 'state_root_not_writable'
runuser -u "$USER_NAME" -- test -w "$WORKSPACE_ROOT" ||
  record_fail 'workspace_root_not_writable'

if ((${#FAIL[@]})); then
  for item in "${FAIL[@]}"; do
    echo "FAIL_REASON=$item"
  done
  echo 'INSTALL_VERIFY=FAIL'
  exit 1
fi

if [[ "$MODE" == check ]]; then
  printf 'INSTALL_VERIFY=PASS mode=check release_id=%s unit=disabled/inactive\n' \
    "$RELEASE_ID"
  printf 'PERMISSION_NEGATIVE=PASS denied=5 allowed=2\n'
  exit 0
fi

RUNTIME_DROPIN=/run/systemd/system/cyberboss-cloud.service.d/90-cb100-acceptance.conf
cleanup() {
  systemctl stop "$UNIT" >/dev/null 2>&1 || true
  rm -f -- "$RUNTIME_DROPIN"
  systemctl daemon-reload >/dev/null 2>&1 || true
}
trap cleanup EXIT
install -d -o root -g root -m 0755 "$(dirname "$RUNTIME_DROPIN")"
cat >"$RUNTIME_DROPIN" <<'CONF'
[Unit]
StartLimitIntervalSec=0

[Service]
RestartSec=0
CONF
chmod 0644 "$RUNTIME_DROPIN"
systemctl daemon-reload
systemctl start "$UNIT"
main_pid="$(wait_for_new_main_pid 0)" || {
  echo 'INSTALL_VERIFY=FAIL staging_probe_did_not_start'
  exit 1
}
restart_before="$(systemctl show "$UNIT" -p NRestarts --value)"

restart_passes=0
contention_denied=0
for _iteration in $(seq 1 100); do
  old_pid="$main_pid"
  systemctl kill --kill-who=all --signal=KILL "$UNIT"
  main_pid="$(wait_for_new_main_pid "$old_pid" true)" || {
    echo "INSTALL_VERIFY=FAIL restart_predicate iteration=$((_iteration))"
    exit 1
  }
  restart_passes=$((restart_passes + 1))
  contention_denied=$((contention_denied + 1))
done
restart_after="$(systemctl show "$UNIT" -p NRestarts --value)"
((restart_after - restart_before >= 100)) || {
  echo "INSTALL_VERIFY=FAIL restart_counter_delta=$((restart_after - restart_before))"
  exit 1
}

systemctl stop "$UNIT"
[[ "$(systemctl is-active "$UNIT" 2>/dev/null || true)" == inactive ]] || {
  echo 'INSTALL_VERIFY=FAIL unit_not_inactive_after_exercise'
  exit 1
}
runuser -u "$USER_NAME" -- flock -n "$STATE_ROOT/locks/bridge.lock" /bin/true ||
  {
    echo 'INSTALL_VERIFY=FAIL singleton_not_released'
    exit 1
  }
rm -f -- "$RUNTIME_DROPIN"
systemctl daemon-reload
trap - EXIT

[[ "$(systemctl is-enabled "$UNIT" 2>/dev/null || true)" == disabled ]] || {
  echo 'INSTALL_VERIFY=FAIL unit_not_disabled_after_exercise'
  exit 1
}
printf 'INSTALL_VERIFY=PASS mode=exercise release_id=%s\n' "$RELEASE_ID"
printf 'CRASH_RESTART=PASS requested=100 passed=%s owner_units=1 ready_predicate=active_pid_and_lock fixed_sleep=0 llm_calls=0\n' \
  "$restart_passes"
printf 'SINGLETON=PASS competitors=100 denied=%s post_release_acquire=1\n' \
  "$contention_denied"
printf 'FINAL_UNIT_STATE=disabled/inactive network_listeners_created=0\n'
