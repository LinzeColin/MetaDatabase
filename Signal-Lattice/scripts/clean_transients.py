#!/usr/bin/env python3
from __future__ import annotations
import argparse,shutil
from pathlib import Path
DIRS={'.pytest_cache','__pycache__','.mypy_cache','.ruff_cache','build','dist','.venv','venv'}
SUFFIXES=('.pyc','.pyo')
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('.'));a=p.parse_args();root=a.root.resolve();removed=[]
 for path in sorted(root.rglob('*'),key=lambda x:len(x.parts),reverse=True):
  if not path.exists() or path.is_symlink():continue
  if path.is_dir() and (path.name in DIRS or path.name.endswith(('.egg-info','.dist-info'))):shutil.rmtree(path);removed.append(path.relative_to(root).as_posix())
  elif path.is_file() and path.suffix in SUFFIXES:path.unlink();removed.append(path.relative_to(root).as_posix())
 print({'state':'PASS','removed_count':len(removed),'removed':removed[:50]});return 0
if __name__=='__main__':raise SystemExit(main())
