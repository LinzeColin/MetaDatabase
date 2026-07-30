#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys
from pathlib import Path
SEVEN=("00_我在哪.md","01_产品需求.md","02_系统架构.md","03_口径字典.md","04_操作流程.md","05_执行与验收.md","06_运维手册.md")
def discover(root:Path):return sorted({p.parents[2] for p in root.rglob('machine/tools/render_human.py') if (p.parents[2]/'文档').is_dir()})
def check(proj:Path,fail:list[str]):
 for n in SEVEN:
  if not (proj/'文档'/n).is_file():fail.append(f'[{proj.name}] MISSING_DOC:{n}')
 for rel in ('machine/facts','machine/tools'):
  if not (proj/rel).is_dir():fail.append(f'[{proj.name}] MISSING:{rel}')
 before={n:(proj/'文档'/n).read_bytes() if (proj/'文档'/n).is_file() else None for n in SEVEN}
 r=subprocess.run([sys.executable,'machine/tools/render_human.py','--root','.'],cwd=proj,capture_output=True,text=True)
 if r.returncode:fail.append(f'[{proj.name}] RENDER_FAILED:{r.stderr[-200:]}')
 for n in SEVEN:
  now=(proj/'文档'/n).read_bytes() if (proj/'文档'/n).is_file() else None
  if before[n]!=now:fail.append(f'[{proj.name}] RENDER_DRIFT:{n}')
 for tool,args in [('check_doc_budget.py',['--docs','文档']),('check_blocker_stop.py',['--machine','machine'])]:
  r=subprocess.run([sys.executable,'machine/tools/'+tool,*args],cwd=proj,capture_output=True,text=True)
  if r.returncode:fail.append(f'[{proj.name}] {tool}:{(r.stdout+r.stderr)[-200:]}')
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--projects',nargs='*');p.add_argument('--require-projects',action='store_true');a=p.parse_args();root=Path(a.root).resolve()
 projects=[root/x for x in a.projects] if a.projects else discover(root)
 if not projects:return 1 if a.require_projects else 0
 fail=[]
 for proj in projects:
  if not proj.is_dir():fail.append(f'[{proj.name}] PROJECT_MISSING')
  else:check(proj,fail)
 if fail:
  print('FAIL —— '+str(len(fail))+' 项');[print('  ✗ '+x) for x in fail];return 1
 print('PASS —— 全部项目双平面合规');return 0
if __name__=='__main__':raise SystemExit(main())
