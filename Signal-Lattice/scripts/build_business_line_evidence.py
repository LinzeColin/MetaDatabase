#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from signal_lattice.status import default_matrix,reconcile
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--evidence-root',type=Path);p.add_argument('--target',action='store_true');a=p.parse_args();m=default_matrix('TARGET_ENVIRONMENT' if a.target else 'PREBUILD_CONTRACT_FIXTURE_NOT_LIVE_STATUS_PROOF')
 if a.target:
  if not a.evidence_root or not a.evidence_root.is_dir():print(json.dumps({'state':'BLOCKED','reason':'EVIDENCE_ROOT_REQUIRED'}));return 2
  for line in m['lines']:
   for cell in line['cells']:
    pth=a.evidence_root/f"{line['line_id']}-{cell['slice_id']}.json"
    if pth.is_file():
     try:
      evidence=json.loads(pth.read_text())
      observed_state=str(evidence.get('state','UNKNOWN'))
     except Exception:
      observed_state='UNKNOWN'
     cell.update({'state':observed_state,'measured':True,'evidence_ref':pth.as_posix(),'freshness':'CURRENT','blocker':None if observed_state=='PASS' else 'DEGRADED_EVIDENCE','next_action':'MONITOR' if observed_state=='PASS' else 'RESTORE_MISSING_INPUTS'})
 result=reconcile(m,target=a.target);m['reconciliation']=result;a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(m,ensure_ascii=False,indent=2,sort_keys=True)+'\n');print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0 if (not a.target or result['state']=='PASS') else 2
if __name__=='__main__':raise SystemExit(main())
