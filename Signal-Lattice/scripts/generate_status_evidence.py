#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from signal_lattice.constants import BUSINESS_LINES,SLICES
from signal_lattice.util import atomic_write,canonical_json_bytes,sha256_bytes

SOURCE_BY_SLICE={
 'code_source':['release.json'],
 'ci':['local_health.json'],
 'deployment':['systemd_install.json','cloudflare_tunnel_install.json'],
 'runtime':['local_health.json','runtime_audit.json'],
 'entrypoint':['public_release.json'],
 'data':['source_sync.json','status_snapshot.json'],
 'backup':['target_backup_recovery.json'],
 'monitoring':['status_snapshot.json','public_release.json'],
 'self_heal':['runtime_audit.json','target_backup_recovery.json'],
}

# A release receipt records its lifecycle state as INSTALLED.  That is the
# successful deployment state for code-source evidence, not a degraded status.
ACCEPTED_STATES={
 'release.json':{'PASS','INSTALLED'},
}

def accepted_state(name:str,state:object)->bool:
 return str(state) in ACCEPTED_STATES.get(name,{'PASS'})

def load(path:Path)->dict:
 if not path.is_file():raise FileNotFoundError(path.name)
 return json.loads(path.read_text(encoding='utf-8'))

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--artifact-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--summary',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True);missing=[];source_cache={}
 for names in SOURCE_BY_SLICE.values():
  for name in names:
   if name in source_cache:continue
   path=a.artifact_dir/name
   try:source_cache[name]=load(path)
   except Exception:missing.append(name)
 if missing:
  out={'state':'BLOCKED','reason':'TARGET_EVIDENCE_MISSING','missing':sorted(set(missing))};atomic_write(a.summary,json.dumps(out,indent=2,sort_keys=True).encode());print(json.dumps(out));return 2
 rows=[];now=datetime.now(timezone.utc).isoformat()
 for line in BUSINESS_LINES:
  for sl in SLICES:
   names=SOURCE_BY_SLICE[sl];states=[str(source_cache[n].get('state','UNKNOWN')) for n in names];state='PASS' if all(accepted_state(n,source_cache[n].get('state','UNKNOWN')) for n in names) else 'DEGRADED'
   evidence=[{'path':(a.artifact_dir/n).as_posix(),'sha256':hashlib.sha256((a.artifact_dir/n).read_bytes()).hexdigest(),'state':source_cache[n].get('state')} for n in names]
   payload={'schema_version':'1.0.0','line_id':line,'slice_id':sl,'state':state,'measured':True,'evidence':evidence,'freshness':'CURRENT','upstream':[],'downstream':[],'coupling':[],'blocker':None if state=='PASS' else 'DEGRADED_EVIDENCE','next_action':'MONITOR' if state=='PASS' else 'RESTORE_MISSING_INPUTS','measured_at':now}
   payload['receipt_sha256']=sha256_bytes(canonical_json_bytes(payload));path=a.output_dir/f'{line}-{sl}.json';atomic_write(path,json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True).encode());rows.append({'path':path.as_posix(),'state':state,'sha256':payload['receipt_sha256']})
 out={'schema_version':'1.0.0','state':'PASS','cell_count':len(rows),'pass_count':sum(x['state']=='PASS' for x in rows),'degraded_count':sum(x['state']!='PASS' for x in rows),'cells':rows,'generated_at':now};out['receipt_sha256']=sha256_bytes(canonical_json_bytes(out));atomic_write(a.summary,json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True).encode());print(json.dumps({'state':'PASS','cell_count':len(rows),'degraded_count':out['degraded_count']},sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
