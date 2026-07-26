#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
RELEASE_ID=""
OUTPUT_DIR=""

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
TOOLCHAIN_BIN="$APP_ROOT/shared/toolchains/bin"
STATE_ROOT="/var/lib/cyberboss"
STAGING_STATE="$STATE_ROOT/cb220-staging"
RUNTIME_ROOT=""
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
EXPECTED_TARGET_HASH="7865f743d174"
UNIT="cyberboss-cloud.service"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"

fail() {
  printf 'JOB_SCHEDULER_ACCEPTANCE=FAIL reason=%s\n' "$1"
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
    *)
      fail "unknown_arg:$1"
      ;;
  esac
done

[[ -n "$MODE" ]] || fail "mode_required"
[[ "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] ||
  fail "release_id_must_be_full_lowercase_git_sha"
if [[ "$MODE" == "check" ]]; then
  printf 'JOB_SCHEDULER_ACCEPTANCE_CHECK=PASS release_id=%s persistent_writes=false live_commands=false service_started=false real_credential_reads=false provider_writes=false private_database_operations=false bounded_pressure_only=true outbox_worker_integrated=false pg_2_executed=false\n' \
    "$RELEASE_ID"
  exit 0
fi

RUNTIME_ROOT="$STATE_ROOT/cb220-runtime-$RELEASE_ID"
[[ "$EUID" -eq 0 ]] || fail "root_required"
[[ "$OUTPUT_DIR" == "$STAGING_STATE/evidence/acceptance-$RELEASE_ID" ]] ||
  fail "output_dir_scope"
for command_name in chmod chown cmp find git grep install jq pgrep \
  readlink realpath sort ss stat sudo systemctl systemd-run; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ -x "$TOOLCHAIN_BIN/node" ]] || fail "pinned_node_missing"
[[ "$("$TOOLCHAIN_BIN/node" --version)" == "v24.18.0" ]] ||
  fail "pinned_node_version"
[[ -x /usr/bin/python3 && -x /usr/bin/env ]] ||
  fail "pinned_host_python_missing"

RELEASE_PATH="$RELEASE_ROOT/$RELEASE_ID"
[[ -d "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]] ||
  fail "candidate_release_missing"
[[ -f "$RELEASE_PATH/release-manifest.json" &&
  -f "$RELEASE_PATH/evidence/job-scheduler-acceptance.json" ]] ||
  fail "candidate_manifest_missing"
jq -e --arg release "$RELEASE_ID" '
  .task_id == "CB-220" and
  .phase == "P2.3" and
  .release_commit == $release and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false and
  .runtime_spool.schema_version == 3 and
  .runtime_spool.channel_poll_integrated == true and
  .runtime_spool.scheduler_integrated == true and
  .runtime_spool.outbox_worker_integrated == false and
  .runtime_spool.pg_2_executed == false and
  .durable_inbox.scheduler_integrated == true and
  .durable_inbox.outbox_worker_integrated == false and
  .job_scheduler.single_runtime_lease == true and
  .job_scheduler.max_runtime_concurrency == 1 and
  .job_scheduler.fifo_order == "created_at,id" and
  .job_scheduler.heartbeat_and_expiry == true and
  .job_scheduler.workspace_alias_gate == true and
  .job_scheduler.resource_readiness_gate == true and
  .job_scheduler.truthful_stop_terminal == true and
  .job_scheduler.unsafe_mutation_auto_replay == false and
  .job_scheduler.outbox_worker_integrated == false and
  .job_scheduler.real_wechat == false and
  .job_scheduler.real_runtime == false and
  .job_scheduler.pg_2_executed == false
' "$RELEASE_PATH/release-manifest.json" >/dev/null ||
  fail "candidate_manifest_contract"
[[ -d "$STAGING_STATE" && ! -L "$STAGING_STATE" ]] ||
  fail "staging_state_missing"
[[ "$(stat -c '%U:%G:%a' "$STAGING_STATE")" == \
  "$CODE_USER:$CODE_GROUP:700" ]] ||
  fail "staging_state_owner_mode"

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
[[ ! -e "$STATE_ROOT/runtime.db" && ! -L "$STATE_ROOT/runtime.db" ]] ||
  fail "canonical_runtime_db_present"
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
  fail "listener_exists_before"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "code_process_exists_before"
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] ||
  fail "output_dir_exists"
[[ ! -e "$RUNTIME_ROOT" && ! -L "$RUNTIME_ROOT" ]] ||
  fail "runtime_root_exists"

install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 "$OUTPUT_DIR"
install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 \
  "$RUNTIME_ROOT" "$RUNTIME_ROOT/tmp"

cleanup() {
  local exit_code=$?
  if [[ -d "${RUNTIME_ROOT:-}" && ! -L "$RUNTIME_ROOT" ]]; then
    find "$RUNTIME_ROOT" -xdev -depth -delete
  elif [[ -e "${RUNTIME_ROOT:-}" || -L "${RUNTIME_ROOT:-}" ]]; then
    exit 70
  fi
  return "$exit_code"
}
trap cleanup EXIT

REPORT="$OUTPUT_DIR/job-scheduler-acceptance.json"
PRESSURE="$OUTPUT_DIR/cgroup-pressure.raw.json"
sudo -u "$CODE_USER" -H env \
  HOME="$STAGING_STATE" \
  TMPDIR="$RUNTIME_ROOT/tmp" \
  PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
  "$TOOLCHAIN_BIN/node" \
  "$RELEASE_PATH/app/scripts/job-scheduler-acceptance.js" \
  --output "$REPORT"

cmp -s "$REPORT" \
  "$RELEASE_PATH/evidence/job-scheduler-acceptance.json" ||
  fail "job_scheduler_report_drift"
jq -e '
  .task_id == "CB-220" and
  .phase == "P2.3" and
  .scheduler.queued_runtime_jobs == 5 and
  .scheduler.max_active_runtime_leases == 1 and
  .scheduler.fifo_dispatch_order == true and
  .scheduler.command_runtime_planes_separated == true and
  .workspace.allowlisted_alias_dispatched == true and
  .workspace.absolute_path_dispatched == false and
  .workspace.unknown_alias_dispatched == false and
  .workspace.symlink_escape_dispatched == false and
  .workspace.filesystem_changed_on_rejection == false and
  .resource_gate.protect_blocks_mutation == true and
  .resource_gate.recover_allows_dispatch == true and
  .stop.cancel_call_count == 3 and
  .stop.acknowledgement_claimed_terminal == false and
  .stop.false_success_count == 0 and
  .recovery.ambiguous_mutation_replayed == false and
  .recovery.stale_owner_heartbeat_succeeded == false and
  .recovery.late_event_released_new_lease == false and
  .runtime_errors.bounded_mutation_auto_replay == false and
  .phase_boundary.outbox_worker_integrated == false and
  .phase_boundary.real_wechat == false and
  .phase_boundary.real_runtime == false and
  .phase_boundary.pg_2_executed == false and
  .result == "passed"
' "$REPORT" >/dev/null || fail "job_scheduler_report_contract"

PRESSURE_UNIT="cyberboss-cb220-pressure-${RELEASE_ID:0:12}"
systemd-run --quiet --wait --pipe --collect \
  --unit "$PRESSURE_UNIT" \
  --property "Type=exec" \
  --property "User=$CODE_USER" \
  --property "Group=$CODE_GROUP" \
  --property "MemoryMax=128M" \
  --property "MemorySwapMax=0" \
  --property "TasksMax=64" \
  --property "RuntimeMaxSec=60s" \
  --property "NoNewPrivileges=yes" \
  /usr/bin/env \
  HOME="$STAGING_STATE" \
  TMPDIR="$RUNTIME_ROOT/tmp" \
  PATH="/usr/bin:/bin" \
  /usr/bin/python3 \
  "$RELEASE_PATH/implementation-kit/scripts/resource-pressure-fixture.py" \
  --memory-mb 16 \
  --disk-mb 8 \
  --queue-items 100 \
  --evidence-scope authorized_live_host_container \
  --output "$PRESSURE"

jq -e '
  .result == "pass" and
  .mode == "bounded_authorized_live_host_container_fixture" and
  .evidence_scope == "authorized_live_host_container" and
  .no_sleep == true and
  .oom_observed == false and
  .hard_caps.memory_mb_max == 64 and
  .hard_caps.disk_mb_max == 64 and
  .hard_caps.queue_items_max == 1000 and
  .cgroup_evidence.state ==
    "verified_bounded_authorized_live_host_container" and
  .cgroup_evidence.reason ==
    "finite_cgroup_memory_limit_and_no_oom_kill" and
  .cgroup_evidence.oom_kill_delta == 0 and
  .cgroup_evidence.claimed_as_live_host_evidence == true and
  ([.guard_ladder[].actual] == [
    "recover",
    "warn",
    "protect",
    "protect",
    "protect",
    "protect",
    "recover"
  ])
' "$PRESSURE" >/dev/null || fail "cgroup_pressure_contract"

[[ "$(find "$OUTPUT_DIR" -maxdepth 1 -type f -printf '%f\n' | sort)" == \
  $'cgroup-pressure.raw.json\njob-scheduler-acceptance.json' ]] ||
  fail "acceptance_output_inventory"
if grep -R -I -nE \
  'PRIVATE KEY|Authorization:[[:space:]]*Bearer|gh[pousr]_[A-Za-z0-9]{20,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|wxid_' \
  "$OUTPUT_DIR" >/dev/null 2>&1; then
  fail "acceptance_output_secret"
fi
[[ -z "$(find "$OUTPUT_DIR" -type f \
  \( ! -user "$CODE_USER" -o ! -group "$CODE_GROUP" -o -perm /027 \) \
  -print -quit)" ]] ||
  fail "acceptance_output_permissions"
[[ ! -e "$STATE_ROOT/runtime.db" && ! -L "$STATE_ROOT/runtime.db" ]] ||
  fail "canonical_runtime_db_created"
[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_changed"
[[ "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_changed"
systemctl is-active --quiet "$UNIT" && fail "service_active_after"
systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
  fail "service_enabled_after"
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
  fail "listener_created"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "process_created"

printf 'JOB_SCHEDULER_ACCEPTANCE=PASS release_id=%s target_id_sha256=%s queued_runtime_jobs=5 max_active_runtime_leases=1 fifo=true workspace_escape_count=0 unsafe_mutation_replay=false stop_false_success=0 oom_kill_delta=0 bounded_cgroup=true current_changed=false workspace_changed=false service_started=false real_credential_reads=0 provider_writes=0 private_database_operations=0 outbox_worker_integrated=false pg_2_executed=false\n' \
  "$RELEASE_ID" "$EXPECTED_TARGET_HASH"
