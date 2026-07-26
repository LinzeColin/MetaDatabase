#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
RELEASE_ID=""
OUTPUT_DIR=""

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
TOOLCHAIN_BIN="$APP_ROOT/shared/toolchains/bin"
STATE_ROOT="/var/lib/cyberboss"
DATA_ROOT="/var/lib/cyberboss-data"
STAGING_STATE="$STATE_ROOT/cb240-staging"
RUNTIME_ROOT=""
DATA_TEST_ROOT=""
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
EXPECTED_TARGET_HASH="7865f743d174"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"
DATA_USER="cyberboss-data"
DATA_GROUP="cyberboss-data"
CLOUD_UNIT="cyberboss-cloud.service"
SYNC_UNIT="cyberboss-canonical-sync.service"
SYNC_TIMER="cyberboss-canonical-sync.timer"

fail() {
  printf 'CANONICAL_SYNC_ACCEPTANCE=FAIL reason=%s\n' "$1"
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
  printf 'CANONICAL_SYNC_ACCEPTANCE_CHECK=PASS release_id=%s persistent_writes=false live_commands=false service_started=false real_credential_reads=false private_database_operations=false object_store_operations=false current_changed=false pg_2_executed=false\n' \
    "$RELEASE_ID"
  exit 0
fi

[[ "$EUID" -eq 0 ]] || fail "root_required"
[[ "$OUTPUT_DIR" == "$STAGING_STATE/evidence/acceptance-$RELEASE_ID" ]] ||
  fail "output_dir_scope"
for command_name in chmod chown cmp find getent git grep install jq openssl \
  pgrep python3 readlink realpath sort ss stat sudo systemctl; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ -x "$TOOLCHAIN_BIN/node" ]] || fail "pinned_node_missing"
[[ "$("$TOOLCHAIN_BIN/node" --version)" == "v24.18.0" ]] ||
  fail "pinned_node_version"
getent passwd "$CODE_USER" >/dev/null || fail "code_user_missing"
getent passwd "$DATA_USER" >/dev/null || fail "data_user_missing"
getent group "$CODE_GROUP" >/dev/null || fail "code_group_missing"
getent group "$DATA_GROUP" >/dev/null || fail "data_group_missing"

RELEASE_PATH="$RELEASE_ROOT/$RELEASE_ID"
[[ -d "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]] ||
  fail "candidate_release_missing"
[[ -f "$RELEASE_PATH/release-manifest.json" &&
  -f "$RELEASE_PATH/evidence/canonical-sync-report.json" ]] ||
  fail "candidate_manifest_missing"
jq -e --arg release "$RELEASE_ID" '
  .task_id == "CB-240" and
  .phase == "P2.5" and
  .release_commit == $release and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false and
  .runtime_spool.schema_version == 5 and
  .runtime_spool.canonical_sync_integrated == true and
  .runtime_spool.pg_2_executed == false and
  .canonical_sync.area == "Private-MetaDatabase" and
  .canonical_sync.domain == "CyberBoss" and
  .canonical_sync.branch == "main" and
  .canonical_sync.access_mode == "no_clone_client" and
  .canonical_sync.allowed_operations == ["ingest","get","list","verify"] and
  .canonical_sync.max_records == 50 and
  .canonical_sync.max_uncompressed_bytes == 262144 and
  .canonical_sync.max_age_seconds == 60 and
  .canonical_sync.deterministic_gzip == true and
  .canonical_sync.content_addressed == true and
  .canonical_sync.manifest_conflict_last_write_wins == false and
  .canonical_sync.same_id_different_hash_quarantine == true and
  .canonical_sync.bounded_mutation_backlog_guard == true and
  .canonical_sync.read_only_drain_allowed == true and
  .canonical_sync.code_data_identity_separated == true and
  .canonical_sync.rebuild_without_sqlite == true and
  .canonical_sync.timeline_projection_only == true and
  .canonical_sync.real_private_database == false and
  .canonical_sync.private_database_activation_status ==
    "activation_pending" and
  .canonical_sync.real_r2 == false and
  .canonical_sync.cb_300_executed == false and
  .canonical_sync.pg_2_executed == false
' "$RELEASE_PATH/release-manifest.json" >/dev/null ||
  fail "candidate_manifest_contract"

for unit in "$CLOUD_UNIT" "$SYNC_UNIT" "$SYNC_TIMER"; do
  systemctl is-active --quiet "$unit" && fail "unit_must_be_inactive:$unit"
  systemctl is-enabled --quiet "$unit" 2>/dev/null &&
    fail "unit_must_be_disabled:$unit"
done
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
[[ -z "$(pgrep -u "$DATA_USER" 2>/dev/null || true)" ]] ||
  fail "data_process_exists_before"
for directory in outgoing receipts quarantine; do
  [[ -d "$STATE_ROOT/canonical-spool/$directory" &&
    ! -L "$STATE_ROOT/canonical-spool/$directory" ]] ||
    fail "canonical_spool_directory_missing:$directory"
  [[ -z "$(find "$STATE_ROOT/canonical-spool/$directory" \
    -mindepth 1 -maxdepth 1 -print -quit)" ]] ||
    fail "canonical_spool_not_empty:$directory"
done

RUNTIME_ROOT="$STATE_ROOT/cb240-runtime-$RELEASE_ID"
DATA_TEST_ROOT="$DATA_ROOT/cb240-acceptance-$RELEASE_ID"
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] ||
  fail "output_dir_exists"
[[ ! -e "$RUNTIME_ROOT" && ! -L "$RUNTIME_ROOT" ]] ||
  fail "runtime_root_exists"
[[ ! -e "$DATA_TEST_ROOT" && ! -L "$DATA_TEST_ROOT" ]] ||
  fail "data_test_root_exists"

install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 \
  "$OUTPUT_DIR" "$RUNTIME_ROOT" "$RUNTIME_ROOT/state" "$RUNTIME_ROOT/tmp"
install -d -o "$DATA_USER" -g "$DATA_GROUP" -m 0700 "$DATA_TEST_ROOT"
install -o "$DATA_USER" -g "$DATA_GROUP" -m 0600 /dev/null \
  "$DATA_TEST_ROOT/identity-probe"
KEY_FILE="$RUNTIME_ROOT/synthetic-aes256.key"
openssl rand -out "$KEY_FILE" 32
chown "$CODE_USER:$CODE_GROUP" "$KEY_FILE"
chmod 0400 "$KEY_FILE"

cleanup() {
  local exit_code=$?
  for target in "${RUNTIME_ROOT:-}" "${DATA_TEST_ROOT:-}"; do
    if [[ -d "$target" && ! -L "$target" ]]; then
      find "$target" -xdev -depth -delete
    elif [[ -e "$target" || -L "$target" ]]; then
      exit 70
    fi
  done
  return "$exit_code"
}
trap cleanup EXIT

SAFE_WRAPPER="$APP_ROOT/shared/private_db_client_safe.py"
PRIVATE_CLIENT="$APP_ROOT/shared/private_db_client.py"
[[ -f "$SAFE_WRAPPER" && ! -L "$SAFE_WRAPPER" &&
  -f "$PRIVATE_CLIENT" && ! -L "$PRIVATE_CLIENT" ]] ||
  fail "no_clone_client_missing"
[[ "$(stat -c '%U:%G:%a' "$SAFE_WRAPPER")" == \
  "root:$DATA_GROUP:550" ]] || fail "safe_wrapper_owner_mode"
[[ "$(stat -c '%U:%G:%a' "$PRIVATE_CLIENT")" == \
  "root:$DATA_GROUP:440" ]] || fail "private_client_owner_mode"
sudo -u "$DATA_USER" -H \
  python3 "$SAFE_WRAPPER" \
  --client "$PRIVATE_CLIENT" \
  --domain CyberBoss \
  list Private-MetaDatabase >/dev/null ||
  fail "data_identity_plan_only"
sudo -u "$CODE_USER" test ! -x "$SAFE_WRAPPER" ||
  fail "code_identity_can_execute_data_wrapper"
sudo -u "$DATA_USER" test ! -w "$WORKSPACE/CyberBoss" ||
  fail "data_identity_can_write_code_workspace"
sudo -u "$CODE_USER" test ! -r "$DATA_TEST_ROOT/identity-probe" ||
  fail "code_identity_can_read_data_state"

sudo -u "$CODE_USER" -H env \
  HOME="$STAGING_STATE" \
  TMPDIR="$RUNTIME_ROOT/tmp" \
  PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
  "$TOOLCHAIN_BIN/node" \
  "$RELEASE_PATH/app/scripts/canonical-sync-acceptance.js" \
  --runtime-root "$RUNTIME_ROOT/state" \
  --key-file "$KEY_FILE" \
  --output-directory "$OUTPUT_DIR" \
  --release-commit "$RELEASE_ID" \
  --target-id-sha256 "$EXPECTED_TARGET_HASH"

[[ "$(find "$OUTPUT_DIR" -maxdepth 1 -type f -printf '%f\n' | sort)" == \
  "canonical-sync-report.json" ]] ||
  fail "acceptance_output_inventory"
REPORT="$OUTPUT_DIR/canonical-sync-report.json"
cmp -s "$REPORT" "$RELEASE_PATH/evidence/canonical-sync-report.json" ||
  fail "canonical_sync_report_drift"
jq -e --arg release "$RELEASE_ID" --arg target "$EXPECTED_TARGET_HASH" '
  .task_id == "CB-240" and
  .phase == "P2.5" and
  .release_commit == $release and
  .target_id_sha256 == $target and
  .claim_level == "deterministic_fixture" and
  .generated_from_synthetic_state == true and
  .executable_suite.failures == 0 and
  .executable_suite.fixed_wait == false and
  .ac_030_rebuild.sqlite_present == false and
  .ac_030_rebuild.canonical_event_count == 1000 and
  .ac_030_rebuild.terminal_job_count == 1000 and
  .ac_030_rebuild.r2_fixture_only == true and
  .ac_030_rebuild.real_r2_operation == false and
  .ac_031_batching_latency.terminal_jobs == 50 and
  .ac_031_batching_latency.latency_p95_seconds <= 60 and
  .ac_031_batching_latency.terminal_events == 1000 and
  .ac_031_batching_latency.count_threshold_batch_count == 20 and
  ([.ac_031_batching_latency.count_threshold_batch_sizes[] == 50] | all) and
  .ac_031_batching_latency.age_threshold_flush_at_seconds == 60 and
  .ac_031_batching_latency.pending_during_failure == true and
  .ac_031_batching_latency.set_diff == 0 and
  .ac_032_conflict_retry.concurrent_sync_groups == 50 and
  .ac_032_conflict_retry.manifest_409_refetch_exercised == true and
  .ac_032_conflict_retry.auth_403_pending_exercised == true and
  .ac_032_conflict_retry.rate_limit_429_exercised == true and
  .ac_032_conflict_retry.retry_hint_ms == 120000 and
  .ac_032_conflict_retry.partial_success_refetch_exercised == true and
  .ac_032_conflict_retry.outage_duration_seconds == 600 and
  .ac_032_conflict_retry.real_wait_calls == 0 and
  .ac_032_conflict_retry.set_diff == 0 and
  .ac_033_privacy.full_prompt_result_identity_hits == 0 and
  .ac_033_privacy.encryption_key_hits == 0 and
  .integrity_protection.same_event_id_different_hash_detected == true and
  .integrity_protection.last_write_wins == false and
  .integrity_protection.bounded_mutation_allowed == false and
  .canonical_truth.area == "Private-MetaDatabase" and
  .canonical_truth.domain == "CyberBoss" and
  .canonical_truth.allowed_operations == ["ingest","get","list","verify"] and
  .canonical_truth.forbidden_operations == ["clone","put","delete"] and
  .boundaries.code_data_identity_separated == true and
  .boundaries.real_private_database_operation == false and
  .boundaries.private_database_activation_status ==
    "activation_pending" and
  .boundaries.real_r2_operation == false and
  .boundaries.timeline_projection_only == true and
  .boundaries.timeline_web_build_search == false and
  .boundaries.cb_300_executed == false and
  .boundaries.pg_2_executed == false and
  .boundaries.service_started == false and
  .boundaries.remote_publication == "none" and
  .boundaries.upstream_clarification_received == false and
  .boundaries.license_expression ==
    "AGPL-3.0-only AND GPL-3.0-only" and
  .result == "passed"
' "$REPORT" >/dev/null || fail "acceptance_report_contract"

if grep -R -I -nE \
  'PRIVATE KEY|Authorization:[[:space:]]*Bearer|gh[pousr]_[A-Za-z0-9]{20,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|wxid_|CB240-PRIVATE' \
  "$OUTPUT_DIR" >/dev/null 2>&1; then
  fail "acceptance_output_secret"
fi
[[ -z "$(find "$OUTPUT_DIR" -type f \
  \( ! -user "$CODE_USER" -o ! -group "$CODE_GROUP" -o -perm /077 \) \
  -print -quit)" ]] ||
  fail "acceptance_output_permissions"
[[ ! -e "$STATE_ROOT/runtime.db" && ! -L "$STATE_ROOT/runtime.db" ]] ||
  fail "canonical_runtime_db_created"
for directory in outgoing receipts quarantine; do
  [[ -z "$(find "$STATE_ROOT/canonical-spool/$directory" \
    -mindepth 1 -maxdepth 1 -print -quit)" ]] ||
    fail "canonical_spool_changed:$directory"
done
for unit in "$CLOUD_UNIT" "$SYNC_UNIT" "$SYNC_TIMER"; do
  systemctl is-active --quiet "$unit" && fail "unit_active_after:$unit"
  systemctl is-enabled --quiet "$unit" 2>/dev/null &&
    fail "unit_enabled_after:$unit"
done
[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_changed"
[[ "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_changed"
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 or sport = :19080 )')" ]] ||
  fail "listener_exists_after"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "code_process_exists_after"
[[ -z "$(pgrep -u "$DATA_USER" 2>/dev/null || true)" ]] ||
  fail "data_process_exists_after"

printf 'CANONICAL_SYNC_ACCEPTANCE=PASS release_id=%s events=1000 concurrent_groups=50 set_diff=0 privacy_hits=0 no_clone=true real_private_database=false real_r2=false current_changed=false service_active=false timer_active=false pg_2_executed=false publication=none\n' \
  "$RELEASE_ID"
