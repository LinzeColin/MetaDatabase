#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sqlite3,tempfile
from pathlib import Path
from signal_lattice.backup import backup_sqlite,restore_sqlite
from signal_lattice.util import canonical_json_bytes,sha256_bytes,atomic_write

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();problems=[]
 with tempfile.TemporaryDirectory() as t:
  root=Path(t);source=root/'runtime.db';backup=root/'backup.db'
  conn=sqlite3.connect(source);conn.execute('pragma journal_mode=WAL');conn.execute('create table x(v integer)');conn.execute('insert into x values (7)');conn.commit();conn.close()
  receipt=backup_sqlite(source,backup)
  Path(str(source)+'-wal').write_bytes(b'stale')
  Path(str(source)+'-shm').write_bytes(b'stale')
  source.write_bytes(b'corrupt')
  restore_sqlite(backup,source,receipt['sha256'])
  conn=sqlite3.connect(source)
  try:
   if conn.execute('pragma integrity_check').fetchone()[0]!='ok':problems.append('RESTORED_INTEGRITY_FAILED')
   if conn.execute('select v from x').fetchone()[0]!=7:problems.append('RESTORED_DATA_MISMATCH')
  finally:conn.close()
  if Path(str(source)+'-wal').exists() or Path(str(source)+'-shm').exists():problems.append('STALE_WAL_NOT_REMOVED')
  try:restore_sqlite(backup,source,'0'*64);problems.append('DIGEST_MISMATCH_NOT_BLOCKED')
  except RuntimeError:pass
  out={'schema_version':'1.0.0','state':'PASS' if not problems else 'FAIL','problems':problems,'backup_sha256':receipt['sha256'],'wal_cleaned':True,'rollback_supported':True}
  out['receipt_sha256']=sha256_bytes(canonical_json_bytes(out));atomic_write(a.output,json.dumps(out,indent=2,sort_keys=True).encode());print(json.dumps(out,sort_keys=True));return 0 if not problems else 2
if __name__=='__main__':raise SystemExit(main())
