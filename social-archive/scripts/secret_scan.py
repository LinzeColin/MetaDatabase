from __future__ import annotations
import json,re,sys
from pathlib import Path
root=Path(sys.argv[1] if len(sys.argv)>1 else '.').resolve()
SKIP={'.git','.venv','__pycache__','.pytest_cache','node_modules','runtime'}
# High-confidence values only. Variable names, examples and scanner source are not findings.
patterns={
 'private_key':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
 'github_pat':re.compile(r'\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b'),
 'aws_style_access_key':re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
 'bearer_token':re.compile(r'Authorization\s*[:=]\s*["\']?Bearer\s+[A-Za-z0-9._~+/-]{20,}',re.I),
}
hits=[]
for p in root.rglob('*'):
 if not p.is_file() or any(part in SKIP for part in p.parts) or p.name=='secret_scan.py':continue
 try:text=p.read_text(encoding='utf-8')
 except (UnicodeDecodeError,OSError):continue
 for name,pat in patterns.items():
  for match in pat.finditer(text):hits.append({'path':str(p.relative_to(root)),'kind':name,'offset':match.start()})
print(json.dumps({'status':'PASS' if not hits else 'FAIL','hits':hits},ensure_ascii=False,indent=2))
raise SystemExit(0 if not hits else 1)
