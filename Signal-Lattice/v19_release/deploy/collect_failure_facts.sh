#!/usr/bin/env bash
set -u
OUT_DIR="/var/lib/signal-lattice-v19/deployment"
OUT="$OUT_DIR/FAILURE_FACTS.txt"
install -d -m 0750 -o signal-lattice -g signal-lattice "$OUT_DIR" 2>/dev/null || mkdir -p "$OUT_DIR"
{
  echo "Signal Lattice V19 deployment failure facts"
  date -Is
  echo
  echo "== Unit states =="
  for unit in signal-lattice-v19-api.service signal-lattice-v19-loop.service signal-lattice-v19-cloudflared.service signal-lattice-api.service signal-lattice-cycle.timer signal-lattice-cloudflared.service; do
    printf '%s enabled=' "$unit"
    systemctl is-enabled "$unit" 2>/dev/null || true
    printf '%s active=' "$unit"
    systemctl is-active "$unit" 2>/dev/null || true
  done
  echo
  echo "== V19 API status =="
  systemctl status signal-lattice-v19-api.service --no-pager --lines=60 2>&1 || true
  echo
  echo "== V19 loop status =="
  systemctl status signal-lattice-v19-loop.service --no-pager --lines=60 2>&1 || true
  echo
  echo "== V19 API journal =="
  journalctl -u signal-lattice-v19-api.service -n 120 --no-pager 2>&1 || true
  echo
  echo "== V19 loop journal =="
  journalctl -u signal-lattice-v19-loop.service -n 120 --no-pager 2>&1 || true
  echo
  echo "== Local endpoints =="
  curl -fsS --max-time 8 http://127.0.0.1:8787/health/live 2>&1 || true
  echo
  curl -fsS --max-time 8 http://127.0.0.1:8787/health/ready 2>&1 || true
  echo
  echo "== Public endpoint =="
  curl -fsS --max-time 12 https://signal-lattice.linzezhang.com/health/ready 2>&1 || true
  echo
  echo "== Latest operational state =="
  if [[ -f /var/lib/signal-lattice-v19/scan_state.json ]]; then
    cat /var/lib/signal-lattice-v19/scan_state.json
  else
    echo "scan_state.json missing"
  fi
} > "$OUT"
chmod 0640 "$OUT" 2>/dev/null || true
printf '%s\n' "$OUT"
