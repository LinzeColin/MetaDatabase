#!/usr/bin/env bash
set -Eeuo pipefail

OFFLINE=0
[[ "${1:-}" == "--offline" ]] && OFFLINE=1

DB="${CB_RUNTIME_DB:-/var/lib/cyberboss/runtime.db}"
ENV_FILE="${CB_ENV_FILE:-/etc/cyberboss/cyberboss.env}"
WORKSPACES="${CYBERBOSS_WORKSPACE_CONFIG:-/etc/cyberboss/workspaces.json}"
HTTP_PORT="${CB_HTTP_PORT:-8780}"
STOP_DISK="${CB_STOP_DISK_PERCENT:-90}"
STOP_MEM="${CB_STOP_MEMORY_PERCENT:-92}"
FAIL=()
DEGRADED=()

[[ -r "$ENV_FILE" ]] || FAIL+=("env_unreadable")
[[ -r "$WORKSPACES" ]] || FAIL+=("workspace_config_unreadable")
[[ -r "$DB" ]] || FAIL+=("runtime_db_unreadable")

if [[ -r "$DB" ]] && command -v sqlite3 >/dev/null 2>&1; then
  INTEGRITY="$(sqlite3 "$DB" 'PRAGMA integrity_check;' 2>/dev/null || true)"
  [[ "$INTEGRITY" == "ok" ]] || FAIL+=("sqlite_integrity:$INTEGRITY")
fi

if command -v node >/dev/null 2>&1 && [[ -r "$WORKSPACES" ]]; then
  node "$(dirname "$0")/../tests/validate_config.js" "$ENV_FILE" "$WORKSPACES" >/dev/null || FAIL+=("config_validation")
fi

DISK="$(df -P / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
MEM="$(awk '/MemTotal:/ {t=$2} /MemAvailable:/ {a=$2} END {printf "%.0f", (t-a)*100/t}' /proc/meminfo)"
(( DISK < STOP_DISK )) || FAIL+=("disk_stop:${DISK}")
(( MEM < STOP_MEM )) || FAIL+=("memory_stop:${MEM}")
(( DISK < 85 )) || DEGRADED+=("disk_pressure:${DISK}")
(( MEM < 85 )) || DEGRADED+=("memory_pressure:${MEM}")

# Codex transport must never listen on a non-loopback address.
if command -v ss >/dev/null 2>&1; then
  if ss -lntH 'sport = :8765' 2>/dev/null | awk '{print $4}' | grep -Evq '^(127\.0\.0\.1|\[::1\]|localhost):8765$'; then
    FAIL+=("codex_port_non_loopback")
  fi
fi

if (( OFFLINE == 0 )); then
  curl -fsS --max-time 5 "http://127.0.0.1:${HTTP_PORT}/healthz" >/dev/null || FAIL+=("http_healthz")
  curl -fsS --max-time 5 "http://127.0.0.1:${HTTP_PORT}/readyz" >/dev/null || DEGRADED+=("http_not_ready")
fi

printf 'DISK_USED_PERCENT=%s\nMEMORY_USED_PERCENT=%s\n' "$DISK" "$MEM"
for x in "${DEGRADED[@]}"; do printf 'DEGRADED_REASON=%s\n' "$x"; done
for x in "${FAIL[@]}"; do printf 'FAIL_REASON=%s\n' "$x"; done

if ((${#FAIL[@]})); then
  echo 'HEALTH=FAIL'
  exit 2
fi
if ((${#DEGRADED[@]})); then
  echo 'HEALTH=DEGRADED'
  exit 1
fi
echo 'HEALTH=PASS'
