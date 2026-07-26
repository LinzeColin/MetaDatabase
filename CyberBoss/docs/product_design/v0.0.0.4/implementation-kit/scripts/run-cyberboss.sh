#!/usr/bin/env bash
set -Eeuo pipefail

APP_ROOT="${CB_APP_ROOT:-/opt/cyberboss-cloud}"
CURRENT="$APP_ROOT/current"
STATE_DIR="${CYBERBOSS_STATE_DIR:-/var/lib/cyberboss}"
START_COMMAND="${CB_START_COMMAND:-npm run shared:start}"

[[ -d "$CURRENT" ]] || { echo "STOP: current release missing: $CURRENT" >&2; exit 2; }
[[ -d "$STATE_DIR" ]] || { echo "STOP: state dir missing: $STATE_DIR" >&2; exit 2; }

for var in CYBERBOSS_RUNTIME CYBERBOSS_CODEX_ENDPOINT CB_RUNTIME_DB; do
  value="${!var:-}"
  [[ -n "$value" ]] || { echo "STOP: missing env $var" >&2; exit 2; }
done

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

if [[ "$CYBERBOSS_CODEX_ENDPOINT" != ws://127.0.0.1:* && "$CYBERBOSS_CODEX_ENDPOINT" != ws://localhost:* ]]; then
  echo 'STOP: Codex endpoint must be loopback' >&2
  exit 2
fi

mkdir -p "$STATE_DIR/locks" "$STATE_DIR/status" "$STATE_DIR/tmp"
cd "$CURRENT"

RELEASE_COMMIT="$(
  node -e "
    const fs = require('node:fs');
    try {
      const m = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
      process.stdout.write(typeof m.commit === 'string' ? m.commit.slice(0, 12) : 'unknown');
    } catch { process.stdout.write('unknown'); }
  " "$CURRENT/release-manifest.json"
)"
printf 'Starting CyberBoss Cloud\nrelease=%s\nruntime=%s\nendpoint=%s\n' \
  "$RELEASE_COMMIT" \
  "$CYBERBOSS_RUNTIME" "$CYBERBOSS_CODEX_ENDPOINT"

# EnvironmentFile is root-controlled. Do not accept CB_START_COMMAND from user input.
exec /bin/bash -lc "$START_COMMAND"
