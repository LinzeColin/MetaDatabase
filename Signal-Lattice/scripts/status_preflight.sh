#!/usr/bin/env bash
set -euo pipefail
umask 077
MODE="${1:-implementation}"
OUT="${2:-/tmp/signal-lattice-status-preflight.json}"
STATUS_SNAPSHOT="${SIGNAL_LATTICE_STATUS_SNAPSHOT:-}"
python3 - "$MODE" "$OUT" "$STATUS_SNAPSHOT" <<'PY'
import json,sys
from pathlib import Path
mode,out,snap=sys.argv[1],Path(sys.argv[2]),sys.argv[3]
result={'schema_version':'1.0.0','mode':mode,'state':'DEGRADED_CONTINUE_READ_ONLY','hard_blockers':[],'warnings':[],'status_tier':'TIER_0','first_step_enforced':True}
if not snap or not Path(snap).is_file():result['warnings'].append('STATUS_SNAPSHOT_NOT_BOUND')
else:
 try:
  d=json.loads(Path(snap).read_text());
  projects=json.dumps(d,ensure_ascii=False)
  if 'signal-lattice' not in projects:result['hard_blockers'].append('PROJECT_NOT_REGISTERED')
 except Exception:result['hard_blockers'].append('STATUS_SNAPSHOT_INVALID')
if result['hard_blockers']:result['state']='BLOCKED'
out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True));out.chmod(0o600)
if result['state']=='BLOCKED':raise SystemExit(2)
PY
