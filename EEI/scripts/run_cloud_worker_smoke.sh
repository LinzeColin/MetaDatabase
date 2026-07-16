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

echo "[smoke] booting wrangler dev --local on :$PORT (with scheduled drill)"
LOG="$(mktemp)"
$WRANGLER dev --local --port "$PORT" --test-scheduled >"$LOG" 2>&1 &
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

echo "[smoke] firing scheduled drills (hourly heartbeat, then SEC slice)"
curl -sf "http://127.0.0.1:$PORT/__scheduled?cron=0+*+*+*+*" >/dev/null
sleep 3
curl -sf "http://127.0.0.1:$PORT/__scheduled?cron=0+18+*+*+*" >/dev/null
sleep 6
HEARTBEAT=$(curl -sf "http://127.0.0.1:$PORT/v1/cloud/runs?limit=5")
echo "$HEARTBEAT" | node -e "
const runs = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const hb = runs.find((run) => run.scope && run.scope.kind === 'health_heartbeat');
if (!hb) { console.error('no health heartbeat row'); process.exit(1); }
if (hb.status === 'failed') { console.error('heartbeat failed', JSON.stringify(hb.detail).slice(0, 300)); process.exit(1); }
console.log('HEARTBEAT_DRILL status=' + hb.status + ' snapshot=' + (hb.detail[0] || {}).snapshot_key);
"
SINCE_EMPTY=$(curl -sf "http://127.0.0.1:$PORT/v1/cloud/runs?limit=500&since=2100-01-01T00:00:00Z")
SINCE_ALL=$(curl -sf "http://127.0.0.1:$PORT/v1/cloud/runs?limit=500&since=2000-01-01T00:00:00Z")
node -e "
const empty = JSON.parse(process.argv[1]);
const all = JSON.parse(process.argv[2]);
if (!Array.isArray(empty) || empty.length !== 0) { console.error('since-future should be empty', empty.length); process.exit(1); }
if (!Array.isArray(all) || all.length < 2) { console.error('since-past should return the drill rows', all.length); process.exit(1); }
console.log('SINCE_FILTER rows=' + all.length);
" "$SINCE_EMPTY" "$SINCE_ALL"
RUNS=$(curl -sf "http://127.0.0.1:$PORT/v1/cloud/runs?limit=1")
echo "$RUNS" | node -e "
const runs = JSON.parse(require('fs').readFileSync(0, 'utf8'));
if (!Array.isArray(runs) || runs.length === 0) { console.error('no cloud_run_log row'); process.exit(1); }
const run = runs[0];
if (!['completed', 'partial', 'failed'].includes(run.status)) { console.error('bad status', run.status); process.exit(1); }
console.log('SCHEDULED_DRILL status=' + run.status + ' slice=' + run.rotation_slice + ' new_filings=' + run.new_filings_count);
if (run.status === 'failed') { console.error('scheduled drill failed', JSON.stringify(run.detail).slice(0, 400)); process.exit(1); }
"

echo "[smoke] PASS"
