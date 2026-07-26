#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
RELEASE_ID=""
OUTPUT_DIR=""

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
TOOLCHAIN_BIN="$APP_ROOT/shared/toolchains/bin"
STATE_ROOT="/var/lib/cyberboss"
STAGING_STATE="$STATE_ROOT/cb230-staging"
RUNTIME_ROOT=""
KEY_FILE=""
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
EXPECTED_TARGET_HASH="7865f743d174"
UNIT="cyberboss-cloud.service"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"

fail() {
  printf 'DURABLE_OUTBOX_ACCEPTANCE=FAIL reason=%s\n' "$1"
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
  printf 'DURABLE_OUTBOX_ACCEPTANCE_CHECK=PASS release_id=%s persistent_writes=false live_commands=false service_started=false real_credential_reads=false provider_writes=false private_database_operations=false fixed_wait=false canonical_sync_integrated=false cb_240_executed=false pg_2_executed=false\n' \
    "$RELEASE_ID"
  exit 0
fi

RUNTIME_ROOT="$STATE_ROOT/cb230-runtime-$RELEASE_ID"
[[ "$EUID" -eq 0 ]] || fail "root_required"
[[ "$OUTPUT_DIR" == "$STAGING_STATE/evidence/acceptance-$RELEASE_ID" ]] ||
  fail "output_dir_scope"
for command_name in chmod chown cmp find git grep install jq openssl pgrep \
  readlink realpath sort ss stat sudo systemctl; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ -x "$TOOLCHAIN_BIN/node" ]] || fail "pinned_node_missing"
[[ "$("$TOOLCHAIN_BIN/node" --version)" == "v24.18.0" ]] ||
  fail "pinned_node_version"

RELEASE_PATH="$RELEASE_ROOT/$RELEASE_ID"
[[ -d "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]] ||
  fail "candidate_release_missing"
[[ -f "$RELEASE_PATH/release-manifest.json" &&
  -f "$RELEASE_PATH/evidence/outbox-recovery-matrix.json" ]] ||
  fail "candidate_manifest_missing"
jq -e --arg release "$RELEASE_ID" '
  .task_id == "CB-230" and
  .phase == "P2.4" and
  .release_commit == $release and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false and
  .runtime_spool.schema_version == 4 and
  .runtime_spool.channel_poll_integrated == true and
  .runtime_spool.scheduler_integrated == true and
  .runtime_spool.outbox_worker_integrated == true and
  .runtime_spool.pg_2_executed == false and
  .durable_inbox.accepted_outbox_before_cursor == true and
  .durable_inbox.scheduler_integrated == true and
  .durable_inbox.outbox_worker_integrated == true and
  .durable_inbox.real_wechat == false and
  .durable_inbox.real_runtime == false and
  .durable_inbox.pg_2_executed == false and
  .job_scheduler.single_runtime_lease == true and
  .job_scheduler.max_runtime_concurrency == 1 and
  .job_scheduler.outbox_worker_integrated == true and
  .job_scheduler.real_wechat == false and
  .job_scheduler.real_runtime == false and
  .job_scheduler.pg_2_executed == false and
  .durable_outbox.schema_version == 4 and
  .durable_outbox.staged_before_provider == true and
  .durable_outbox.stable_dedupe_key == true and
  .durable_outbox.stable_provider_client_id == true and
  .durable_outbox.max_attempts == 5 and
  .durable_outbox.retry_strategy == "bounded_jittered_exponential" and
  .durable_outbox.provider_confirmation_required == true and
  .durable_outbox.unknown_outcome_auto_replay == false and
  .durable_outbox.terminal_advice_redacted == true and
  .durable_outbox.provider_chunk_limit_code_points == 3800 and
  .durable_outbox.replay_count == 1000 and
  .durable_outbox.accepted_reply_integrated == true and
  .durable_outbox.final_reply_integrated == true and
  .durable_outbox.terminal_reply_integrated == true and
  .durable_outbox.canonical_sync_integrated == false and
  .durable_outbox.real_wechat == false and
  .durable_outbox.real_runtime == false and
  .durable_outbox.cb_240_executed == false and
  .durable_outbox.pg_2_executed == false
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
  "$RUNTIME_ROOT" "$RUNTIME_ROOT/state" "$RUNTIME_ROOT/tmp"
KEY_FILE="$RUNTIME_ROOT/synthetic-aes256.key"
openssl rand -out "$KEY_FILE" 32
chown "$CODE_USER:$CODE_GROUP" "$KEY_FILE"
chmod 0400 "$KEY_FILE"

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

sudo -u "$CODE_USER" -H env \
  HOME="$STAGING_STATE" \
  TMPDIR="$RUNTIME_ROOT/tmp" \
  PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
  "$TOOLCHAIN_BIN/node" \
  "$RELEASE_PATH/app/scripts/durable-outbox-acceptance.js" \
  --runtime-root "$RUNTIME_ROOT/state" \
  --key-file "$KEY_FILE" \
  --output-directory "$OUTPUT_DIR" \
  --release-commit "$RELEASE_ID" \
  --target-id-sha256 "$EXPECTED_TARGET_HASH"

[[ "$(find "$OUTPUT_DIR" -maxdepth 1 -type f -printf '%f\n' | sort)" == \
  "outbox-recovery-matrix.json" ]] ||
  fail "acceptance_output_inventory"
REPORT="$OUTPUT_DIR/outbox-recovery-matrix.json"
cmp -s "$REPORT" \
  "$RELEASE_PATH/evidence/outbox-recovery-matrix.json" ||
  fail "outbox_recovery_report_drift"
jq -e --arg release "$RELEASE_ID" --arg target "$EXPECTED_TARGET_HASH" '
  .task_id == "CB-230" and
  .phase == "P2.4" and
  .release_commit == $release and
  .target_id_sha256 == $target and
  .claim_level == "deterministic_fixture" and
  .generated_from_synthetic_state == true and
  .executable_suite.failures == 0 and
  .executable_suite.fixed_wait == false and
  .executable_suite.real_provider == false and
  .executable_suite.real_credentials == false and
  .ac_020_send_before_crash.outbox_committed_before_provider == true and
  .ac_020_send_before_crash.restart_delivery_count == 1 and
  .ac_020_send_before_crash.final_status == "confirmed" and
  .ac_021_retry.provider_sequence == [503, 503, 200] and
  .ac_021_retry.attempts == 3 and
  .ac_021_retry.retry_delays_ms == [1000, 2000] and
  .ac_021_retry.real_wait_calls == 0 and
  .ac_021_retry.clock == "virtual" and
  .ac_021_retry.final_status == "confirmed" and
  .ac_022_dedupe.stage_count == 1000 and
  .ac_022_dedupe.durable_row_count == 1 and
  .ac_022_dedupe.unique_provider_client_ids == 1 and
  .ac_022_dedupe.confirmed_delivery_count == 1 and
  .ac_024_terminal.original_final_status == "failed_terminal" and
  .ac_024_terminal.advice_staged_with_refreshed_context == true and
  .ac_024_terminal.advice_is_fixed_redacted_text == true and
  .ac_024_terminal.raw_provider_detail_forwarded == false and
  .ac_025_chunks.exceeds_three_times_provider_limit == true and
  .ac_025_chunks.source_sha256 ==
    .ac_025_chunks.reconstructed_sha256 and
  .ac_025_chunks.provider_calls == .ac_025_chunks.chunk_count and
  .ac_025_chunks.replied_before_all_final_chunks_confirmed == false and
  .ac_025_chunks.final_job_status == "replied" and
  .ac_062_recovery.case_count == 4 and
  ([.ac_062_recovery.cases[] | .result == "passed"] | all) and
  .ac_062_recovery.state_predicate_driven == true and
  .ac_062_recovery.fixed_wait == false and
  .ac_062_recovery.false_green_count == 0 and
  .ac_062_recovery.unknown_dispatch_auto_replay_count == 0 and
  .confirmation_truth.provider_confirmation_required == true and
  .confirmation_truth.void_receipt.void_response_confirmed == false and
  .confirmation_truth.replied_before_all_final_chunks_confirmed == false and
  .security.plaintext_db_wal_shm_hits == 0 and
  .security.encryption_key_hits == 0 and
  .security.real_credentials_used == false and
  .security.real_provider_used == false and
  .boundaries.accepted_reply_integrated == true and
  .boundaries.scheduler_integrated == true and
  .boundaries.outbox_worker_integrated == true and
  .boundaries.canonical_sync_integrated == false and
  .boundaries.private_database_operations == false and
  .boundaries.real_wechat == false and
  .boundaries.real_runtime == false and
  .boundaries.cb_240_executed == false and
  .boundaries.pg_2_executed == false and
  .result == "passed"
' "$REPORT" >/dev/null || fail "acceptance_report_contract"
if grep -R -I -nE \
  'CB230-FIXTURE|PRIVATE KEY|Authorization:[[:space:]]*Bearer|gh[pousr]_[A-Za-z0-9]{20,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|wxid_' \
  "$OUTPUT_DIR" >/dev/null 2>&1; then
  fail "acceptance_output_secret"
fi
[[ -z "$(find "$OUTPUT_DIR" -type f \
  \( ! -user "$CODE_USER" -o ! -group "$CODE_GROUP" -o -perm /077 \) \
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

printf 'DURABLE_OUTBOX_ACCEPTANCE=PASS release_id=%s target_id_sha256=%s attempts=3 replay_count=1000 confirmed_delivery_count=1 recovery_cases=4 unknown_dispatch_auto_replay=0 plaintext_hits=0 key_hits=0 real_wait_calls=0 current_changed=false workspace_changed=false service_started=false real_credential_reads=0 provider_writes=0 private_database_operations=0 canonical_sync_integrated=false cb_240_executed=false pg_2_executed=false\n' \
  "$RELEASE_ID" "$EXPECTED_TARGET_HASH"
