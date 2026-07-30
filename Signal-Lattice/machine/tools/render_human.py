#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
SEVEN=("00_我在哪.md","01_产品需求.md","02_系统架构.md","03_口径字典.md","04_操作流程.md","05_执行与验收.md","06_运维手册.md")
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',default='.');a=p.parse_args();root=Path(a.root)
 source=root/'machine/facts/human_documents.json';data=json.loads(source.read_text(encoding='utf-8'))
 docs=data.get('documents',{});missing=[n for n in SEVEN if not isinstance(docs.get(n),str) or not docs[n].strip()]
 extra=sorted(set(docs)-set(SEVEN))
 if missing or extra: raise SystemExit(f'HUMAN_DOCUMENT_SOURCE_INVALID:missing={missing}:extra={extra}')
 out=root/'文档';out.mkdir(parents=True,exist_ok=True)
 for name in SEVEN:(out/name).write_text(docs[name].rstrip()+'\n',encoding='utf-8')
 print(f'PASS: rendered {len(SEVEN)} human documents from {source.as_posix()}')
 return 0
if __name__=='__main__':raise SystemExit(main())
