#!/usr/bin/env bash
set -euo pipefail
umask 077
MATRIX="${1:?business-line evidence json required}"
OUT="${2:-/var/lib/signal-lattice/artifacts/status_closure.json}"
PYTHONPATH="${PYTHONPATH:-}:$(cd "$(dirname "$0")/.." && pwd)/src" python3 - "$MATRIX" "$OUT" <<'PY'
import hashlib,json,os,sys,tempfile
from pathlib import Path
from signal_lattice.status import reconcile
m=json.loads(Path(sys.argv[1]).read_text()); result=reconcile(m,target=True);result['schema_version']='1.0.0';result['status_tier']='TIER_0';result['last_step_enforced']=True
result['receipt_sha256']=hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
out=Path(sys.argv[2]);out.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix='.'+out.name+'.',dir=out.parent)
with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
os.chmod(tmp,0o600);os.replace(tmp,out)
print(json.dumps(result,ensure_ascii=False,sort_keys=True))
if result['state']!='PASS':raise SystemExit(2)
PY
