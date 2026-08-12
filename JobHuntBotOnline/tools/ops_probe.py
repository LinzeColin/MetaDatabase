#!/usr/bin/env python3
"""Validate optional status/Private-Database/R2 integration evidence without Secrets."""
from __future__ import annotations
import argparse, json, os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

def evidence_state(name: str) -> dict:
    value = os.getenv(name, "").strip()
    if not value:
        return {"name": name, "status": "BLOCKED", "reason": "evidence path not configured"}
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file() or path.stat().st_size == 0:
        return {"name": name, "status": "FAIL", "path": str(path), "reason": "evidence file is missing or empty"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"name": name, "status": "FAIL", "path": str(path), "reason": "evidence is not valid JSON"}
    verdict = payload.get("verdict")
    if verdict == "PASS":
        return {"name": name, "status": "PASS", "path": str(path), "evidence_verdict": verdict}
    if verdict in {"BLOCKED", "NOT_CONFIGURED", "NOT_APPLICABLE", "EMAIL_ONLY_BLOCKED"}:
        return {
            "name": name,
            "status": "BLOCKED",
            "path": str(path),
            "evidence_verdict": verdict,
            "reason": payload.get("reason", "integration evidence is not a PASS"),
        }
    return {
        "name": name,
        "status": "FAIL",
        "path": str(path),
        "evidence_verdict": verdict,
        "reason": "evidence has no recognized PASS verdict",
    }

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--output',default='evidence/target-ops.json'); args=parser.parse_args()
    checks=[evidence_state('STATUS_REGISTRATION_EVIDENCE'), evidence_state('PRIVATE_DATABASE_SYNC_EVIDENCE'), evidence_state('R2_SYNC_EVIDENCE')]
    status_url=os.getenv('STATUS_URL','').strip()
    if status_url:
        try:
            request = Request(status_url, headers={"User-Agent": "jobhuntbot-ops-probe/0.4"})
            with urlopen(request, timeout=10) as response:
                status_code = response.status
            checks.append({"name":"STATUS_URL","status":"PASS" if status_code < 500 else "FAIL","http_status":status_code})
        except HTTPError as exc:
            checks.append({"name":"STATUS_URL","status":"FAIL","http_status":exc.code})
        except (OSError, URLError) as exc:
            checks.append({"name":"STATUS_URL","status":"FAIL","error_type":type(exc).__name__})
    verdict='PASS' if checks and all(x['status']=='PASS' for x in checks) else 'BLOCKED'
    result={"verdict":verdict,"critical":False,"checks":checks,"secret_values_read":False,"production_claimed":False,"completion_authority":"root ACCEPTANCE_RESULT.json only"}
    out=Path(args.output); out=out if out.is_absolute() else ROOT/out; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
if __name__=='__main__': raise SystemExit(main())
