#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SPEC="$SCRIPT_DIR/../config/runtime-versions.json"
MODE=""
RELEASE_ID=""

fail() {
  printf 'RUNTIME_TOOLCHAIN=FAIL reason=%s\n' "$1"
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
    --spec)
      (($# >= 2)) || fail "spec_value_missing"
      SPEC="$2"
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
[[ -f "$SPEC" && ! -L "$SPEC" ]] || fail "runtime_spec_missing_or_symlink"
command -v jq >/dev/null 2>&1 || fail "required_command_missing:jq"

jq -e '
  .schema_version == 1 and
  .task_id == "CB-110" and
  .platform == "linux-x64" and
  (.node.version | test("^[0-9]+\\.[0-9]+\\.[0-9]+$")) and
  (.node.archive_sha256 | test("^[0-9a-f]{64}$")) and
  (.node.archive_url | startswith("https://nodejs.org/dist/")) and
  (.codex.version | test("^[0-9]+\\.[0-9]+\\.[0-9]+-alpha\\.[0-9]+\\.[0-9]+$")) and
  (.codex.main_archive_sha256 | test("^[0-9a-f]{64}$")) and
  (.codex.platform_archive_sha256 | test("^[0-9a-f]{64}$")) and
  (.codex.main_archive_url |
    startswith("https://registry.npmjs.org/@openai/codex/-/")) and
  (.codex.platform_archive_url |
    startswith("https://registry.npmjs.org/@openai/codex/-/")) and
  .claude_code.install_policy == "optional_not_installed" and
  .claude_code.credential_policy == "absent" and
  .claude_code.feature_flag_default == false and
  .claude_code.evaluation_gate_default == false and
  .runtime.codex_home == "/var/lib/cyberboss/.codex" and
  .runtime.loopback_endpoint == "ws://127.0.0.1:8765" and
  .runtime.toolchain_root == "/opt/cyberboss-cloud/shared/toolchains"
' "$SPEC" >/dev/null || fail "runtime_spec_invalid"

NODE_VERSION="$(jq -er '.node.version' "$SPEC")"
NODE_VERSION_OUTPUT="$(jq -er '.node.version_output' "$SPEC")"
NODE_URL="$(jq -er '.node.archive_url' "$SPEC")"
NODE_SHA256="$(jq -er '.node.archive_sha256' "$SPEC")"
CODEX_VERSION="$(jq -er '.codex.version' "$SPEC")"
CODEX_VERSION_OUTPUT="$(jq -er '.codex.version_output' "$SPEC")"
CODEX_MAIN_URL="$(jq -er '.codex.main_archive_url' "$SPEC")"
CODEX_MAIN_SHA256="$(jq -er '.codex.main_archive_sha256' "$SPEC")"
CODEX_PLATFORM_URL="$(jq -er '.codex.platform_archive_url' "$SPEC")"
CODEX_PLATFORM_SHA256="$(jq -er '.codex.platform_archive_sha256' "$SPEC")"
CODEX_HOME="$(jq -er '.runtime.codex_home' "$SPEC")"
ENDPOINT="$(jq -er '.runtime.loopback_endpoint' "$SPEC")"
TOOLCHAIN_ROOT="$(jq -er '.runtime.toolchain_root' "$SPEC")"

APP_ROOT="/opt/cyberboss-cloud"
RELEASE_ROOT="$APP_ROOT/releases"
NODE_DEST="$TOOLCHAIN_ROOT/node/$NODE_VERSION"
CODEX_DEST="$TOOLCHAIN_ROOT/codex/$CODEX_VERSION"
BIN_DIR="$TOOLCHAIN_ROOT/bin"
NODE_COMMAND="$BIN_DIR/node"
CODEX_COMMAND="$BIN_DIR/codex"
VERSION_MANIFEST="$RELEASE_ROOT/$RELEASE_ID/version-manifest.json"
SPEC_SHA256=""
TMP_ROOT=""

if [[ "$MODE" == "check" ]]; then
  printf 'RUNTIME_TOOLCHAIN_CHECK=PASS release_id=%s node=%s codex=%s live_commands=false persistent_writes=false\n' \
    "$RELEASE_ID" "$NODE_VERSION" "$CODEX_VERSION"
  exit 0
fi

[[ "$(uname -s)" == "Linux" && "$(uname -m)" == "x86_64" ]] ||
  fail "unsupported_target_platform"
for command_name in awk chmod chown cmp curl find grep install ln mv readlink \
  realpath sha256sum stat tar xz; do
  command -v "$command_name" >/dev/null 2>&1 ||
    fail "required_command_missing:$command_name"
done
[[ "$EUID" -eq 0 ]] || fail "root_required"
id cyberboss >/dev/null 2>&1 || fail "service_user_missing"
[[ -d "$APP_ROOT" && ! -L "$APP_ROOT" ]] || fail "app_root_missing_or_symlink"
[[ -d "$RELEASE_ROOT" && ! -L "$RELEASE_ROOT" ]] ||
  fail "release_root_missing_or_symlink"

TMP_ROOT="$(mktemp -d /tmp/cyberboss-cb110-install.XXXXXXXX)"
cleanup() {
  local exit_code=$?
  if [[ -n "${TMP_ROOT:-}" ]]; then
    case "$TMP_ROOT" in
      /tmp/cyberboss-cb110-install.*)
        find "$TMP_ROOT" -xdev -depth -delete 2>/dev/null || true
        ;;
      *)
        printf 'RUNTIME_TOOLCHAIN=FAIL reason=unsafe_cleanup_path\n' >&2
        exit 70
        ;;
    esac
  fi
  return "$exit_code"
}
trap cleanup EXIT
SPEC_SHA256="$(sha256sum "$SPEC" | awk '{print $1}')"

ensure_root_directory() {
  local path="$1"
  local mode="$2"
  if [[ -e "$path" || -L "$path" ]]; then
    [[ -d "$path" && ! -L "$path" ]] || fail "directory_type:$path"
    [[ "$(stat -c '%U:%G:%a' "$path")" == "root:root:$mode" ]] ||
      fail "directory_owner_or_mode:$path"
  else
    install -d -o root -g root -m "0$mode" "$path"
  fi
}

[[ -d "$APP_ROOT/shared" && ! -L "$APP_ROOT/shared" ]] ||
  fail "shared_root_missing_or_symlink"
[[ "$(stat -c '%U:%G:%a' "$APP_ROOT/shared")" == "root:cyberboss:750" ]] ||
  fail "shared_root_owner_or_mode"

if [[ "$MODE" == "apply" ]]; then
  ensure_root_directory "$TOOLCHAIN_ROOT" 755
  ensure_root_directory "$TOOLCHAIN_ROOT/node" 755
  ensure_root_directory "$TOOLCHAIN_ROOT/codex" 755
  ensure_root_directory "$BIN_DIR" 755

  if [[ -e "$CODEX_HOME" || -L "$CODEX_HOME" ]]; then
    [[ -d "$CODEX_HOME" && ! -L "$CODEX_HOME" ]] ||
      fail "codex_home_type"
    [[ "$(stat -c '%U:%G:%a' "$CODEX_HOME")" == "cyberboss:cyberboss:700" ]] ||
      fail "codex_home_owner_or_mode"
  else
    install -d -o cyberboss -g cyberboss -m 0700 "$CODEX_HOME"
  fi
fi

download_and_verify() {
  local url="$1"
  local expected="$2"
  local destination="$3"
  curl --fail --location --silent --show-error \
    --proto '=https' --tlsv1.2 \
    --output "$destination" "$url" ||
    fail "download_failed"
  local actual
  actual="$(sha256sum "$destination" | awk '{print $1}')"
  [[ "$actual" == "$expected" ]] || fail "archive_sha256_mismatch"
}

harden_tree() {
  local root="$1"
  chown -R root:root "$root"
  find "$root" -type d -exec chmod 0555 {} +
  find "$root" -type f -perm /111 -exec chmod 0555 {} +
  find "$root" -type f ! -perm /111 -exec chmod 0444 {} +
}

assert_no_escaping_symlink() {
  local root="$1"
  local link target resolved
  while IFS= read -r -d '' link; do
    target="$(readlink "$link")"
    [[ "$target" != /* ]] || fail "absolute_symlink_in_archive"
    resolved="$(realpath -m "$(dirname "$link")/$target")"
    [[ "$resolved" == "$root" || "$resolved" == "$root/"* ]] ||
      fail "escaping_symlink_in_archive"
  done < <(find "$root" -type l -print0)
}

if [[ "$MODE" == "apply" ]]; then
  NODE_STAGE=""
  CODEX_STAGE=""
  if [[ ! -e "$NODE_DEST" && ! -L "$NODE_DEST" ]]; then
    NODE_ARCHIVE="$TMP_ROOT/node.tar.xz"
    NODE_STAGE="$TMP_ROOT/node"
    download_and_verify "$NODE_URL" "$NODE_SHA256" "$NODE_ARCHIVE"
    install -d -m 0700 "$NODE_STAGE"
    tar -xJf "$NODE_ARCHIVE" --strip-components=1 -C "$NODE_STAGE"
    assert_no_escaping_symlink "$NODE_STAGE"
    [[ "$("$NODE_STAGE/bin/node" --version)" == "$NODE_VERSION_OUTPUT" ]] ||
      fail "staged_node_version"
    "$NODE_STAGE/bin/node" -e '
      const { DatabaseSync } = require("node:sqlite");
      const db = new DatabaseSync(":memory:");
      db.exec("CREATE TABLE probe(value INTEGER); INSERT INTO probe VALUES (110)");
      if (db.prepare("SELECT value FROM probe").get().value !== 110) process.exit(1);
      db.close();
    ' || fail "staged_node_sqlite"
    harden_tree "$NODE_STAGE"
  elif [[ ! -d "$NODE_DEST" || -L "$NODE_DEST" ]]; then
    fail "node_destination_collision"
  fi

  if [[ ! -e "$CODEX_DEST" && ! -L "$CODEX_DEST" ]]; then
    CODEX_MAIN_ARCHIVE="$TMP_ROOT/codex-main.tgz"
    CODEX_PLATFORM_ARCHIVE="$TMP_ROOT/codex-platform.tgz"
    CODEX_STAGE="$TMP_ROOT/codex"
    CODEX_MAIN_ROOT="$CODEX_STAGE/lib/node_modules/@openai/codex"
    CODEX_PLATFORM_ROOT="$CODEX_MAIN_ROOT/node_modules/@openai/codex-linux-x64"
    download_and_verify "$CODEX_MAIN_URL" "$CODEX_MAIN_SHA256" "$CODEX_MAIN_ARCHIVE"
    download_and_verify \
      "$CODEX_PLATFORM_URL" "$CODEX_PLATFORM_SHA256" "$CODEX_PLATFORM_ARCHIVE"
    install -d -m 0700 "$CODEX_MAIN_ROOT" "$CODEX_PLATFORM_ROOT" "$CODEX_STAGE/bin"
    tar -xzf "$CODEX_MAIN_ARCHIVE" --strip-components=1 -C "$CODEX_MAIN_ROOT"
    tar -xzf "$CODEX_PLATFORM_ARCHIVE" \
      --strip-components=1 -C "$CODEX_PLATFORM_ROOT"
    assert_no_escaping_symlink "$CODEX_STAGE"
    printf '#!/usr/bin/env bash\nexec "%s/bin/node" "%s/lib/node_modules/@openai/codex/bin/codex.js" "$@"\n' \
      "$NODE_DEST" "$CODEX_DEST" >"$CODEX_STAGE/bin/codex"
    chmod 0555 "$CODEX_STAGE/bin/codex"
    TEST_NODE="${NODE_STAGE:+$NODE_STAGE/bin/node}"
    TEST_NODE="${TEST_NODE:-$NODE_DEST/bin/node}"
    [[ "$("$TEST_NODE" "$CODEX_MAIN_ROOT/bin/codex.js" --version)" == \
      "$CODEX_VERSION_OUTPUT" ]] || fail "staged_codex_version"
    harden_tree "$CODEX_STAGE"
  elif [[ ! -d "$CODEX_DEST" || -L "$CODEX_DEST" ]]; then
    fail "codex_destination_collision"
  fi

  if [[ -n "$NODE_STAGE" ]]; then
    mv -T "$NODE_STAGE" "$NODE_DEST"
    NODE_STAGE=""
  fi
  if [[ -n "$CODEX_STAGE" ]]; then
    mv -T "$CODEX_STAGE" "$CODEX_DEST"
    CODEX_STAGE=""
  fi
fi

ensure_exact_link() {
  local target="$1"
  local link="$2"
  local temporary="$link.cb110.$RELEASE_ID"
  if [[ -e "$link" || -L "$link" ]]; then
    [[ -L "$link" && "$(readlink "$link")" == "$target" ]] ||
      fail "toolchain_link_collision:$link"
    return
  fi
  ln -s "$target" "$temporary"
  mv -T "$temporary" "$link"
}

if [[ "$MODE" == "apply" ]]; then
  ensure_exact_link "$NODE_DEST/bin/node" "$BIN_DIR/node"
  ensure_exact_link "$NODE_DEST/bin/npm" "$BIN_DIR/npm"
  ensure_exact_link "$NODE_DEST/bin/npx" "$BIN_DIR/npx"
  ensure_exact_link "$CODEX_DEST/bin/codex" "$BIN_DIR/codex"
fi

build_version_manifest() {
  local output="$1"
  jq -n \
    --arg release_commit "$RELEASE_ID" \
    --arg source_spec_sha256 "$SPEC_SHA256" \
    --arg node_version "$NODE_VERSION" \
    --arg node_archive_sha256 "$NODE_SHA256" \
    --arg node_command "$NODE_COMMAND" \
    --arg codex_version "$CODEX_VERSION" \
    --arg codex_main_archive_sha256 "$CODEX_MAIN_SHA256" \
    --arg codex_platform_archive_sha256 "$CODEX_PLATFORM_SHA256" \
    --arg codex_command "$CODEX_COMMAND" \
    --arg codex_home "$CODEX_HOME" \
    --arg endpoint "$ENDPOINT" \
    '{
      schema_version: 1,
      task_id: "CB-110",
      release_commit: $release_commit,
      source_spec_sha256: $source_spec_sha256,
      node: {
        version: $node_version,
        archive_sha256: $node_archive_sha256,
        command: $node_command,
        sqlite_adapter: "node:sqlite"
      },
      codex: {
        version: $codex_version,
        main_archive_sha256: $codex_main_archive_sha256,
        platform_archive_sha256: $codex_platform_archive_sha256,
        command: $codex_command,
        app_server_endpoint: $endpoint,
        auth_activation: "activation_pending"
      },
      codex_home: {
        path: $codex_home,
        required_mode: "0700",
        credential_content_read: false
      },
      claude_code: {
        binary: "absent",
        credential: "absent",
        feature_flag_default: false,
        evaluation_gate_default: false,
        adapter_state: "disabled"
      },
      device_auth_command: (
        "sudo -u cyberboss -H env HOME=/var/lib/cyberboss CODEX_HOME=" +
        $codex_home + " " + $codex_command + " login --device-auth"
      ),
      loopback_startup_command: (
        "sudo -u cyberboss -H env HOME=/var/lib/cyberboss CODEX_HOME=" +
        $codex_home + " " + $codex_command +
        " app-server --listen " + $endpoint
      ),
      public_callback_required: false,
      business_runtime_started: false
    }' >"$output"
}

EXPECTED_MANIFEST="$TMP_ROOT/version-manifest.json"
build_version_manifest "$EXPECTED_MANIFEST"
if [[ "$MODE" == "apply" ]]; then
  if [[ -e "$RELEASE_ROOT/$RELEASE_ID" || -L "$RELEASE_ROOT/$RELEASE_ID" ]]; then
    [[ -d "$RELEASE_ROOT/$RELEASE_ID" && ! -L "$RELEASE_ROOT/$RELEASE_ID" ]] ||
      fail "version_release_type"
    [[ -f "$VERSION_MANIFEST" && ! -L "$VERSION_MANIFEST" ]] ||
      fail "version_manifest_missing_or_symlink"
    cmp -s "$EXPECTED_MANIFEST" "$VERSION_MANIFEST" ||
      fail "version_manifest_drift"
  else
    RELEASE_STAGE="$TMP_ROOT/release"
    install -d -o root -g root -m 0755 "$RELEASE_STAGE"
    install -o root -g root -m 0444 "$EXPECTED_MANIFEST" \
      "$RELEASE_STAGE/version-manifest.json"
    chmod 0555 "$RELEASE_STAGE"
    mv -T "$RELEASE_STAGE" "$RELEASE_ROOT/$RELEASE_ID"
  fi
fi

verify_installation() {
  [[ "$("$NODE_COMMAND" --version)" == "$NODE_VERSION_OUTPUT" ]] ||
    fail "node_version"
  "$NODE_COMMAND" -e '
    const { DatabaseSync } = require("node:sqlite");
    const db = new DatabaseSync(":memory:");
    db.exec("CREATE TABLE probe(value INTEGER); INSERT INTO probe VALUES (110)");
    if (db.prepare("SELECT value FROM probe").get().value !== 110) process.exit(1);
    db.close();
  ' || fail "node_sqlite"
  [[ "$("$CODEX_COMMAND" --version)" == "$CODEX_VERSION_OUTPUT" ]] ||
    fail "codex_version"
  "$CODEX_COMMAND" app-server --help 2>&1 |
    grep -Fq 'ws://IP:PORT' || fail "codex_app_server_protocol"
  [[ "$(stat -c '%U:%G:%a' "$CODEX_HOME")" == \
    "cyberboss:cyberboss:700" ]] || fail "codex_home_owner_or_mode"
  for immutable_root in "$NODE_DEST" "$CODEX_DEST"; do
    [[ -d "$immutable_root" && ! -L "$immutable_root" ]] ||
      fail "toolchain_version_type"
    [[ -z "$(find "$immutable_root" \( -type f -o -type d \) \
      \( ! -user root -o ! -group root -o -perm /022 \) -print -quit)" ]] ||
      fail "toolchain_version_mutable"
  done
  for pair in \
    "$NODE_DEST/bin/node|$BIN_DIR/node" \
    "$NODE_DEST/bin/npm|$BIN_DIR/npm" \
    "$NODE_DEST/bin/npx|$BIN_DIR/npx" \
    "$CODEX_DEST/bin/codex|$BIN_DIR/codex"; do
    expected_target="${pair%%|*}"
    link_path="${pair#*|}"
    [[ -L "$link_path" && "$(readlink "$link_path")" == "$expected_target" ]] ||
      fail "toolchain_link_drift"
  done
  [[ -f "$VERSION_MANIFEST" && ! -L "$VERSION_MANIFEST" ]] ||
    fail "version_manifest_type"
  [[ "$(stat -c '%U:%G:%a' "$VERSION_MANIFEST")" == "root:root:444" ]] ||
    fail "version_manifest_owner_or_mode"
  cmp -s "$EXPECTED_MANIFEST" "$VERSION_MANIFEST" ||
    fail "version_manifest_content"
  if PATH="$BIN_DIR:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" \
    command -v claude >/dev/null 2>&1; then
    fail "claude_binary_must_remain_absent"
  fi
}

verify_installation
AUTH_PRESENT=false
[[ -e "$CODEX_HOME/auth.json" || -L "$CODEX_HOME/auth.json" ]] &&
  AUTH_PRESENT=true
printf 'RUNTIME_TOOLCHAIN_VERIFY=PASS release_id=%s node=%s sqlite=PASS codex=%s codex_home_mode=0700 auth_file_present=%s auth_content_read=false claude_binary=absent public_listener_started=false\n' \
  "$RELEASE_ID" "$NODE_VERSION" "$CODEX_VERSION" "$AUTH_PRESENT"
if [[ "$MODE" == "apply" ]]; then
  printf 'RUNTIME_TOOLCHAIN_APPLY=PASS release_id=%s idempotent_safe=true global_toolchain_modified=false business_runtime_started=false\n' \
    "$RELEASE_ID"
fi
