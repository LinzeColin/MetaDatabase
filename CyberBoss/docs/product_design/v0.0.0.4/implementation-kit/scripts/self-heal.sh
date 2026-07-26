#!/usr/bin/env bash
set -Eeuo pipefail

STATE_DIR="${CYBERBOSS_STATE_DIR:-/var/lib/cyberboss}"
STATE_FILE="$STATE_DIR/self-heal.state"
SERVICE="${CB_SYSTEMD_SERVICE:-cyberboss-cloud.service}"
COOLDOWN="${CB_SELFHEAL_COOLDOWN_SECONDS:-120}"
RESTART_UNHEALTHY="${CB_SELFHEAL_RESTART_ON_UNHEALTHY:-false}"
MAX_10M="${CB_SELFHEAL_MAX_RESTARTS_10M:-3}"
HEALTH_SCRIPT="${CB_HEALTH_SCRIPT:-/opt/cyberboss-cloud/current/implementation-kit/scripts/health-check.sh}"
mkdir -p "$STATE_DIR"
NOW="${CB_NOW_EPOCH:-$(date +%s)}"
LAST_ACTION=0
WINDOW_START="$NOW"
COUNT=0
if [[ -r "$STATE_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$STATE_FILE"
fi

save_state() {
  umask 077
  cat > "$STATE_FILE.tmp" <<STATE
LAST_ACTION=$LAST_ACTION
WINDOW_START=$WINDOW_START
COUNT=$COUNT
STATE
  mv "$STATE_FILE.tmp" "$STATE_FILE"
}

if (( NOW - WINDOW_START >= 600 )); then WINDOW_START="$NOW"; COUNT=0; fi

if ! systemctl is-active --quiet "$SERVICE"; then
  if (( NOW - LAST_ACTION < COOLDOWN )); then
    echo 'SELFHEAL=DEGRADED action=cooldown service=inactive'
    exit 1
  fi
  if (( COUNT >= MAX_10M )); then
    echo 'SELFHEAL=STOP reason=restart_budget_exhausted'
    exit 2
  fi
  systemctl restart "$SERVICE"
  LAST_ACTION="$NOW"; COUNT=$((COUNT + 1)); save_state
  echo 'SELFHEAL=ACTION action=restart_inactive_service'
  exit 0
fi

set +e
"$HEALTH_SCRIPT" >/tmp/cyberboss-health.$$ 2>&1
RC=$?
set -e
if (( RC == 0 )); then
  echo 'SELFHEAL=PASS action=none'
  rm -f /tmp/cyberboss-health.$$
  exit 0
fi

# Conservative default: do not restart an active service with a possibly ambiguous mutation.
if [[ "$RESTART_UNHEALTHY" != "true" ]]; then
  echo "SELFHEAL=DEGRADED action=none reason=health_failed rc=$RC"
  sed -n '1,20p' /tmp/cyberboss-health.$$ | sed -E 's/(token|authorization|bearer)=[^ ]+/\1=[REDACTED]/Ig'
  rm -f /tmp/cyberboss-health.$$
  exit 1
fi

if (( NOW - LAST_ACTION < COOLDOWN || COUNT >= MAX_10M )); then
  echo 'SELFHEAL=STOP reason=active_unhealthy_restart_guard'
  rm -f /tmp/cyberboss-health.$$
  exit 2
fi
systemctl restart "$SERVICE"
LAST_ACTION="$NOW"; COUNT=$((COUNT + 1)); save_state
rm -f /tmp/cyberboss-health.$$
echo 'SELFHEAL=ACTION action=restart_unhealthy_service'
