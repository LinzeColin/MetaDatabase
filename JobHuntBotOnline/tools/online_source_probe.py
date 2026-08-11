#!/usr/bin/env python3
"""Probe configured external job adapters using a synthetic candidate profile."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.config import get_settings
from app.discovery import fetch_sources, safe_http_url


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--require-success", action="store_true")
    args = parser.parse_args()
    settings = replace(get_settings(), discovery_fixture_path="")
    profile = {"primary_role_families": ["Finance", "Data"], "target_locations": ["Sydney", "Remote Australia"]}
    rows = []
    total = 0
    for source, status, jobs, detail in fetch_sources(settings, profile):
        safe_count = sum(bool(safe_http_url(job.url)) for job in jobs)
        rows.append({
            "source": source, "status": status, "jobs": len(jobs), "safe_urls": safe_count,
            "detail": detail[:300] if detail else "",
        })
        if status == "ok" and jobs and safe_count == len(jobs):
            total += len(jobs)
    if total:
        verdict, exit_code = "PASS", 0
    else:
        network_like = bool(rows) and all(
            row["status"] == "failed" and any(token in row["detail"].lower() for token in [
                "name resolution", "connecterror", "network", "temporary failure", "dns", "nodename"
            ]) for row in rows
        )
        verdict = "BLOCKED_NETWORK" if network_like else "FAIL"
        exit_code = 1 if args.require_success else 0
    result = {
        "verdict": verdict, "synthetic_profile_only": True,
        "successful_job_count": total, "sources": rows, "production_claimed": False,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = Path(args.output)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(text, end="")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
