#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE="$(mktemp -d)"
PORT="${SL19_LOCAL_ACCEPTANCE_PORT:-18787}"
cleanup() {
  [[ -n "${LOOP_PID:-}" ]] && kill "$LOOP_PID" 2>/dev/null || true
  [[ -n "${API_PID:-}" ]] && kill "$API_PID" 2>/dev/null || true
  rm -rf "$STATE"
}
trap cleanup EXIT
export PYTHONPATH="$ROOT/src"
export SL19_STATE_DIR="$STATE"
export SL19_CONFIG_DIR="$ROOT/config"
export SL19_WEB_DIR="$ROOT/web"
export SL19_FIXTURE_DIR="$ROOT/fixtures"
export SL19_MARKET_PROVIDER=fixture
export SL19_HOST=127.0.0.1
export SL19_PORT="$PORT"
python3 -m signal_lattice_v19.cli bootstrap >/dev/null
python3 -m signal_lattice_v19.cli once >/dev/null
python3 -m signal_lattice_v19.cli serve & API_PID=$!
python3 -m signal_lattice_v19.cli loop & LOOP_PID=$!
for _ in $(seq 1 20); do
  curl -fsS --max-time 2 "http://127.0.0.1:$PORT/health/ready" >/dev/null 2>&1 && break
  sleep 1
done
python3 "$ROOT/scripts/run_acceptance.py" --base-url "http://127.0.0.1:$PORT" --verify-cadence
