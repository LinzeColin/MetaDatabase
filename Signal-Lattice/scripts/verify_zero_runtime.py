#!/usr/bin/env python3
from __future__ import annotations
import argparse,ast,json,re,tomllib
from pathlib import Path
FORBIDDEN_IMPORTS={'openai','anthropic','google.generativeai','langchain','autogen','crewai','llama_index'}
FORBIDDEN_WORDS=('api.openai.com','api.anthropic.com','generativelanguage.googleapis.com')
FORBIDDEN_ENV=('OPENAI_API_KEY','ANTHROPIC_API_KEY','GOOGLE_API_KEY','GEMINI_API_KEY')
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));a=p.parse_args();root=a.root.resolve();find=[]
 py=tomllib.loads((root/'pyproject.toml').read_text())
 if py.get('project',{}).get('dependencies') not in ([],None):find.append('RUNTIME_DEPENDENCIES_NOT_EMPTY')
 for path in (root/'src').rglob('*.py'):
  tree=ast.parse(path.read_text())
  for n in ast.walk(tree):
   if isinstance(n,ast.Import):names=[x.name for x in n.names]
   elif isinstance(n,ast.ImportFrom):names=[n.module or '']
   else:continue
   for name in names:
    if any(name==x or name.startswith(x+'.') for x in FORBIDDEN_IMPORTS):find.append('FORBIDDEN_IMPORT:'+path.as_posix()+':'+name)
 for path in list((root/'src').rglob('*'))+list((root/'deploy').rglob('*'))+list((root/'config').rglob('*')):
  if not path.is_file() or path.stat().st_size>1_000_000:continue
  try:text=path.read_text()
  except UnicodeDecodeError:continue
  for word in FORBIDDEN_WORDS:
   if word in text:find.append('MODEL_EGRESS:'+path.as_posix())
  if path.name.endswith('.service') and re.search(r'(?i)(codex|claude|openai|anthropic|agent-loop|mcp)',text):find.append('AGENT_SERVICE:'+path.as_posix())
 env=Path('/proc/self/environ').read_bytes().decode(errors='ignore') if Path('/proc/self/environ').is_file() else ''
 for key in FORBIDDEN_ENV:
  if key+'=' in env:find.append('FORBIDDEN_RUNTIME_ENV:'+key)
 result={'state':'PASS' if not find else 'FAIL','agent_dependency':0,'model_mode':'DISABLED','token_budget':0,'findings':sorted(set(find))}
 print(json.dumps(result,ensure_ascii=False,sort_keys=True));return 0 if not find else 2
if __name__=='__main__':raise SystemExit(main())
