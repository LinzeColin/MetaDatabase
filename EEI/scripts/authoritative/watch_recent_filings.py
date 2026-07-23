#!/usr/bin/env python3
"""Near-real-time SEC filing watcher — ~1-minute freshness, fair-access safe.

Why this exists: a full-universe re-sweep cannot run every minute (a sweep
takes minutes and would hammer SEC's fair-access budget re-fetching unchanged
submission feeds). Instead this watcher polls SEC's cheap *global latest
filings* feed once a minute, keeps only genuinely NEW material filings for
companies already in our universe, enriches just those companies, and upserts
ONLY the touched rows to live D1 (incremental publish — a few writes per
filing, never a full republish). The daily full sweep still runs for
completeness/repair.

Fair-access footprint: 1 getcurrent request/min (~56 KB) + at most one
submissions request per newly-filed universe company. Usually 0-few/min.

Idempotent: events dedupe on (cik:accession:form); a bounded state file of
seen accessions prevents re-enriching the same filing.

Usage:
  python -m scripts.authoritative.watch_recent_filings            # one poll
  python -m scripts.authoritative.watch_recent_filings --loop --interval-seconds 60
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.authoritative.common import (
    SecClient,
    connect_database,
    normalize_cik,
    source_id_for,
)
from scripts.authoritative.enrich_sec import enrich_one
from scripts.publish_to_cloud_channel import push_incremental

ROOT = Path(__file__).resolve().parents[2]
# Global "latest filings" firehose (Atom). count=100 covers normal load between
# polls; the daily full sweep reconciles anything missed in a filing burst.
GETCURRENT_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
    "&type=&company=&dateb=&owner=include&count=100&output=atom"
)
STATE_PATH = Path(os.environ.get("EEI_WATCH_STATE", ROOT / ".eei_watch_state.json"))
RUN_LOG = Path(os.environ.get("EEI_WATCH_RUN_LOG", ROOT / ".eei_watch_runs.jsonl"))
# Bound the seen-accession memory (ring); one filing day is a few thousand.
MAX_SEEN = 20000

# One Atom <entry> block: form is the title prefix, CIK is the 10-digit paren
# group, accession rides in the <id> urn.
_ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
_TITLE_RE = re.compile(r"<title>\s*([^<]+?)\s*</title>", re.S)
_CIK_RE = re.compile(r"\((\d{10})\)")
_ACC_RE = re.compile(r"accession-number=([0-9-]+)")
# The getcurrent firehose is ~95% routine insider-ownership forms (3/4/5 and
# their /A amendments) plus Form 144 proposed sales, which never map to a
# material business event. Skip THOSE (exclude-list, not include-list) so we
# stay robust to getcurrent's form-label spelling differing from the
# submissions API (e.g. "SCHEDULE 13D/A" here vs "SC 13D" there) — anything
# not skipped is handed to enrich_one, which decides what becomes an event.
_SKIP_FORM_RE = re.compile(r"^(3|4|5)(/A)?$|^144$", re.I)


def parse_getcurrent(xml: str) -> list[tuple[str, str, str]]:
    """Return (form, cik10, accession) for each non-routine filing entry."""
    out: list[tuple[str, str, str]] = []
    for block in _ENTRY_RE.findall(xml):
        title = _TITLE_RE.search(block)
        cik = _CIK_RE.search(block)
        acc = _ACC_RE.search(block)
        if not (title and cik and acc):
            continue
        form = title.group(1).split(" - ", 1)[0].strip()
        if _SKIP_FORM_RE.match(form):
            continue
        try:
            cik10 = normalize_cik(cik.group(1))
        except ValueError:
            continue
        out.append((form, cik10, acc.group(1)))
    return out


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def save_state(seen: list[str]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps({"seen_accessions": seen[-MAX_SEEN:]}, ensure_ascii=False),
        encoding="utf-8",
    )


def universe_entity_for_ciks(conn, ciks: list[str]) -> dict[str, tuple[str, str]]:
    """Map cik10 -> (entity_id, canonical_name) for CIKs already in our universe.
    A filing for a CIK we don't track is ignored (we never invent entities from
    the firehose; the curated universe is the gate)."""
    if not ciks:
        return {}
    rows = conn.execute(
        """
        SELECT ei.value, e.id, e.canonical_name
        FROM entity_identifiers ei
        JOIN entities e ON e.id = ei.entity_id
        WHERE ei.scheme = 'cik' AND ei.value = ANY(%s)
        """,
        (ciks,),
    ).fetchall()
    return {r[0]: (str(r[1]), r[2]) for r in rows}


def one_poll(sec: SecClient, *, apply: bool) -> dict:
    started = datetime.now(UTC).isoformat()
    result: dict = {"started_at": started}

    status, body = sec.get(GETCURRENT_URL)
    if status != 200 or not body:
        result["error"] = f"getcurrent status {status}"
        result["finished_at"] = datetime.now(UTC).isoformat()
        return result

    entries = parse_getcurrent(body.decode("utf-8", errors="replace"))
    state = load_state()
    seen = list(state.get("seen_accessions", []))
    seen_set = set(seen)

    fresh = [(form, cik, acc) for (form, cik, acc) in entries if acc not in seen_set]
    result["feed_candidates"] = len(entries)
    result["fresh"] = len(fresh)
    if not fresh:
        # Nothing new since last poll; record the poll and return cheaply.
        result.update(matched_universe=0, enriched=0, finished_at=datetime.now(UTC).isoformat())
        _log(result)
        return result

    fresh_ciks = sorted({cik for (_f, cik, _a) in fresh})
    affected: dict[str, tuple[str, str]] = {}
    new_events = 0

    with connect_database() as conn:
        sec_src = source_id_for(conn, "sec_edgar")
        universe = universe_entity_for_ciks(conn, fresh_ciks)
        result["matched_universe"] = len(universe)
        for cik10, (entity_id, name) in universe.items():
            try:
                ev, _ind = enrich_one(conn, sec, sec_src, entity_id, name, cik10)
                new_events += ev
                if ev:
                    affected[entity_id] = (entity_id, name)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - one bad company must not stop the poll
                result.setdefault("warnings", []).append(f"{name} ({cik10}): {exc}")

    # Mark every fresh accession seen (even non-universe / zero-event ones) so we
    # never re-process it; the daily sweep owns completeness.
    for _f, _c, acc in fresh:
        if acc not in seen_set:
            seen.append(acc)
            seen_set.add(acc)
    save_state(seen)

    result["new_events"] = new_events
    result["enriched"] = len(affected)

    if apply and affected:
        publish_url = os.environ.get("EEI_PUBLISH_URL", "").strip()
        publish_token = os.environ.get("EEI_PUBLISH_TOKEN", "").strip()
        if publish_url and publish_token:
            try:
                push = push_incremental(
                    [eid for eid in affected], publish_url=publish_url, publish_token=publish_token
                )
                result["published"] = push
            except Exception as exc:  # noqa: BLE001 - publish retry next poll; DB already has it
                result["publish_error"] = str(exc)[:200]
        else:
            result["publish_skipped"] = "EEI_PUBLISH_URL/TOKEN unset"

    result["finished_at"] = datetime.now(UTC).isoformat()
    _log(result)
    return result


def _log(result: dict) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"[watch] {json.dumps(result, ensure_ascii=False)}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--loop", action="store_true", help="poll forever")
    p.add_argument("--interval-seconds", type=int, default=60)
    p.add_argument("--no-apply", action="store_true", help="enrich locally but do not push to D1")
    args = p.parse_args()

    sec = SecClient()
    try:
        if not args.loop:
            r = one_poll(sec, apply=not args.no_apply)
            return 0 if "error" not in r else 1
        print(f"[watch] loop mode, interval={args.interval_seconds}s")
        while True:
            try:
                one_poll(sec, apply=not args.no_apply)
            except Exception as exc:  # noqa: BLE001 - a watcher must never die
                print(f"[watch] poll error (continuing): {exc}")
            time.sleep(args.interval_seconds)
    finally:
        sec.close()


if __name__ == "__main__":
    raise SystemExit(main())
