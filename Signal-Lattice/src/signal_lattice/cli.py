from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from .config import Settings
from .constants import VERSION
from .db import RuntimeDB
from .api import serve
from .worker import run_once
from .status import default_matrix,reconcile
from .backup import backup_sqlite,restore_sqlite

def root()->Path:return Path(__file__).resolve().parents[2]
def db(settings:Settings)->RuntimeDB:return RuntimeDB(settings.state_dir/'runtime.db',Path(__file__).with_name('schema.sql'))
def main(argv:list[str]|None=None)->int:
 p=argparse.ArgumentParser(prog='signal-lattice');p.add_argument('--version',action='version',version=VERSION)
 sub=p.add_subparsers(dest='cmd',required=True)
 sub.add_parser('serve');sub.add_parser('worker-once');sub.add_parser('verify-runtime')
 b=sub.add_parser('backup');b.add_argument('output',type=Path)
 r=sub.add_parser('restore');r.add_argument('backup',type=Path);r.add_argument('sha256')
 s=sub.add_parser('status-fixture');s.add_argument('output',type=Path)
 a=p.parse_args(argv);settings=Settings.from_env(root()); runtime=db(settings)
 if a.cmd=='serve':serve(settings,runtime);return 0
 if a.cmd=='worker-once':return 0 if run_once(runtime) else 3
 if a.cmd=='verify-runtime':
  forbidden=[k for k in os.environ if k.upper() in {'OPENAI_API_KEY','ANTHROPIC_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY'}]
  payload={'state':'PASS' if not forbidden else 'FAIL','agent_dependency':0,'model_mode':'DISABLED','token_budget':0,'forbidden_env':forbidden}
  print(json.dumps(payload,ensure_ascii=False));return 0 if not forbidden else 2
 if a.cmd=='backup':print(json.dumps(backup_sqlite(settings.state_dir/'runtime.db',a.output)));return 0
 if a.cmd=='restore':restore_sqlite(a.backup,settings.state_dir/'runtime.db',a.sha256);return 0
 if a.cmd=='status-fixture':a.output.write_text(json.dumps(default_matrix(),ensure_ascii=False,indent=2));return 0
 return 2
if __name__=='__main__':raise SystemExit(main())
