#!/usr/bin/env python3
from __future__ import annotations
import json,os
from datetime import datetime,timezone
from pathlib import Path
from signal_lattice.config import Settings
from signal_lattice.constants import VERSION
from signal_lattice.db import RuntimeDB
from signal_lattice.util import atomic_write

def main()->int:
 root=Path(__file__).resolve().parents[1];settings=Settings.from_env(root);artifacts=settings.artifact_dir;db=RuntimeDB(settings.state_dir/'runtime.db',root/'db/schema.sql');latest=db.latest_action();mode='HUMAN_DECISION_SUPPORT' if settings.recommendation_enabled else 'RESEARCH_AND_NO_ACTION';payload={'project_id':'signal-lattice','version':VERSION,'state':'PASS' if settings.runtime_environment=='production' else 'DEGRADED','live_action':False,'human_decision_support':settings.recommendation_enabled,'mode':mode,'current_action':latest.get('action') if latest else 'NO_ACTION','public_url':settings.public_url,'status_url':settings.status_url,'counts':db.runtime_counts(),'agent_process_count':0,'model_api_calls_total':0,'llm_input_tokens_total':0,'llm_output_tokens_total':0,'model_provider_egress_attempts_total':0,'automatic_trading':False,'updated_at':datetime.now(timezone.utc).isoformat(),'reason':None if settings.runtime_environment=='production' else 'TARGET_STATUS_BINDING_REQUIRED'};atomic_write(artifacts/'status_snapshot.json',json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True).encode());print(json.dumps(payload,ensure_ascii=False,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
