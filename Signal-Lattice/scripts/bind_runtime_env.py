#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,os,re
from pathlib import Path
FORBIDDEN=('OPENAI_API_KEY','ANTHROPIC_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY','SIGNAL_LATTICE_LIVE_ACTION=1')
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--dest',type=Path,required=True);p.add_argument('--apply',action='store_true');a=p.parse_args()
 if not a.source.is_file():print(json.dumps({'state':'BLOCKED','reason':'RUNTIME_ENV_SOURCE_MISSING'}));return 2
 text=a.source.read_text();bad=[x for x in FORBIDDEN if x in text]
 if bad:print(json.dumps({'state':'BLOCKED','reason':'FORBIDDEN_RUNTIME_CONFIGURATION','items':bad}));return 2
 required={'SIGNAL_LATTICE_ENV','SIGNAL_LATTICE_HOST','SIGNAL_LATTICE_STATE_DIR','SIGNAL_LATTICE_LIVE_ACTION'}
 keys={m.group(1) for m in re.finditer(r'^([A-Z][A-Z0-9_]*)=',text,re.M)}
 missing=sorted(required-keys)
 if missing:print(json.dumps({'state':'BLOCKED','reason':'RUNTIME_ENV_KEYS_MISSING','missing':missing}));return 2
 if a.apply:
  a.dest.parent.mkdir(parents=True,exist_ok=True);tmp=a.dest.with_suffix('.tmp');tmp.write_text(text);tmp.chmod(0o600);os.replace(tmp,a.dest)
 print(json.dumps({'state':'PASS','applied':a.apply,'dest':a.dest.as_posix(),'secret_values_emitted':False}));return 0
if __name__=='__main__':raise SystemExit(main())
