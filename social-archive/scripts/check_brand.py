from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PATTERNS=[re.compile(r'xhs[-_ ]?douyin[-_ ]?2[-_ ]?notion',re.I),re.compile(r'(?<![A-Za-z0-9])x2n(?![A-Za-z0-9])',re.I)]
ALLOW_PREFIXES=(Path('docs/migration'),)
ALLOW_FILES={Path('CHANGELOG.md'),Path('tests/focused/test_brand_migration.py'),Path('scripts/check_brand.py')}
SKIP_PARTS={'.git','.venv','runtime','__pycache__','.pytest_cache','node_modules'}
hits=[]
for p in ROOT.rglob('*'):
    if not p.is_file() or any(part in SKIP_PARTS for part in p.parts):continue
    rel=p.relative_to(ROOT)
    allowed=rel in ALLOW_FILES or any(rel==prefix or prefix in rel.parents for prefix in ALLOW_PREFIXES)
    if allowed:continue
    try:text=p.read_text(encoding='utf-8')
    except (UnicodeDecodeError,OSError):continue
    for n,line in enumerate(text.splitlines(),1):
        if any(pattern.search(line) for pattern in PATTERNS):hits.append({'path':str(rel),'line':n,'text':line[:240]})
print(json.dumps({'status':'PASS' if not hits else 'FAIL','hits':hits},ensure_ascii=False,indent=2))
raise SystemExit(0 if not hits else 1)
