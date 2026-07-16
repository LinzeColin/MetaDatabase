#!/usr/bin/env bash
# S10PAT01 cloud worker D1 integration smoke: schema + seed into local D1,
# boot `wrangler dev --local`, then assert the read-path contracts
# (health / explore / reroot / expand / explanation / evidence / search).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="$REPO_ROOT/apps/cloudflare-public"
PORT="${EEI_CLOUD_SMOKE_PORT:-8787}"
WRANGLER="npx --yes wrangler@4.42.0"

cd "$APP_DIR"

echo "[smoke] applying schema + seed to local D1"
$WRANGLER d1 execute eei-publication --local --file "$REPO_ROOT/infra/cloudflare/d1_publication_schema.sql" >/dev/null
$WRANGLER d1 execute eei-publication --local --file "$REPO_ROOT/infra/cloudflare/d1_user_state_schema.sql" >/dev/null
$WRANGLER d1 execute eei-publication --local --file tests/smoke_seed.sql >/dev/null

echo "[smoke] booting wrangler dev --local on :$PORT"
LOG="$(mktemp)"
$WRANGLER dev --local --port "$PORT" >"$LOG" 2>&1 &
DEV_PID=$!
trap 'kill "$DEV_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$DEV_PID" 2>/dev/null; then
    echo "[smoke] wrangler dev exited early:" >&2
    tail -20 "$LOG" >&2
    exit 1
  fi
  sleep 1
done

echo "[smoke] asserting contracts"
node "$REPO_ROOT/apps/cloudflare-public/tests/smoke_assert.mjs" "http://127.0.0.1:$PORT"

echo "[smoke] PASS"
