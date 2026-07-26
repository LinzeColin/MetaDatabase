#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${CB_APP_ROOT:-/opt/cyberboss-cloud}"
CURRENT="$APP_ROOT/current"
RELEASE_ROOT="${CB_RELEASE_ROOT:-$CURRENT}"
STATE_DIR="${CYBERBOSS_STATE_DIR:-/var/lib/cyberboss}"
NODE="$APP_ROOT/shared/toolchains/bin/node"

[[ -d "$RELEASE_ROOT" && ! -L "$RELEASE_ROOT" ]] ||
  { echo "STOP: release root missing or symbolic" >&2; exit 2; }
[[ "$RELEASE_ROOT" == "$APP_ROOT/releases/"* ]] ||
  { echo "STOP: release root outside immutable releases" >&2; exit 2; }
[[ -x "$NODE" ]] ||
  { echo "STOP: pinned Node launcher missing" >&2; exit 2; }
NODE_REAL="$(readlink -f "$NODE")"
[[ "$NODE_REAL" == "$APP_ROOT/shared/toolchains/node/"*/bin/node ]] ||
  { echo "STOP: Node launcher outside pinned toolchain" >&2; exit 2; }

for var in CB_EXPECTED_RELEASE_ID CB_RUNTIME_PROVIDER CB_CHANNEL_PROVIDER \
  CB_STATUS_TOKEN_FILE CYBERBOSS_RUNTIME CYBERBOSS_CODEX_ENDPOINT \
  CYBERBOSS_WEIXIN_BASE_URL CB_HTTP_HOST CB_HTTP_PORT; do
  value="${!var:-}"
  [[ -n "$value" ]] || { echo "STOP: missing env $var" >&2; exit 2; }
done
[[ "$CB_EXPECTED_RELEASE_ID" =~ ^[0-9a-f]{40}$ ]] ||
  { echo "STOP: expected release must be a full lowercase commit" >&2; exit 2; }
[[ "$(basename "$RELEASE_ROOT")" == "$CB_EXPECTED_RELEASE_ID" ]] ||
  { echo "STOP: release path does not match expected commit" >&2; exit 2; }
[[ "$CB_RUNTIME_PROVIDER" == "simulator" || "$CB_RUNTIME_PROVIDER" == "real" ]] ||
  { echo "STOP: invalid Runtime provider" >&2; exit 2; }
[[ "$CB_CHANNEL_PROVIDER" == "simulator" || "$CB_CHANNEL_PROVIDER" == "real" ]] ||
  { echo "STOP: invalid channel provider" >&2; exit 2; }

if [[ "$CYBERBOSS_RUNTIME" == "claudecode" ]]; then
  if [[ "${CB_CLAUDE_RUNTIME:-false}" != "true" ||
        "${CB_CLAUDE_EVAL_PASSED:-false}" != "true" ]]; then
    echo 'STOP: Claude adapter disabled; both CB_CLAUDE_RUNTIME=true and CB_CLAUDE_EVAL_PASSED=true are required' >&2
    exit 2
  fi
fi

if env | grep -Eq '(^|=)REPLACE_WITH|REPLACE_'; then
  echo 'STOP: unresolved REPLACE_ placeholder in environment' >&2
  exit 2
fi

if [[ "$CYBERBOSS_CODEX_ENDPOINT" != "ws://127.0.0.1:8765" ]]; then
  echo 'STOP: Codex endpoint must be exact loopback port 8765' >&2
  exit 2
fi
[[ "$CB_HTTP_HOST" == "127.0.0.1" && "$CB_HTTP_PORT" == "8780" ]] ||
  { echo "STOP: status endpoint must be exact loopback port 8780" >&2; exit 2; }
[[ "$CB_STATUS_TOKEN_FILE" == /run/cyberboss-cb130/* ||
  "$CB_STATUS_TOKEN_FILE" == /run/cyberboss-cb140/* ]] ||
  { echo "STOP: status token must be ephemeral" >&2; exit 2; }

mkdir -p "$STATE_DIR/locks" "$STATE_DIR/status" "$STATE_DIR/tmp"
cd "$RELEASE_ROOT"

RELEASE_COMMIT="$(
  "$NODE" -e "
    const fs = require('node:fs');
    try {
      const m = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
      process.stdout.write(typeof m.release_commit === 'string' ? m.release_commit : 'unknown');
    } catch { process.stdout.write('unknown'); }
  " "$RELEASE_ROOT/release-manifest.json"
)"
[[ "$RELEASE_COMMIT" == "$CB_EXPECTED_RELEASE_ID" ]] ||
  { echo "STOP: embedded release manifest mismatch" >&2; exit 2; }
[[ -f "$RELEASE_ROOT/health-contract.json" &&
  -f "$RELEASE_ROOT/process-tree.txt" &&
  -f "$RELEASE_ROOT/app/scripts/cloud-supervisor.js" ]] ||
  { echo "STOP: CB-130 release contract incomplete" >&2; exit 2; }
printf 'Starting CyberBoss Cloud\nrelease=%s\nruntime=%s\nendpoint=%s\n' \
  "${RELEASE_COMMIT:0:12}" \
  "$CYBERBOSS_RUNTIME" "$CYBERBOSS_CODEX_ENDPOINT"

# The entrypoint is commit-bound. Environment-provided shell commands are ignored.
unset CB_START_COMMAND
cd "$RELEASE_ROOT/app"
exec "$NODE" ./scripts/cloud-supervisor.js
