#!/usr/bin/env python3
"""Dynamic refresh loop — keeps the published graph current and deepens it.

The industry graph must stay timely: new SEC filings become new events, new
companies get covered, ownership edges get topped up, and the cloud is
republished — automatically, on a schedule, with no human in the loop.

Mechanism (a rolling window over the whole universe, so one simple cursor
delivers BOTH freshness and growth):
  1. enrich_sec over the next `--enrich-batch` companies from a rolling
     offset — re-fetches their SEC feed, so new filings appear as new events
     (freshness) and never-enriched companies get covered (growth);
  2. collect_gleif over the next `--gleif-batch` companies from its own
     rolling offset — tops up ownership/structure coverage;
  3. publish_to_cloud_channel --apply — one-way republish to live D1.
The cursor wraps at the end of the universe, so successive daily runs sweep
every company and come back around, keeping the whole graph fresh over time.

State: a small JSON cursor file (EEI_REFRESH_STATE env, else <root>/.eei_refresh_state.json).
Run once (default) for cron/Coolify-scheduled use, or `--loop --interval-seconds N`
as a long-running container command.

Usage:
  python -m scripts.authoritative.refresh_cycle                       # one cycle
  python -m scripts.authoritative.refresh_cycle --loop --interval-seconds 86400
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../EEI
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.authoritative.common import connect_database  # noqa: E402

STATE_PATH = Path(
    os.getenv("EEI_REFRESH_STATE", str(ROOT / ".eei_refresh_state.json"))
)
RUN_LOG = Path(
    os.getenv("EEI_REFRESH_RUN_LOG", str(ROOT / ".eei_refresh_runs.jsonl"))
)


def load_state() -> dict[str, int]:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"enrich_offset": 0, "gleif_offset": 0}


def save_state(state: dict[str, int]) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def universe_size() -> int:
    with connect_database() as conn:
        return int(
            conn.execute(
                """
                SELECT count(*) FROM entities e
                JOIN entity_identifiers ei ON ei.entity_id = e.id AND ei.scheme = 'cik'
                WHERE e.status = 'research_target'
                """
            ).fetchone()[0]
        )


def run_step(argv: list[str], *, label: str) -> tuple[int, str]:
    """Run a collector/publisher as a subprocess; return (rc, tail)."""
    proc = subprocess.run(
        [sys.executable, *argv],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tail = (proc.stdout or "")[-600:] + (proc.stderr or "")[-300:]
    print(f"[refresh] {label} rc={proc.returncode}\n{tail.strip()}")
    return proc.returncode, tail.strip()


def one_cycle(args) -> dict:
    started = datetime.now(UTC).isoformat()
    total = max(universe_size(), 1)
    state = load_state()
    enrich_off = state.get("enrich_offset", 0) % total
    gleif_off = state.get("gleif_offset", 0) % total

    result: dict = {"started_at": started, "universe": total,
                    "enrich_offset": enrich_off, "gleif_offset": gleif_off}

    if not args.skip_enrich:
        rc, _ = run_step(
            ["-m", "scripts.authoritative.enrich_sec",
             "--limit", str(args.enrich_batch), "--offset", str(enrich_off)],
            label=f"enrich[{enrich_off}:{enrich_off + args.enrich_batch}]",
        )
        result["enrich_rc"] = rc
        state["enrich_offset"] = (enrich_off + args.enrich_batch) % total

    if not args.skip_gleif:
        rc, _ = run_step(
            ["-m", "scripts.authoritative.collect_gleif",
             "--limit", str(args.gleif_batch), "--offset", str(gleif_off)],
            label=f"gleif[{gleif_off}:{gleif_off + args.gleif_batch}]",
        )
        result["gleif_rc"] = rc
        state["gleif_offset"] = (gleif_off + args.gleif_batch) % total

    if not args.skip_publish:
        report = ROOT / ".eei_refresh_publish_report.json"
        sqlout = ROOT / ".eei_refresh_publish.sql"
        rc, tail = run_step(
            ["scripts/publish_to_cloud_channel.py",
             "--report", str(report), "--sql-out", str(sqlout), "--apply"],
            label="publish",
        )
        result["publish_rc"] = rc
        result["publish_drill_passed"] = '"drill_passed": true' in tail or \
                                         '"drill_passed":true' in tail

    save_state(state)
    result["finished_at"] = datetime.now(UTC).isoformat()
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"[refresh] cycle done: {json.dumps(result, ensure_ascii=False)}")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--enrich-batch", type=int, default=500)
    p.add_argument("--gleif-batch", type=int, default=300)
    p.add_argument("--skip-enrich", action="store_true")
    p.add_argument("--skip-gleif", action="store_true")
    p.add_argument("--skip-publish", action="store_true")
    p.add_argument("--loop", action="store_true", help="run forever")
    p.add_argument("--interval-seconds", type=int, default=86400)
    args = p.parse_args()

    if not args.loop:
        r = one_cycle(args)
        return 0 if r.get("publish_rc", 0) == 0 else 1

    print(f"[refresh] loop mode, interval={args.interval_seconds}s")
    while True:
        try:
            one_cycle(args)
        except Exception as exc:  # noqa: BLE001 - a scheduled loop must not die
            print(f"[refresh] cycle error (continuing): {exc}")
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
