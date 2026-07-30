from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from .constants import BUSINESS_LINES,SLICES,MODEL_MODE,RUNTIME_TOKEN_BUDGET

def default_matrix(scope:str='PREBUILD_CONTRACT_FIXTURE_NOT_LIVE_STATUS_PROOF')->dict[str,Any]:
    now=datetime.now(timezone.utc).isoformat(); lines=[]
    for line in BUSINESS_LINES:
        cells=[]
        for sl in SLICES:
            cells.append({'slice_id':sl,'state':'NOT_EXECUTED_IN_TARGET_ENVIRONMENT','measured':False,
                          'evidence_ref':None,'freshness':'UNKNOWN','upstream':[],'downstream':[],
                          'coupling':[],'blocker':'TARGET_ENVIRONMENT_NOT_BOUND','next_action':'TARGET_COMPATIBILITY_CHECK'})
        lines.append({'line_id':line,'stage':'PREBUILD','runtime_state':'DEGRADED','cells':cells})
    return {'scope':scope,'updated_at':now,'lines':lines,'runtime_agent_dependency':0,
            'runtime_model_mode':MODEL_MODE,'runtime_token_budget':RUNTIME_TOKEN_BUDGET}

def reconcile(matrix:dict[str,Any],target:bool=False)->dict[str,Any]:
    lines=matrix.get('lines',[]); ids=[x.get('line_id') for x in lines]
    problems=[]
    if sorted(ids)!=sorted(BUSINESS_LINES):problems.append('BUSINESS_LINE_SET_MISMATCH')
    for line in lines:
        cells=line.get('cells',[])
        if sorted(c.get('slice_id') for c in cells)!=sorted(SLICES):problems.append(f"SLICE_SET_MISMATCH:{line.get('line_id')}")
        for c in cells:
            if target and c.get('measured') is not True:problems.append(f"UNMEASURED:{line.get('line_id')}:{c.get('slice_id')}")
            if target and not c.get('evidence_ref'):problems.append(f"MISSING_EVIDENCE:{line.get('line_id')}:{c.get('slice_id')}")
    return {'state':'PASS' if not problems else 'BLOCKED','problems':problems,'line_count':len(lines),'cell_count':sum(len(x.get('cells',[])) for x in lines)}
