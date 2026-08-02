from __future__ import annotations
import hashlib,json,subprocess
from pathlib import Path

def cmd(*args):
    p=subprocess.run(args,text=True,capture_output=True,check=False);return p.stdout.strip() if p.returncode==0 else None
def main()->int:
    root=Path('.').resolve();doc={'repository':cmd('git','config','--get','remote.origin.url'),'target_project':'social-archive','expected_outcome':'Social Archive v0.0.0.6 frozen acceptance contract','commit':cmd('git','rev-parse','HEAD'),'dirty':cmd('git','status','--porcelain'),'taskpack_digest':(root/'machine/TASKPACK_DIGEST').read_text().strip() if (root/'machine/TASKPACK_DIGEST').exists() else None,'acceptance_contract':'machine/acceptance_contract.json','task_dag':'machine/task_dag.yaml','traceability':'machine/traceability.json'};out=root/'evidence/verifier-input.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(out);return 0
if __name__=='__main__':raise SystemExit(main())
