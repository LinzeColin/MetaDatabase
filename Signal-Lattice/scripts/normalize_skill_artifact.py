#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
from signal_lattice.skill_adapters import normalize_skill_artifact
from signal_lattice.util import atomic_write
p=argparse.ArgumentParser();p.add_argument('input',type=Path);p.add_argument('output',type=Path);p.add_argument('--skill-id')
a=p.parse_args();payload=json.loads(a.input.read_text());result=normalize_skill_artifact(payload,skill_id=a.skill_id)
atomic_write(a.output,json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True).encode());print(json.dumps({'state':'PASS','output':str(a.output),'skill_id':result['skill_id']},ensure_ascii=False,sort_keys=True))
