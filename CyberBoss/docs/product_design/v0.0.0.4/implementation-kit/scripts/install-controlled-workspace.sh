#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
KIT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
MODE=""
RELEASE_ID=""
ARTIFACTS=""

APP_ROOT="/opt/cyberboss-cloud"
SHARED_ROOT="$APP_ROOT/shared"
RELEASE_ROOT="$APP_ROOT/releases"
TOOLCHAIN_ROOT="$SHARED_ROOT/toolchains"
BIN_ROOT="$TOOLCHAIN_ROOT/bin"
WORKSPACE_BASE="/srv/cyberboss-workspaces"
WORKSPACE="$WORKSPACE_BASE/cyberboss"
STATE_ROOT="/var/lib/cyberboss"
DATA_STATE_ROOT="/var/lib/cyberboss-data"
CONFIG_ROOT="/etc/cyberboss"
CODE_USER="cyberboss"
CODE_GROUP="cyberboss"
DATA_USER="cyberboss-data"
DATA_GROUP="cyberboss-data"
BRANCH="codex/cyberboss-prestage0"
GH_VERSION="2.96.0"
GH_ROOT="$TOOLCHAIN_ROOT/gh/$GH_VERSION"
GH_LINK="$BIN_ROOT/gh"
CLIENT_PATH="$SHARED_ROOT/private_db_client.py"
WRAPPER_PATH="$SHARED_ROOT/private_db_client_safe.py"
SCOPE_MODULE_PATH="$SHARED_ROOT/scope_policy.py"
BUDGET_COMMAND="$SHARED_ROOT/workspace_budget.py"
MAINTENANCE_COMMAND="$SHARED_ROOT/workspace-maintenance.sh"

fail() {
  printf 'CONTROLLED_WORKSPACE=FAIL reason=%s\n' "$1"
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
    *)
      fail "unknown_arg:$1"
      ;;
  esac
done

[[ -n "$MODE" ]] || fail "mode_required"
[[ "$RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] ||
  fail "release_id_must_be_full_lowercase_git_sha"

for source_file in \
  "$KIT_ROOT/config/workspaces.json.example" \
  "$KIT_ROOT/config/workspace-budget.json" \
  "$KIT_ROOT/config/identity-scope.policy.json" \
  "$KIT_ROOT/config/no-clone-client-versions.json" \
  "$KIT_ROOT/config/cyberboss.env.example" \
  "$SCRIPT_DIR/private_db_client_safe.py" \
  "$SCRIPT_DIR/scope_policy.py" \
  "$SCRIPT_DIR/workspace_budget.py" \
  "$SCRIPT_DIR/workspace-maintenance.sh"; do
  [[ -f "$source_file" && ! -L "$source_file" ]] ||
    fail "source_missing_or_symlink:$(basename "$source_file")"
done

python3 - "$KIT_ROOT/config/workspaces.json.example" \
  "$KIT_ROOT/config/workspace-budget.json" \
  "$KIT_ROOT/config/identity-scope.policy.json" \
  "$KIT_ROOT/config/no-clone-client-versions.json" <<'PY' ||
import json
import sys
from pathlib import Path

workspaces, budget, scope, versions = [
    json.loads(Path(value).read_text(encoding="utf-8")) for value in sys.argv[1:]
]
workspace = (workspaces.get("workspaces") or {}).get("cyberboss") or {}
assert workspaces.get("default_alias") == "cyberboss"
assert workspaces.get("workspace_base") == "/srv/cyberboss-workspaces"
assert workspace.get("root") == "/srv/cyberboss-workspaces/cyberboss"
assert workspace.get("repo") == "LinzeColin/MetaDatabase"
assert workspace.get("sparse_paths") == ["CyberBoss", ".github"]
assert workspace.get("root_integration_write") is False
assert workspace.get("max_bytes") == 4294967296
assert budget.get("workspace_root") == workspace.get("root")
assert budget.get("workspace_max_bytes") == workspace.get("max_bytes")
assert budget.get("hard_stop_workspace_bytes") == 8589934592
assert "--prune=now" not in json.dumps(budget.get("cleanup_commands"))
assert budget.get("forbidden_cleanup_flags") == ["--prune=now"]
assert scope.get("code", {}).get("execution_identity") == "cyberboss"
assert scope.get("data", {}).get("execution_identity") == "cyberboss-data"
assert scope.get("data", {}).get("access_mode") == "no_clone_client"
assert scope.get("data", {}).get("forbidden_operations") == ["clone", "put", "delete"]
assert versions.get("task_id") == "CB-120"
assert versions.get("private_db_client", {}).get("sha256") == (
    "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa"
)
assert versions.get("github_cli", {}).get("version") == "2.96.0"
assert versions.get("github_cli", {}).get("archive_sha256") == (
    "83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60"
)
PY
  fail "static_policy_contract"

if [[ "$MODE" == "check" ]]; then
  printf 'CONTROLLED_WORKSPACE_CHECK=PASS release_id=%s persistent_writes=false live_commands=false private_database_clone=false\n' \
    "$RELEASE_ID"
  exit 0
fi

[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] ||
  fail "unsupported_target_platform"
[[ "$EUID" -eq 0 ]] || fail "root_required"
for command_name in chmod chown cmp cut find getent git grep groupadd id install \
  jq ln mktemp mv python3 readlink realpath sed sha256sum stat sudo systemctl \
  tar tr useradd usermod; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ -d /run/systemd/system ]] || fail "systemd_runtime_unavailable"
systemctl is-active --quiet cyberboss-cloud.service &&
  fail "service_must_be_inactive"
systemctl is-enabled --quiet cyberboss-cloud.service 2>/dev/null &&
  fail "service_must_be_disabled"

[[ -n "$ARTIFACTS" && "$ARTIFACTS" == /* ]] ||
  fail "artifacts_absolute_path_required"
[[ -d "$ARTIFACTS" && ! -L "$ARTIFACTS" ]] ||
  fail "artifacts_missing_or_symlink"
ARTIFACTS="$(realpath "$ARTIFACTS")"
[[ "$ARTIFACTS" == /var/lib/cyberboss/incoming/* ]] ||
  fail "artifacts_outside_incoming"

for artifact in SHA256SUMS artifact-manifest.json private_db_client.py \
  gh_2.96.0_linux_amd64.tar.gz; do
  [[ -f "$ARTIFACTS/$artifact" && ! -L "$ARTIFACTS/$artifact" ]] ||
    fail "artifact_missing_or_symlink:$artifact"
done
(
  cd "$ARTIFACTS"
  sha256sum -c SHA256SUMS >/dev/null
) || fail "artifact_checksum"

MANIFEST="$ARTIFACTS/artifact-manifest.json"
jq -e --arg release "$RELEASE_ID" --arg branch "$BRANCH" '
  .schema_version == 1 and
  .task_id == "CB-120" and
  .release_commit == $release and
  .branch == $branch and
  .repository == "LinzeColin/MetaDatabase" and
  .source.corresponding_source_complete == true and
  .source.license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .source.original_licenses_preserved == true and
  .source.upstream_clarification_received == false and
  .workspace_seed.filter == "blob:none" and
  .workspace_seed.sparse_paths == ["CyberBoss", ".github"] and
  .workspace_seed.root_integration_write == false and
  .private_db_client.access_mode == "no_clone_client" and
  .private_db_client.allowed_operations == ["ingest", "get", "list", "verify"] and
  .private_db_client.real_operation_activation == "activation_pending" and
  .github_cli.version == "2.96.0" and
  .deployment.switch_current == false and
  .deployment.enable_service == false and
  .deployment.start_business_runtime == false and
  .deployment.clone_private_database == false and
  .deployment.remote_publication == "none"
' "$MANIFEST" >/dev/null || fail "artifact_manifest_contract"

SOURCE_ARCHIVE="$(jq -er '.source.archive' "$MANIFEST")"
SEED_ARCHIVE="$(jq -er '.workspace_seed.archive' "$MANIFEST")"
[[ "$SOURCE_ARCHIVE" == "cyberboss-source-$RELEASE_ID.tar.gz" ]] ||
  fail "source_archive_name"
[[ "$SEED_ARCHIVE" == "metadatabase-seed-$RELEASE_ID.git.tar.gz" ]] ||
  fail "seed_archive_name"
for artifact in "$SOURCE_ARCHIVE" "$SEED_ARCHIVE"; do
  [[ -f "$ARTIFACTS/$artifact" && ! -L "$ARTIFACTS/$artifact" ]] ||
    fail "artifact_missing_or_symlink:$artifact"
done
[[ "$(sha256sum "$ARTIFACTS/private_db_client.py" | cut -d' ' -f1)" == \
  "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa" ]] ||
  fail "private_db_client_hash"
[[ "$(sha256sum "$ARTIFACTS/gh_2.96.0_linux_amd64.tar.gz" | cut -d' ' -f1)" == \
  "83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60" ]] ||
  fail "github_cli_hash"

archive_paths_safe() {
  local archive="$1"
  local required_root="$2"
  local entry
  while IFS= read -r entry; do
    [[ -n "$entry" ]] || continue
    [[ "$entry" != /* ]] || return 1
    case "/$entry/" in
      *"/../"*|*"/./"*) return 1 ;;
    esac
    [[ "$entry" == "$required_root" || "$entry" == "$required_root/"* ]] ||
      return 1
  done < <(tar -tzf "$archive")
}
archive_paths_safe "$ARTIFACTS/$SOURCE_ARCHIVE" "cyberboss-source" ||
  fail "source_archive_paths"
archive_paths_safe "$ARTIFACTS/$SEED_ARCHIVE" "metadatabase-seed.git" ||
  fail "seed_archive_paths"
archive_paths_safe "$ARTIFACTS/gh_2.96.0_linux_amd64.tar.gz" \
  "gh_2.96.0_linux_amd64" ||
  fail "github_cli_archive_paths"

CURRENT_BEFORE="absent"
if [[ -e "$APP_ROOT/current" || -L "$APP_ROOT/current" ]]; then
  [[ -L "$APP_ROOT/current" ]] || fail "current_not_symlink"
  CURRENT_BEFORE="$(readlink "$APP_ROOT/current")"
fi

TMP_ROOT="$(mktemp -d /tmp/cyberboss-cb120-install.XXXXXXXX)"
RELEASE_STAGE=""
WORKSPACE_STAGE=""
cleanup() {
  local exit_code=$?
  if [[ -n "${WORKSPACE_STAGE:-}" ]]; then
    case "$WORKSPACE_STAGE" in
      "$WORKSPACE_BASE"/.cb120-"$RELEASE_ID"-*)
        find "$WORKSPACE_STAGE" -xdev -depth -delete 2>/dev/null || true
        ;;
      *)
        printf 'CONTROLLED_WORKSPACE=FAIL reason=unsafe_workspace_cleanup_path\n' >&2
        exit 70
        ;;
    esac
  fi
  if [[ -n "${RELEASE_STAGE:-}" ]]; then
    case "$RELEASE_STAGE" in
      "$RELEASE_ROOT"/.cb120-"$RELEASE_ID"-*)
        find "$RELEASE_STAGE" -xdev -depth -delete 2>/dev/null || true
        ;;
      *)
        printf 'CONTROLLED_WORKSPACE=FAIL reason=unsafe_release_cleanup_path\n' >&2
        exit 70
        ;;
    esac
  fi
  case "${TMP_ROOT:-}" in
    /tmp/cyberboss-cb120-install.*)
      find "$TMP_ROOT" -xdev -depth -delete 2>/dev/null || true
      ;;
    *)
      printf 'CONTROLLED_WORKSPACE=FAIL reason=unsafe_cleanup_path\n' >&2
      exit 70
      ;;
  esac
  return "$exit_code"
}
trap cleanup EXIT

ensure_group() {
  local group_name="$1"
  if getent group "$group_name" >/dev/null 2>&1; then
    [[ "$(getent group "$group_name" | cut -d: -f3)" != 0 ]] ||
      fail "group_is_root:$group_name"
  elif [[ "$MODE" == "apply" ]]; then
    groupadd --system "$group_name"
  else
    fail "group_missing:$group_name"
  fi
}

ensure_user() {
  local user_name="$1"
  local group_name="$2"
  local home_path="$3"
  if getent passwd "$user_name" >/dev/null 2>&1; then
    local user_uid user_gid user_home user_shell
    IFS=: read -r _ _ user_uid user_gid _ user_home user_shell < <(
      getent passwd "$user_name"
    )
    [[ "$user_uid" != 0 ]] || fail "user_is_root:$user_name"
    [[ "$user_gid" == "$(getent group "$group_name" | cut -d: -f3)" ]] ||
      fail "user_group:$user_name"
    [[ "$user_home" == "$home_path" ]] || fail "user_home:$user_name"
    [[ "$user_shell" == /usr/sbin/nologin || "$user_shell" == /sbin/nologin ]] ||
      fail "user_shell:$user_name"
  elif [[ "$MODE" == "apply" ]]; then
    useradd --system --gid "$group_name" --home-dir "$home_path" \
      --shell /usr/sbin/nologin "$user_name"
  else
    fail "user_missing:$user_name"
  fi
}

install_exact() {
  local source="$1"
  local destination="$2"
  local owner="$3"
  local group="$4"
  local mode="$5"
  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] ||
      fail "destination_collision:$destination"
    cmp -s "$source" "$destination" ||
      fail "destination_drift:$destination"
  elif [[ "$MODE" == "apply" ]]; then
    install -o "$owner" -g "$group" -m "$mode" "$source" "$destination"
  else
    fail "destination_missing:$destination"
  fi
  [[ "$(stat -c '%U:%G:%a' "$destination")" == \
    "$owner:$group:${mode#0}" ]] ||
    fail "destination_owner_mode:$destination"
}

install_config() {
  local source="$1"
  local destination="$2"
  local backup_root="$STATE_ROOT/install-backups/cb120-$RELEASE_ID"
  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] ||
      fail "config_collision:$destination"
    if ! cmp -s "$source" "$destination"; then
      [[ "$MODE" == "apply" ]] || fail "config_drift:$destination"
      install -d -o root -g root -m 0700 "$backup_root"
      local backup="$backup_root/$(basename "$destination").pre-cb120"
      if [[ ! -e "$backup" && ! -L "$backup" ]]; then
        install -o root -g root -m 0600 "$destination" "$backup"
      elif [[ ! -f "$backup" || -L "$backup" ]]; then
        fail "config_backup_collision:$backup"
      fi
      install -o root -g "$CODE_GROUP" -m 0640 "$source" \
        "$destination.cb120"
      mv -T "$destination.cb120" "$destination"
    fi
  elif [[ "$MODE" == "apply" ]]; then
    install -o root -g "$CODE_GROUP" -m 0640 "$source" "$destination"
  else
    fail "config_missing:$destination"
  fi
  [[ "$(stat -c '%U:%G:%a' "$destination")" == \
    "root:$CODE_GROUP:640" ]] ||
    fail "config_owner_mode:$destination"
}

if [[ "$MODE" == "apply" ]]; then
  ensure_group "$DATA_GROUP"
  ensure_user "$DATA_USER" "$DATA_GROUP" "$DATA_STATE_ROOT"
  usermod -a -G "$CODE_GROUP" "$DATA_USER"
else
  ensure_group "$DATA_GROUP"
  ensure_user "$DATA_USER" "$DATA_GROUP" "$DATA_STATE_ROOT"
fi
id "$CODE_USER" >/dev/null 2>&1 || fail "code_user_missing"
id -nG "$DATA_USER" | tr ' ' '\n' | grep -Fxq "$CODE_GROUP" ||
  fail "data_user_shared_traverse_group"
if id -nG "$CODE_USER" | tr ' ' '\n' | grep -Fxq "$DATA_GROUP"; then
  fail "code_user_in_data_group"
fi

if [[ "$MODE" == "apply" ]]; then
  install -d -o root -g "$CODE_GROUP" -m 0750 "$WORKSPACE_BASE"
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 \
    "$STATE_ROOT/cache" "$STATE_ROOT/cache/npm"
  install -d -o "$DATA_USER" -g "$DATA_GROUP" -m 0700 \
    "$DATA_STATE_ROOT" "$DATA_STATE_ROOT/.config" \
    "$DATA_STATE_ROOT/.config/gh"
  install -d -o root -g "$CODE_GROUP" -m 0750 \
    "$CONFIG_ROOT" "$SHARED_ROOT"
  install -d -o root -g root -m 0755 \
    "$TOOLCHAIN_ROOT" "$TOOLCHAIN_ROOT/gh" "$BIN_ROOT"
fi

[[ "$(stat -c '%U:%G:%a' "$WORKSPACE_BASE")" == "root:$CODE_GROUP:750" ]] ||
  fail "workspace_base_owner_mode"
[[ "$(stat -c '%U:%G:%a' "$DATA_STATE_ROOT/.config/gh")" == \
  "$DATA_USER:$DATA_GROUP:700" ]] ||
  fail "data_credential_dir_owner_mode"
[[ ! -e "$DATA_STATE_ROOT/.config/gh/hosts.yml" &&
  ! -L "$DATA_STATE_ROOT/.config/gh/hosts.yml" ]] ||
  fail "data_credential_must_remain_activation_pending"

install_config "$KIT_ROOT/config/workspaces.json.example" \
  "$CONFIG_ROOT/workspaces.json"
install_config "$KIT_ROOT/config/workspace-budget.json" \
  "$CONFIG_ROOT/workspace-budget.json"
install_config "$KIT_ROOT/config/identity-scope.policy.json" \
  "$CONFIG_ROOT/identity-scope.policy.json"
install_config "$KIT_ROOT/config/no-clone-client-versions.json" \
  "$CONFIG_ROOT/no-clone-client-versions.json"
install_exact "$KIT_ROOT/config/cyberboss.env.example" \
  "$CONFIG_ROOT/cyberboss.env.cb120.example" root "$CODE_GROUP" 0640
install_exact "$ARTIFACTS/private_db_client.py" \
  "$CLIENT_PATH" root "$DATA_GROUP" 0440
install_exact "$SCRIPT_DIR/private_db_client_safe.py" \
  "$WRAPPER_PATH" root "$DATA_GROUP" 0550
install_exact "$SCRIPT_DIR/scope_policy.py" \
  "$SCOPE_MODULE_PATH" root "$DATA_GROUP" 0440
install_exact "$SCRIPT_DIR/workspace_budget.py" \
  "$BUDGET_COMMAND" root "$CODE_GROUP" 0550
install_exact "$SCRIPT_DIR/workspace-maintenance.sh" \
  "$MAINTENANCE_COMMAND" root "$CODE_GROUP" 0550

harden_tree() {
  local root="$1"
  local owner="$2"
  local group="$3"
  chown -hR "$owner:$group" "$root"
  find "$root" -type d -exec chmod 0550 {} +
  find "$root" -type f -perm /111 -exec chmod 0550 {} +
  find "$root" -type f ! -perm /111 -exec chmod 0440 {} +
}

harden_public_tree() {
  local root="$1"
  chown -hR root:root "$root"
  find "$root" -type d -exec chmod 0555 {} +
  find "$root" -type f -perm /111 -exec chmod 0555 {} +
  find "$root" -type f ! -perm /111 -exec chmod 0444 {} +
}

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

if [[ ! -e "$GH_ROOT" && ! -L "$GH_ROOT" ]]; then
  [[ "$MODE" == "apply" ]] || fail "github_cli_missing"
  GH_STAGE="$TMP_ROOT/gh"
  install -d -m 0700 "$GH_STAGE"
  tar -xzf "$ARTIFACTS/gh_2.96.0_linux_amd64.tar.gz" \
    --strip-components=1 -C "$GH_STAGE"
  assert_no_escaping_symlink "$GH_STAGE"
  "$GH_STAGE/bin/gh" version | grep -Fq "gh version $GH_VERSION " ||
    fail "github_cli_version_staged"
  harden_public_tree "$GH_STAGE"
  mv -T "$GH_STAGE" "$GH_ROOT"
elif [[ ! -d "$GH_ROOT" || -L "$GH_ROOT" ]]; then
  fail "github_cli_destination_collision"
fi
"$GH_ROOT/bin/gh" version | sed -n '1p' |
  grep -Eq "^gh version $GH_VERSION \\([0-9]{4}-[0-9]{2}-[0-9]{2}\\)$" ||
  fail "github_cli_version"
[[ -z "$(find "$GH_ROOT" \( -type f -o -type d \) \
  \( ! -user root -o ! -group root -o -perm /022 \) -print -quit)" ]] ||
  fail "github_cli_mutable"
if [[ -e "$GH_LINK" || -L "$GH_LINK" ]]; then
  [[ -L "$GH_LINK" && "$(readlink "$GH_LINK")" == "$GH_ROOT/bin/gh" ]] ||
    fail "github_cli_link_collision"
elif [[ "$MODE" == "apply" ]]; then
  ln -s "$GH_ROOT/bin/gh" "$GH_LINK.cb120"
  mv -T "$GH_LINK.cb120" "$GH_LINK"
else
  fail "github_cli_link_missing"
fi
sudo -u "$DATA_USER" "$GH_LINK" version | sed -n '1p' |
  grep -Eq "^gh version $GH_VERSION " ||
  fail "data_identity_github_cli_unavailable"

SEED_ROOT="$SHARED_ROOT/repository-seeds"
SEED_PATH="$SEED_ROOT/metadatabase-$RELEASE_ID.git"
if [[ "$MODE" == "apply" ]]; then
  install -d -o root -g "$CODE_GROUP" -m 0750 "$SEED_ROOT"
fi
if [[ ! -e "$SEED_PATH" && ! -L "$SEED_PATH" ]]; then
  [[ "$MODE" == "apply" ]] || fail "seed_missing"
  SEED_STAGE="$TMP_ROOT/metadatabase-seed.git"
  tar -xzf "$ARTIFACTS/$SEED_ARCHIVE" -C "$TMP_ROOT"
  [[ -d "$SEED_STAGE" && ! -L "$SEED_STAGE" ]] ||
    fail "seed_archive_root"
  GIT_NO_LAZY_FETCH=1 git -C "$SEED_STAGE" rev-parse \
    "refs/heads/$BRANCH" | grep -Fxq "$RELEASE_ID" ||
    fail "seed_commit"
  [[ "$(git -C "$SEED_STAGE" config --get remote.origin.url)" == \
    "artifact://LinzeColin/MetaDatabase/$RELEASE_ID" ]] ||
    fail "seed_origin"
  [[ "$(git -C "$SEED_STAGE" config --get remote.origin.partialclonefilter)" == \
    "blob:none" ]] ||
    fail "seed_filter"
  grep -Fq 'uploadpack' "$SEED_STAGE/config" || fail "seed_uploadpack"
  harden_tree "$SEED_STAGE" root "$CODE_GROUP"
  mv -T "$SEED_STAGE" "$SEED_PATH"
elif [[ ! -d "$SEED_PATH" || -L "$SEED_PATH" ]]; then
  fail "seed_destination_collision"
fi
GIT_NO_LAZY_FETCH=1 git -C "$SEED_PATH" rev-parse \
  "refs/heads/$BRANCH" | grep -Fxq "$RELEASE_ID" ||
  fail "seed_commit_installed"
[[ "$(git -C "$SEED_PATH" config --get remote.origin.url)" == \
  "artifact://LinzeColin/MetaDatabase/$RELEASE_ID" ]] ||
  fail "seed_origin_installed"
[[ "$(git -C "$SEED_PATH" config --get remote.origin.partialclonefilter)" == \
  "blob:none" ]] ||
  fail "seed_filter_installed"
[[ -z "$(find "$SEED_PATH" \( -type f -o -type d \) \
  \( ! -user root -o ! -group "$CODE_GROUP" -o -perm /022 \) \
  -print -quit)" ]] ||
  fail "seed_mutable"

run_as_code() {
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" \
    PATH="$BIN_ROOT:/usr/bin:/bin" \
    GIT_OPTIONAL_LOCKS=0 \
    "$@"
}

if [[ ! -e "$WORKSPACE" && ! -L "$WORKSPACE" ]]; then
  [[ "$MODE" == "apply" ]] || fail "workspace_missing"
  WORKSPACE_STAGE="$WORKSPACE_BASE/.cb120-$RELEASE_ID-$$"
  [[ ! -e "$WORKSPACE_STAGE" && ! -L "$WORKSPACE_STAGE" ]] ||
    fail "workspace_stage_collision"
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 "$WORKSPACE_STAGE"
  run_as_code git -c protocol.file.allow=always clone \
    --filter=blob:none --no-checkout --single-branch --branch "$BRANCH" \
    "file://$SEED_PATH" "$WORKSPACE_STAGE"
  run_as_code git -C "$WORKSPACE_STAGE" sparse-checkout init --cone
  run_as_code git -C "$WORKSPACE_STAGE" sparse-checkout set CyberBoss .github
  run_as_code git -C "$WORKSPACE_STAGE" checkout "$BRANCH"
  run_as_code git -C "$WORKSPACE_STAGE" config fetch.prune true
  run_as_code git -C "$WORKSPACE_STAGE" config gc.auto 0
  chown root:"$CODE_GROUP" "$WORKSPACE_STAGE"
  chmod 0750 "$WORKSPACE_STAGE"
  chown -R "$CODE_USER:$CODE_GROUP" \
    "$WORKSPACE_STAGE/.git" "$WORKSPACE_STAGE/CyberBoss"
  find "$WORKSPACE_STAGE/.git" "$WORKSPACE_STAGE/CyberBoss" \
    -perm /022 -exec chmod go-w {} +
  while IFS= read -r -d '' root_entry; do
    [[ "$root_entry" == "$WORKSPACE_STAGE/.git" ||
      "$root_entry" == "$WORKSPACE_STAGE/CyberBoss" ]] && continue
    chown -R root:"$CODE_GROUP" "$root_entry"
    if [[ -d "$root_entry" ]]; then
      find "$root_entry" -type d -exec chmod 0550 {} +
      find "$root_entry" -type f -exec chmod 0440 {} +
    else
      chmod 0440 "$root_entry"
    fi
  done < <(find "$WORKSPACE_STAGE" -mindepth 1 -maxdepth 1 -print0)
  mv -T "$WORKSPACE_STAGE" "$WORKSPACE"
  WORKSPACE_STAGE=""
elif [[ ! -d "$WORKSPACE" || -L "$WORKSPACE" ]]; then
  fail "workspace_destination_collision"
fi

[[ "$(realpath "$WORKSPACE")" == "$WORKSPACE" ]] ||
  fail "workspace_realpath"
[[ "$(stat -c '%U:%G:%a' "$WORKSPACE")" == "root:$CODE_GROUP:750" ]] ||
  fail "workspace_owner_mode"
[[ -d "$WORKSPACE/.github" && ! -L "$WORKSPACE/.github" ]] ||
  fail "root_integration_missing_or_symlink"
[[ "$(stat -c '%U:%G:%a' "$WORKSPACE/.github")" == \
  "root:$CODE_GROUP:550" ]] ||
  fail "root_integration_owner_mode"
[[ "$(run_as_code git -C "$WORKSPACE" rev-parse HEAD)" == "$RELEASE_ID" ]] ||
  fail "workspace_commit"
[[ "$(run_as_code git -C "$WORKSPACE" branch --show-current)" == "$BRANCH" ]] ||
  fail "workspace_branch"
[[ "$(run_as_code git -C "$WORKSPACE" remote get-url origin)" == \
  "file://$SEED_PATH" ]] ||
  fail "workspace_origin"
[[ "$(run_as_code git -C "$WORKSPACE" config --get remote.origin.promisor)" == \
  "true" ]] ||
  fail "workspace_promisor"
[[ "$(run_as_code git -C "$WORKSPACE" config --get \
  remote.origin.partialclonefilter)" == "blob:none" ]] ||
  fail "workspace_filter"
mapfile -t SPARSE_PATHS < <(run_as_code git -C "$WORKSPACE" sparse-checkout list)
[[ "${#SPARSE_PATHS[@]}" -eq 2 ]] || fail "workspace_sparse_count"
printf '%s\n' "${SPARSE_PATHS[@]}" | grep -Fxq ".github" ||
  fail "workspace_sparse_github"
printf '%s\n' "${SPARSE_PATHS[@]}" | grep -Fxq "CyberBoss" ||
  fail "workspace_sparse_cyberboss"
[[ -z "$(run_as_code git -C "$WORKSPACE" status --porcelain=v1)" ]] ||
  fail "workspace_dirty"
run_as_code test -w "$WORKSPACE/CyberBoss" ||
  fail "code_workspace_not_writable"
if run_as_code test -w "$WORKSPACE/.github"; then
  fail "root_integration_writable"
fi
if sudo -u "$DATA_USER" test -w "$WORKSPACE/CyberBoss"; then
  fail "data_identity_code_writable"
fi
if sudo -u "$CODE_USER" test -r "$CLIENT_PATH" ||
  sudo -u "$CODE_USER" test -x "$WRAPPER_PATH"; then
  fail "code_identity_data_client_access"
fi
sudo -u "$DATA_USER" test -r "$CLIENT_PATH" &&
  sudo -u "$DATA_USER" test -x "$WRAPPER_PATH" ||
  fail "data_identity_client_access"

RELEASE_PATH="$RELEASE_ROOT/$RELEASE_ID"
if [[ ! -e "$RELEASE_PATH" && ! -L "$RELEASE_PATH" ]]; then
  [[ "$MODE" == "apply" ]] || fail "candidate_release_missing"
  RELEASE_STAGE="$RELEASE_ROOT/.cb120-$RELEASE_ID-$$"
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 "$RELEASE_STAGE"
  tar -xzf "$ARTIFACTS/$SOURCE_ARCHIVE" \
    --strip-components=1 -C "$RELEASE_STAGE"
  assert_no_escaping_symlink "$RELEASE_STAGE"
  for required in LICENSE app/LICENSE vendor/timeline-for-agent/LICENSE \
    vendor/whereabouts-mcp/LICENSE \
    docs/evidence/CB-000/LICENSE_COMPLIANCE.md \
    machine/facts/post-baseline-change-ledger.json; do
    [[ -f "$RELEASE_STAGE/$required" && ! -L "$RELEASE_STAGE/$required" ]] ||
      fail "candidate_corresponding_source:$required"
  done
  chown -R "$CODE_USER:$CODE_GROUP" "$RELEASE_STAGE"
  install -d -o "$CODE_USER" -g "$CODE_GROUP" -m 0750 "$STATE_ROOT/cache/npm"
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" \
    PATH="$BIN_ROOT:/usr/bin:/bin" \
    npm_config_cache="$STATE_ROOT/cache/npm" \
    "$BIN_ROOT/npm" --prefix "$RELEASE_STAGE/app" ci \
      --ignore-scripts --no-audit --no-fund
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" PATH="$BIN_ROOT:/usr/bin:/bin" \
    "$BIN_ROOT/npm" --prefix "$RELEASE_STAGE/app" run check
  sudo -u "$CODE_USER" -H env \
    HOME="$STATE_ROOT" PATH="$BIN_ROOT:/usr/bin:/bin" \
    "$BIN_ROOT/npm" --prefix "$RELEASE_STAGE/app" test
  jq -n \
    --arg release_commit "$RELEASE_ID" \
    --arg repository_tree "$(jq -er '.repository_tree' "$MANIFEST")" \
    --arg cyberboss_tree "$(jq -er '.cyberboss_tree' "$MANIFEST")" \
    --arg source_archive_sha256 "$(jq -er '.source.sha256' "$MANIFEST")" \
    '{
      schema_version: 1,
      task_id: "CB-120",
      release_commit: $release_commit,
      repository_tree: $repository_tree,
      cyberboss_tree: $cyberboss_tree,
      source_archive_sha256: $source_archive_sha256,
      corresponding_source_complete: true,
      license_expression: "AGPL-3.0-only AND GPL-3.0-only",
      upstream_clarification_received: false,
      candidate_only: true,
      current_switched: false,
      service_enabled: false,
      business_runtime_started: false
    }' >"$RELEASE_STAGE/cb120-release.json"
  assert_no_escaping_symlink "$RELEASE_STAGE"
  harden_tree "$RELEASE_STAGE" root "$CODE_GROUP"
  mv -T "$RELEASE_STAGE" "$RELEASE_PATH"
  RELEASE_STAGE=""
elif [[ ! -d "$RELEASE_PATH" || -L "$RELEASE_PATH" ]]; then
  fail "candidate_release_collision"
fi

jq -e --arg release "$RELEASE_ID" \
  --arg source_sha "$(jq -er '.source.sha256' "$MANIFEST")" '
  .schema_version == 1 and
  .task_id == "CB-120" and
  .release_commit == $release and
  .source_archive_sha256 == $source_sha and
  .corresponding_source_complete == true and
  .license_expression == "AGPL-3.0-only AND GPL-3.0-only" and
  .upstream_clarification_received == false and
  .candidate_only == true and
  .current_switched == false and
  .service_enabled == false and
  .business_runtime_started == false
' "$RELEASE_PATH/cb120-release.json" >/dev/null ||
  fail "candidate_release_manifest"
[[ -z "$(find "$RELEASE_PATH" \( -type f -o -type d \) \
  \( ! -user root -o ! -group "$CODE_GROUP" -o -perm /022 \) \
  -print -quit)" ]] ||
  fail "candidate_release_mutable"
[[ -z "$(find "$RELEASE_PATH" -type l \
  \( ! -user root -o ! -group "$CODE_GROUP" \) -print -quit)" ]] ||
  fail "candidate_release_symlink_owner"

"$BUDGET_COMMAND" \
  --policy "$CONFIG_ROOT/workspace-budget.json" \
  --workspace-root "$WORKSPACE" \
  --cache-root "$STATE_ROOT/cache" \
  --output "$TMP_ROOT/workspace-budget.json" >/dev/null ||
  fail "workspace_budget"
[[ "$(jq -er '.state' "$TMP_ROOT/workspace-budget.json")" == "recover" ]] ||
  fail "workspace_budget_not_recover"

CURRENT_AFTER="absent"
if [[ -e "$APP_ROOT/current" || -L "$APP_ROOT/current" ]]; then
  [[ -L "$APP_ROOT/current" ]] || fail "current_not_symlink_after"
  CURRENT_AFTER="$(readlink "$APP_ROOT/current")"
fi
[[ "$CURRENT_AFTER" == "$CURRENT_BEFORE" ]] || fail "current_changed"
systemctl is-active --quiet cyberboss-cloud.service &&
  fail "service_active_after"
systemctl is-enabled --quiet cyberboss-cloud.service 2>/dev/null &&
  fail "service_enabled_after"

printf 'CONTROLLED_WORKSPACE=PASS mode=%s release_id=%s alias=cyberboss filter=blob:none sparse_paths=2 current_changed=false service_active=false service_enabled=false private_database_clone=false data_activation=activation_pending budget_state=recover\n' \
  "$MODE" "$RELEASE_ID"
