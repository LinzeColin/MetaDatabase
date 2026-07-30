from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from .constants import HARD_GATE_REASONS

REQUIRED_GATES=(
 'upstream_seal','point_in_time','freshness','license','evidence','evidence_independence',
 'oos_edge','overfit','cost','liquidity','capacity','portfolio_risk','runtime_zero_token'
)

def decide(request:dict[str,Any], trusted:dict[str,bool], now:datetime|None=None)->dict[str,Any]:
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    failed=[g for g in REQUIRED_GATES if trusted.get(g) is not True]
    symbol=str(request.get('symbol','UNKNOWN')).upper()[:24]
    if failed:
        return {
          'symbol':symbol,'market':str(request.get('market','UNKNOWN')),'action':'NO_ACTION',
          'reasons':failed,'valid_until':(now+timedelta(hours=1)).isoformat(),
          'human_execution_only':True,'automatic_execution_allowed':False,
          'runtime_agent_dependency':0,'runtime_llm_tokens':0,
          'as_of':now.isoformat(),'confidence_namespace':'not_calibrated','evidence_refs':[],
        }
    # Live action remains disabled in v0.0.0.1.39 even if caller presents all booleans.
    return {
      'symbol':symbol,'market':str(request.get('market','UNKNOWN')),'action':'NO_ACTION',
      'reasons':['LIVE_ACTION_DISABLED_IN_CURRENT_RELEASE'],
      'valid_until':(now+timedelta(hours=1)).isoformat(),'human_execution_only':True,
      'automatic_execution_allowed':False,'runtime_agent_dependency':0,'runtime_llm_tokens':0,
      'as_of':now.isoformat(),'confidence_namespace':'sealed_data_required','evidence_refs':[],
    }
