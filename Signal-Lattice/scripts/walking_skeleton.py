#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,tempfile
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from signal_lattice.clock import FakeClock
from signal_lattice.config import Settings
from signal_lattice.db import RuntimeDB
from signal_lattice.recommendation import validate_market_snapshot,validate_skill_signal
from signal_lattice.worker import run_once

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--receipt',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1]
 with tempfile.TemporaryDirectory() as t:
  r=Path(t);clock=FakeClock(datetime(2026,7,30,tzinfo=timezone.utc));db=RuntimeDB(r/'runtime.db',root/'db/schema.sql',clock)
  for name in ('commercial_signal.json','bottleneck_signal.json'):
   db.upsert_skill_signal(validate_skill_signal(json.loads((root/'fixtures/northstar'/name).read_text())))
  db.upsert_market_snapshot(validate_market_snapshot(json.loads((root/'fixtures/northstar/market_snapshot.json').read_text())))
  settings=Settings(state_dir=r,artifact_dir=r/'artifacts',web_dir=root/'web',recommendation_enabled=True,runtime_environment='test',decision_policy_path=root/'config/decision_policy.json')
  job,created=db.enqueue({'symbol':'DEMO','market':'US','current_position_pct':0.0,'requested_position_value_usd':1000},'walking-skeleton-northstar')
  ran=run_once(db,'walking-worker',120,settings=settings);result=db.get_job(job)
  fail_job,_=db.enqueue({'symbol':'MISSING','market':'US'},'walking-skeleton-failclosed');run_once(db,'walking-worker',120,settings=settings);fail_result=db.get_job(fail_job)
  with db.connect() as c:counts={x:c.execute(f'SELECT count(*) FROM {x}').fetchone()[0] for x in ('actions','outbox','runtime_journal','attempts','decision_snapshots')}
  checks={'job_created':created,'worker_ran':ran,'job_completed':result and result['state']=='COMPLETED','human_recommendation':result and result['result']['action'] in {'BUY','ADD','HOLD','REDUCE','SELL','WATCH','AVOID'},'human_only':result and result['result']['human_execution_only'] is True and result['result']['automatic_execution_allowed'] is False,'fail_closed_no_action':fail_result and fail_result['result']['action']=='NO_ACTION','decision_snapshot_written':counts['decision_snapshots']>=1,'atomic_event_counts':counts['actions']==2 and counts['outbox']==2 and counts['runtime_journal']==2 and counts['attempts']==2}
  payload={'schema_version':'2.0.0','state':'PASS' if all(checks.values()) else 'FAIL','checks':checks,'counts':counts,'recommended_action':result['result']['action'] if result else None,'runtime_agent_dependency':0,'runtime_llm_tokens':0,'automatic_trading':False}
  a.receipt.parent.mkdir(parents=True,exist_ok=True);a.receipt.write_text(json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+'\n');print(json.dumps(payload,ensure_ascii=False,sort_keys=True));return 0 if payload['state']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
