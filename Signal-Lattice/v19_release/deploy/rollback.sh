#!/usr/bin/env bash
set -euo pipefail
PREVIOUS="/var/lib/signal-lattice-v19/deployment/previous_state.json"

systemctl disable --now \
  signal-lattice-v19-cloudflared.service \
  signal-lattice-v19-loop.service \
  signal-lattice-v19-api.service 2>/dev/null || true

python3 - "$PREVIOUS" <<'PY'
import json
import subprocess
import sys
from pathlib import Path

path = Path(sys.argv[1])
state = json.loads(path.read_text()) if path.is_file() else {}
units = ("signal-lattice-api.service", "signal-lattice-cycle.timer", "signal-lattice-cloudflared.service")
for unit in units:
    row = state.get(unit, {})
    if row.get("enabled") in {"enabled", "enabled-runtime", "static"}:
        subprocess.run(["systemctl", "enable", unit], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for unit in units:
    if state.get(unit, {}).get("active") == "active":
        subprocess.run(["systemctl", "start", unit], check=False)
PY

systemctl daemon-reload
printf '{"state":"ROLLED_BACK","restored_from":"%s","time":"%s"}\n' "$PREVIOUS" "$(date -Is)" > /var/lib/signal-lattice-v19/deployment/ROLLBACK_RESULT.json
cat /var/lib/signal-lattice-v19/deployment/ROLLBACK_RESULT.json
