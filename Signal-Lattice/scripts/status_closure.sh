#!/usr/bin/env bash
set -euo pipefail
umask 077
MATRIX="${1:?business-line evidence json required}"
OUT="${2:-/var/lib/signal-lattice/artifacts/status_closure.json}"
PYTHONPATH="${PYTHONPATH:-}:$(cd "$(dirname "$0")/.." && pwd)/src" python3 - "$MATRIX" "$OUT" <<'PY'
import json,sys
from pathlib import Path
from signal_lattice.status import reconcile
m=json.loads(Path(sys.argv[1]).read_text()); result=reconcile(m,target=True);result['status_tier']='TIER_0';result['last_step_enforced']=True
out=Path(sys.argv[2]);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True));out.chmod(0o600)
if result['state']!='PASS':raise SystemExit(2)
PY
