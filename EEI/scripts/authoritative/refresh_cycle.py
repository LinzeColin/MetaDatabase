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


def _publish_credentials() -> tuple[str, str] | None:
    url = os.environ.get("EEI_PUBLISH_URL", "").strip()
    token = os.environ.get("EEI_PUBLISH_TOKEN", "").strip()
    return (url, token) if url and token else None


def publish_incremental_since(since: str) -> dict:
    creds = _publish_credentials()
    if not creds:
        return {"skipped": "EEI_PUBLISH_URL/TOKEN unset"}
    try:
        from scripts.publish_to_cloud_channel import push_recent

        return push_recent(since, publish_url=creds[0], publish_token=creds[1])
    except Exception as exc:  # noqa: BLE001 - retried next cycle; DB already has it
        return {"error": str(exc)[:200]}


def publish_pulse() -> dict:
    creds = _publish_credentials()
    if not creds:
        return {"skipped": "EEI_PUBLISH_URL/TOKEN unset"}
    try:
        from scripts.publish_to_cloud_channel import push_pulse

        return push_pulse(publish_url=creds[0], publish_token=creds[1])
    except Exception as exc:  # noqa: BLE001 - a metrics beat must never break a cycle
        return {"error": str(exc)[:200]}


def one_cycle(args, *, publish: bool = True) -> dict:
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

    # Completeness backstop: the minute watcher only sees a 100-entry window,
    # so anything filed in a burst between two polls is lost to it. The daily
    # index is the authoritative full list of a day's filings.
    if not args.skip_daily_index:
        rc, _ = run_step(
            ["-m", "scripts.authoritative.sec_daily_index",
             "--days-back", str(args.daily_index_days_back)],
            label="daily-index",
        )
        result["daily_index_rc"] = rc

    # History depth: the freshness sweep above deliberately stops at each
    # company's most-recent filings, so once it has caught up it adds nothing
    # and the corpus stops growing. This cursor walks the same universe far
    # more slowly with a much deeper per-company bound, so every cycle keeps
    # pulling real archive back toward 1994.
    if args.deep_batch > 0:
        deep_off = state.get("deep_offset", 0) % total
        rc, _ = run_step(
            ["-m", "scripts.authoritative.enrich_sec",
             "--limit", str(args.deep_batch), "--offset", str(deep_off),
             "--max-events", str(args.deep_max_events)],
            label=f"deep[{deep_off}:{deep_off + args.deep_batch}]",
        )
        result["deep_rc"] = rc
        result["deep_offset"] = deep_off
        state["deep_offset"] = (deep_off + args.deep_batch) % total

    if not args.skip_publish and publish:
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
    elif not args.skip_publish:
        # The full DELETE+INSERT republish is deferred (it rewrites the whole
        # surface), but everything this cycle collected still goes live now:
        # upsert just the entities whose published surface changed. Without
        # this, ownership edges and deepened history sat invisible for up to a
        # day and the site looked frozen while the collector was working.
        result["publish_skipped_this_cycle"] = True
        result["incremental"] = publish_incremental_since(started)

    # Recompute the pulse every cycle (a few hundred small rows) so the growth
    # curve, today's delta and the totals move without waiting for a republish.
    result["pulse"] = publish_pulse()

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
    p.add_argument("--skip-daily-index", action="store_true")
    p.add_argument(
        "--daily-index-days-back", type=int, default=4,
        help="how far back the daily-index completeness sweep looks for gaps",
    )
    p.add_argument(
        "--deep-batch", type=int, default=12,
        help="companies per cycle for the deep-history sweep (0 disables). Kept"
             " small: each one walks far more of the EDGAR archive than the"
             " freshness sweep does.",
    )
    p.add_argument(
        "--deep-max-events", type=int, default=400,
        help="material filings per company for the deep-history sweep",
    )
    p.add_argument(
        "--publish-every", type=int, default=1,
        help="full republish only every Nth cycle (enrich/gleif still run every"
             " cycle). Keeps D1 writes in the free tier when the enrich sweep"
             " runs frequently; the watcher owns minute-cadence freshness.",
    )
    p.add_argument("--loop", action="store_true", help="run forever")
    p.add_argument("--interval-seconds", type=int, default=86400)
    args = p.parse_args()

    if not args.loop:
        r = one_cycle(args)
        return 0 if r.get("publish_rc", 0) == 0 else 1

    print(f"[refresh] loop mode, interval={args.interval_seconds}s, "
          f"publish_every={args.publish_every}")
    n = 0
    while True:
        try:
            one_cycle(args, publish=(n % max(args.publish_every, 1) == 0))
        except Exception as exc:  # noqa: BLE001 - a scheduled loop must not die
            print(f"[refresh] cycle error (continuing): {exc}")
        n += 1
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
