from __future__ import annotations
import argparse,json,subprocess
from pathlib import Path
import httpx
def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--base-url');ap.add_argument('--command',nargs='+');ap.add_argument('--output',required=True);args=ap.parse_args()
    result={'name':args.name,'status':'BLOCKED_ENVIRONMENT','http':None,'help':None}
    if args.base_url:
        try:
            r=httpx.get(args.base_url.rstrip('/')+'/openapi.json',timeout=5);result['http']={'status_code':r.status_code,'openapi':r.json() if r.status_code==200 else None};result['status']='PASS' if r.status_code==200 else 'DEGRADED'
        except Exception as exc: result['http']={'error_type':exc.__class__.__name__}
    if args.command:
        p=subprocess.run(args.command+['--help'],text=True,capture_output=True,timeout=30,check=False);result['help']={'argv':args.command+['--help'],'exit_code':p.returncode,'stdout':p.stdout[-8000:],'stderr':p.stderr[-2000:]};result['status']='PASS' if p.returncode==0 else 'DEGRADED'
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps({'status':result['status'],'output':args.output},ensure_ascii=False));return 0 if result['status']=='PASS' else 3
if __name__=='__main__':raise SystemExit(main())
