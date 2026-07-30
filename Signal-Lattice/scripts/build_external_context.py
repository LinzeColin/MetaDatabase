#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json, re, subprocess
from pathlib import Path
from typing import Iterable

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def git(repo:Path,*a:str)->str:return subprocess.run(['git',*a],cwd=repo,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout.strip()
def relevant(p:Path)->bool:
 n=p.name.lower(); parts='/'.join(p.parts).lower()
 return n in {'readme.md','agents.md','contributing.md','pyproject.toml','package.json','docker-compose.yml','compose.yaml','openapi.yaml','openapi.json'} or any(k in n for k in ('schema','api','contract','adapter','deploy','status','config')) or '/docs/' in '/'+parts+'/'
def capture(root:Path)->dict:
 files=[]
 for p in root.rglob('*'):
  if not p.is_file() or '.git' in p.parts or p.stat().st_size>2_000_000:continue
  if relevant(p):files.append({'path':p.relative_to(root).as_posix(),'size':p.stat().st_size,'sha256':sha(p)})
 return {'root':root.name,'files':sorted(files,key=lambda x:x['path']),'file_count':len(files)}
def find_top(repo:Path,names:Iterable[str])->Path|None:
 wanted={x.lower().replace('-','').replace('_','') for x in names}
 for p in repo.iterdir():
  if p.is_dir() and p.name.lower().replace('-','').replace('_','') in wanted:return p
 return None
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--meta',type=Path,required=True);ap.add_argument('--status',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 systems={
  'PFI':['PFI'],'EEI':['EEI'],'QBE':['QBE'],'QBVS':['QBVS'],'QVE':['QVE'],'Serenity':['Serenity-Alipay','Serenity'],
  'Alpha':['Alpha'],'Status':['status']
 }
 result={'schema_version':'1.0.0','meta_commit':git(a.meta,'rev-parse','HEAD'),'status_commit':git(a.status,'rev-parse','HEAD'),'systems':{}}
 for sid,names in systems.items():
  if sid=='Status':root=find_top(a.status,['status']) or a.status
  else:root=find_top(a.meta,names)
  result['systems'][sid]={'state':'FOUND','capture':capture(root)} if root else {'state':'NOT_FOUND','capture':None,'default':'ADAPTER_DISABLED_FAIL_CLOSED'}
 result['rules']={'no_interface_guessing':True,'context_capture_read_only':True,'schema_major_negotiation_required':True,'external_system_may_modify_champion':False,'external_system_may_modify_acceptance':False,'alpha_auto_execute':False}
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))
if __name__=='__main__':main()
