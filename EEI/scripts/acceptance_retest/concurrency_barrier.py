#!/usr/bin/env python3
"""C-001 barrier concurrency retest: user-state optimistic-concurrency correctness.

Fires N concurrent saved-view updates that ALL claim expected_version=1 against
one view, at a synchronization barrier, and asserts the write path admits exactly
ONE winner (HTTP 200) with the rest rejected as version conflicts (HTTP 409) —
no lost updates, no split-brain version numbers. Read-only public endpoints are
stateless so the only concurrency-correctness surface is the user-state write path.

Runs against an isolated instance (local wrangler by default). Production-scale
runs require the Run Contract's authorized isolated clone + dedicated account.
"""
import argparse
import json
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

UA = {"user-agent": "eei-retest/1.0", "content-type": "application/json"}

def _parse(raw):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_nonjson": raw[:200]}

def req(base, method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(base+path, data=data, method=method, headers=UA)
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, _parse(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, _parse(e.read().decode())

def wait_ready(base, tries=40):
    import time
    for _ in range(tries):
        try:
            code, _ = req(base, "GET", "/health")
            if code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def run(base, fanout):
    # 1. create a saved view (version 1)
    code, created = req(base, "POST", "/v1/saved-views", {
        "name": "c001-barrier", "workspace_key": "retest",
        "state": {"subject": "nvidia"}, "schema_version": "saved-view-v1"})
    assert code == 201, f"create failed {code}"
    vid = created["id"]
    assert created["current_version"] == 1

    # 2. barrier: fanout concurrent PUTs all claiming expected_version=1
    barrier = threading.Barrier(fanout)
    def contend(i):
        barrier.wait()  # release all threads simultaneously
        return req(base, "PUT", f"/v1/saved-views/{vid}", {
            "expected_version": 1,
            "state": {"subject": f"contender-{i}"},
            "change_note": f"barrier-{i}"})
    with ThreadPoolExecutor(max_workers=fanout) as ex:
        outcomes = list(ex.map(contend, range(fanout)))

    winners = [o for o in outcomes if o[0] == 200]
    conflicts = [o for o in outcomes if o[0] == 409]
    others = [o for o in outcomes if o[0] not in (200, 409)]

    # 3. final state must be exactly version 2 (one winner applied)
    code, final = req(base, "GET", f"/v1/saved-views/{vid}")
    final_ver = final.get("current_version")

    ok = (len(winners) == 1 and len(conflicts) == fanout-1 and not others and final_ver == 2)
    return {
        "acceptance_id": "C-001",
        "fanout": fanout,
        "winners": len(winners),
        "conflicts": len(conflicts),
        "unexpected": [o[0] for o in others],
        "final_version": final_ver,
        "verdict": "PASS" if ok else "FAIL",
        "invariant": "exactly-one-winner, N-1 conflicts, final_version==2 (no lost update)",
    }

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8788")
    ap.add_argument("--fanout", type=int, default=16)
    ap.add_argument("--rounds", type=int, default=5)
    a = ap.parse_args()
    # Warm the worker before the barrier so cold-start latency does not surface
    # as a transient 500 in round 0 (a warmup artifact, not a lost update).
    if not wait_ready(a.base):
        raise SystemExit(f"target {a.base} not ready")
    # a couple of real writes to fully warm the D1 write path
    for _ in range(2):
        req(a.base, "POST", "/v1/saved-views", {
            "name": "warmup", "workspace_key": "retest",
            "state": {"subject": "nvidia"}, "schema_version": "saved-view-v1"})
    results = []
    for rnd in range(a.rounds):
        r = run(a.base, a.fanout)
        r["round"] = rnd
        print(json.dumps(r))
        results.append(r)
    verdict = "PASS" if all(r["verdict"]=="PASS" for r in results) else "FAIL"
    out = {"suite":"C-001-concurrency-barrier","base":a.base,"ran_at":datetime.now(timezone.utc).isoformat(),
           "rounds":results,"verdict":verdict}
    print("\n=== C-001 VERDICT:", verdict, "===")
    import os
    os.makedirs("out", exist_ok=True)
    open("out/c001_concurrency.json","w").write(json.dumps(out, indent=2))
