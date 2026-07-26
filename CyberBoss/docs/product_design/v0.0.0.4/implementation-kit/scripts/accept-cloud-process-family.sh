#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
RELEASE_ID=""
OUTPUT=""
JOURNAL_OUTPUT=""
EXTERNAL_8765=""
EXTERNAL_8780=""

UNIT="cyberboss-cloud.service"
APP_ROOT="/opt/cyberboss-cloud"
STATE_ROOT="/var/lib/cyberboss"
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
RUNTIME_ROOT="/run/cyberboss-cb130"
TOKEN_FILE="$RUNTIME_ROOT/status.token"
HEADER_FILE="$RUNTIME_ROOT/status.header"
STARTED_FILE="$RUNTIME_ROOT/started.epoch"
DROPIN_DIR="/run/systemd/system/$UNIT.d"
DROPIN="$DROPIN_DIR/90-cb130-staging.conf"
STAGING_ENV="/etc/cyberboss/cb130-staging.env"

fail() {
  printf 'CLOUD_PROCESS_ACCEPTANCE=FAIL reason=%s\n' "$1"
  exit 2
}

while (($#)); do
  case "$1" in
    --prepare|--exercise|--cleanup)
      [[ -z "$MODE" ]] || fail "mode_must_be_unique"
      MODE="${1#--}"
      shift
      ;;
    --release-id)
      (($# >= 2)) || fail "release_id_value_missing"
      RELEASE_ID="$2"
      shift 2
      ;;
    --output)
      (($# >= 2)) || fail "output_value_missing"
      OUTPUT="$2"
      shift 2
      ;;
    --journal-output)
      (($# >= 2)) || fail "journal_output_value_missing"
      JOURNAL_OUTPUT="$2"
      shift 2
      ;;
    --external-8765-unreachable)
      (($# >= 2)) || fail "external_8765_value_missing"
      EXTERNAL_8765="$2"
      shift 2
      ;;
    --external-8780-unreachable)
      (($# >= 2)) || fail "external_8780_value_missing"
      EXTERNAL_8780="$2"
      shift 2
      ;;
    *)
      fail "unknown_arg:$1"
      ;;
  esac
done

[[ -n "$MODE" ]] || fail "mode_required"
[[ "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] ||
  fail "release_id_must_be_full_lowercase_git_sha"
[[ "$EUID" -eq 0 ]] || fail "root_required"

RELEASE="$APP_ROOT/releases/$RELEASE_ID"
[[ -d "$RELEASE" && ! -L "$RELEASE" ]] || fail "release_missing"
[[ -f "$RELEASE/release-manifest.json" ]] || fail "release_manifest_missing"
jq -e --arg release "$RELEASE_ID" '
  .task_id == "CB-130" and
  .release_commit == $release and
  .process_family.kill_mode == "control-group" and
  .process_family.detached_children == false and
  .candidate_only == true and
  .current_switched == false and
  .real_adapter_activation == "activation_pending"
' "$RELEASE/release-manifest.json" >/dev/null ||
  fail "release_manifest_contract"
[[ -f "$STAGING_ENV" && ! -L "$STAGING_ENV" ]] ||
  fail "staging_env_missing"
grep -Fxq "CB_EXPECTED_RELEASE_ID=$RELEASE_ID" "$STAGING_ENV" ||
  fail "staging_env_release"
[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_baseline"
[[ "$(sudo -u cyberboss git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_baseline"
systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
  fail "service_must_remain_disabled"

for command_name in awk curl date find flock grep install jq kill openssl pgrep \
  readlink rmdir sed seq sort ss stat sudo systemctl tr wc; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done

http_code() {
  local url="$1"
  local code=""
  if code="$(curl -sS -o /dev/null -w '%{http_code}' \
    --connect-timeout 1 --max-time 1 "$url" 2>/dev/null)"; then
    printf '%s\n' "$code"
  else
    printf '000\n'
  fi
}

wait_ready() {
  local deadline=$((SECONDS + 45))
  while ((SECONDS < deadline)); do
    if [[ "$(http_code http://127.0.0.1:8780/readyz)" == "200" ]] &&
      systemctl is-active --quiet "$UNIT"; then
      return 0
    fi
  done
  return 1
}

wait_inactive() {
  local deadline=$((SECONDS + 30))
  while ((SECONDS < deadline)); do
    if ! systemctl is-active --quiet "$UNIT"; then
      return 0
    fi
  done
  return 1
}

write_dropin() {
  local fixture_role="${1:-}"
  install -d -o root -g root -m 0755 "$DROPIN_DIR"
  {
    printf '[Unit]\n'
    printf 'StartLimitIntervalSec=0\n'
    printf 'StartLimitBurst=0\n\n'
    printf '[Service]\n'
    printf 'EnvironmentFile=\n'
    printf 'EnvironmentFile=%s\n' "$STAGING_ENV"
    printf 'EnvironmentFile=-/etc/cyberboss/resource-profile.env\n'
    printf 'Environment=CB_ACCEPTANCE_MODE=%s\n' \
      "$([[ -n "$fixture_role" ]] && printf true || printf false)"
    printf 'Environment=CB_ACCEPTANCE_UNREADY_ROLE=%s\n' "$fixture_role"
    printf 'WorkingDirectory=%s\n' "$RELEASE"
    printf 'ExecStart=\n'
    printf 'ExecStart=/usr/bin/flock -n %s/locks/bridge.lock %s/implementation-kit/scripts/run-cyberboss.sh\n' \
      "$STATE_ROOT" "$RELEASE"
    printf 'Restart=on-failure\n'
    printf 'RestartSec=0\n'
  } >"$DROPIN"
  chown root:root "$DROPIN"
  chmod 0644 "$DROPIN"
}

role_count() {
  local role="$1"
  local control_group cgroup_file pid command_line count=0 pattern=""
  case "$role" in
    supervisor) pattern="scripts/cloud-supervisor.js" ;;
    runtime) pattern="codex-app-server-simulator.mjs" ;;
    channel) pattern="weixin-ilink-simulator.mjs" ;;
    bridge) pattern="bin/cyberboss.js start" ;;
    *) return 64 ;;
  esac
  control_group="$(systemctl show -p ControlGroup --value "$UNIT")"
  cgroup_file="/sys/fs/cgroup${control_group}/cgroup.procs"
  [[ -r "$cgroup_file" ]] || {
    printf '0\n'
    return
  }
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || continue
    command_line="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
    [[ "$command_line" == *"$pattern"* ]] && count=$((count + 1))
  done <"$cgroup_file"
  printf '%s\n' "$count"
}

role_pid() {
  local role="$1"
  local control_group cgroup_file pid command_line pattern="" found=""
  case "$role" in
    runtime) pattern="codex-app-server-simulator.mjs" ;;
    channel) pattern="weixin-ilink-simulator.mjs" ;;
    bridge) pattern="bin/cyberboss.js start" ;;
    *) return 64 ;;
  esac
  control_group="$(systemctl show -p ControlGroup --value "$UNIT")"
  cgroup_file="/sys/fs/cgroup${control_group}/cgroup.procs"
  [[ -r "$cgroup_file" ]] || return 1
  while IFS= read -r pid; do
    [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]] || continue
    command_line="$(tr '\0' ' ' <"/proc/$pid/cmdline")"
    if [[ "$command_line" == *"$pattern"* ]]; then
      [[ -z "$found" ]] || return 1
      found="$pid"
    fi
  done <"$cgroup_file"
  [[ -n "$found" ]] || return 1
  printf '%s\n' "$found"
}

cgroup_members() {
  local control_group cgroup_file
  control_group="$(systemctl show -p ControlGroup --value "$UNIT")"
  cgroup_file="/sys/fs/cgroup${control_group}/cgroup.procs"
  [[ -r "$cgroup_file" ]] || return 1
  sort -n "$cgroup_file"
}

assert_family_replaced() {
  local before="$1"
  local after old_pid
  after="$(cgroup_members)" || fail "replacement_cgroup_missing"
  [[ -n "$before" && -n "$after" ]] || fail "replacement_cgroup_empty"
  while IFS= read -r old_pid; do
    [[ "$old_pid" =~ ^[0-9]+$ ]] || continue
    if grep -Fxq "$old_pid" <<<"$after"; then
      fail "old_cgroup_member_retained"
    fi
  done <<<"$before"
}

assert_single_family() {
  local role
  for role in supervisor runtime channel bridge; do
    [[ "$(role_count "$role")" == "1" ]] ||
      fail "owner_count:$role"
  done
}

assert_loopback_listeners() {
  local port rows addresses
  for port in 8765 8780 19080; do
    rows="$(ss -lntH "sport = :$port" | wc -l | tr -d ' ')"
    [[ "$rows" == "1" ]] || fail "listener_count:$port"
    addresses="$(ss -lntH "sport = :$port" | awk '{print $4}')"
    [[ "$addresses" == "127.0.0.1:$port" ]] ||
      fail "listener_not_loopback:$port"
  done
}

wait_recovery() {
  local invocation_before="$1"
  local deadline=$((SECONDS + 45))
  local observed_down=false
  local code invocation_after
  while ((SECONDS < deadline)); do
    code="$(http_code http://127.0.0.1:8780/readyz)"
    [[ "$code" == "200" ]] || observed_down=true
    invocation_after="$(systemctl show -p InvocationID --value "$UNIT")"
    if [[ "$observed_down" == "true" &&
      -n "$invocation_after" &&
      "$invocation_after" != "$invocation_before" &&
      "$code" == "200" ]]; then
      assert_single_family
      return 0
    fi
  done
  return 1
}

cleanup_runtime() {
  systemctl stop "$UNIT" >/dev/null 2>&1 || true
  systemctl kill --kill-whom=main --signal=SIGKILL "$UNIT" \
    >/dev/null 2>&1 || true
  wait_inactive >/dev/null 2>&1 || true
  if [[ -e "$DROPIN" || -L "$DROPIN" ]]; then
    find "$DROPIN" -maxdepth 0 -type f -delete 2>/dev/null || true
  fi
  rmdir "$DROPIN_DIR" >/dev/null 2>&1 || true
  if [[ -d "$RUNTIME_ROOT" && ! -L "$RUNTIME_ROOT" ]]; then
    find "$RUNTIME_ROOT" -xdev -depth -delete 2>/dev/null || true
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
}

assert_final_cleanup() {
  systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
    fail "service_enabled_after"
  systemctl is-active --quiet "$UNIT" && fail "service_active_after"
  [[ ! -e "$DROPIN" && ! -e "$RUNTIME_ROOT" ]] ||
    fail "transient_runtime_remaining"
  [[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == \
    "$EXPECTED_CURRENT" ]] || fail "current_changed"
  [[ "$(sudo -u cyberboss git -c safe.directory="$WORKSPACE" \
    -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
    fail "workspace_changed"
  [[ -z "$(sudo -u cyberboss git -c safe.directory="$WORKSPACE" \
    -C "$WORKSPACE" status --porcelain=v1)" ]] ||
    fail "workspace_dirty_after"
  [[ -z "$(ss -lntH \
    '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
    fail "listener_remaining"
  [[ -z "$(pgrep -u cyberboss 2>/dev/null || true)" ]] ||
    fail "process_remaining"
}

if [[ "$MODE" == "cleanup" ]]; then
  cleanup_runtime
  assert_final_cleanup
  printf 'CLOUD_PROCESS_CLEANUP=PASS release_id=%s service=disabled/inactive listeners=0 processes=0 current_changed=false\n' \
    "$RELEASE_ID"
  exit 0
fi

if [[ "$MODE" == "prepare" ]]; then
  systemctl is-active --quiet "$UNIT" && fail "service_active_before_prepare"
  [[ ! -e "$DROPIN" && ! -e "$RUNTIME_ROOT" ]] ||
    fail "staging_collision"
  [[ -z "$(ss -lntH \
    '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
    fail "listener_before_prepare"
  [[ -z "$(pgrep -u cyberboss 2>/dev/null || true)" ]] ||
    fail "process_before_prepare"
  prepare_ok=false
  trap '[[ "$prepare_ok" == "true" ]] || cleanup_runtime' EXIT
  install -d -o root -g cyberboss -m 0750 "$RUNTIME_ROOT"
  openssl rand -hex 32 >"$TOKEN_FILE"
  chown root:cyberboss "$TOKEN_FILE"
  chmod 0440 "$TOKEN_FILE"
  {
    printf 'Authorization: Bearer '
    tr -d '\n' <"$TOKEN_FILE"
    printf '\n'
  } >"$HEADER_FILE"
  chown root:root "$HEADER_FILE"
  chmod 0400 "$HEADER_FILE"
  date +%s >"$STARTED_FILE"
  chown root:root "$STARTED_FILE"
  chmod 0400 "$STARTED_FILE"
  write_dropin
  systemctl daemon-reload
  systemctl start "$UNIT"
  wait_ready || fail "initial_ready_predicate"
  assert_single_family
  assert_loopback_listeners
  prepare_ok=true
  trap - EXIT
  printf 'CLOUD_PROCESS_STAGING=READY release_id=%s runtime=loopback status=loopback owner=1 external_scan=pending\n' \
    "$RELEASE_ID"
  exit 0
fi

[[ "$MODE" == "exercise" ]] || fail "unsupported_mode"
[[ "$OUTPUT" == /* && "$JOURNAL_OUTPUT" == /* ]] ||
  fail "absolute_output_paths_required"
[[ "$EXTERNAL_8765" == "true" && "$EXTERNAL_8780" == "true" ]] ||
  fail "external_scan_must_be_unreachable"
[[ -f "$TOKEN_FILE" && -f "$HEADER_FILE" && -f "$STARTED_FILE" &&
  -f "$DROPIN" ]] || fail "prepare_state_missing"
wait_ready || fail "exercise_initial_ready"
assert_single_family
assert_loopback_listeners

exercise_ok=false
trap 'cleanup_runtime' EXIT
HEALTHY_CODE="$(http_code http://127.0.0.1:8780/healthz)"
READY_CODE="$(http_code http://127.0.0.1:8780/readyz)"
[[ "$HEALTHY_CODE" == "200" && "$READY_CODE" == "200" ]] ||
  fail "healthy_fixture"
UNAUTHORIZED_CODE="$(http_code http://127.0.0.1:8780/status/snapshot.json)"
WRONG_AUTH_CODE="$(curl -sS -o /dev/null -w '%{http_code}' \
  -H 'Authorization: Bearer invalid' \
  http://127.0.0.1:8780/status/snapshot.json)"
[[ "$UNAUTHORIZED_CODE" == "401" && "$WRONG_AUTH_CODE" == "401" ]] ||
  fail "snapshot_unprotected"
SNAPSHOT="$RUNTIME_ROOT/snapshot.json"
curl -fsS -H "@$HEADER_FILE" \
  http://127.0.0.1:8780/status/snapshot.json >"$SNAPSHOT"
jq -e --arg release "$RELEASE_ID" '
  .schema_version == 1 and
  .task_id == "CB-130" and
  .release_commit == $release and
  .claim_level == "simulator_fixture" and
  .status == "ready" and
  .healthy == true and
  .ready == true and
  .components == {
    supervisor: true,
    runtime: true,
    channel: true,
    bridge: true
  } and
  .providers.runtime == "simulator_verified" and
  .providers.channel == "simulator_verified" and
  .process_family.detached_children == false and
  .network.public_listener == false and
  .recovery.fixed_wait == false and
  .recovery.llm_call == false
' "$SNAPSHOT" >/dev/null || fail "snapshot_contract"
if grep -Eiq 'token|thread|account|message|prompt|result|/var/|/srv/|"pid"' \
  "$SNAPSHOT"; then
  fail "snapshot_forbidden_content"
fi

write_dropin runtime
systemctl daemon-reload
systemctl restart "$UNIT"
UNREADY_DEADLINE=$((SECONDS + 45))
UNREADY_FIXTURE=false
while ((SECONDS < UNREADY_DEADLINE)); do
  if [[ "$(http_code http://127.0.0.1:8780/healthz)" == "200" &&
    "$(http_code http://127.0.0.1:8780/readyz)" == "503" ]]; then
    if curl -fsS -H "@$HEADER_FILE" \
      http://127.0.0.1:8780/status/snapshot.json |
      jq -e '
        .healthy == true and
        .ready == false and
        .unready_components == ["runtime"] and
        .components.runtime == false and
        .components.channel == true and
        .components.bridge == true
      ' >/dev/null; then
      UNREADY_FIXTURE=true
      break
    fi
  fi
done
[[ "$UNREADY_FIXTURE" == "true" ]] || fail "unready_fixture"
write_dropin
systemctl daemon-reload
systemctl restart "$UNIT"
wait_ready || fail "ready_after_unready_fixture"
assert_single_family

systemctl stop "$UNIT"
wait_inactive || fail "inactive_before_concurrent_start"
START_RESULTS="$RUNTIME_ROOT/start-results"
install -d -o root -g root -m 0700 "$START_RESULTS"
for attempt in $(seq 1 100); do
  (
    if systemctl start "$UNIT"; then
      printf 'pass\n' >"$START_RESULTS/$attempt"
    else
      printf 'fail\n' >"$START_RESULTS/$attempt"
    fi
  ) &
done
wait || true
CONCURRENT_START_PASSES="$(grep -l '^pass$' "$START_RESULTS"/* |
  wc -l | tr -d ' ')"
[[ "$CONCURRENT_START_PASSES" == "100" ]] ||
  fail "concurrent_start_attempts"
wait_ready || fail "ready_after_concurrent_start"
assert_single_family

LOCK_RESULTS="$RUNTIME_ROOT/lock-results"
install -d -o root -g root -m 0700 "$LOCK_RESULTS"
for attempt in $(seq 1 100); do
  (
    if flock -n "$STATE_ROOT/locks/bridge.lock" true; then
      printf 'acquired\n' >"$LOCK_RESULTS/$attempt"
    else
      printf 'denied\n' >"$LOCK_RESULTS/$attempt"
    fi
  ) &
done
wait || true
LOCK_DENIALS="$(grep -l '^denied$' "$LOCK_RESULTS"/* |
  wc -l | tr -d ' ')"
[[ "$LOCK_DENIALS" == "100" ]] || fail "singleton_lock_denials"
assert_single_family

RESTART_PASSES=0
for attempt in $(seq 1 100); do
  INVOCATION_BEFORE="$(systemctl show -p InvocationID --value "$UNIT")"
  MEMBERS_BEFORE="$(cgroup_members)" || fail "restart_cgroup:$attempt"
  systemctl kill --kill-whom=main --signal=SIGKILL "$UNIT"
  wait_recovery "$INVOCATION_BEFORE" || fail "restart_cycle:$attempt"
  assert_family_replaced "$MEMBERS_BEFORE"
  RESTART_PASSES=$((RESTART_PASSES + 1))
done
[[ "$RESTART_PASSES" == "100" ]] || fail "restart_count"

RUNTIME_FAULT=false
CHANNEL_FAULT=false
BRIDGE_FAULT=false
SERVICE_FAULT=false
for role in runtime channel bridge; do
  INVOCATION_BEFORE="$(systemctl show -p InvocationID --value "$UNIT")"
  MEMBERS_BEFORE="$(cgroup_members)" || fail "fault_cgroup:$role"
  ROLE_PID="$(role_pid "$role")" || fail "fault_role_pid:$role"
  kill -KILL "$ROLE_PID"
  wait_recovery "$INVOCATION_BEFORE" || fail "fault_recovery:$role"
  assert_family_replaced "$MEMBERS_BEFORE"
  case "$role" in
    runtime) RUNTIME_FAULT=true ;;
    channel) CHANNEL_FAULT=true ;;
    bridge) BRIDGE_FAULT=true ;;
  esac
done
INVOCATION_BEFORE="$(systemctl show -p InvocationID --value "$UNIT")"
MEMBERS_BEFORE="$(cgroup_members)" || fail "fault_cgroup:service"
systemctl kill --kill-whom=main --signal=SIGKILL "$UNIT"
wait_recovery "$INVOCATION_BEFORE" || fail "fault_recovery:service"
assert_family_replaced "$MEMBERS_BEFORE"
SERVICE_FAULT=true
assert_loopback_listeners
assert_single_family
NRESTARTS="$(systemctl show -p NRestarts --value "$UNIT")"

STARTED_EPOCH="$(tr -d '\n' <"$STARTED_FILE")"
journalctl --namespace=cyberboss -u "$UNIT" \
  --since "@$STARTED_EPOCH" --no-pager -o cat 2>/dev/null |
  grep -E '^CB_SUPERVISOR_EVENT event=(status_listening|component_ready|service_ready|component_exit|shutdown|startup_failure)' |
  sort -u >"$JOURNAL_OUTPUT"
chmod 0600 "$JOURNAL_OUTPUT"
for marker in \
  'event=component_ready role=runtime' \
  'event=component_ready role=channel' \
  'event=component_ready role=bridge' \
  'event=service_ready claim=fixture' \
  'event=component_exit role=runtime' \
  'event=component_exit role=channel' \
  'event=component_exit role=bridge'; do
  grep -Fq "$marker" "$JOURNAL_OUTPUT" ||
    fail "journal_marker:$marker"
done
if grep -Eiq 'token|thread|account|message|prompt|result|/var/|/srv/' \
  "$JOURNAL_OUTPUT"; then
  fail "journal_forbidden_content"
fi

SUPERVISOR_COUNT="$(role_count supervisor)"
RUNTIME_COUNT="$(role_count runtime)"
CHANNEL_COUNT="$(role_count channel)"
BRIDGE_COUNT="$(role_count bridge)"
cleanup_runtime
trap - EXIT
assert_final_cleanup

jq -n \
  --arg release "$RELEASE_ID" \
  --argjson concurrent_start_passes "$CONCURRENT_START_PASSES" \
  --argjson lock_denials "$LOCK_DENIALS" \
  --argjson restart_passes "$RESTART_PASSES" \
  --argjson nrestarts "$NRESTARTS" \
  --argjson supervisor_count "$SUPERVISOR_COUNT" \
  --argjson runtime_count "$RUNTIME_COUNT" \
  --argjson channel_count "$CHANNEL_COUNT" \
  --argjson bridge_count "$BRIDGE_COUNT" \
  '{
    schema_version: 1,
    task_id: "CB-130",
    phase: "P1.4",
    implementation_commit: $release,
    acceptance: {
      "AC-011": "passed",
      "AC-040": "passed",
      "AC-044": "passed",
      "AC-062": "passed"
    },
    health_fixture: {
      health_status: 200,
      ready_status: 200,
      unready_health_status: 200,
      unready_ready_status: 503,
      snapshot_unauthorized_status: 401,
      snapshot_wrong_auth_status: 401,
      snapshot_authorized_status: 200,
      snapshot_forbidden_hits: 0
    },
    network: {
      runtime_listener: "127.0.0.1:8765",
      status_listener: "127.0.0.1:8780",
      channel_fixture_listener: "127.0.0.1:19080",
      external_8765_unreachable: true,
      external_8780_unreachable: true,
      public_listeners: 0
    },
    process_family: {
      one_systemd_cgroup: true,
      kill_mode: "control-group",
      detached_children: false,
      supervisor_count: $supervisor_count,
      runtime_count: $runtime_count,
      channel_count: $channel_count,
      bridge_count: $bridge_count
    },
    singleton: {
      concurrent_start_attempts: 100,
      concurrent_start_passes: $concurrent_start_passes,
      lock_contenders: 100,
      lock_denials: $lock_denials,
      active_owner: 1
    },
    restart: {
      kill_restart_attempts: 100,
      kill_restart_passes: $restart_passes,
      systemd_nrestarts_observed: $nrestarts,
      ready_predicate: true,
      whole_family_replaced: true,
      fixed_wait: false,
      llm_calls: 0
    },
    fault_matrix: {
      runtime: {down_observed: true, recovered: true},
      channel: {down_observed: true, recovered: true},
      bridge: {down_observed: true, recovered: true},
      service: {down_observed: true, recovered: true},
      false_green_observed: false
    },
    adapters: {
      runtime_simulator: "verified",
      channel_simulator: "verified",
      real_codex: "activation_pending",
      real_wechat: "activation_pending",
      real_credential_operations: 0
    },
    final: {
      service_enabled: false,
      service_active: false,
      current_changed: false,
      workspace_changed: false,
      processes: 0,
      listeners_8765_8780_19080: 0,
      transient_dropins: 0,
      ephemeral_tokens: 0
    },
    target_address_persisted: false,
    result: "passed"
  }' >"$OUTPUT"
chmod 0600 "$OUTPUT"
exercise_ok=true
printf 'CLOUD_PROCESS_ACCEPTANCE=PASS release_id=%s acceptances=AC-011,AC-040,AC-044,AC-062 restart=100/100 concurrent=100/100 lock_denied=100/100 faults=4/4 service=disabled/inactive listeners=0 processes=0 current_changed=false real_adapters=activation_pending\n' \
  "$RELEASE_ID"
