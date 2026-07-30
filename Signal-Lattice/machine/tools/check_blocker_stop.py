#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from collections import defaultdict
from pathlib import Path
AUDIT={'audit','review','recheck','reaudit','replay'}
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--machine',default='machine');a=p.parse_args();m=Path(a.machine)
 bp=m/'facts/blockers.json';blockers=json.loads(bp.read_text()) if bp.is_file() else []
 runs=[]
 for f in sorted((m/'runs').glob('*.json')) if (m/'runs').is_dir() else []:
  try:d=json.loads(f.read_text());runs.extend(d if isinstance(d,list) else [d])
  except Exception:continue
 audits=defaultdict(int)
 for r in runs:
  if str(r.get('action','')).lower() in AUDIT:audits[str(r.get('blocker_id',''))]+=1
 body=Path('文档/00_我在哪.md').read_text(encoding='utf-8') if Path('文档/00_我在哪.md').is_file() else ''
 fail=[]
 for b in blockers:
  bid=str(b.get('id',''))
  if b.get('owner_only') and audits[bid]>1:fail.append(f'{bid}:OWNER_BLOCKER_REAUDITED')
  if b.get('owner_only') and bid not in body:fail.append(f'{bid}:OWNER_BLOCKER_NOT_SURFACED')
 if fail:
  print('FAIL —— '+str(len(fail))+' 项');[print('  ✗ '+x) for x in fail];return 1
 print(f'PASS —— {len(blockers)} 个阻塞，无重复 Owner 重审');return 0
if __name__=='__main__':raise SystemExit(main())
