#!/usr/bin/env python3
from __future__ import annotations
import json, os, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from signal_lattice.util import atomic_write

def main():
 state=Path(os.environ.get('SIGNAL_LATTICE_STATE_DIR','/var/lib/signal-lattice')); db=state/'runtime.db'
 pending=0
 if db.exists():
  c=sqlite3.connect(db); pending=c.execute("SELECT count(*) FROM outbox WHERE state='PENDING'").fetchone()[0];c.close()
 out=Path(os.environ.get('SIGNAL_LATTICE_ARTIFACT_DIR',str(state/'artifacts')))/'outbox_sync.json'
 receipt={'state':'DEGRADED' if pending else 'PASS','pending':pending,'sink':'Private-Database','reason':'TARGET_CREDENTIAL_BINDING_REQUIRED' if pending else None,'updated_at':datetime.now(timezone.utc).isoformat()}
 atomic_write(out,json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True).encode())
if __name__=='__main__':main()
