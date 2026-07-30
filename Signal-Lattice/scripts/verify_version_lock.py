#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,tomllib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from signal_lattice.constants import VERSION
VERSION_RE=re.compile(r'0\.0\.0\.1\.\d+')
CHECK_FILES=(
 'CANONICAL_STATE.json','00_READ_FIRST.md','ROADMAP.md','CODEX_LAST_MILE_PROMPT.txt','machine/facts/project.json','machine/facts/requirements.json',
 'machine/facts/task_dag.json','machine/facts/acceptance_contract.json','machine/facts/release_boundary.json',
 'config/default.json','openapi.yaml','events.yaml','web/index.html','文档/00_我在哪.md'
)
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));a=p.parse_args();root=a.root.resolve();find=[]
 py=tomllib.loads((root/'pyproject.toml').read_text());declared=py['project']['version']
 if declared!=VERSION:find.append(f'PYPROJECT_VERSION_DRIFT:{declared}:{VERSION}')
 for rel in CHECK_FILES:
  path=root/rel
  if not path.is_file():find.append('MISSING_VERSION_FILE:'+rel);continue
  values=sorted(set(VERSION_RE.findall(path.read_text())))
  if values and values!=[VERSION]:find.append(f'VERSION_DRIFT:{rel}:{values}')
 state=json.loads((root/'CANONICAL_STATE.json').read_text())
 for key in ('product_version','taskpack_version'):
  if state.get(key)!=VERSION:find.append(f'CANONICAL_VERSION_DRIFT:{key}')
 project=json.loads((root/'machine/facts/project.json').read_text())
 for key in ('product_version','taskpack_version'):
  if project.get(key)!=VERSION:find.append(f'PROJECT_VERSION_DRIFT:{key}')
 result={'state':'PASS' if not find else 'FAIL','version':VERSION,'findings':find}
 print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0 if not find else 2
if __name__=='__main__':raise SystemExit(main())
