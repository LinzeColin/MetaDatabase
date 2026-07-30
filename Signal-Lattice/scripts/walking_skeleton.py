#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,tempfile
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from signal_lattice.clock import FakeClock
from signal_lattice.db import RuntimeDB
from signal_lattice.worker import run_once
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);a=p.parse_args()
 with tempfile.TemporaryDirectory() as t:
  r=Path(t);db=RuntimeDB(r/'runtime.db',Path(__file__).resolve().parents[1]/'db/schema.sql',FakeClock(datetime(2026,1,1,tzinfo=timezone.utc)))
  job,created=db.enqueue({'symbol':'TEST','market':'US'},'walking-skeleton')
  ran=run_once(db,'walking-worker',120);result=db.get_job(job)
  with db.connect() as c:counts={x:c.execute(f'SELECT count(*) FROM {x}').fetchone()[0] for x in ('actions','outbox','runtime_journal','attempts')}
  checks={'job_created':created,'worker_ran':ran,'job_completed':result and result['state']=='COMPLETED','no_action':result and result['result']['action']=='NO_ACTION','atomic_counts':counts=={'actions':1,'outbox':1,'runtime_journal':1,'attempts':1}}
  payload={'schema_version':'1.0.0','state':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'counts':counts}
  a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n');print(json.dumps(payload,sort_keys=True));return 0 if payload['state']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
