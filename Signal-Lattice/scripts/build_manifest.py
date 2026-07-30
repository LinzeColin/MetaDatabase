#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,os
from pathlib import Path
EXCLUDE={'MANIFEST.json','SUBJECT_LOCK.json','CANONICAL_STATE.json','evidence/skill_router/pass_c.json'}
EXCLUDED_PREFIXES=('evidence/formal_review/','evidence/owner_gate/')
EMBEDDED_SOURCE_ROOTS=('Stock_Skill',)
FORBIDDEN_PARTS={'.git','.pytest_cache','__pycache__','build','dist','.mypy_cache','.ruff_cache','.venv','node_modules'}
ALLOWED_ROOT_FILES={
 '00_READ_FIRST.md','CANONICAL_STATE.json','CODEX_LAST_MILE_PROMPT.txt','MEMORY_RECONCILIATION.md',
 'PURSUING_GOAL.txt','README.md','ROADMAP.md','SUBJECT_LOCK.json','MANIFEST.json',
 'events.yaml','openapi.yaml','pyproject.toml'
}
def sha(p:Path):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
 rows=[]
 for p in sorted(a.root.rglob('*')):
  if p.is_symlink():raise SystemExit(f'SYMLINK_FORBIDDEN:{p}')
  if not p.is_file():continue
  rel=p.relative_to(a.root).as_posix()
  if '/' not in rel and rel not in ALLOWED_ROOT_FILES:raise SystemExit(f'UNEXPECTED_ROOT_FILE:{rel}')
  if rel.split('/',1)[0] in EMBEDDED_SOURCE_ROOTS or rel in EXCLUDE or any(rel.startswith(prefix) for prefix in EXCLUDED_PREFIXES) or any(x in p.parts for x in FORBIDDEN_PARTS) or rel.endswith(('.pyc','.zip','.whl','.egg-info')):continue
  rows.append({'path':rel,'size':p.stat().st_size,'sha256':sha(p)})
 payload={'schema_version':'1.0.0','candidate_version':'0.0.0.1.39','manifest_payload_file_count':len(rows),'manifest_payload_bytes':sum(x['size'] for x in rows),'files':rows}
 payload['payload_sha256']=hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 a.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True))
if __name__=='__main__':main()
