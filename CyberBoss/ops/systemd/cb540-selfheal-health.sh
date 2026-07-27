#!/usr/bin/env bash
set -Eeuo pipefail

# CB-540 is deliberately limited to the cloud service's loopback status plane.
# It never contacts a public origin or invokes a provider/model control plane.
SYSTEMCTL_BIN="${CB540_SYSTEMCTL_BIN:-systemctl}"
CURL_BIN="${CB540_CURL_BIN:-curl}"
SERVICE="cyberboss-cloud.service"
BASE_URL="http://127.0.0.1:8780"

HTTP_BODY=""
HTTP_CODE=""

fail_closed() {
  printf 'CB540_SELFHEAL_HEALTH=FAILED reason=%s\n' "$1"
  exit 2
}

fetch_loopback() {
  local path="$1"
  local response
  if ! response="$("$CURL_BIN" --silent --show-error --connect-timeout 2 --max-time 5 --write-out $'\n%{http_code}' "${BASE_URL}${path}")"; then
    fail_closed "request_${path//\//_}"
  fi
  HTTP_CODE="${response##*$'\n'}"
  HTTP_BODY="${response%$'\n'*}"
  while [[ "$HTTP_BODY" == *$'\n' || "$HTTP_BODY" == *$'\r' ]]; do
    HTTP_BODY="${HTTP_BODY%$'\n'}"
    HTTP_BODY="${HTTP_BODY%$'\r'}"
  done
  [[ "$HTTP_CODE" =~ ^[0-9]{3}$ ]] || fail_closed "response_${path//\//_}"
}

"$SYSTEMCTL_BIN" is-active --quiet "$SERVICE" || fail_closed "cloud_inactive"

fetch_loopback "/healthz"
[[ "$HTTP_CODE" == "200" && "$HTTP_BODY" == '{"status":"healthy"}' ]] || fail_closed "health_contract"

fetch_loopback "/timeline/"
[[ "$HTTP_CODE" == "200" ]] || fail_closed "timeline_contract"

fetch_loopback "/readyz"
if [[ "$HTTP_CODE" == "200" && "$HTTP_BODY" == '{"status":"ready","unready_components":[]}' ]]; then
  printf 'CB540_SELFHEAL_HEALTH=PASS readiness=ready\n'
  exit 0
fi

# A missing real WeChat credential has a precise, non-fatal service shape.  It
# must stay visible as degraded and must not trigger a restart of an active
# cloud process.  The frozen self-heal runner maps this exit 1 to its existing
# no-mutation branch; systemd accepts only that known degraded exit.
if [[ "$HTTP_CODE" == "503" && "$HTTP_BODY" == '{"status":"unready","unready_components":["channel","bridge"]}' ]]; then
  printf 'CB540_SELFHEAL_HEALTH=DEGRADED reason=channel_pending\n'
  exit 1
fi

fail_closed "ready_contract"
