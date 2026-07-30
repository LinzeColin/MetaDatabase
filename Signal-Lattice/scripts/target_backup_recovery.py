#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,sqlite3,tempfile
from datetime import datetime,timezone
from pathlib import Path
from signal_lattice.backup import backup_sqlite,restore_sqlite
from signal_lattice.util import atomic_write,canonical_json_bytes,sha256_bytes

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--backup',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if not a.source.is_file():
  print(json.dumps({'state':'BLOCKED','reason':'RUNTIME_DB_MISSING'}));return 2
 receipt=backup_sqlite(a.source,a.backup)
 with tempfile.TemporaryDirectory() as t:
  restored=Path(t)/'restored.db';restore_sqlite(a.backup,restored,receipt['sha256']);con=sqlite3.connect(restored)
  try:integrity=con.execute('pragma integrity_check').fetchone()[0];tables=con.execute("select count(*) from sqlite_master where type='table'").fetchone()[0]
  finally:con.close()
 out={'schema_version':'1.0.0','state':'PASS' if integrity=='ok' and tables>0 else 'BLOCKED','source':a.source.as_posix(),'backup':a.backup.as_posix(),'backup_size':receipt['size'],'backup_sha256':receipt['sha256'],'restored_integrity':integrity,'restored_table_count':tables,'verified_at':datetime.now(timezone.utc).isoformat(),'live_database_mutated':False}
 out['receipt_sha256']=sha256_bytes(canonical_json_bytes(out));atomic_write(a.output,json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True).encode());print(json.dumps(out,ensure_ascii=False,sort_keys=True));return 0 if out['state']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
