#!/usr/bin/env bash
set -euo pipefail
url="http://127.0.0.1:${CYBERBOSS_LISTEN_PORT:-8787}/readyz"
if [[ "${1:-}" == --write-snapshot ]]; then
  mkdir -p /run/cyberboss
  state=degraded
  if /usr/bin/curl -fsS --max-time 5 "$url" >/dev/null; then state=healthy; fi
  tmp=/run/cyberboss/status.json.tmp
  printf '{"schema_version":1,"service":"cyberboss","version":"v0.0.0.8","state":"%s","generated_at":"%s","contains_pii":false}\n' "$state" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$tmp"
  chmod 0640 "$tmp" && mv "$tmp" /run/cyberboss/status.json
  [[ "$state" == healthy ]]
else
  /usr/bin/curl -fsS --max-time 5 "$url"
fi
