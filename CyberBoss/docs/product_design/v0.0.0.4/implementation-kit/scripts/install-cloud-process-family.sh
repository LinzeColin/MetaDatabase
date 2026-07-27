#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
KIT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
MODE=""
RELEASE_ID=""
ARTIFACTS=""
TASK_ID="CB-130"
PHASE=""
STAGING_TAG=""
CONTRACT_PATH=""
ACCEPTANCE_SCRIPT=""
REPORT_PREFIX="CLOUD_PROCESS_INSTALL"

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
TOOLCHAIN_BIN="$APP_ROOT/shared/toolchains/bin"
STATE_ROOT="/var/lib/cyberboss"
CONFIG_ROOT="/etc/cyberboss"
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"
DATA_USER="cyberboss-data"
DATA_GROUP="cyberboss-data"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
UNIT="cyberboss-cloud.service"

fail() {
  printf '%s=FAIL reason=%s\n' "$REPORT_PREFIX" "$1"
  exit 2
}

while (($#)); do
  case "$1" in
    --check|--apply|--verify)
      [[ -z "$MODE" ]] || fail "mode_must_be_unique"
      MODE="${1#--}"
      shift
      ;;
    --release-id)
      (($# >= 2)) || fail "release_id_value_missing"
      RELEASE_ID="$2"
      shift 2
      ;;
    --artifacts)
      (($# >= 2)) || fail "artifacts_value_missing"
      ARTIFACTS="$2"
      shift 2
      ;;
    --task-id)
      (($# >= 2)) || fail "task_id_value_missing"
      TASK_ID="$2"
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
case "$TASK_ID" in
  CB-130)
    PHASE="P1.4"
    STAGING_TAG="cb130"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P1_4_CB_130.md"
    ACCEPTANCE_SCRIPT="accept-cloud-process-family.sh"
    ;;
  CB-140)
    PHASE="P1.5"
    STAGING_TAG="cb140"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P1_5_CB_140.md"
    ACCEPTANCE_SCRIPT="accept-cloud-walking-skeleton.sh"
    REPORT_PREFIX="CLOUD_WALKING_SKELETON_INSTALL"
    ;;
  CB-200)
    PHASE="P2.1"
    STAGING_TAG="cb200"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P2_1_CB_200.md"
    ACCEPTANCE_SCRIPT="accept-runtime-spool.sh"
    REPORT_PREFIX="RUNTIME_SPOOL_INSTALL"
    ;;
  CB-210)
    PHASE="P2.2"
    STAGING_TAG="cb210"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P2_2_CB_210.md"
    ACCEPTANCE_SCRIPT="accept-durable-inbox.sh"
    REPORT_PREFIX="DURABLE_INBOX_INSTALL"
    ;;
  CB-220)
    PHASE="P2.3"
    STAGING_TAG="cb220"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P2_3_CB_220.md"
    ACCEPTANCE_SCRIPT="accept-job-scheduler.sh"
    REPORT_PREFIX="JOB_SCHEDULER_INSTALL"
    ;;
  CB-230)
    PHASE="P2.4"
    STAGING_TAG="cb230"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P2_4_CB_230.md"
    ACCEPTANCE_SCRIPT="accept-durable-outbox.sh"
    REPORT_PREFIX="DURABLE_OUTBOX_INSTALL"
    ;;
  CB-240)
    PHASE="P2.5"
    STAGING_TAG="cb240"
    CONTRACT_PATH="docs/governance/RUN_CONTRACT_P2_5_CB_240.md"
    ACCEPTANCE_SCRIPT="accept-canonical-sync.sh"
    REPORT_PREFIX="CANONICAL_SYNC_INSTALL"
    ;;
  *)
    fail "unsupported_task_id"
    ;;
esac
STAGING_STATE="$STATE_ROOT/$STAGING_TAG-staging"
STAGING_ENV="$CONFIG_ROOT/$STAGING_TAG-staging.env"

for required in \
  "$KIT_ROOT/config/cloud-process-health.json" \
  "$KIT_ROOT/config/cloud-process-tree.txt" \
  "$KIT_ROOT/scripts/run-cyberboss.sh" \
  "$KIT_ROOT/scripts/health-check.sh" \
  "$KIT_ROOT/scripts/$ACCEPTANCE_SCRIPT"; do
  [[ -f "$required" && ! -L "$required" ]] ||
    fail "kit_contract_missing:$(basename "$required")"
done
if [[ "$TASK_ID" == "CB-240" ]]; then
  for required in \
    "$KIT_ROOT/systemd/cyberboss-canonical-sync.service" \
    "$KIT_ROOT/systemd/cyberboss-canonical-sync.timer" \
    "$KIT_ROOT/systemd/cyberboss-canonical-sync-material.service" \
    "$KIT_ROOT/systemd/cyberboss-canonical-sync-material.path" \
    "$KIT_ROOT/scripts/private_db_client_safe.py"; do
    [[ -f "$required" && ! -L "$required" ]] ||
      fail "kit_contract_missing:$(basename "$required")"
  done
fi

python3 - "$KIT_ROOT/config/cloud-process-health.json" \
  "$KIT_ROOT/config/cloud-process-tree.txt" <<'PY' ||
import json
import sys
from pathlib import Path

health = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
tree = Path(sys.argv[2]).read_text(encoding="utf-8")
assert health.get("task_id") == "CB-130"
assert health.get("runtime_endpoint") == "ws://127.0.0.1:8765"
assert health.get("health_endpoint") == "http://127.0.0.1:8780/healthz"
assert health.get("ready_endpoint") == "http://127.0.0.1:8780/readyz"
assert health.get("critical_components") == ["runtime", "channel", "bridge"]
assert health.get("recovery") == {
    "mode": "probe_driven",
    "fixed_wait": False,
    "llm_call": False,
}
assert "KillMode=control-group" in tree
assert "detached=false" in tree
assert "127.0.0.1:8765 only" in tree
assert "127.0.0.1:8780 only" in tree
PY
  fail "kit_contract"

if [[ "$MODE" == "check" ]]; then
  printf '%s_CHECK=PASS task_id=%s release_id=%s persistent_writes=false live_commands=false service_started=false current_changed=false\n' \
    "$REPORT_PREFIX" "$TASK_ID" "$RELEASE_ID"
  exit 0
fi

[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] ||
  fail "unsupported_target_platform"
[[ "$EUID" -eq 0 ]] || fail "root_required"
for command_name in awk cat chmod chown cmp cut find getent git grep install \
  jq ln mktemp mv pgrep python3 readlink realpath sed sha256sum ss stat sudo \
  systemctl tail tar tee; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ -x "$TOOLCHAIN_BIN/node" && -x "$TOOLCHAIN_BIN/npm" &&
  -x "$TOOLCHAIN_BIN/codex" ]] ||
  fail "pinned_toolchain_missing"
"$TOOLCHAIN_BIN/node" --version | grep -Fxq "v24.18.0" ||
  fail "node_version"
"$TOOLCHAIN_BIN/codex" --version |
  grep -Fxq "codex-cli 0.146.0-alpha.3.1" ||
  fail "codex_version"
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
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 )')" ]] ||
  fail "listener_exists_before_install"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "code_process_exists_before_install"

[[ -n "$ARTIFACTS" && "$ARTIFACTS" == /* ]] ||
  fail "artifacts_absolute_path_required"
[[ -d "$ARTIFACTS" && ! -L "$ARTIFACTS" ]] ||
  fail "artifacts_missing_or_symlink"
ARTIFACTS="$(realpath "$ARTIFACTS")"
[[ "$ARTIFACTS" == "$STATE_ROOT/incoming/"* ]] ||
  fail "artifacts_outside_incoming"
for artifact in SHA256SUMS artifact-manifest.json; do
  [[ -f "$ARTIFACTS/$artifact" && ! -L "$ARTIFACTS/$artifact" ]] ||
    fail "artifact_missing_or_symlink:$artifact"
done
(
  cd "$ARTIFACTS"
  sha256sum -c SHA256SUMS >/dev/null
) || fail "artifact_checksum"

MANIFEST="$ARTIFACTS/artifact-manifest.json"
jq -e --arg release "$RELEASE_ID" --arg task "$TASK_ID" --arg phase "$PHASE" '
  .schema_version == 1 and
  .task_id == $task and
  .phase == $phase and
  .release_commit == $release and
  .branch == "codex/cyberboss-prestage0" and
  .repository == "LinzeColin/MetaDatabase" and
  .source.corresponding_source_complete == true and
  .source.original_licenses_preserved == true and
  .source.license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .source.upstream_clarification_received == false and
  .process_family.kill_mode == "control-group" and
  .process_family.detached_children == false and
  .process_family.runtime_endpoint == "ws://127.0.0.1:8765" and
  .process_family.status_endpoint == "http://127.0.0.1:8780" and
  .process_family.simulator_when_auth_pending == true and
  .process_family.configuration_only_provider_switch == true and
  .deployment.candidate_only == true and
  .deployment.switch_current == false and
  .deployment.enable_service == false and
  .deployment.activate_real_credentials == false and
  .deployment.clone_private_database == false and
  .deployment.remote_publication == "none" and
  (if $task == "CB-140" then
    .walking_skeleton.simulator_e2e_expected == 10 and
    .walking_skeleton.latency_samples_expected == 20 and
    .walking_skeleton.max_input_bytes == 32768 and
    .walking_skeleton.trace_raw_content_allowed == false and
    .walking_skeleton.mac_dependency_allowed == false and
    .walking_skeleton.real_adapters == "activation_pending" and
    .walking_skeleton.pg_1_executed == false and
    .walking_skeleton.stage_2_spool_claimed == false
  elif $task == "CB-200" then
    .runtime_spool.schema_version == 2 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.journal_mode == "WAL" and
    .runtime_spool.synchronous == "FULL" and
    .runtime_spool.foreign_keys == true and
    .runtime_spool.busy_timeout_ms == 5000 and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.active_payload_ttl_hours == 24 and
    .runtime_spool.real_canonical_sync == false and
    .runtime_spool.channel_poll_integrated == false and
    .runtime_spool.scheduler_integrated == false and
    .runtime_spool.outbox_worker_integrated == false and
    .runtime_spool.pg_2_executed == false
  elif $task == "CB-210" then
    .runtime_spool.schema_version == 2 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == false and
    .runtime_spool.outbox_worker_integrated == false and
    .runtime_spool.pg_2_executed == false and
    .durable_inbox.candidate_cursor_api == true and
    .durable_inbox.cursor_commit_after_durable == true and
    .durable_inbox.numeric_continuity_guard == true and
    .durable_inbox.stable_source_id_required == true and
    .durable_inbox.replay_count == 1000 and
    .durable_inbox.crash_cut_points == [
      "after_fetch_before_durable",
      "after_durable_before_cursor",
      "after_cursor"
    ] and
    .durable_inbox.channel_poll_integrated == true and
    .durable_inbox.scheduler_integrated == false and
    .durable_inbox.outbox_worker_integrated == false and
    .durable_inbox.real_wechat == false and
    .durable_inbox.real_runtime == false and
    .durable_inbox.pg_2_executed == false
  elif $task == "CB-220" then
    .runtime_spool.schema_version == 3 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == true and
    .runtime_spool.outbox_worker_integrated == false and
    .runtime_spool.pg_2_executed == false and
    .durable_inbox.candidate_cursor_api == true and
    .durable_inbox.cursor_commit_after_durable == true and
    .durable_inbox.numeric_continuity_guard == true and
    .durable_inbox.scheduler_integrated == true and
    .durable_inbox.outbox_worker_integrated == false and
    .durable_inbox.real_wechat == false and
    .durable_inbox.real_runtime == false and
    .durable_inbox.pg_2_executed == false and
    .job_scheduler.single_runtime_lease == true and
    .job_scheduler.max_runtime_concurrency == 1 and
    .job_scheduler.fifo_order == "created_at,id" and
    .job_scheduler.transactional_claim == true and
    .job_scheduler.heartbeat_and_expiry == true and
    .job_scheduler.command_runtime_planes_separated == true and
    .job_scheduler.workspace_alias_gate == true and
    .job_scheduler.resource_readiness_gate == true and
    .job_scheduler.truthful_stop_terminal == true and
    .job_scheduler.unsafe_mutation_auto_replay == false and
    .job_scheduler.outbox_worker_integrated == false and
    .job_scheduler.real_wechat == false and
    .job_scheduler.real_runtime == false and
    .job_scheduler.pg_2_executed == false
  elif $task == "CB-230" then
    .runtime_spool.schema_version == 4 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == true and
    .runtime_spool.outbox_worker_integrated == true and
    .runtime_spool.pg_2_executed == false and
    .durable_inbox.candidate_cursor_api == true and
    .durable_inbox.cursor_commit_after_durable == true and
    .durable_inbox.numeric_continuity_guard == true and
    .durable_inbox.accepted_outbox_before_cursor == true and
    .durable_inbox.scheduler_integrated == true and
    .durable_inbox.outbox_worker_integrated == true and
    .durable_inbox.real_wechat == false and
    .durable_inbox.real_runtime == false and
    .durable_inbox.pg_2_executed == false and
    .job_scheduler.single_runtime_lease == true and
    .job_scheduler.max_runtime_concurrency == 1 and
    .job_scheduler.fifo_order == "created_at,id" and
    .job_scheduler.transactional_claim == true and
    .job_scheduler.heartbeat_and_expiry == true and
    .job_scheduler.unsafe_mutation_auto_replay == false and
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
    .durable_outbox.recovery_cut_points == [
      "pending_before_claim",
      "claimed_before_dispatch",
      "provider_returned_before_confirmation_commit",
      "confirmation_committed_before_crash"
    ] and
    .durable_outbox.accepted_reply_integrated == true and
    .durable_outbox.final_reply_integrated == true and
    .durable_outbox.terminal_reply_integrated == true and
    .durable_outbox.canonical_sync_integrated == false and
    .durable_outbox.real_wechat == false and
    .durable_outbox.real_runtime == false and
    .durable_outbox.cb_240_executed == false and
    .durable_outbox.pg_2_executed == false
  elif $task == "CB-240" then
    .runtime_spool.schema_version == 5 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == true and
    .runtime_spool.outbox_worker_integrated == true and
    .runtime_spool.canonical_sync_integrated == true and
    .runtime_spool.pg_2_executed == false and
    .canonical_sync.schema_version == 1 and
    .canonical_sync.area == "Private-MetaDatabase" and
    .canonical_sync.domain == "CyberBoss" and
    .canonical_sync.branch == "main" and
    .canonical_sync.access_mode == "no_clone_client" and
    .canonical_sync.allowed_operations == ["ingest","get","list","verify"] and
    .canonical_sync.max_records == 50 and
    .canonical_sync.max_uncompressed_bytes == 262144 and
    .canonical_sync.ordinary_sync_schedule == "daily" and
    .canonical_sync.ordinary_sync_on_calendar == "*-*-* 03:20:00 UTC" and
    .canonical_sync.ordinary_remote_age_trigger == false and
    .canonical_sync.immediate_event_types == ["incident_declared","recovery_completed","release_completed"] and
    .canonical_sync.immediate_flush_target_seconds == 60 and
    .canonical_sync.empty_commit_allowed == false and
    .canonical_sync.ordinary_age_blocks_mutation == false and
    .canonical_sync.material_backlog_protects_mutation == true and
    .canonical_sync.max_events_per_invocation == 2000 and
    .canonical_sync.max_uncompressed_bytes_per_invocation == 10485760 and
    .canonical_sync.max_attempts_per_invocation == 5 and
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
  else true end)
' "$MANIFEST" >/dev/null || fail "artifact_manifest_contract"
if [[ "$TASK_ID" == "CB-210" ]]; then
  [[ -f "$ARTIFACTS/durable-inbox-matrix.json" &&
    ! -L "$ARTIFACTS/durable-inbox-matrix.json" ]] ||
    fail "durable_inbox_matrix_missing"
  jq -e --arg release "$RELEASE_ID" '
    .task_id == "CB-210" and
    .phase == "P2.2" and
    .release_commit == $release and
    .generated_from_synthetic_state == true and
    .replay.replay_count == 1000 and
    .replay.inbox_count == 1 and
    .replay.job_count == 1 and
    .replay.execution_count == 1 and
    .database.committed_inbox_rpo == 0 and
    .database.canonical_reconcile_set_diff == 0 and
    .database.integrity_check == "ok" and
    .security.plaintext_db_wal_shm_hits == 0 and
    .security.encryption_key_hits == 0 and
    .boundaries.scheduler_integrated == false and
    .boundaries.outbox_worker_integrated == false and
    .boundaries.real_wechat == false and
    .boundaries.real_runtime == false and
    .boundaries.pg_2_executed == false and
    .result == "passed"
  ' "$ARTIFACTS/durable-inbox-matrix.json" >/dev/null ||
    fail "durable_inbox_matrix_contract"
fi
if [[ "$TASK_ID" == "CB-220" ]]; then
  [[ -f "$ARTIFACTS/job-scheduler-acceptance.json" &&
    ! -L "$ARTIFACTS/job-scheduler-acceptance.json" ]] ||
    fail "job_scheduler_matrix_missing"
  jq -e '
    .task_id == "CB-220" and
    .phase == "P2.3" and
    .claim_level == "deterministic_fixture" and
    .scheduler.queued_runtime_jobs == 5 and
    .scheduler.max_active_runtime_leases == 1 and
    .scheduler.fifo_dispatch_order == true and
    .scheduler.command_runtime_planes_separated == true and
    .workspace.allowlisted_alias_dispatched == true and
    .workspace.absolute_path_dispatched == false and
    .workspace.unknown_alias_dispatched == false and
    .workspace.symlink_escape_dispatched == false and
    .resource_gate.protect_blocks_mutation == true and
    .resource_gate.recover_allows_dispatch == true and
    .stop.cancel_call_count == 3 and
    .stop.acknowledgement_claimed_terminal == false and
    .recovery.ambiguous_mutation_replayed == false and
    .runtime_errors.bounded_mutation_auto_replay == false and
    .phase_boundary.outbox_worker_integrated == false and
    .phase_boundary.real_wechat == false and
    .phase_boundary.real_runtime == false and
    .phase_boundary.pg_2_executed == false and
    .result == "passed"
  ' "$ARTIFACTS/job-scheduler-acceptance.json" >/dev/null ||
    fail "job_scheduler_matrix_contract"
fi
if [[ "$TASK_ID" == "CB-230" ]]; then
  [[ -f "$ARTIFACTS/outbox-recovery-matrix.json" &&
    ! -L "$ARTIFACTS/outbox-recovery-matrix.json" ]] ||
    fail "durable_outbox_matrix_missing"
  jq -e --arg release "$RELEASE_ID" '
    .task_id == "CB-230" and
    .phase == "P2.4" and
    .release_commit == $release and
    .claim_level == "deterministic_fixture" and
    .generated_from_synthetic_state == true and
    .ac_020_send_before_crash.outbox_committed_before_provider == true and
    .ac_020_send_before_crash.restart_delivery_count == 1 and
    .ac_021_retry.provider_sequence == [503, 503, 200] and
    .ac_021_retry.attempts == 3 and
    .ac_021_retry.retry_delays_ms == [1000, 2000] and
    .ac_021_retry.real_wait_calls == 0 and
    .ac_022_dedupe.stage_count == 1000 and
    .ac_022_dedupe.confirmed_delivery_count == 1 and
    .ac_024_terminal.raw_provider_detail_forwarded == false and
    .ac_025_chunks.source_sha256 ==
      .ac_025_chunks.reconstructed_sha256 and
    .ac_025_chunks.replied_before_all_final_chunks_confirmed == false and
    .ac_062_recovery.case_count == 4 and
    .ac_062_recovery.fixed_wait == false and
    .ac_062_recovery.false_green_count == 0 and
    .ac_062_recovery.unknown_dispatch_auto_replay_count == 0 and
    .confirmation_truth.void_receipt.void_response_confirmed == false and
    .security.plaintext_db_wal_shm_hits == 0 and
    .security.encryption_key_hits == 0 and
    .boundaries.outbox_worker_integrated == true and
    .boundaries.canonical_sync_integrated == false and
    .boundaries.cb_240_executed == false and
    .boundaries.pg_2_executed == false and
    .result == "passed"
  ' "$ARTIFACTS/outbox-recovery-matrix.json" >/dev/null ||
    fail "durable_outbox_matrix_contract"
fi
if [[ "$TASK_ID" == "CB-240" ]]; then
  [[ -f "$ARTIFACTS/canonical-sync-report.json" &&
    ! -L "$ARTIFACTS/canonical-sync-report.json" ]] ||
    fail "canonical_sync_report_missing"
  jq -e --arg release "$RELEASE_ID" '
    .task_id == "CB-240" and
    .phase == "P2.5" and
    .release_commit == $release and
    .claim_level == "deterministic_fixture" and
    .generated_from_synthetic_state == true and
    .ac_030_rebuild.sqlite_present == false and
    .ac_030_rebuild.canonical_event_count == 1000 and
    .ac_030_rebuild.terminal_job_count == 1000 and
    .ac_030_rebuild.r2_fixture_only == true and
    .ac_030_rebuild.real_r2_operation == false and
    .ac_031_batching_latency.ordinary_events == 50 and
    .ac_031_batching_latency.material_events == 3 and
    .ac_031_batching_latency.material_event_types == ["incident_declared","recovery_completed","release_completed"] and
    .ac_031_batching_latency.ordinary_sync_schedule == "daily" and
    .ac_031_batching_latency.ordinary_sync_on_calendar == "*-*-* 03:20:00 UTC" and
    .ac_031_batching_latency.ordinary_remote_commits_before_daily == 0 and
    .ac_031_batching_latency.empty_commits == 0 and
    .ac_031_batching_latency.no_new_fact_status == "noop_no_commit" and
    .ac_031_batching_latency.ordinary_age_blocks_mutation == false and
    .ac_031_batching_latency.ordinary_age_remote_trigger == false and
    .ac_031_batching_latency.material_latency_p95_seconds <= 60 and
    .ac_031_batching_latency.terminal_events == 1000 and
    .ac_031_batching_latency.count_threshold_batch_count == 20 and
    .ac_031_batching_latency.set_diff == 0 and
    .ac_032_conflict_retry.concurrent_sync_groups == 50 and
    .ac_032_conflict_retry.initial_pending_groups == 3 and
    .ac_032_conflict_retry.outage_duration_seconds == 600 and
    .ac_032_conflict_retry.real_wait_calls == 0 and
    .ac_032_conflict_retry.set_diff == 0 and
    .ac_033_privacy.full_prompt_result_identity_hits == 0 and
    .ac_033_privacy.encryption_key_hits == 0 and
    .integrity_protection.last_write_wins == false and
    .integrity_protection.bounded_mutation_allowed == false and
    .canonical_truth.allowed_operations == ["ingest","get","list","verify"] and
    .canonical_truth.forbidden_operations == ["clone","put","delete"] and
    .boundaries.real_private_database_operation == false and
    .boundaries.private_database_activation_status ==
      "activation_pending" and
    .boundaries.cb_300_executed == false and
    .boundaries.pg_2_executed == false and
    .boundaries.remote_publication == "none" and
    .result == "passed"
  ' "$ARTIFACTS/canonical-sync-report.json" >/dev/null ||
    fail "canonical_sync_report_contract"
fi

SOURCE_ARCHIVE="$(jq -er '.source.archive' "$MANIFEST")"
[[ "$SOURCE_ARCHIVE" == "cyberboss-source-$RELEASE_ID.tar.gz" ]] ||
  fail "source_archive_name"
[[ -f "$ARTIFACTS/$SOURCE_ARCHIVE" &&
  ! -L "$ARTIFACTS/$SOURCE_ARCHIVE" ]] ||
  fail "source_archive_missing"
[[ "$(sha256sum "$ARTIFACTS/$SOURCE_ARCHIVE" | cut -d' ' -f1)" == \
  "$(jq -er '.source.sha256' "$MANIFEST")" ]] ||
  fail "source_archive_hash"

archive_paths_safe() {
  local archive="$1"
  local entry
  while IFS= read -r entry; do
    [[ -n "$entry" ]] || continue
    [[ "$entry" != /* ]] || return 1
    case "/$entry/" in
      *"/../"*|*"/./"*) return 1 ;;
    esac
    [[ "$entry" == "cyberboss-source" ||
      "$entry" == "cyberboss-source/"* ]] || return 1
  done < <(tar -tzf "$archive")
}
archive_paths_safe "$ARTIFACTS/$SOURCE_ARCHIVE" ||
  fail "source_archive_paths"

TMP_ROOT="$(mktemp -d "/tmp/cyberboss-$STAGING_TAG-install.XXXXXXXX")"
RELEASE_STAGE=""
cleanup() {
  local exit_code=$?
  if [[ -n "${RELEASE_STAGE:-}" ]]; then
    case "$RELEASE_STAGE" in
      "$RELEASE_ROOT"/."$STAGING_TAG"-"$RELEASE_ID"-*)
        find "$RELEASE_STAGE" -xdev -depth -delete 2>/dev/null || true
        ;;
      *)
        printf '%s=FAIL reason=unsafe_release_cleanup\n' "$REPORT_PREFIX" >&2
        exit 70
        ;;
    esac
  fi
  case "${TMP_ROOT:-}" in
    /tmp/cyberboss-"$STAGING_TAG"-install.*)
      find "$TMP_ROOT" -xdev -depth -delete 2>/dev/null || true
      ;;
    *)
      printf '%s=FAIL reason=unsafe_tmp_cleanup\n' "$REPORT_PREFIX" >&2
      exit 70
      ;;
  esac
  return "$exit_code"
}
trap cleanup EXIT

assert_no_escaping_symlink() {
  local root="$1"
  local link target resolved
  while IFS= read -r -d '' link; do
    target="$(readlink "$link")"
    [[ "$target" != /* ]] || fail "absolute_symlink:$link"
    resolved="$(realpath -m "$(dirname "$link")/$target")"
    [[ "$resolved" == "$root" || "$resolved" == "$root/"* ]] ||
      fail "escaping_symlink:$link"
  done < <(find "$root" -type l -print0)
}

harden_tree() {
  local root="$1"
  chown -hR root:"$CODE_GROUP" "$root"
  find "$root" -type d -exec chmod 0550 {} +
  find "$root" -type f -perm /111 -exec chmod 0550 {} +
  find "$root" -type f ! -perm /111 -exec chmod 0440 {} +
}

RELEASE_PATH="$RELEASE_ROOT/$RELEASE_ID"
RELEASE_ACTION="verified"
TEST_COUNT="not_rerun"
if [[ ! -e "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]]; then
  [[ "$MODE" == "apply" ]] || fail "candidate_release_missing"
  RELEASE_STAGE="$RELEASE_ROOT/.$STAGING_TAG-$RELEASE_ID-$$"
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 "$RELEASE_STAGE"
  tar -xzf "$ARTIFACTS/$SOURCE_ARCHIVE" \
    --strip-components=1 -C "$RELEASE_STAGE"
  assert_no_escaping_symlink "$RELEASE_STAGE"
  for required in LICENSE app/LICENSE app/package-lock.json \
    app/scripts/cloud-supervisor.js \
    vendor/timeline-for-agent/LICENSE vendor/whereabouts-mcp/LICENSE \
    docs/evidence/CB-000/LICENSE_COMPLIANCE.md \
    "$CONTRACT_PATH" \
    machine/facts/post-baseline-change-ledger.json; do
    [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
      fail "candidate_corresponding_source:$required"
  done
  if [[ "$TASK_ID" == "CB-140" ]]; then
    for required in \
      app/src/core/walking-skeleton-trace.js \
      app/test/cloud-walking-skeleton.test.js \
      app/test/cloud-walking-skeleton-live.test.js \
      docs/product_design/v0.0.0.4/implementation-kit/scripts/run-walking-skeleton-acceptance.mjs; do
      [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
        fail "candidate_walking_skeleton_source:$required"
    done
  fi
  if [[ "$TASK_ID" == "CB-200" ]]; then
    for required in \
      app/migrations/001_runtime_spool.sql \
      app/migrations/002_cb200_retention_and_transitions.sql \
      app/scripts/runtime-spool-acceptance.js \
      app/src/services/db/database-adapter.js \
      app/src/services/jobs/job-state-machine.js \
      app/test/job-state-machine.test.js \
      app/test/runtime-spool.test.js; do
      [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
        fail "candidate_runtime_spool_source:$required"
    done
  fi
  if [[ "$TASK_ID" == "CB-210" ]]; then
    for required in \
      app/migrations/001_runtime_spool.sql \
      app/migrations/002_cb200_retention_and_transitions.sql \
      app/scripts/durable-inbox-acceptance.js \
      app/src/adapters/channel/weixin/index.js \
      app/src/adapters/channel/weixin/sync-buffer-store.js \
      app/src/services/db/database-adapter.js \
      app/src/services/inbox/durable-inbox.js \
      app/test/durable-inbox-crash-cut.test.js \
      app/test/weixin-cursor-commit.test.js; do
      [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
        fail "candidate_durable_inbox_source:$required"
    done
  fi
  if [[ "$TASK_ID" == "CB-220" ]]; then
    for required in \
      app/migrations/001_runtime_spool.sql \
      app/migrations/002_cb200_retention_and_transitions.sql \
      app/migrations/003_cb220_scheduler_control.sql \
      app/scripts/job-scheduler-acceptance.js \
      app/src/adapters/runtime/claudecode/events.js \
      app/src/adapters/runtime/codex/events.js \
      app/src/services/db/database-adapter.js \
      app/src/services/jobs/job-scheduler.js \
      app/src/services/jobs/resource-readiness-gate.js \
      app/test/job-scheduler.test.js \
      app/test/resource-readiness-gate.test.js \
      app/test/workspace-scope.test.js \
      docs/product_design/v0.0.0.4/implementation-kit/scripts/resource-pressure-fixture.py; do
      [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
        fail "candidate_job_scheduler_source:$required"
    done
  fi
  if [[ "$TASK_ID" == "CB-230" ]]; then
    for required in \
      app/migrations/001_runtime_spool.sql \
      app/migrations/002_cb200_retention_and_transitions.sql \
      app/migrations/003_cb220_scheduler_control.sql \
      app/migrations/004_cb230_durable_outbox.sql \
      app/scripts/durable-outbox-acceptance.js \
      app/src/adapters/channel/weixin/api.js \
      app/src/adapters/channel/weixin/index.js \
      app/src/core/app.js \
      app/src/core/stream-delivery.js \
      app/src/services/db/database-adapter.js \
      app/src/services/inbox/durable-inbox.js \
      app/src/services/jobs/job-scheduler.js \
      app/src/services/outbox/durable-outbox.js \
      app/test/durable-inbox-crash-cut.test.js \
      app/test/durable-outbox-crash-cut.test.js \
      app/test/stream-delivery.test.js \
      app/test/weixin-outbox-transport.test.js; do
      [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
        fail "candidate_durable_outbox_source:$required"
    done
  fi
  if [[ "$TASK_ID" == "CB-240" ]]; then
    for required in \
      app/migrations/001_runtime_spool.sql \
      app/migrations/002_cb200_retention_and_transitions.sql \
      app/migrations/003_cb220_scheduler_control.sql \
      app/migrations/004_cb230_durable_outbox.sql \
      app/migrations/005_cb240_canonical_sync.sql \
      app/scripts/canonical-rebuild.js \
      app/scripts/canonical-sync-acceptance.js \
      app/scripts/canonical-sync-data.js \
      app/src/services/canonical/canonical-sync.js \
      app/src/services/db/database-adapter.js \
      app/src/services/jobs/job-scheduler.js \
      app/test/canonical-sync.test.js \
      app/test/job-scheduler.test.js \
      tests/canonical-sync.test.js; do
      [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
        fail "candidate_canonical_sync_source:$required"
    done
  fi
  chown -R "$CODE_USER:$CODE_GROUP" "$RELEASE_STAGE"
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 "$STATE_ROOT/cache/npm"
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" \
    PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
    npm_config_cache="$STATE_ROOT/cache/npm" \
    "$TOOLCHAIN_BIN/npm" --prefix "$RELEASE_STAGE/app" ci \
      --ignore-scripts --no-audit --no-fund
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
    "$TOOLCHAIN_BIN/npm" --prefix "$RELEASE_STAGE/app" run check
  TEST_OUTPUT="$TMP_ROOT/app-tests.txt"
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
    "$TOOLCHAIN_BIN/npm" --prefix "$RELEASE_STAGE/app" test |
    tee "$TEST_OUTPUT"
  TEST_COUNT="$(awk '
    $2 == "tests" && $3 ~ /^[0-9]+$/ { count = $3 }
    END { if (count != "") print count }
  ' "$TEST_OUTPUT")"
  [[ "$TEST_COUNT" =~ ^[0-9]+$ ]] || fail "candidate_test_count"
  ln -s "docs/product_design/v0.0.0.4/implementation-kit" \
    "$RELEASE_STAGE/implementation-kit"
  if [[ "$TASK_ID" == "CB-200" || "$TASK_ID" == "CB-210" ||
    "$TASK_ID" == "CB-220" || "$TASK_ID" == "CB-230" ||
    "$TASK_ID" == "CB-240" ]]; then
    ln -s "app/migrations" "$RELEASE_STAGE/migrations"
    jq '{
      schema_version: 1,
      task_id,
      phase,
      release_commit,
      runtime_spool
    }' "$MANIFEST" >"$RELEASE_STAGE/schema-manifest.json"
  fi
  if [[ "$TASK_ID" == "CB-210" ]]; then
    install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 \
      "$RELEASE_STAGE/evidence"
    install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
      "$ARTIFACTS/durable-inbox-matrix.json" \
      "$RELEASE_STAGE/evidence/durable-inbox-matrix.json"
  fi
  if [[ "$TASK_ID" == "CB-220" ]]; then
    install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 \
      "$RELEASE_STAGE/evidence"
    install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
      "$ARTIFACTS/job-scheduler-acceptance.json" \
      "$RELEASE_STAGE/evidence/job-scheduler-acceptance.json"
  fi
  if [[ "$TASK_ID" == "CB-230" ]]; then
    install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 \
      "$RELEASE_STAGE/evidence"
    install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
      "$ARTIFACTS/outbox-recovery-matrix.json" \
      "$RELEASE_STAGE/evidence/outbox-recovery-matrix.json"
  fi
  if [[ "$TASK_ID" == "CB-240" ]]; then
    install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 \
      "$RELEASE_STAGE/evidence"
    install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
      "$ARTIFACTS/canonical-sync-report.json" \
      "$RELEASE_STAGE/evidence/canonical-sync-report.json"
  fi
  install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
    "$KIT_ROOT/config/cloud-process-health.json" \
    "$RELEASE_STAGE/health-contract.json"
  install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
    "$KIT_ROOT/config/cloud-process-tree.txt" \
    "$RELEASE_STAGE/process-tree.txt"
  jq -n --slurpfile artifact "$MANIFEST" \
    --arg task_id "$TASK_ID" \
    --arg phase "$PHASE" \
    --arg release_commit "$RELEASE_ID" \
    --arg repository_tree "$(jq -er '.repository_tree' "$MANIFEST")" \
    --arg cyberboss_tree "$(jq -er '.cyberboss_tree' "$MANIFEST")" \
    --arg source_archive_sha256 "$(jq -er '.source.sha256' "$MANIFEST")" \
    --argjson app_test_count "$TEST_COUNT" \
    '{
      schema_version: 1,
      task_id: $task_id,
      phase: $phase,
      release_commit: $release_commit,
      repository_tree: $repository_tree,
      cyberboss_tree: $cyberboss_tree,
      source_archive_sha256: $source_archive_sha256,
      app_test_count: $app_test_count,
      corresponding_source_complete: true,
      license_expression: "AGPL-3.0-only AND GPL-3.0-only",
      upstream_clarification_received: false,
      process_family: {
        kill_mode: "control-group",
        detached_children: false,
        runtime_endpoint: "ws://127.0.0.1:8765",
        status_endpoint: "http://127.0.0.1:8780"
      },
      candidate_only: true,
      current_switched: false,
      service_enabled: false,
      real_adapter_activation: "activation_pending"
    }
    | if $task_id == "CB-200"
      then . + {runtime_spool: $artifact[0].runtime_spool}
      elif $task_id == "CB-210"
      then . + {
        runtime_spool: $artifact[0].runtime_spool,
        durable_inbox: $artifact[0].durable_inbox
      }
      elif $task_id == "CB-220"
      then . + {
        runtime_spool: $artifact[0].runtime_spool,
        durable_inbox: $artifact[0].durable_inbox,
        job_scheduler: $artifact[0].job_scheduler
      }
      elif $task_id == "CB-230"
      then . + {
        runtime_spool: $artifact[0].runtime_spool,
        durable_inbox: $artifact[0].durable_inbox,
        job_scheduler: $artifact[0].job_scheduler,
        durable_outbox: $artifact[0].durable_outbox
      }
      elif $task_id == "CB-240"
      then . + {
        runtime_spool: $artifact[0].runtime_spool,
        canonical_sync: $artifact[0].canonical_sync
      }
      else .
      end' >"$RELEASE_STAGE/release-manifest.json"
  assert_no_escaping_symlink "$RELEASE_STAGE"
  harden_tree "$RELEASE_STAGE"
  mv -T "$RELEASE_STAGE" "$RELEASE_PATH"
  RELEASE_STAGE=""
  RELEASE_ACTION="installed_and_tested"
elif [[ ! -d "$RELEASE_PATH" || -L "$RELEASE_PATH" ]]; then
  fail "candidate_release_collision"
fi

jq -e --arg release "$RELEASE_ID" \
  --arg task "$TASK_ID" --arg phase "$PHASE" \
  --arg source_sha "$(jq -er '.source.sha256' "$MANIFEST")" '
  .schema_version == 1 and
  .task_id == $task and
  .phase == $phase and
  .release_commit == $release and
  .source_archive_sha256 == $source_sha and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .process_family.kill_mode == "control-group" and
  .process_family.detached_children == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false and
  .real_adapter_activation == "activation_pending" and
  (if $task == "CB-200" then
    .runtime_spool.schema_version == 2 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.real_canonical_sync == false and
    .runtime_spool.pg_2_executed == false
  elif $task == "CB-210" then
    .runtime_spool.schema_version == 2 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == false and
    .runtime_spool.outbox_worker_integrated == false and
    .runtime_spool.pg_2_executed == false and
    .durable_inbox.candidate_cursor_api == true and
    .durable_inbox.cursor_commit_after_durable == true and
    .durable_inbox.numeric_continuity_guard == true and
    .durable_inbox.replay_count == 1000 and
    .durable_inbox.scheduler_integrated == false and
    .durable_inbox.outbox_worker_integrated == false and
    .durable_inbox.real_wechat == false and
    .durable_inbox.real_runtime == false and
    .durable_inbox.pg_2_executed == false
  elif $task == "CB-220" then
    .runtime_spool.schema_version == 3 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == true and
    .runtime_spool.outbox_worker_integrated == false and
    .runtime_spool.pg_2_executed == false and
    .durable_inbox.candidate_cursor_api == true and
    .durable_inbox.cursor_commit_after_durable == true and
    .durable_inbox.numeric_continuity_guard == true and
    .durable_inbox.scheduler_integrated == true and
    .durable_inbox.outbox_worker_integrated == false and
    .durable_inbox.real_wechat == false and
    .durable_inbox.real_runtime == false and
    .durable_inbox.pg_2_executed == false and
    .job_scheduler.single_runtime_lease == true and
    .job_scheduler.max_runtime_concurrency == 1 and
    .job_scheduler.fifo_order == "created_at,id" and
    .job_scheduler.transactional_claim == true and
    .job_scheduler.heartbeat_and_expiry == true and
    .job_scheduler.command_runtime_planes_separated == true and
    .job_scheduler.workspace_alias_gate == true and
    .job_scheduler.resource_readiness_gate == true and
    .job_scheduler.truthful_stop_terminal == true and
    .job_scheduler.unsafe_mutation_auto_replay == false and
    .job_scheduler.outbox_worker_integrated == false and
    .job_scheduler.real_wechat == false and
    .job_scheduler.real_runtime == false and
    .job_scheduler.pg_2_executed == false
  elif $task == "CB-230" then
    .runtime_spool.schema_version == 4 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == true and
    .runtime_spool.outbox_worker_integrated == true and
    .runtime_spool.pg_2_executed == false and
    .durable_inbox.candidate_cursor_api == true and
    .durable_inbox.cursor_commit_after_durable == true and
    .durable_inbox.numeric_continuity_guard == true and
    .durable_inbox.accepted_outbox_before_cursor == true and
    .durable_inbox.scheduler_integrated == true and
    .durable_inbox.outbox_worker_integrated == true and
    .durable_inbox.real_wechat == false and
    .durable_inbox.real_runtime == false and
    .durable_inbox.pg_2_executed == false and
    .job_scheduler.single_runtime_lease == true and
    .job_scheduler.max_runtime_concurrency == 1 and
    .job_scheduler.fifo_order == "created_at,id" and
    .job_scheduler.transactional_claim == true and
    .job_scheduler.heartbeat_and_expiry == true and
    .job_scheduler.unsafe_mutation_auto_replay == false and
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
  elif $task == "CB-240" then
    .runtime_spool.schema_version == 5 and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    .runtime_spool.channel_poll_integrated == true and
    .runtime_spool.scheduler_integrated == true and
    .runtime_spool.outbox_worker_integrated == true and
    .runtime_spool.canonical_sync_integrated == true and
    .runtime_spool.pg_2_executed == false and
    .canonical_sync.schema_version == 1 and
    .canonical_sync.area == "Private-MetaDatabase" and
    .canonical_sync.domain == "CyberBoss" and
    .canonical_sync.branch == "main" and
    .canonical_sync.access_mode == "no_clone_client" and
    .canonical_sync.max_records == 50 and
    .canonical_sync.max_uncompressed_bytes == 262144 and
    .canonical_sync.ordinary_sync_schedule == "daily" and
    .canonical_sync.ordinary_sync_on_calendar == "*-*-* 03:20:00 UTC" and
    .canonical_sync.ordinary_remote_age_trigger == false and
    .canonical_sync.immediate_event_types == ["incident_declared","recovery_completed","release_completed"] and
    .canonical_sync.immediate_flush_target_seconds == 60 and
    .canonical_sync.empty_commit_allowed == false and
    .canonical_sync.ordinary_age_blocks_mutation == false and
    .canonical_sync.material_backlog_protects_mutation == true and
    .canonical_sync.max_events_per_invocation == 2000 and
    .canonical_sync.max_uncompressed_bytes_per_invocation == 10485760 and
    .canonical_sync.max_attempts_per_invocation == 5 and
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
  else true end)
' "$RELEASE_PATH/release-manifest.json" >/dev/null ||
  fail "candidate_release_manifest"
[[ -f "$RELEASE_PATH/health-contract.json" &&
  -f "$RELEASE_PATH/process-tree.txt" &&
  -f "$RELEASE_PATH/app/scripts/cloud-supervisor.js" ]] ||
  fail "candidate_contract_files"
if [[ "$TASK_ID" == "CB-200" || "$TASK_ID" == "CB-210" ||
  "$TASK_ID" == "CB-220" || "$TASK_ID" == "CB-230" ||
  "$TASK_ID" == "CB-240" ]]; then
  [[ -L "$RELEASE_PATH/migrations" &&
    "$(realpath "$RELEASE_PATH/migrations")" == \
      "$RELEASE_PATH/app/migrations" &&
    -f "$RELEASE_PATH/schema-manifest.json" ]] ||
    fail "candidate_runtime_spool_contract_files"
  jq -e --arg release "$RELEASE_ID" \
    --arg task "$TASK_ID" --arg phase "$PHASE" '
    .schema_version == 1 and
    .task_id == $task and
    .phase == $phase and
    .release_commit == $release and
    .runtime_spool.schema_version ==
      (if $task == "CB-240" then 5
       elif $task == "CB-230" then 4
       elif $task == "CB-220" then 3
       else 2 end) and
    .runtime_spool.migration_mode == "additive_backward_compatible" and
    .runtime_spool.active_payload_encryption == "AES-256-GCM" and
    (if $task == "CB-240"
     then .runtime_spool.canonical_sync_integrated == true
     else .runtime_spool.real_canonical_sync == false end)
  ' "$RELEASE_PATH/schema-manifest.json" >/dev/null ||
    fail "candidate_schema_manifest"
  for migration in \
    001_runtime_spool.sql \
    002_cb200_retention_and_transitions.sql; do
    [[ "$(sha256sum "$RELEASE_PATH/app/migrations/$migration" |
      cut -d' ' -f1)" == \
      "$(jq -er --arg migration "$migration" \
        '.runtime_spool.migration_sha256[$migration]' \
        "$RELEASE_PATH/schema-manifest.json")" ]] ||
      fail "candidate_migration_hash:$migration"
  done
  if [[ "$TASK_ID" == "CB-220" || "$TASK_ID" == "CB-230" ||
    "$TASK_ID" == "CB-240" ]]; then
    migration="003_cb220_scheduler_control.sql"
    [[ "$(sha256sum "$RELEASE_PATH/app/migrations/$migration" |
      cut -d' ' -f1)" == \
      "$(jq -er --arg migration "$migration" \
        '.runtime_spool.migration_sha256[$migration]' \
        "$RELEASE_PATH/schema-manifest.json")" ]] ||
      fail "candidate_migration_hash:$migration"
  fi
  if [[ "$TASK_ID" == "CB-230" || "$TASK_ID" == "CB-240" ]]; then
    migration="004_cb230_durable_outbox.sql"
    [[ "$(sha256sum "$RELEASE_PATH/app/migrations/$migration" |
      cut -d' ' -f1)" == \
      "$(jq -er --arg migration "$migration" \
        '.runtime_spool.migration_sha256[$migration]' \
        "$RELEASE_PATH/schema-manifest.json")" ]] ||
      fail "candidate_migration_hash:$migration"
  fi
  if [[ "$TASK_ID" == "CB-240" ]]; then
    migration="005_cb240_canonical_sync.sql"
    [[ "$(sha256sum "$RELEASE_PATH/app/migrations/$migration" |
      cut -d' ' -f1)" == \
      "$(jq -er --arg migration "$migration" \
        '.runtime_spool.migration_sha256[$migration]' \
        "$RELEASE_PATH/schema-manifest.json")" ]] ||
      fail "candidate_migration_hash:$migration"
  fi
fi
if [[ "$TASK_ID" == "CB-210" ]]; then
  [[ -f "$RELEASE_PATH/evidence/durable-inbox-matrix.json" &&
    ! -L "$RELEASE_PATH/evidence/durable-inbox-matrix.json" ]] ||
    fail "candidate_durable_inbox_matrix"
  cmp -s "$ARTIFACTS/durable-inbox-matrix.json" \
    "$RELEASE_PATH/evidence/durable-inbox-matrix.json" ||
    fail "candidate_durable_inbox_matrix_drift"
fi
if [[ "$TASK_ID" == "CB-220" ]]; then
  [[ -f "$RELEASE_PATH/evidence/job-scheduler-acceptance.json" &&
    ! -L "$RELEASE_PATH/evidence/job-scheduler-acceptance.json" ]] ||
    fail "candidate_job_scheduler_matrix"
  cmp -s "$ARTIFACTS/job-scheduler-acceptance.json" \
    "$RELEASE_PATH/evidence/job-scheduler-acceptance.json" ||
    fail "candidate_job_scheduler_matrix_drift"
fi
if [[ "$TASK_ID" == "CB-230" ]]; then
  [[ -f "$RELEASE_PATH/evidence/outbox-recovery-matrix.json" &&
    ! -L "$RELEASE_PATH/evidence/outbox-recovery-matrix.json" ]] ||
    fail "candidate_durable_outbox_matrix"
  cmp -s "$ARTIFACTS/outbox-recovery-matrix.json" \
    "$RELEASE_PATH/evidence/outbox-recovery-matrix.json" ||
    fail "candidate_durable_outbox_matrix_drift"
fi
if [[ "$TASK_ID" == "CB-240" ]]; then
  [[ -f "$RELEASE_PATH/evidence/canonical-sync-report.json" &&
    ! -L "$RELEASE_PATH/evidence/canonical-sync-report.json" ]] ||
    fail "candidate_canonical_sync_report"
  cmp -s "$ARTIFACTS/canonical-sync-report.json" \
    "$RELEASE_PATH/evidence/canonical-sync-report.json" ||
    fail "candidate_canonical_sync_report_drift"
fi
[[ -L "$RELEASE_PATH/implementation-kit" &&
  "$(realpath "$RELEASE_PATH/implementation-kit")" == \
    "$RELEASE_PATH/docs/product_design/v0.0.0.4/implementation-kit" ]] ||
  fail "candidate_implementation_kit_link"
assert_no_escaping_symlink "$RELEASE_PATH"
[[ -z "$(find "$RELEASE_PATH" \( -type f -o -type d \) \
  \( ! -user root -o ! -group "$CODE_GROUP" -o -perm /022 \) \
  -print -quit)" ]] ||
  fail "candidate_release_mutable"
[[ -z "$(find "$RELEASE_PATH" -type l \
  \( ! -user root -o ! -group "$CODE_GROUP" \) -print -quit)" ]] ||
  fail "candidate_release_symlink_owner"

ENV_STAGE="$TMP_ROOT/$STAGING_TAG-staging.env"
cat >"$ENV_STAGE" <<ENV
NODE_ENV=production
TZ=UTC
CB_PRODUCT_VERSION=0.0.0.5
CYBERBOSS_USER_NAME=Fixture
CYBERBOSS_USER_GENDER=neutral
CYBERBOSS_ALLOWED_USER_IDS=sim-authorized-user
CYBERBOSS_STATE_DIR=$STAGING_STATE
CYBERBOSS_SHARED_ROOT=$STAGING_STATE
CYBERBOSS_WORKSPACE_CONFIG=$CONFIG_ROOT/workspaces.json
CYBERBOSS_WORKSPACE_BASE=/srv/cyberboss-workspaces
CYBERBOSS_WORKSPACE_ALIAS=cyberboss
CYBERBOSS_WORKSPACE_ROOT=$WORKSPACE
GIT_CONFIG_SYSTEM=$CONFIG_ROOT/cyberboss.gitconfig
CYBERBOSS_RUNTIME=codex
CYBERBOSS_CODEX_ENDPOINT=ws://127.0.0.1:8765
CYBERBOSS_CODEX_LISTEN=ws://127.0.0.1:8765
CYBERBOSS_CODEX_COMMAND=$TOOLCHAIN_BIN/codex
CYBERBOSS_WEIXIN_BASE_URL=http://127.0.0.1:19080/
CB_RUNTIME_PROVIDER=simulator
CB_CHANNEL_PROVIDER=simulator
CB_CLAUDE_RUNTIME=false
CB_CLAUDE_EVAL_PASSED=false
CB_RELEASE_ROOT=$RELEASE_PATH
CB_EXPECTED_RELEASE_ID=$RELEASE_ID
CB_STATUS_TOKEN_FILE=/run/cyberboss-$STAGING_TAG/status.token
CB_HTTP_HOST=127.0.0.1
CB_HTTP_PORT=8780
CB_ENV_FILE=$STAGING_ENV
CB_REQUIRE_RUNTIME_DB=false
CB_RUNTIME_DB=$STAGING_STATE/runtime.db
CB_RUNTIME_ENCRYPTION_KEY_FILE=$STAGING_STATE/credentials/runtime-encryption.key
CB_RUNTIME_IDENTITY_KEY_FILE=$STAGING_STATE/credentials/runtime-identity.key
CB_STATUS_PATH=$STAGING_STATE/status/snapshot.json
CB_SINGLETON_LOCK=$STATE_ROOT/locks/bridge.lock
CB_DURABLE_INBOX=true
CB_DURABLE_OUTBOX=true
CB_OUTBOX_LEASE_MS=10000
CB_OUTBOX_MAX_ATTEMPTS=5
CB_OUTBOX_BASE_DELAY_MS=1000
CB_OUTBOX_MAX_DELAY_MS=60000
CB_OUTBOX_CHUNK_CHARS=3600
CB_PRIVATE_DB_CANONICAL_SYNC=true
# Legacy aliases stay parse-compatible, but never trigger a remote sync by age.
CB_CANONICAL_FLUSH_ON_TERMINAL=true
CB_CANONICAL_BATCH_MAX_AGE_MS=60000
CB_CANONICAL_ORDINARY_SYNC_SCHEDULE=daily
CB_CANONICAL_ORDINARY_SYNC_ON_CALENDAR=*-*-* 03:20:00 UTC
CB_CANONICAL_MATERIAL_EVENT_TYPES=release_completed,incident_declared,recovery_completed
CB_CANONICAL_MAX_EVENTS_PER_INVOCATION=2000
CB_CANONICAL_MAX_UNCOMPRESSED_BYTES_PER_INVOCATION=10485760
CB_CANONICAL_MAX_ATTEMPTS_PER_INVOCATION=5
CB_CANONICAL_SPOOL_ROOT=$STATE_ROOT/canonical-spool
CB_CANONICAL_DATA_STATE_ROOT=/var/lib/cyberboss-data/canonical-sync
CB_CANONICAL_BATCH_MAX=50
CB_CANONICAL_BATCH_MAX_BYTES=262144
CB_CANONICAL_BACKLOG_MAX_EVENTS=10000
CB_CANONICAL_BACKLOG_MAX_BYTES=67108864
CB_CANONICAL_MAX_LAG_SECONDS=900
CB_TIMELINE_WEB=true
CB_STATUS_EXPORTER=true
CB_R2_SNAPSHOT=true
CB_OCI_BACKUP=false
CB_FILE_ATTACHMENTS=false
CB_STORE_FULL_CONTENT=false
CB_AUTONOMOUS_MUTATION=false
CB_JOB_SCHEDULER=true
CB_JOB_CONCURRENCY=1
CB_RUNTIME_LEASE_MS=30000
CB_CONTROL_LEASE_MS=10000
CB_POLL_STALE_MS=90000
CB_QUEUE_STUCK_MS=300000
CB_QUEUE_LIMIT=100
CB_MAX_INPUT_BYTES=32768
CB_DATA_REPO_SLUG=LinzeColin/Private-Database
CB_DATA_AREA=Private-MetaDatabase
CB_DATA_DOMAIN=CyberBoss
CB_PRIVATE_DB_CLIENT=$APP_ROOT/shared/private_db_client.py
CB_PRIVATE_DB_SAFE_WRAPPER=$APP_ROOT/shared/private_db_client_safe.py
CB_PRIVATE_DB_AUTH_MODE=gh-login
CB_PRIVATE_DB_GH_COMMAND=$TOOLCHAIN_BIN/gh
CB_PRIVATE_DB_GH_CONFIG_DIR=/var/lib/cyberboss-data/.config/gh
CB_CODE_EXECUTION_IDENTITY=cyberboss
CB_DATA_EXECUTION_IDENTITY=cyberboss-data
CB_IDENTITY_SCOPE_POLICY=$CONFIG_ROOT/identity-scope.policy.json
CB_APP_REPO_SLUG=LinzeColin/MetaDatabase
CB_APP_SUBPATH=CyberBoss
CB_APP_ROOT=$APP_ROOT
CB_INCOMING_ROOT=$STATE_ROOT/incoming
CB_APP_USER=cyberboss
CB_APP_GROUP=cyberboss
CB_R2_BUCKET=cyberboss-cold
CB_R2_PREFIX=ovh-singapore-vps-1/
CB_OCI_BUCKET_FILE=$CONFIG_ROOT/credentials/oci-bucket-name
CB_OCI_PREFIX=cyberboss-cold-backup/ovh-singapore-vps-1/
CB_PROVIDER_ACTIVATION_CONFIG=$CONFIG_ROOT/provider-activation.json
ENV
if [[ "$TASK_ID" == "CB-140" ]]; then
  printf 'CYBERBOSS_WALKING_SKELETON_TRACE_FILE=%s/evidence/walking-skeleton.ndjson\n' \
    "$STAGING_STATE" >>"$ENV_STAGE"
fi
chmod 0600 "$ENV_STAGE"

if [[ ! -e "$STAGING_ENV" && ! -L "$STAGING_ENV" ]]; then
  [[ "$MODE" == "apply" ]] || fail "staging_env_missing"
  install -o root -g "$CODE_GROUP" -m 0640 "$ENV_STAGE" "$STAGING_ENV"
elif [[ ! -f "$STAGING_ENV" || -L "$STAGING_ENV" ]]; then
  fail "staging_env_collision"
else
  cmp -s "$ENV_STAGE" "$STAGING_ENV" || fail "staging_env_drift"
fi
[[ "$(stat -c '%U:%G:%a' "$STAGING_ENV")" == \
  "root:$CODE_GROUP:640" ]] ||
  fail "staging_env_owner_mode"
if [[ "$MODE" == "apply" ]]; then
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 \
    "$STAGING_STATE" "$STAGING_STATE/logs" "$STAGING_STATE/status" \
    "$STAGING_STATE/tmp" "$STAGING_STATE/evidence"
fi
[[ "$(stat -c '%U:%G:%a' "$STAGING_STATE")" == \
  "$CODE_USER:$CODE_GROUP:700" ]] ||
  fail "staging_state_owner_mode"
"$TOOLCHAIN_BIN/node" "$RELEASE_PATH/implementation-kit/tests/validate_config.js" \
  "$STAGING_ENV" "$CONFIG_ROOT/workspaces.json" >/dev/null ||
  fail "staging_config_validation"

if [[ "$TASK_ID" == "CB-240" ]]; then
  command -v systemd-analyze >/dev/null 2>&1 ||
    fail "required_command_missing:systemd-analyze"
  getent passwd "$DATA_USER" >/dev/null || fail "data_user_missing"
  getent group "$DATA_GROUP" >/dev/null || fail "data_group_missing"
  CANONICAL_UNIT_SOURCE="$KIT_ROOT/systemd/cyberboss-canonical-sync.service"
  CANONICAL_TIMER_SOURCE="$KIT_ROOT/systemd/cyberboss-canonical-sync.timer"
  CANONICAL_MATERIAL_UNIT_SOURCE="$KIT_ROOT/systemd/cyberboss-canonical-sync-material.service"
  CANONICAL_MATERIAL_PATH_SOURCE="$KIT_ROOT/systemd/cyberboss-canonical-sync-material.path"
  CANONICAL_UNIT_TARGET="/etc/systemd/system/cyberboss-canonical-sync.service"
  CANONICAL_TIMER_TARGET="/etc/systemd/system/cyberboss-canonical-sync.timer"
  CANONICAL_MATERIAL_UNIT_TARGET="/etc/systemd/system/cyberboss-canonical-sync-material.service"
  CANONICAL_MATERIAL_PATH_TARGET="/etc/systemd/system/cyberboss-canonical-sync-material.path"
  SAFE_WRAPPER_TARGET="$APP_ROOT/shared/private_db_client_safe.py"
  if [[ "$MODE" == "apply" ]]; then
    install -o root -g root -m 0644 \
      "$CANONICAL_UNIT_SOURCE" "$CANONICAL_UNIT_TARGET"
    install -o root -g root -m 0644 \
      "$CANONICAL_TIMER_SOURCE" "$CANONICAL_TIMER_TARGET"
    install -o root -g root -m 0644 \
      "$CANONICAL_MATERIAL_UNIT_SOURCE" "$CANONICAL_MATERIAL_UNIT_TARGET"
    install -o root -g root -m 0644 \
      "$CANONICAL_MATERIAL_PATH_SOURCE" "$CANONICAL_MATERIAL_PATH_TARGET"
    install -o root -g "$DATA_GROUP" -m 0550 \
      "$KIT_ROOT/scripts/private_db_client_safe.py" "$SAFE_WRAPPER_TARGET"
    install -d -o root -g "$CODE_GROUP" -m 0750 \
      "$STATE_ROOT/canonical-spool"
    install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 \
      "$STATE_ROOT/canonical-spool/outgoing"
    install -d -o "$DATA_USER" -g "$CODE_GROUP" -m 0750 \
      "$STATE_ROOT/canonical-spool/receipts"
    install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 \
      "$STATE_ROOT/canonical-spool/quarantine"
    install -d -o "$DATA_USER" -g "$DATA_GROUP" -m 0700 \
      /var/lib/cyberboss-data/canonical-sync \
      /var/lib/cyberboss-data/canonical-sync/locks
    systemctl daemon-reload
  fi
  cmp -s "$CANONICAL_UNIT_SOURCE" "$CANONICAL_UNIT_TARGET" ||
    fail "canonical_unit_drift"
  cmp -s "$CANONICAL_TIMER_SOURCE" "$CANONICAL_TIMER_TARGET" ||
    fail "canonical_timer_drift"
  cmp -s "$CANONICAL_MATERIAL_UNIT_SOURCE" "$CANONICAL_MATERIAL_UNIT_TARGET" ||
    fail "canonical_material_unit_drift"
  cmp -s "$CANONICAL_MATERIAL_PATH_SOURCE" "$CANONICAL_MATERIAL_PATH_TARGET" ||
    fail "canonical_material_path_drift"
  cmp -s "$KIT_ROOT/scripts/private_db_client_safe.py" \
    "$SAFE_WRAPPER_TARGET" || fail "safe_wrapper_drift"
  [[ "$(stat -c '%U:%G:%a' "$SAFE_WRAPPER_TARGET")" == \
    "root:$DATA_GROUP:550" ]] || fail "safe_wrapper_owner_mode"
  [[ "$(stat -c '%U:%G:%a' "$STATE_ROOT/canonical-spool")" == \
    "root:$CODE_GROUP:750" ]] || fail "canonical_spool_owner_mode"
  [[ "$(stat -c '%U:%G:%a' "$STATE_ROOT/canonical-spool/outgoing")" == \
    "$CODE_USER:$CODE_GROUP:750" ]] ||
    fail "canonical_outgoing_owner_mode"
  [[ "$(stat -c '%U:%G:%a' "$STATE_ROOT/canonical-spool/receipts")" == \
    "$DATA_USER:$CODE_GROUP:750" ]] ||
    fail "canonical_receipts_owner_mode"
  [[ "$(stat -c '%U:%G:%a' "$STATE_ROOT/canonical-spool/quarantine")" == \
    "$CODE_USER:$CODE_GROUP:700" ]] ||
    fail "canonical_quarantine_owner_mode"
  [[ "$(stat -c '%U:%G:%a' /var/lib/cyberboss-data/canonical-sync)" == \
    "$DATA_USER:$DATA_GROUP:700" ]] ||
    fail "canonical_data_state_owner_mode"
  systemd-analyze verify "$CANONICAL_UNIT_TARGET" "$CANONICAL_TIMER_TARGET" \
    "$CANONICAL_MATERIAL_UNIT_TARGET" "$CANONICAL_MATERIAL_PATH_TARGET" \
    >/dev/null || fail "canonical_systemd_verify"
  systemctl is-active --quiet cyberboss-canonical-sync.service &&
    fail "canonical_service_active"
  systemctl is-enabled --quiet cyberboss-canonical-sync.service 2>/dev/null &&
    fail "canonical_service_enabled"
  systemctl is-active --quiet cyberboss-canonical-sync.timer &&
    fail "canonical_timer_active"
  systemctl is-enabled --quiet cyberboss-canonical-sync.timer 2>/dev/null &&
    fail "canonical_timer_enabled"
  systemctl is-active --quiet cyberboss-canonical-sync-material.service &&
    fail "canonical_material_service_active"
  systemctl is-enabled --quiet cyberboss-canonical-sync-material.service 2>/dev/null &&
    fail "canonical_material_service_enabled"
  systemctl is-active --quiet cyberboss-canonical-sync-material.path &&
    fail "canonical_material_path_active"
  systemctl is-enabled --quiet cyberboss-canonical-sync-material.path 2>/dev/null &&
    fail "canonical_material_path_enabled"
fi

[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_changed"
[[ "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_changed"
systemctl is-active --quiet "$UNIT" && fail "service_active_after"
systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
  fail "service_enabled_after"
if [[ "$TASK_ID" == "CB-240" ]]; then
  systemctl is-active --quiet cyberboss-canonical-sync.service &&
    fail "canonical_service_active_after"
  systemctl is-enabled --quiet cyberboss-canonical-sync.service 2>/dev/null &&
    fail "canonical_service_enabled_after"
  systemctl is-active --quiet cyberboss-canonical-sync.timer &&
    fail "canonical_timer_active_after"
  systemctl is-enabled --quiet cyberboss-canonical-sync.timer 2>/dev/null &&
    fail "canonical_timer_enabled_after"
  systemctl is-active --quiet cyberboss-canonical-sync-material.service &&
    fail "canonical_material_service_active_after"
  systemctl is-enabled --quiet cyberboss-canonical-sync-material.service 2>/dev/null &&
    fail "canonical_material_service_enabled_after"
  systemctl is-active --quiet cyberboss-canonical-sync-material.path &&
    fail "canonical_material_path_active_after"
  systemctl is-enabled --quiet cyberboss-canonical-sync-material.path 2>/dev/null &&
    fail "canonical_material_path_enabled_after"
fi
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 )')" ]] ||
  fail "listener_created"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "process_created"

printf '%s=PASS task_id=%s mode=%s release_id=%s release_action=%s app_tests=%s current_changed=false service_active=false service_enabled=false runtime_started=false real_adapter_activation=activation_pending\n' \
  "$REPORT_PREFIX" "$TASK_ID" "$MODE" "$RELEASE_ID" "$RELEASE_ACTION" "$TEST_COUNT"
