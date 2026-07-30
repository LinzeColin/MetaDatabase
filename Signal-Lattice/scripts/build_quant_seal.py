#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from signal_lattice.quant import PointInTimeRecord,visible_at,net_expected_return,max_drawdown,pbo,deflated_sharpe_gate
from signal_lattice.action import decide,REQUIRED_GATES
from signal_lattice.util import canonical_json_bytes,sha256_bytes,atomic_write

def main(out:Path):
 d=datetime(2026,1,15,tzinfo=timezone.utc)
 future_ingest=PointInTimeRecord(d-timedelta(days=30),d-timedelta(days=2),d+timedelta(days=1),10)
 known=PointInTimeRecord(d-timedelta(days=30),d-timedelta(days=2),d-timedelta(days=1),10)
 checks={
  'future_ingest_excluded':visible_at([future_ingest],d)==[],
  'known_record_included':visible_at([known],d)==[known],
  'high_win_negative_expectancy':net_expected_return(.75,.01,.08,.001,.001,.002)<0,
  'cost_can_erase_edge':net_expected_return(.55,.02,.015,.004,.003,.006)<0,
  'drawdown_detected':max_drawdown([.1,-.2,.05])<-.1,
  'pbo_overfit_fixture':pbo([[.9,.2],[.8,.1],[.7,.2]],[[.1,.8],[.2,.7],[.1,.6]])==1.0,
  'dsr_penalizes_trials':deflated_sharpe_gate(2.0,100)<2.0,
  'all_gates_still_no_live_action':decide({'symbol':'TEST','market':'US'},{g:True for g in REQUIRED_GATES},d)['action']=='NO_ACTION',
  'missing_gates_no_action':decide({'symbol':'TEST','market':'US'},{},d)['action']=='NO_ACTION',
 }
 state='PASS' if all(checks.values()) else 'FAIL'
 receipt={'schema_version':'1.0.0','state':state,'scope':'TASKPACK_ALGORITHM_AND_FAIL_CLOSED_BEHAVIOR_ONLY','checks':checks,
          'live_market_edge_proven':False,'live_action_enabled':False,'runtime_agent_dependency':0,'runtime_llm_token_budget':0,
          'limitations':['合法 Point-in-time 市场数据、Provider 许可、市场状态和持有期校准属于部署启用门。']}
 receipt['receipt_sha256']=sha256_bytes(canonical_json_bytes(receipt))
 atomic_write(out,json.dumps(receipt,ensure_ascii=False,indent=2,sort_keys=True).encode())
 if state!='PASS':raise SystemExit(2)
if __name__=='__main__':main(Path(sys.argv[1]))
