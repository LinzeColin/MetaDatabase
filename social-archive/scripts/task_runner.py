from __future__ import annotations
import argparse,json,subprocess,time
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
def load_tasks(): return yaml.safe_load((ROOT/'machine/task_dag.yaml').read_text(encoding='utf-8'))['tasks']
def run_command(command:str)->dict:
    argv=['bash','-lc',command];started=time.time();p=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,check=False)
    return {'argv':argv,'exit_code':p.returncode,'duration_seconds':round(time.time()-started,3),'stdout':p.stdout[-12000:],'stderr':p.stderr[-12000:]}
def main()->int:
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='action',required=True)
    for name in ('run-stage','gate'):
        s=sub.add_parser(name);s.add_argument('stage');s.add_argument('--focused',action='store_true');s.add_argument('--full',action='store_true')
    args=ap.parse_args();tasks=load_tasks();selected=[t for t in tasks if t['stage']==args.stage and ((args.action=='gate' and t['id'].endswith('GATE')) or (args.action=='run-stage' and not t['id'].endswith('GATE')))]
    all_ok=True
    for t in selected:
        evidence=ROOT/'evidence'/t['id'];evidence.mkdir(parents=True,exist_ok=True);results=[]
        for command in t['commands']:
            result=run_command(command.replace('<TASKPACK>','..'));results.append(result)
            if result['exit_code']!=0: all_ok=False;break
        payload={'task_id':t['id'],'status':'PASS' if results and all(r['exit_code']==0 for r in results) else 'FAIL','results':results}
        (evidence/'RESULT.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');(evidence/'COMMAND_LOG.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(f"{t['id']}: {payload['status']}")
        if not all_ok: break
    return 0 if all_ok else 1
if __name__=='__main__':raise SystemExit(main())
