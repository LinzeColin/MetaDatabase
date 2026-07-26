#!/usr/bin/env python3
"""SEC daily-index sweep — the completeness backstop for the minute watcher.

The getcurrent watcher is fast but structurally lossy: it sees a 100-entry
window, and EDGAR publishes far more than 100 filings a minute in the 16:05 ET
burst. Anything that scrolls past between two polls is gone forever, and the
per-company enrich sweep will not find it either (that sweep only re-reads each
company's N most-recent filings, so it goes quiet once it has caught up).

EDGAR also publishes a complete, authoritative daily index — every filing
accepted that day, one line each:

    https://www.sec.gov/Archives/edgar/daily-index/<year>/QTR<q>/form.<YYYYMMDD>.idx

Sweeping it closes the gap by construction: for each day we walk the whole
index, keep the filings whose CIK is in our universe, and enrich those
companies. Days with no index (weekends, federal holidays) are recorded as
covered-and-empty so we never re-fetch them.

State: JSON at EEI_DAILY_INDEX_STATE (default <root>/.eei_daily_index_state.json),
holding the set of days already swept.

Usage:
  python -m scripts.authoritative.sec_daily_index                 # today + any gaps
  python -m scripts.authoritative.sec_daily_index --days-back 10  # widen the catch-up
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../EEI
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.authoritative.common import (  # noqa: E402
    SecClient,
    connect_database,
    source_id_for,
)
from scripts.authoritative.enrich_sec import enrich_one  # noqa: E402

INDEX_URL = (
    "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/form.{ymd}.idx"
)
STATE_PATH = Path(
    os.getenv("EEI_DAILY_INDEX_STATE", str(ROOT / ".eei_daily_index_state.json"))
)
RUN_LOG = Path(
    os.getenv("EEI_DAILY_INDEX_RUN_LOG", str(ROOT / ".eei_daily_index_runs.jsonl"))
)

# Ownership/insider churn (3/4/5) and 144 notices dominate the index by volume
# and are not material-disclosure events; the same exclusion the watcher uses.
SKIP_FORMS = {"3", "4", "5", "3/A", "4/A", "5/A", "144", "144/A"}

# Never sweep more days in one run than this, so a long outage catches up over
# several runs instead of hammering EDGAR (and blowing the D1 write budget) in
# a single burst.
MAX_DAYS_PER_RUN = 6


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("swept_days", [])
                return data
        except ValueError:
            pass
    return {"swept_days": []}


def save_state(state: dict) -> None:
    # Keep a bounded tail; older days are settled and never re-swept.
    state["swept_days"] = sorted(set(state.get("swept_days", [])))[-400:]
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def index_url_for(day: date) -> str:
    return INDEX_URL.format(
        year=day.year, quarter=(day.month - 1) // 3 + 1, ymd=day.strftime("%Y%m%d")
    )


def parse_index(text: str) -> set[str]:
    """Return the set of 10-digit CIKs with a material filing in this index.

    The .idx form file is whitespace-aligned:
    ``Form Type  Company Name  CIK  Date Filed  File Name``. Company names
    contain spaces (and some form types do too, e.g. "1-A POS"), so the only
    reliable anchors are the ends: the last field is the archive path, the one
    before it the filing date, and the one before that the CIK. The form type
    is the first token, which is enough for the exclusion set (3/4/5/144 are
    all single tokens).
    """
    ciks: set[str] = set()
    for line in text.splitlines():
        line = line.rstrip()
        if not line or ".txt" not in line:
            continue
        parts = line.split()
        if len(parts) < 4 or parts[0] in SKIP_FORMS:
            continue
        cik, filed = parts[-3], parts[-2]
        if not (cik.isdigit() and len(filed) == 8 and filed.isdigit()):
            continue
        ciks.add(cik.zfill(10))
    return ciks


def universe_entities_for_ciks(conn, ciks: set[str]) -> list[tuple[str, str, str]]:
    """Map CIKs to entities we already track. Never invents entities: the daily
    index covers all of EDGAR, and only the curated universe is in scope."""
    if not ciks:
        return []
    rows = conn.execute(
        """
        SELECT e.id::text, e.canonical_name, ei.value
        FROM entity_identifiers ei
        JOIN entities e ON e.id = ei.entity_id
        WHERE ei.scheme = 'cik' AND ei.value = ANY(%s)
        """,
        (sorted(ciks),),
    ).fetchall()
    return [(r[0], r[1], str(r[2]).zfill(10)) for r in rows]


def sweep_day(conn, sec: SecClient, sec_src: str, day: date, *, max_events: int) -> dict:
    url = index_url_for(day)
    status, body = sec.get(url)
    if status == 404:
        # No index for this day (weekend/holiday) — covered, and empty.
        return {"day": day.isoformat(), "index": "absent", "matched": 0, "events": 0}
    if status != 200 or not body:
        return {"day": day.isoformat(), "index": f"http_{status}", "matched": 0,
                "events": 0, "retry": True}

    ciks = parse_index(body if isinstance(body, str) else body.decode("utf-8", "replace"))
    targets = universe_entities_for_ciks(conn, ciks)
    events = 0
    for entity_id, name, cik10 in targets:
        try:
            made, _ind = enrich_one(
                conn, sec, sec_src, entity_id, name, cik10, max_events=max_events
            )
            events += made
        except Exception as exc:  # noqa: BLE001 - one bad company never stops the day
            print(f"[daily-index] WARN {name} ({cik10}): {exc}")
    conn.commit()
    return {
        "day": day.isoformat(),
        "index": "present",
        "index_ciks": len(ciks),
        "matched": len(targets),
        "events": events,
    }


def run(args, sec: SecClient) -> dict:
    started = datetime.now(UTC).isoformat()
    state = load_state()
    swept = set(state.get("swept_days", []))

    today = datetime.now(UTC).date()
    # Today's index is only complete after the filing day closes, so today is
    # always re-swept (cheap: enrich is idempotent) and never marked settled.
    candidates = [today - timedelta(days=n) for n in range(0, args.days_back + 1)]
    pending = [d for d in candidates if d == today or d.isoformat() not in swept]
    pending = sorted(pending)[-MAX_DAYS_PER_RUN:]

    result: dict = {
        "started_at": started,
        "days_considered": len(candidates),
        "days_swept": [],
        "matched_total": 0,
        "events_total": 0,
    }
    if not pending:
        result["finished_at"] = datetime.now(UTC).isoformat()
        return result

    with connect_database() as conn:
        sec_src = source_id_for(conn, "sec_edgar")
        for day in pending:
            day_result = sweep_day(conn, sec, sec_src, day, max_events=args.max_events)
            result["days_swept"].append(day_result)
            result["matched_total"] += day_result.get("matched", 0)
            result["events_total"] += day_result.get("events", 0)
            if day != today and not day_result.get("retry"):
                swept.add(day.isoformat())

    state["swept_days"] = sorted(swept)
    save_state(state)
    result["finished_at"] = datetime.now(UTC).isoformat()
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--days-back", type=int, default=4,
                   help="how far back to look for un-swept days")
    p.add_argument("--max-events", type=int, default=40,
                   help="material filings per matched company to walk back")
    args = p.parse_args()

    sec = SecClient()
    try:
        result = run(args, sec)
    finally:
        sec.close()

    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    print(f"[daily-index] {json.dumps(result, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
