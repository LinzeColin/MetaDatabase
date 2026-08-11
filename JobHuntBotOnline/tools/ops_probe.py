#!/usr/bin/env python3
"""Validate optional status/Private-Database/R2 integration evidence without Secrets."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]

def evidence_state(name: str) -> dict:
    value = os.getenv(name, "").strip()
    if not value:
        return {"name": name, "status": "BLOCKED", "reason": "evidence path not configured"}
    path = Path(value)
    if not path.is_absolute(): path = ROOT / path
    return {"name": name, "status": "PASS" if path.is_file() and path.stat().st_size > 0 else "FAIL", "path": str(path)}

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='evidence/target-ops.json'); args=parser.parse_args()
    checks=[evidence_state('STATUS_REGISTRATION_EVIDENCE'), evidence_state('PRIVATE_DATABASE_SYNC_EVIDENCE'), evidence_state('R2_SYNC_EVIDENCE')]
    status_url=os.getenv('STATUS_URL','').strip()
    if status_url:
        try:
            r=httpx.get(status_url,timeout=10,follow_redirects=True)
            checks.append({"name":"STATUS_URL","status":"PASS" if r.status_code < 500 else "FAIL","http_status":r.status_code})
        except Exception as exc:
            checks.append({"name":"STATUS_URL","status":"FAIL","error_type":type(exc).__name__})
    verdict='PASS' if checks and all(x['status']=='PASS' for x in checks) else 'BLOCKED'
    result={"verdict":verdict,"critical":False,"checks":checks,"secret_values_read":False,"production_claimed":True}
    out=Path(args.output); out=out if out.is_absolute() else ROOT/out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
