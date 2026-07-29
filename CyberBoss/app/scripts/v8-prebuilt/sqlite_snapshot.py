#!/usr/bin/env python3
from __future__ import annotations
import argparse, pathlib, sqlite3, tempfile, os
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);a=p.parse_args()
src=pathlib.Path(a.source).resolve();out=pathlib.Path(a.output).resolve();out.parent.mkdir(parents=True,exist_ok=True)
fd,tmp=tempfile.mkstemp(prefix='.snapshot.',dir=str(out.parent));os.close(fd)
try:
    with sqlite3.connect(f'file:{src}?mode=ro',uri=True,timeout=10) as source, sqlite3.connect(tmp) as target:
        source.backup(target,pages=256)
        if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('SNAPSHOT_INTEGRITY_FAILED')
    os.chmod(tmp,0o600);os.replace(tmp,out)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
