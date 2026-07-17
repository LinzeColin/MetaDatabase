#!/usr/bin/env python3
"""R-002 fault-injection / recovery retest: controlled failures at the request
boundary, verifying the surface fails CLOSED (structured error, no fixture leak,
no stack-trace disclosure) and RECOVERS (a valid request immediately after a
fault still succeeds — no lingering bad state).

Scenarios (all safe, request-level; no container restarts so the monitoring
heartbeat chain is never disturbed):
  R2-a  unknown relationship id            -> 404 structured, no stack
  R2-b  malformed explore body (no focus)  -> 400 structured, no crash
  R2-c  malformed JSON body                -> 4xx structured, no crash
  R2-d  oversized query term               -> handled, no 500
  R2-e  fail-closed proof                  -> no fault response leaks fixture/
                                              synthetic tokens or a stack trace
  R2-f  recovery                           -> valid request after each fault
                                              returns 200 with real published data

Container-level fault injection (kill worker / DB unavailable / restart RTO/RPO)
is specified in the Run Contract for the authorized isolated clone; it is NOT
run here because the only local backend is the monitoring-critical docker pair.
"""
import argparse
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = {"user-agent":"eei-retest/1.0"}
BAD = "00000000-0000-4000-9000-00000000dead"
NVIDIA = "00000000-0000-4000-8000-000000000002"
LEAK_TOKENS = ["Traceback", 'File "', "fixture-v1", "synthetic", "Synthetic", "@gmail", "at Object.", "SQLITE_"]

def call(base, method, path, raw=None, payload=None):
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    hdr = dict(UA)
    if data: hdr["content-type"]="application/json"
    r = urllib.request.Request(base+path, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def leaks(body):
    return [t for t in LEAK_TOKENS if t in body]

def valid_recovery(base):
    code, body = call(base, "POST", "/v1/explore", payload={"focus":{"object_type":"entity","object_id":NVIDIA}})
    d = json.loads(body) if body.strip().startswith("{") else {}
    return code==200 and len(d.get("edges",[]))>=1

def wait_ready(base, tries=40):
    import time
    for _ in range(tries):
        try:
            if call(base, "GET", "/health")[0] == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--base", default="http://127.0.0.1:8788"); a=ap.parse_args()
    if not wait_ready(a.base):
        raise SystemExit(f"target {a.base} not ready")
    scen = []
    def check(cid, desc, code, body, want_codes):
        lk = leaks(body)
        rec = valid_recovery(a.base)
        ok = code in want_codes and not lk and rec
        scen.append({"id":cid,"desc":desc,"http":code,"want":want_codes,"leaks":lk,"recovered":rec,"verdict":"PASS" if ok else "FAIL"})
        print(json.dumps(scen[-1]))

    c,b = call(a.base,"GET",f"/v1/scoring/relationship/{BAD}/explanation")
    check("R2-a","unknown relationship id",c,b,[404])
    c,b = call(a.base,"POST","/v1/explore",payload={"no_focus":True})
    check("R2-b","explore without focus",c,b,[400])
    c,b = call(a.base,"POST","/v1/explore",raw=b"{not valid json")
    check("R2-c","malformed JSON body",c,b,[400])
    c,b = call(a.base,"GET","/v1/entities?q="+("A"*5000))
    check("R2-d","oversized query term",c,b,[200,400,414])
    c,b = call(a.base,"GET","/v1/entities")  # missing required q
    check("R2-e","missing required param",c,b,[400])

    verdict = "PASS" if all(s["verdict"]=="PASS" for s in scen) else "FAIL"
    out={"suite":"R-002-fault-injection","base":a.base,"ran_at":datetime.now(timezone.utc).isoformat(),
         "scenarios":scen,"verdict":verdict,
         "note":"request-level fail-closed + recovery; container RTO/RPO drills specified in Run Contract for authorized isolated clone"}
    print("\n=== R-002 VERDICT:", verdict, "===")
    import os; os.makedirs("out",exist_ok=True); open("out/r002_fault.json","w").write(json.dumps(out,indent=2))
