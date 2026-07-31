#!/usr/bin/env bash
set -euo pipefail
APPLY="${SIGNAL_LATTICE_APPLY:-0}"
ROOT="${SIGNAL_LATTICE_INSTALL_ROOT:-/opt/signal-lattice}"
STATE="${SIGNAL_LATTICE_STATE_DIR:-/var/lib/signal-lattice}"
USER_NAME="${SIGNAL_LATTICE_SERVICE_USER:-signal-lattice}"
if [ "$APPLY" != 1 ]; then printf '{"state":"READY","apply_required":true,"root":"%s","state_dir":"%s"}\n' "$ROOT" "$STATE"; exit 0; fi
[ "$(id -u)" -eq 0 ] || { echo ROOT_REQUIRED >&2; exit 2; }
id "$USER_NAME" >/dev/null 2>&1 || useradd --system --home-dir "$STATE" --shell /usr/sbin/nologin "$USER_NAME"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 "$ROOT/releases" "$STATE" "$STATE/artifacts" "$STATE/backups" "$STATE/skill-inputs" "$STATE/market-data" "$STATE/calibration" "$STATE/decision-snapshots" "$STATE/status-evidence" "$STATE/upstream" "$STATE/evidence" "$STATE/evidence/securities" "$STATE/cycles"
printf '{"state":"PASS","user":"%s","root":"%s","state_dir":"%s"}\n' "$USER_NAME" "$ROOT" "$STATE"
