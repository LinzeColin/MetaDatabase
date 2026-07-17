#!/usr/bin/env python3
"""P-003 load/capacity retest: staged load with SLO thresholds and abort gate.

Runs average-load -> stress stages against the public read path, records
p50/p95/p99 latency and error rate per stage, and asserts against SLO
thresholds. Includes an abort gate: if error rate exceeds the abort ceiling
in any stage, the stage stops early (protects the target).

SLO thresholds (API layer; derived from docs/28 interaction budgets scaled to
network round-trips):
  - p95 latency  <= 800 ms
  - p99 latency  <= 1500 ms
  - error rate   <  1.0 %
  - abort ceiling (stop stage): error rate >= 10 %

Runs against an isolated instance (local wrangler by default). PRODUCTION load
is NOT run here: the acceptance capped production at 1 VU / 1 RPS and load is
unauthorized. Production-scale runs require the Run Contract's isolated clone,
service telemetry and an authorized abort owner.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

UA = {"user-agent": "eei-retest/1.0"}
SLO = {"p95_ms": 800, "p99_ms": 1500, "error_rate_pct": 1.0, "abort_error_pct": 10.0}

READ_PATHS = [
    ("GET", "/health", None),
    ("GET", "/v1/publication/meta", None),
    ("GET", "/v1/scoring/active-context", None),
    ("GET", "/v1/supply-chain/overview", None),
    ("GET", "/v1/changes", None),
    ("GET", "/v1/entities?q=nvidia", None),
    ("POST", "/v1/explore", {"focus":{"object_type":"entity","object_id":"00000000-0000-4000-8000-000000000002"}}),
]

def one(base, method, path, payload):
    data = json.dumps(payload).encode() if payload else None
    hdr = dict(UA) 
    if data: hdr["content-type"]="application/json"
    r = urllib.request.Request(base+path, data=data, method=method, headers=hdr)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            resp.read()
            return (time.perf_counter()-t0)*1000, resp.status < 400
    except Exception:
        return (time.perf_counter()-t0)*1000, False

def stage(base, concurrency, requests_per):
    total = concurrency * requests_per
    lat, errors = [], 0
    def worker(i):
        m,p,pl = READ_PATHS[i % len(READ_PATHS)]
        return one(base, m, p, pl)
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        for ms, ok in ex.map(worker, range(total)):
            lat.append(ms)
            if not ok: errors += 1
            # abort gate
            if len(lat) >= 20 and (errors/len(lat))*100 >= SLO["abort_error_pct"]:
                break
    lat.sort()
    def pct(p): return lat[min(len(lat)-1, int(len(lat)*p/100))] if lat else 0
    err_pct = (errors/len(lat))*100 if lat else 100
    passed = pct(95) <= SLO["p95_ms"] and pct(99) <= SLO["p99_ms"] and err_pct < SLO["error_rate_pct"]
    return {
        "concurrency": concurrency, "requests": len(lat),
        "p50_ms": round(pct(50),1), "p95_ms": round(pct(95),1), "p99_ms": round(pct(99),1),
        "max_ms": round(max(lat),1) if lat else 0, "error_pct": round(err_pct,2),
        "slo_pass": passed,
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8788")
    ap.add_argument("--stages", default="1,4,8,16", help="comma concurrency levels (avg-load -> stress)")
    ap.add_argument("--per", type=int, default=30, help="requests per virtual user per stage")
    a = ap.parse_args()
    # warm the worker so the first stage does not measure cold start
    import time
    for _ in range(40):
        if one(a.base, "GET", "/health", None)[1]:
            break
        time.sleep(1)
    stages = []
    for c in [int(x) for x in a.stages.split(",")]:
        s = stage(a.base, c, a.per)
        print(json.dumps(s))
        stages.append(s)
    verdict = "PASS" if all(s["slo_pass"] for s in stages) else "FAIL"
    out = {"suite":"P-003-load-capacity","base":a.base,"ran_at":datetime.now(timezone.utc).isoformat(),
           "slo":SLO,"stages":stages,"verdict":verdict,
           "note":"isolated-instance baseline; production-scale capacity requires authorized isolated clone + telemetry"}
    print("\n=== P-003 VERDICT:", verdict, "===")
    import os; os.makedirs("out", exist_ok=True)
    open("out/p003_load.json","w").write(json.dumps(out, indent=2))
