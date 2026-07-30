#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path

def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);p.add_argument('--version',required=True);a=p.parse_args()
 if not a.result.is_file():print(json.dumps({'state':'BLOCKED','reason':'DELIVERY_RESULT_MISSING'}));return 2
 d=json.loads(a.result.read_text());copy=dict(d);expected=copy.pop('receipt_sha256',None);actual=hashlib.sha256(json.dumps(copy,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();uv=d.get('user_visible_result',{})
 checks={
  'state':d.get('state')=='PASS','claim':d.get('completion_claim')=='DEPLOYED_AND_PUBLICLY_VERIFIED','version':d.get('version')==a.version,
  'url':d.get('public_url')=='https://signal-lattice.linzezhang.com','status_url':d.get('status_url')=='https://status.linzezhang.com','hash':expected==actual,
  'software_website':uv.get('software_website') is True,'aggregation':uv.get('multi_skill_aggregation') is True,'coordination':uv.get('internal_consensus_coordination') is True,
  'decision_support_capability':uv.get('human_decision_support_capability') is True,'automatic_trading':uv.get('automatic_trading') is False,
  'runtime_agent_zero':d.get('runtime_agent_dependency')==0,'runtime_token_zero':d.get('runtime_llm_tokens')==0,
 }
 out={'state':'PASS' if all(checks.values()) else 'BLOCKED','checks':checks,'public_url':d.get('public_url'),'current_action':uv.get('current_action'),'recommendation_available_now':uv.get('recommendation_available_now')}
 print(json.dumps(out,ensure_ascii=False,sort_keys=True));return 0 if out['state']=='PASS' else 2
if __name__=='__main__':raise SystemExit(main())
