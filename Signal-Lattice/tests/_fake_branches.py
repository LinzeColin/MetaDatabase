"""branch_runner 测试用的假分支（在子进程里被导入）。"""

import os
import resource
import sys
import time
from pathlib import Path


def _verdict(symbol="AAA", verdict="PASS"):
    return {"symbol": symbol, "cik": 1, "name": symbol, "market_cap_usd": 1e9, "verdict": verdict, "label": "T", "score": 1.0,
            "rank_key": 1.0, "reasons": [], "links": [], "evidence": {}}


def ok_branch(snapshot, log):
    Path("secret-of-%s.txt" % os.environ.get("SL_TEST_TAG", "ok")).write_text("only mine", "utf-8")
    return {"branch_status": "PASS", "branch_reasons": [], "verdicts": [_verdict("AAA", "PASS"), _verdict("BBB", "ABSTAIN")],
            "meta": {"as_of": snapshot.as_of, "entries": len(snapshot.entries)}}


def abstain_branch(snapshot, log):
    return {"branch_status": "ABSTAIN", "branch_reasons": ["NOT_BETTER_THAN_BASE_RATE"], "verdicts": [_verdict("AAA", "ABSTAIN")], "meta": {}}


def crash_branch(snapshot, log):
    raise RuntimeError("boom inside branch")


def exit_branch(snapshot, log):
    os._exit(3)


def sleep_branch(snapshot, log):
    pidfile = os.environ.get("SL_TEST_PIDFILE")
    if pidfile:
        Path(pidfile).write_text(str(os.getpid()), "utf-8")
    while True:
        time.sleep(0.2)


def hog_branch(snapshot, log):
    hoard = []
    while True:
        chunk = bytearray(40 * 1024 * 1024)
        for i in range(0, len(chunk), 4096):
            chunk[i] = 1
        hoard.append(chunk)
        time.sleep(0.05)


def cpu_branch(snapshot, log):
    x = 0
    while True:
        x += 1


def spy_branch(snapshot, log):
    cwd = Path(os.getcwd())
    work_root = Path(os.environ["TMPDIR"]).parent
    siblings = sorted(p.name for p in work_root.iterdir() if p != cwd and p.name.startswith("sl-"))
    secrets = [str(p) for p in work_root.rglob("secret-of-*.txt")]
    out_hint = os.environ.get("SL_TEST_OUT_DIR")
    outputs_visible = [str(p) for p in Path(out_hint).rglob("*")] if out_hint and Path(out_hint).exists() else []
    return {"branch_status": "PASS", "branch_reasons": [], "verdicts": [_verdict()],
            "meta": {"cwd": str(cwd), "own_files": sorted(p.name for p in cwd.iterdir()), "sibling_dirs": siblings,
                     "secrets_found": secrets, "outputs_visible": outputs_visible, "env_keys": sorted(os.environ),
                     "home_is_private": os.environ.get("HOME") == str(cwd) or os.environ.get("HOME") == os.environ.get("TMPDIR"),
                     "cwd_mode": oct(cwd.stat().st_mode & 0o777)}}


def limits_branch(snapshot, log):
    return {"branch_status": "PASS", "branch_reasons": [], "verdicts": [_verdict()],
            "meta": {"cpu": list(resource.getrlimit(resource.RLIMIT_CPU)), "core": list(resource.getrlimit(resource.RLIMIT_CORE))}}


def bad_status_branch(snapshot, log):
    return {"branch_status": "MAYBE", "branch_reasons": [], "verdicts": [], "meta": {}}
