#!/usr/bin/env bash
set -Eeuo pipefail

URL="${1:-http://127.0.0.1:${CB_HTTP_PORT:-8780}/readyz}"
ATTEMPTS="${CB_READY_ATTEMPTS:-40}"
[[ "$ATTEMPTS" =~ ^[0-9]+$ && "$ATTEMPTS" -gt 0 ]] || { echo 'READY=FAIL invalid_attempts'; exit 2; }

for ((i=1; i<=ATTEMPTS; i++)); do
  if curl -fsS --connect-timeout 1 --max-time 2 "$URL" >/dev/null 2>&1; then
    echo "READY=PASS attempt=$i"
    exit 0
  fi
done

echo "READY=FAIL attempts=$ATTEMPTS url=$URL"
exit 1
