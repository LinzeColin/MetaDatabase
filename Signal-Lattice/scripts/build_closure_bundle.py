#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--evidence-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();rows=[]
 for path in sorted(a.evidence_dir.rglob('*.json')):
  rows.append({'path':path.relative_to(a.evidence_dir).as_posix(),'size':path.stat().st_size,'sha256':sha(path)})
 payload={'schema_version':'1.0.0','state':'PASS' if rows else 'BLOCKED','files':rows,'file_count':len(rows)};a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps({'state':payload['state'],'file_count':len(rows)}));return 0 if rows else 2
if __name__=='__main__':raise SystemExit(main())
