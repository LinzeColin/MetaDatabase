#!/usr/bin/env python3
"""Sustained source-health watch for S7PAT03 (T1301 / ACC-A202, A206-adjacent).

Probes every registered official source on a fixed interval for a bounded
duration, recording per-cycle JSONL checkpoints with source health, retry
attempts and degradation transitions. Honest by construction: failures are
recorded, never masked; nothing is published; no release gate moves.

Intended run shape: a detached 4h window (16 cycles at 900s) whose checkpoint
file plus summary become runtime evidence for the source-health/retry portion
of S7PAT03. Dead-letter evidence is produced separately by driving the real
background-job queue to exhaustion (see 文档/05_执行与验收.md, S7PAT03).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import fetch_official_source_full_text as official_source  # noqa: E402

SCHEMA_VERSION = "eei-source-health-watch-v1"
TASK_ID = "S7PAT03"
LEGACY_TASK_ID = "T1301"
ACCEPTANCE_IDS = ["A202", "A206"]


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_client(timeout_seconds: float) -> httpx.Client:
    user_agent = os.environ.get("SEC_USER_AGENT", "").strip() or (
        "EEI/0.1 source-health-watch "
        "(Enterprise Ecosystem Intelligence; contact=operator)"
    )
    return httpx.Client(timeout=timeout_seconds, headers={"User-Agent": user_agent})


def probe_cycle(
    rows: list[dict[str, str]],
    *,
    client: httpx.Client,
    cycle: int,
) -> dict[str, Any]:
    payload = official_source.capture_live_official_sources(rows=rows, client=client)
    sources = []
    for anchor in payload.get("anchors", []):
        health = anchor.get("source_health") or {}
        attempts = health.get("attempts") or []
        sources.append(
            {
                "anchor_id": anchor.get("anchor_id"),
                "health_status": health.get("status"),
                "http_status": health.get("http_status"),
                "text_char_count": health.get("text_char_count"),
                "attempt_count": len(attempts),
                "retried": len(attempts) > 1,
                "source_text_sha256": anchor.get("source_text_sha256"),
            }
        )
    healthy = sum(1 for s in sources if s["health_status"] == "healthy")
    return {
        "schema_version": SCHEMA_VERSION,
        "cycle": cycle,
        "recorded_at": utc_now_iso(),
        "capture_status": payload.get("status"),
        "sources_total": len(sources),
        "sources_healthy": healthy,
        "sources_retried": sum(1 for s in sources if s["retried"]),
        "sources": sources,
    }


def summarize(checkpoints: list[dict[str, Any]], *, planned_cycles: int) -> dict[str, Any]:
    transitions: list[dict[str, Any]] = []
    previous: dict[str, Any] = {}
    for checkpoint in checkpoints:
        for source in checkpoint["sources"]:
            anchor_id = source["anchor_id"]
            prior = previous.get(anchor_id)
            if prior is not None and prior != source["health_status"]:
                transitions.append(
                    {
                        "cycle": checkpoint["cycle"],
                        "anchor_id": anchor_id,
                        "from": prior,
                        "to": source["health_status"],
                    }
                )
            previous[anchor_id] = source["health_status"]
    total_probes = sum(c["sources_total"] for c in checkpoints)
    healthy_probes = sum(c["sources_healthy"] for c in checkpoints)
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": TASK_ID,
        "legacy_task_id": LEGACY_TASK_ID,
        "acceptance_ids": ACCEPTANCE_IDS,
        "generated_at": utc_now_iso(),
        "cycles_planned": planned_cycles,
        "cycles_completed": len(checkpoints),
        "window_completed": len(checkpoints) >= planned_cycles,
        "probes_total": total_probes,
        "probes_healthy": healthy_probes,
        "healthy_ratio": round(healthy_probes / total_probes, 4) if total_probes else 0.0,
        "retries_observed": sum(c["sources_retried"] for c in checkpoints),
        "degradation_transitions": transitions,
        "release_scope": {
            "relationship_publication_performed": False,
            "release_clearance": False,
            "a202_closed_by_watch": False,
            "mvp_release_ready": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-hours", type=float, default=4.0)
    parser.add_argument("--interval-seconds", type=float, default=900.0)
    parser.add_argument("--allow-live-network", action="store_true")
    parser.add_argument("--checkpoints", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    args = parser.parse_args()

    if not args.allow_live_network:
        print("source-health watch requires --allow-live-network", file=sys.stderr)
        return 2
    if args.duration_hours <= 0 or args.interval_seconds <= 0:
        print("duration and interval must be positive", file=sys.stderr)
        return 2

    rows = official_source.read_csv(official_source.ANCHOR_PATH)
    planned_cycles = max(1, int((args.duration_hours * 3600) // args.interval_seconds))
    args.checkpoints.parent.mkdir(parents=True, exist_ok=True)
    checkpoints: list[dict[str, Any]] = []

    print(
        json.dumps(
            {
                "started_at": utc_now_iso(),
                "planned_cycles": planned_cycles,
                "interval_seconds": args.interval_seconds,
                "sources": [row["anchor_id"] for row in rows],
                "registry_sha256": hashlib.sha256(
                    official_source.ANCHOR_PATH.read_bytes()
                ).hexdigest(),
            }
        ),
        flush=True,
    )

    with build_client(args.timeout_seconds) as client:
        for cycle in range(1, planned_cycles + 1):
            started = time.monotonic()
            try:
                checkpoint = probe_cycle(rows, client=client, cycle=cycle)
            except Exception as exc:  # record, never mask
                checkpoint = {
                    "schema_version": SCHEMA_VERSION,
                    "cycle": cycle,
                    "recorded_at": utc_now_iso(),
                    "capture_status": "CYCLE_ERROR",
                    "error_class": type(exc).__name__,
                    "error_message": str(exc)[:400],
                    "sources_total": len(rows),
                    "sources_healthy": 0,
                    "sources_retried": 0,
                    "sources": [],
                }
            checkpoints.append(checkpoint)
            with args.checkpoints.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(checkpoint, ensure_ascii=False) + "\n")
            summary = summarize(checkpoints, planned_cycles=planned_cycles)
            args.summary.parent.mkdir(parents=True, exist_ok=True)
            args.summary.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(
                json.dumps(
                    {
                        "cycle": cycle,
                        "of": planned_cycles,
                        "healthy": checkpoint["sources_healthy"],
                        "total": checkpoint["sources_total"],
                    }
                ),
                flush=True,
            )
            if cycle < planned_cycles:
                elapsed = time.monotonic() - started
                time.sleep(max(0.0, args.interval_seconds - elapsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
