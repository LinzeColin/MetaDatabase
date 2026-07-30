from __future__ import annotations
import json, os, sqlite3, tempfile
from pathlib import Path
from .util import sha256_file, atomic_write

def backup_sqlite(source:Path,destination:Path)->dict:
    destination.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.backup.',dir=destination.parent); os.close(fd)
    try:
        src=sqlite3.connect(source); dst=sqlite3.connect(tmp)
        try: src.backup(dst)
        finally: src.close(); dst.close()
        check=sqlite3.connect(tmp)
        try:
            result=check.execute('PRAGMA integrity_check').fetchone()[0]
        finally: check.close()
        if result!='ok':raise RuntimeError('SQLITE_INTEGRITY_FAILED')
        os.chmod(tmp,0o600); os.replace(tmp,destination)
    finally:
        try:os.unlink(tmp)
        except FileNotFoundError:pass
    receipt={'state':'PASS','path':str(destination),'size':destination.stat().st_size,'sha256':sha256_file(destination)}
    atomic_write(destination.with_suffix(destination.suffix+'.receipt.json'),json.dumps(receipt,sort_keys=True,indent=2).encode())
    return receipt

def restore_sqlite(backup:Path,destination:Path,expected_sha256:str)->None:
    if sha256_file(backup)!=expected_sha256:raise RuntimeError('BACKUP_DIGEST_MISMATCH')
    check=sqlite3.connect(backup)
    try:
        if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('BACKUP_INTEGRITY_FAILED')
    finally:check.close()
    destination.parent.mkdir(parents=True,exist_ok=True)
    for suffix in ('-wal','-shm'):
        try:Path(str(destination)+suffix).unlink()
        except FileNotFoundError:pass
    data=backup.read_bytes(); atomic_write(destination,data)
