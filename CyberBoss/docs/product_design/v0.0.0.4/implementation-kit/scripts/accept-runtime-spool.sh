#!/usr/bin/env bash
set -Eeuo pipefail

MODE=""
RELEASE_ID=""
OUTPUT_DIR=""

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
TOOLCHAIN_BIN="$APP_ROOT/shared/toolchains/bin"
STATE_ROOT="/var/lib/cyberboss"
STAGING_STATE="$STATE_ROOT/cb200-staging"
RUNTIME_ROOT="/run/cyberboss-cb200"
DATABASE_PATH=""
KEY_FILE=""
WORKSPACE="/srv/cyberboss-workspaces/cyberboss"
EXPECTED_CURRENT="b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE="10d988e908d72ea1a43bbed04a2130a338663363"
EXPECTED_TARGET_HASH="7865f743d174"
UNIT="cyberboss-cloud.service"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"

fail() {
  printf 'RUNTIME_SPOOL_ACCEPTANCE=FAIL reason=%s\n' "$1"
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
  printf 'RUNTIME_SPOOL_ACCEPTANCE_CHECK=PASS release_id=%s persistent_writes=false live_commands=false service_started=false real_credential_reads=false provider_writes=false private_database_operations=false pg_2_executed=false\n' \
    "$RELEASE_ID"
  exit 0
fi

[[ "$EUID" -eq 0 ]] || fail "root_required"
[[ "$OUTPUT_DIR" == "$STAGING_STATE/evidence/acceptance-$RELEASE_ID" ]] ||
  fail "output_dir_scope"
for command_name in basename chmod chown find git grep install jq openssl \
  pgrep readlink realpath sort ss stat sudo systemctl unlink; do
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
  -f "$RELEASE_PATH/schema-manifest.json" ]] ||
  fail "candidate_manifest_missing"
jq -e --arg release "$RELEASE_ID" '
  .task_id == "CB-200" and
  .phase == "P2.1" and
  .release_commit == $release and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false and
  .runtime_spool.schema_version == 2 and
  .runtime_spool.migration_mode == "additive_backward_compatible" and
  .runtime_spool.active_payload_encryption == "AES-256-GCM" and
  .runtime_spool.real_canonical_sync == false and
  .runtime_spool.channel_poll_integrated == false and
  .runtime_spool.scheduler_integrated == false and
  .runtime_spool.outbox_worker_integrated == false and
  .runtime_spool.pg_2_executed == false
' "$RELEASE_PATH/release-manifest.json" >/dev/null ||
  fail "candidate_manifest_contract"
[[ -L "$RELEASE_PATH/migrations" &&
  "$(realpath "$RELEASE_PATH/migrations")" == "$RELEASE_PATH/app/migrations" ]] ||
  fail "candidate_migrations_contract"
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
install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0700 "$RUNTIME_ROOT"
KEY_FILE="$RUNTIME_ROOT/synthetic-aes256.key"
DATABASE_PATH="$STAGING_STATE/tmp/runtime-acceptance-$RELEASE_ID.db"
[[ ! -e "$DATABASE_PATH" && ! -L "$DATABASE_PATH" ]] ||
  fail "acceptance_database_exists"
openssl rand -out "$KEY_FILE" 32
chown "$CODE_USER:$CODE_GROUP" "$KEY_FILE"
chmod 0400 "$KEY_FILE"

cleanup() {
  local exit_code=$?
  for suffix in "" "-wal" "-shm"; do
    local candidate="${DATABASE_PATH:-}$suffix"
    if [[ -n "${DATABASE_PATH:-}" && -f "$candidate" && ! -L "$candidate" ]]; then
      unlink "$candidate"
    elif [[ -n "${DATABASE_PATH:-}" &&
      ( -e "$candidate" || -L "$candidate" ) ]]; then
      exit 70
    fi
  done
  if [[ -d "$RUNTIME_ROOT" && ! -L "$RUNTIME_ROOT" ]]; then
    find "$RUNTIME_ROOT" -xdev -depth -delete
  elif [[ -e "$RUNTIME_ROOT" || -L "$RUNTIME_ROOT" ]]; then
    exit 70
  fi
  return "$exit_code"
}
trap cleanup EXIT

sudo -u "$CODE_USER" -H env \
  HOME="$STAGING_STATE" \
  PATH="$TOOLCHAIN_BIN:/usr/bin:/bin" \
  "$TOOLCHAIN_BIN/node" \
  "$RELEASE_PATH/app/scripts/runtime-spool-acceptance.js" \
  --database "$DATABASE_PATH" \
  --key-file "$KEY_FILE" \
  --output-directory "$OUTPUT_DIR" \
  --release-commit "$RELEASE_ID" \
  --target-id-sha256 "$EXPECTED_TARGET_HASH"

[[ "$(find "$OUTPUT_DIR" -maxdepth 1 -type f -printf '%f\n' | sort)" == \
  $'acceptance-report.json\nschema-dump.redacted.sql' ]] ||
  fail "acceptance_output_inventory"
REPORT="$OUTPUT_DIR/acceptance-report.json"
jq -e --arg release "$RELEASE_ID" --arg target "$EXPECTED_TARGET_HASH" '
  .task_id == "CB-200" and
  .phase == "P2.1" and
  .release_commit == $release and
  .target_id_sha256 == $target and
  .generated_from_synthetic_state == true and
  .migration.clean_migration == "passed" and
  .migration.existing_v1_migration == "passed" and
  .migration.legacy_v1_reader_after_v2 == "passed" and
  .migration.schema_version == 2 and
  .migration.journal_mode == "wal" and
  .migration.synchronous == "full" and
  .migration.foreign_keys == true and
  .migration.busy_timeout_ms == 5000 and
  .migration.integrity_check == "ok" and
  .migration.destructive_statements == 0 and
  .property.stable_id_fixture_count == 10000 and
  .property.stable_id_collisions == 0 and
  .property.stable_id_mismatches == 0 and
  .property.property_transition_attempts >= 10000 and
  .property.illegal_transition_successes == 0 and
  .property.raw_sql_illegal_transition_successes == 0 and
  .property.concurrent_inserters >= 32 and
  .property.duplicate_inbox_rows == 0 and
  .property.duplicate_job_rows == 0 and
  .property.canonical_reconcile_set_diff == 0 and
  .crash.cut_points == [
    "after_begin", "after_inbox_insert", "after_job_insert",
    "after_event_insert", "after_commit"
  ] and
  .crash.accepted_but_lost == 0 and
  .crash.uncommitted_fragments == 0 and
  .crash.duplicate_executable_jobs == 0 and
  .crash.integrity_failures == 0 and
  .security.active_payload_encryption == "AES-256-GCM" and
  .security.plaintext_db_wal_shm_hits == 0 and
  .security.encryption_key_hits == 0 and
  .result == "passed"
' "$REPORT" >/dev/null || fail "acceptance_report_contract"
grep -Fq "CREATE TABLE inbox_messages" \
  "$OUTPUT_DIR/schema-dump.redacted.sql" ||
  fail "schema_dump_inbox"
grep -Fq "CREATE TRIGGER jobs_status_transition_guard" \
  "$OUTPUT_DIR/schema-dump.redacted.sql" ||
  fail "schema_dump_transition_guard"
if grep -R -I -nE \
  'PRIVATE KEY|Authorization:[[:space:]]*Bearer|gh[pousr]_[A-Za-z0-9]{20,}|sk-(proj-)?[A-Za-z0-9_-]{20,}|wxid_' \
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

printf 'RUNTIME_SPOOL_ACCEPTANCE=PASS release_id=%s fixtures=10000 transitions=10000 concurrent_inserters=32 crash_cut_points=5 plaintext_hits=0 reconcile_set_diff=0 current_changed=false workspace_changed=false service_started=false real_credential_reads=0 provider_writes=0 private_database_operations=0 pg_2_executed=false\n' \
  "$RELEASE_ID"
