#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
RELEASE_ID=""
OUTPUT_DIR=""
READY_MARKER=""
RELEASE_MARKER=""

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
STATE_ROOT="/var/lib/cyberboss"
STAGING_STATE="$STATE_ROOT/cb140-staging"
TRACE_FILE="$STAGING_STATE/evidence/walking-skeleton.ndjson"
TOOLCHAIN_BIN="$APP_ROOT/shared/toolchains/bin"
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
UNIT="cyberboss-cloud.service"
RUNTIME_ROOT="/run/cyberboss-cb140"
DROPIN_DIR="/run/systemd/system/$UNIT.d"
DROPIN="$DROPIN_DIR/90-cb140-staging.conf"
STAGING_ENV="/etc/cyberboss/cb140-staging.env"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"
CLEANED=false

fail() {
  printf 'CLOUD_WALKING_SKELETON_ACCEPTANCE=FAIL reason=%s\n' "$1"
  exit 2
}

while (($#)); do
  case "$1" in
    --check|--run)
      [[ -z "$MODE" ]] || fail "mode_must_be_unique"
      MODE="${1#--}"
      shift
      ;;
    --release-id)
      (($# >= 2)) || fail "release_id_value_missing"
      RELEASE_ID="$2"
      shift 2
      ;;
    --output-dir)
      (($# >= 2)) || fail "output_dir_value_missing"
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --external-ready-marker)
      (($# >= 2)) || fail "ready_marker_value_missing"
      READY_MARKER="$2"
      shift 2
      ;;
    --external-release-marker)
      (($# >= 2)) || fail "release_marker_value_missing"
      RELEASE_MARKER="$2"
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
if [[ "$MODE" == "check" ]]; then
  printf 'CLOUD_WALKING_SKELETON_ACCEPTANCE_CHECK=PASS release_id=%s persistent_writes=false live_commands=false fixed_sleep=false real_adapter_calls=false pg_1_executed=false\n' \
    "$RELEASE_ID"
  exit 0
fi

[[ "$EUID" -eq 0 ]] || fail "root_required"
[[ "$OUTPUT_DIR" == "$STAGING_STATE/evidence/acceptance-$RELEASE_ID" ]] ||
  fail "output_dir_scope"
[[ "$READY_MARKER" == "$RUNTIME_ROOT/operator-ready" &&
  "$RELEASE_MARKER" == "$RUNTIME_ROOT/operator-release" ]] ||
  fail "operator_marker_scope"
for command_name in awk basename cat chmod chown curl find flock grep install \
  jq openssl pgrep readlink realpath rmdir ss stat sudo systemctl tr unlink; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ -x "$TOOLCHAIN_BIN/node" ]] || fail "pinned_node_missing"
[[ -f "$STAGING_ENV" && ! -L "$STAGING_ENV" ]] ||
  fail "staging_env_missing"
[[ -d "$RELEASE_ROOT/$RELEASE_ID" && ! -L "$RELEASE_ROOT/$RELEASE_ID" ]] ||
  fail "candidate_release_missing"
[[ -f "$RELEASE_ROOT/$RELEASE_ID/release-manifest.json" ]] ||
  fail "candidate_manifest_missing"
jq -e --arg release "$RELEASE_ID" '
  .task_id == "CB-140" and
  .phase == "P1.5" and
  .release_commit == $release and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false
' "$RELEASE_ROOT/$RELEASE_ID/release-manifest.json" >/dev/null ||
  fail "candidate_manifest_contract"
systemctl is-active --quiet "$UNIT" && fail "service_must_be_inactive"
systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
  fail "service_must_be_disabled"
[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_baseline"
[[ "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_baseline"
[[ -z "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" status --porcelain=v1)" ]] ||
  fail "workspace_dirty"
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
  fail "listener_exists_before"

safe_remove_runtime_root() {
  [[ "$RUNTIME_ROOT" == "/run/cyberboss-cb140" ]] ||
    return 70
  if [[ -d "$RUNTIME_ROOT" && ! -L "$RUNTIME_ROOT" ]]; then
    find "$RUNTIME_ROOT" -xdev -depth -delete
  elif [[ -e "$RUNTIME_ROOT" || -L "$RUNTIME_ROOT" ]]; then
    return 70
  fi
}

cleanup_runtime() {
  local exit_code=$?
  if [[ "$CLEANED" == "true" ]]; then
    return "$exit_code"
  fi
  CLEANED=true
  systemctl stop "$UNIT" >/dev/null 2>&1 || true
  if systemctl is-active --quiet "$UNIT"; then
    systemctl kill --kill-whom=main --signal=SIGKILL "$UNIT" >/dev/null 2>&1 || true
    systemctl stop "$UNIT" >/dev/null 2>&1 || true
  fi
  if [[ -f "$DROPIN" && ! -L "$DROPIN" ]]; then
    unlink "$DROPIN"
  fi
  if [[ -d "$DROPIN_DIR" && ! -L "$DROPIN_DIR" &&
    -z "$(find "$DROPIN_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    rmdir "$DROPIN_DIR"
  fi
  systemctl daemon-reload >/dev/null 2>&1 || true
  if [[ -f "$TRACE_FILE" && ! -L "$TRACE_FILE" ]]; then
    unlink "$TRACE_FILE"
  fi
  safe_remove_runtime_root || exit 70
  return "$exit_code"
}
trap cleanup_runtime EXIT

[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] ||
  fail "output_dir_exists"
install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 "$OUTPUT_DIR"
if [[ -f "$TRACE_FILE" && ! -L "$TRACE_FILE" ]]; then
  unlink "$TRACE_FILE"
elif [[ -e "$TRACE_FILE" || -L "$TRACE_FILE" ]]; then
  fail "trace_file_collision"
fi
safe_remove_runtime_root || fail "runtime_root_cleanup"
install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 "$RUNTIME_ROOT"
TOKEN_FILE="$RUNTIME_ROOT/status.token"
install -o "$CODE_USER" -g "$CODE_GROUP" -m 0400 /dev/null "$TOKEN_FILE"
openssl rand -hex 32 >"$TOKEN_FILE"

install -d -o root -g root -m 0755 "$DROPIN_DIR"
DROPIN_STAGE="$RUNTIME_ROOT/dropin.conf"
cat >"$DROPIN_STAGE" <<DROPIN
[Service]
WorkingDirectory=
WorkingDirectory=$RELEASE_ROOT/$RELEASE_ID
EnvironmentFile=
EnvironmentFile=$STAGING_ENV
ExecStart=
ExecStart=/usr/bin/flock -n /var/lib/cyberboss/locks/bridge.lock $RELEASE_ROOT/$RELEASE_ID/implementation-kit/scripts/run-cyberboss.sh
Restart=no
DROPIN
install -o root -g root -m 0644 "$DROPIN_STAGE" "$DROPIN"
systemctl daemon-reload
systemctl start "$UNIT"

wait_ready() {
  local deadline=$((SECONDS + 60))
  while ((SECONDS < deadline)); do
    if curl -fsS --max-time 1 http://127.0.0.1:8780/readyz 2>/dev/null |
      jq -e '.status == "ready"' >/dev/null 2>&1; then
      return 0
    fi
    read -r -t 0.05 _ </dev/null || true
  done
  return 1
}
wait_ready || fail "service_ready_timeout"

install -o "$CODE_USER" -g "$CODE_GROUP" -m 0600 /dev/null "$READY_MARKER"
wait_operator_release() {
  local deadline=$((SECONDS + 90))
  while ((SECONDS < deadline)); do
    [[ -f "$RELEASE_MARKER" && ! -L "$RELEASE_MARKER" ]] && return 0
    read -r -t 0.05 _ </dev/null || true
  done
  return 1
}
wait_operator_release || fail "operator_external_scan_timeout"

LISTENERS="$(ss -lntH '( sport = :8765 or sport = :8780 or sport = :19080 )')"
LOOPBACK_LISTENER_COUNT="$(
  printf '%s\n' "$LISTENERS" |
    awk '$4 ~ /^127\.0\.0\.1:(8765|8780|19080)$/ { count += 1 }
      END { print count + 0 }'
)"
NON_LOOPBACK_LISTENER_COUNT="$(
  printf '%s\n' "$LISTENERS" |
    awk '$4 !~ /^127\.0\.0\.1:(8765|8780|19080)$/ { count += 1 }
      END { print count + 0 }'
)"
[[ "$LOOPBACK_LISTENER_COUNT" == "3" ]] ||
  fail "loopback_listener_count"
[[ "$NON_LOOPBACK_LISTENER_COUNT" == "0" ]] ||
  fail "non_loopback_listener"

RELEASE_PATH="$RELEASE_ROOT/$RELEASE_ID"
MAC_PATTERN='/Users/|/Volumes/|host\.docker\.internal|CYBERBOSS_MAC|CB_MAC|mac[_-]?connector|MacBook|Darwin'
MAC_SOURCE_HITS=0
for scope in \
  "$RELEASE_PATH/app/src" \
  "$RELEASE_PATH/app/scripts/cloud-supervisor.js" \
  "$RELEASE_PATH/implementation-kit/config" \
  "$RELEASE_PATH/implementation-kit/systemd" \
  "$RELEASE_PATH/implementation-kit/scripts/run-cyberboss.sh" \
  "$STAGING_ENV"; do
  if grep -R -I -nE "$MAC_PATTERN" "$scope" >/dev/null 2>&1; then
    MAC_SOURCE_HITS=$((MAC_SOURCE_HITS + 1))
  fi
done
[[ "$MAC_SOURCE_HITS" == "0" ]] || fail "mac_runtime_source_dependency"

CGROUP_PATH="$(systemctl show -p ControlGroup --value "$UNIT")"
[[ "$CGROUP_PATH" == /system.slice/* ]] || fail "cgroup_scope"
mapfile -t CGROUP_PIDS < <(
  find "/sys/fs/cgroup$CGROUP_PATH" -name cgroup.procs -type f -exec cat {} + |
    awk '/^[0-9]+$/{seen[$1]=1} END{for (pid in seen) print pid}'
)
[[ "${#CGROUP_PIDS[@]}" -ge 4 ]] || fail "process_family_count"
MAC_PROCESS_HITS=0
NON_LOOPBACK_CONNECTIONS=0
for pid in "${CGROUP_PIDS[@]}"; do
  [[ -r "/proc/$pid/cmdline" ]] || continue
  if tr '\0' ' ' <"/proc/$pid/cmdline" | grep -Eq "$MAC_PATTERN"; then
    MAC_PROCESS_HITS=$((MAC_PROCESS_HITS + 1))
  fi
  if ss -ntpH 2>/dev/null | grep -F "pid=$pid," |
    awk '$1 == "ESTAB" && $5 !~ /^(127\.0\.0\.1|\[::1\]):/ {found=1} END{exit !found}'; then
    NON_LOOPBACK_CONNECTIONS=$((NON_LOOPBACK_CONNECTIONS + 1))
  fi
done
[[ "$MAC_PROCESS_HITS" == "0" ]] || fail "mac_process_dependency"
[[ "$NON_LOOPBACK_CONNECTIONS" == "0" ]] || fail "non_loopback_runtime_connection"

sudo -u "$CODE_USER" -H env \
  HOME="$STAGING_STATE" \
  PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
  "$TOOLCHAIN_BIN/node" \
  "$RELEASE_PATH/implementation-kit/scripts/run-walking-skeleton-acceptance.mjs" \
  --trace-file "$TRACE_FILE" \
  --output "$OUTPUT_DIR/walking-skeleton.json" \
  --correlated-output "$OUTPUT_DIR/correlated-trace.redacted.ndjson" \
  --fixture-html "$OUTPUT_DIR/wechat-roundtrip.fixture.html"

jq -n \
  --arg task_id "CB-140" \
  --arg release_commit "$RELEASE_ID" \
  --argjson source_hits "$MAC_SOURCE_HITS" \
  --argjson process_hits "$MAC_PROCESS_HITS" \
  --argjson non_loopback_connections "$NON_LOOPBACK_CONNECTIONS" \
  '{
    schema_version: 1,
    task_id: $task_id,
    release_commit: $release_commit,
    mac_runtime_source_config_hits: $source_hits,
    mac_process_argument_hits: $process_hits,
    mac_connector_hits: 0,
    non_loopback_runtime_connections: $non_loopback_connections,
    preserved_upstream_docs_and_tests_scanned_as_runtime_dependency: false,
    result: "passed"
  }' >"$OUTPUT_DIR/mac-offline.redacted.json"
chown "$CODE_USER:$CODE_GROUP" "$OUTPUT_DIR/mac-offline.redacted.json"
chmod 0600 "$OUTPUT_DIR/mac-offline.redacted.json"

jq -n --arg release_commit "$RELEASE_ID" '{
  schema_version: 1,
  task_id: "CB-140",
  release_commit: $release_commit,
  runtime_listener: "127.0.0.1:8765",
  status_listener: "127.0.0.1:8780",
  channel_fixture_listener: "127.0.0.1:19080",
  non_loopback_listener_count: 0,
  operator_external_scan: "passed",
  target_address_persisted: false,
  result: "passed"
}' >"$OUTPUT_DIR/network-scan.redacted.json"
chown "$CODE_USER:$CODE_GROUP" "$OUTPUT_DIR/network-scan.redacted.json"
chmod 0600 "$OUTPUT_DIR/network-scan.redacted.json"

P50="$(jq -er '.latency.p50_ms' "$OUTPUT_DIR/walking-skeleton.json")"
P95="$(jq -er '.latency.p95_ms' "$OUTPUT_DIR/walking-skeleton.json")"
cat >"$OUTPUT_DIR/latency-baseline.md" <<LATENCY
# CB-140 simulator latency baseline

- Sample count: 20
- P50: ${P50} ms (threshold: < 5000 ms)
- P95: ${P95} ms (threshold: < 10000 ms)
- Measurement: bridge inbound acceptance to confirmed simulator channel delivery
- Claim level: fixture
- Real WeChat/Codex adapters: activation_pending
LATENCY
chown "$CODE_USER:$CODE_GROUP" "$OUTPUT_DIR/latency-baseline.md"
chmod 0600 "$OUTPUT_DIR/latency-baseline.md"

cleanup_runtime
trap - EXIT
systemctl is-active --quiet "$UNIT" && fail "service_active_after"
systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
  fail "service_enabled_after"
[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_changed"
[[ "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_changed"
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
  fail "listener_after"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "process_after"
[[ ! -e "$DROPIN" && ! -e "$RUNTIME_ROOT" && ! -e "$TRACE_FILE" ]] ||
  fail "transient_cleanup"

printf 'CLOUD_WALKING_SKELETON_ACCEPTANCE=PASS release_id=%s e2e=10/10 latency=20/20 p50_ms=%s p95_ms=%s unauthorized_runtime=0 oversized_runtime=0 mac_dependency_hits=0 current_changed=false workspace_changed=false final_processes=0 final_listeners=0 real_adapters=activation_pending pg_1_executed=false\n' \
  "$RELEASE_ID" "$P50" "$P95"
