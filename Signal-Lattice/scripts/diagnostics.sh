#!/usr/bin/env bash
set -euo pipefail
OUT="${1:-/tmp/signal-lattice-diagnostics.txt}"
{
 echo '== version =='; /opt/signal-lattice/current/venv/bin/signal-lattice --version || true
 echo '== units =='; systemctl --no-pager --full status 'signal-lattice*' || true
 echo '== journal =='; journalctl -u 'signal-lattice*' -n 300 --no-pager || true
 echo '== disk =='; df -h /opt/signal-lattice /var/lib/signal-lattice || true
 echo '== sqlite =='; sqlite3 /var/lib/signal-lattice/runtime.db 'PRAGMA integrity_check;' || true
 echo '== status snapshot =='; cat /var/lib/signal-lattice/artifacts/status_snapshot.json || true
} > "$OUT" 2>&1
chmod 0600 "$OUT"
