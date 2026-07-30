#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-/etc/systemd/system}"
[ "$(id -u)" -eq 0 ] || { echo ROOT_REQUIRED >&2; exit 2; }
install -d -m 0755 "$DEST"
for unit in "$ROOT"/deploy/systemd/signal-lattice-*; do install -m 0644 "$unit" "$DEST/$(basename "$unit")"; done
systemctl daemon-reload
systemctl enable \
  signal-lattice-api.service signal-lattice-worker.service \
  signal-lattice-cloudflared.service \
  signal-lattice-source-sync.timer signal-lattice-evolution.timer \
  signal-lattice-outbox-sync.timer signal-lattice-status.timer signal-lattice-backup.timer
systemd-analyze verify "$DEST"/signal-lattice-* >/dev/null
printf '{"state":"PASS","unit_count":%s,"cloudflared_unit_installed":true}\n' "$(find "$ROOT/deploy/systemd" -type f | wc -l)"
