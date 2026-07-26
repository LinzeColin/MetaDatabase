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
  else true end)
' "$MANIFEST" >/dev/null || fail "artifact_manifest_contract"

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
  install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
    "$KIT_ROOT/config/cloud-process-health.json" \
    "$RELEASE_STAGE/health-contract.json"
  install -o "$CODE_USER" -g "$CODE_GROUP" -m 0440 \
    "$KIT_ROOT/config/cloud-process-tree.txt" \
    "$RELEASE_STAGE/process-tree.txt"
  jq -n \
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
    }' >"$RELEASE_STAGE/release-manifest.json"
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
  .real_adapter_activation == "activation_pending"
' "$RELEASE_PATH/release-manifest.json" >/dev/null ||
  fail "candidate_release_manifest"
[[ -f "$RELEASE_PATH/health-contract.json" &&
  -f "$RELEASE_PATH/process-tree.txt" &&
  -f "$RELEASE_PATH/app/scripts/cloud-supervisor.js" ]] ||
  fail "candidate_contract_files"
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
CB_PRODUCT_VERSION=0.0.0.4
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
CB_STATUS_PATH=$STAGING_STATE/status/snapshot.json
CB_SINGLETON_LOCK=$STATE_ROOT/locks/bridge.lock
CB_DURABLE_INBOX=true
CB_DURABLE_OUTBOX=true
CB_PRIVATE_DB_CANONICAL_SYNC=true
CB_TIMELINE_WEB=true
CB_STATUS_EXPORTER=true
CB_R2_SNAPSHOT=true
CB_OCI_BACKUP=false
CB_FILE_ATTACHMENTS=false
CB_STORE_FULL_CONTENT=false
CB_AUTONOMOUS_MUTATION=false
CB_JOB_CONCURRENCY=1
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

[[ "$(basename "$(readlink -f "$APP_ROOT/current")")" == "$EXPECTED_CURRENT" ]] ||
  fail "current_changed"
[[ "$(sudo -u "$CODE_USER" git -c safe.directory="$WORKSPACE" \
  -C "$WORKSPACE" rev-parse HEAD)" == "$EXPECTED_WORKSPACE" ]] ||
  fail "workspace_changed"
systemctl is-active --quiet "$UNIT" && fail "service_active_after"
systemctl is-enabled --quiet "$UNIT" 2>/dev/null &&
  fail "service_enabled_after"
[[ -z "$(ss -lntH '( sport = :8765 or sport = :8780 )')" ]] ||
  fail "listener_created"
[[ -z "$(pgrep -u "$CODE_USER" 2>/dev/null || true)" ]] ||
  fail "process_created"

printf '%s=PASS task_id=%s mode=%s release_id=%s release_action=%s app_tests=%s current_changed=false service_active=false service_enabled=false runtime_started=false real_adapter_activation=activation_pending\n' \
  "$REPORT_PREFIX" "$TASK_ID" "$MODE" "$RELEASE_ID" "$RELEASE_ACTION" "$TEST_COUNT"
