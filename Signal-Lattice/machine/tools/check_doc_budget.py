#!/usr/bin/env python3
from __future__ import annotations
import argparse,re
from pathlib import Path
BUDGET={"00_我在哪.md":120,"01_产品需求.md":200,"02_系统架构.md":200,"03_口径字典.md":1000000,"04_操作流程.md":150,"05_执行与验收.md":140,"06_运维手册.md":220}
REQUIRED_ZH=re.compile(r'[\u4e00-\u9fff]')
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--docs',default='文档');a=p.parse_args();docs=Path(a.docs);fail=[]
 for name,limit in BUDGET.items():
  path=docs/name
  if not path.is_file():fail.append(f'缺失:{name}');continue
  text=path.read_text(encoding='utf-8');lines=len(text.splitlines())
  if lines>limit:fail.append(f'超出行数:{name}:{lines}>{limit}')
  if not REQUIRED_ZH.search(text):fail.append(f'缺少中文正文:{name}')
  if 'machine/tools/render_human.py' not in text.splitlines()[0]:fail.append(f'缺少生成声明:{name}')
 if fail:
  print('FAIL —— '+str(len(fail))+' 项');[print('  ✗ '+x) for x in fail];return 1
 print('PASS —— 七文件体积、中文与生成声明通过');return 0
if __name__=='__main__':raise SystemExit(main())
