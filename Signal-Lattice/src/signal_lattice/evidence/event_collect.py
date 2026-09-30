"""事件采集编排：候选池 → 申报索引 → 内部人数据集 → Form 4 原文 → submissions → 股数 → 日线。

    python -m signal_lattice.evidence.event_collect --run-dir DIR --universe snapshot.json \
        --as-of 2026-09-29 --stages index,dera,form4,owners,submissions,shares

每个阶段可重复运行（已抓过的不重抓）。全程只走 SEC 免 key 接口，进程内统一限速。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from .edgar_index import discover_filings
from .eventstore import EventStore
from .insider_dataset import list_dataset_urls, load_dataset_zip, pool_p_candidates
from .history_prices import BENCHMARK, BarStore, fetch_history
from .prospectus import label_424b5
from .insiders import _month_end, fetch_form4_batch, resolve_owner_history
from .sec_client import GLOBAL_LIMITER, RateLimiter, SecClient, SecFetchError, SecNotFound

# 与其他进程（另一条线也在调 SEC）共享 10 次/秒上限：本进程取 4 次/秒，留余量。
SHARED_SAFE_INTERVAL_SECONDS = 0.25

INDEX_FORMS = ("4", "8-K", "S-3", "S-3ASR", "S-1", "424B5", "SC 13D", "SCHEDULE 13D", "10-K", "10-Q")
DERA_FIRST_LABEL = "2021q4"
SHARES_FRAME_CONCEPT = ("dei", "EntityCommonStockSharesOutstanding", "shares")


def load_pool(snapshot_path: Path, max_cap_usd: float = 5e9, min_cap_usd: float = 3e8) -> tuple[list[dict], dict]:
    snapshot = json.loads(Path(snapshot_path).read_text("utf-8"))
    entries = [e for e in snapshot["entries"] if min_cap_usd <= e["market_cap_usd"] <= max_cap_usd]
    return entries, {k: snapshot.get(k) for k in ("as_of_date", "content_sha256", "count")}


def make_client(cache_dir: Path, interval: float = SHARED_SAFE_INTERVAL_SECONDS) -> SecClient:
    return SecClient(Path(cache_dir), limiter=RateLimiter(min_interval=interval), compress_cache=True)


def stage_index(client: SecClient, store: EventStore, pool_ciks: Sequence[int], start: date, as_of: date,
                log: Callable[[str], None]) -> dict:
    rows = discover_filings(client, start, as_of, INDEX_FORMS, pool_ciks, as_of=as_of)
    added = store.add_filings(rows)
    by_form = Counter(row.form for row in rows)
    log("index: %d pool filings %s (added %d), SEC requests %d" % (len(rows), dict(by_form), added, client.requests_sent))
    return dict(by_form)


def stage_dera(client: SecClient, store: EventStore, pool_ciks: Sequence[int], log: Callable[[str], None]) -> dict:
    urls = list_dataset_urls(client)
    done = {row[0] for row in store.db.execute("SELECT name FROM dataset_loaded")}
    results = {}
    for label in sorted(urls):
        if label < DERA_FIRST_LABEL or label in done:
            continue
        payload = client.get_bytes(urls[label], cache=False)
        results[label] = load_dataset_zip(store, payload, label, pool_ciks)
        log("dera %s: %s" % (label, results[label]))
    return results


def dera_coverage_end(store: EventStore) -> Optional[str]:
    """数据集里最晚的申报日（最新一季）。之后的 Form 4 只能走原文。"""
    row = store.db.execute("SELECT MAX(filed) FROM insider_p WHERE source LIKE 'dera:%'").fetchone()
    return row[0] if row and row[0] else None


def stage_form4(client: SecClient, store: EventStore, pool_ciks: Sequence[int], event_start: date, as_of: date,
                min_amount_usd: float, log: Callable[[str], None], limit: Optional[int] = None,
                workers: int = 4) -> dict:
    coverage = dera_coverage_end(store)
    targets: list = []
    filed_of = {}
    if coverage:
        until = min(coverage, as_of.isoformat())
        for accession, issuer in pool_p_candidates(store, pool_ciks, event_start.isoformat(), until, min_amount_usd):
            row = store.db.execute("SELECT filed FROM insider_p WHERE accession = ? LIMIT 1", (accession,)).fetchone()
            targets.append((accession, issuer, row[0]))
        log("form4: %d DERA-screened candidates up to %s" % (len(targets), until))
    gap_start = (date.fromisoformat(coverage) + timedelta(days=1)) if coverage else event_start
    gap_rows = store.filings_as_of(["4"], as_of, since=max(gap_start, event_start), ciks=list(pool_ciks))
    targets += [(r["accession"], r["cik"], r["filed"]) for r in gap_rows]
    log("form4: %d gap-period filings (>%s) fetched raw; total %d" % (len(gap_rows), coverage, len(targets)))
    stats = fetch_form4_batch(client, store, targets, workers=workers, limit=limit, log=log)
    return dict(stats)


def stage_owners(client: SecClient, store: EventStore, log: Callable[[str], None],
                 min_amount_usd: float, limit: Optional[int] = None) -> int:
    """对窗口内够格的买入，数据集里首次出现太晚的内部人，去 submissions 查真正的首次申报日。"""
    owners = []
    for row in store.db.execute(
            "SELECT DISTINCT b.owner_cik, b.first_trade FROM form4_buys b WHERE b.plan_10b5_1 = 0 AND b.amount_usd >= ?",
            (min_amount_usd,)):
        first = store.owner_first_filed(row["owner_cik"])
        need_end = _month_end(int(row["first_trade"][:4]) - 3, int(row["first_trade"][5:7]))
        if first is None or first > need_end:
            owners.append(row["owner_cik"])
    unique = list(dict.fromkeys(owners))
    log("owners needing history check: %d" % len(unique))
    return resolve_owner_history(client, store, unique, log=log, max_owners=limit)


def stage_submissions(client: SecClient, store: EventStore, pool_ciks: Sequence[int], event_start: date,
                      log: Callable[[str], None], limit: Optional[int] = None) -> int:
    count = 0
    for cik in pool_ciks[:limit] if limit else pool_ciks:
        try:
            payload = client.submissions(cik)
        except SecFetchError:
            continue
        extras = []
        recent = (payload.get("filings") or {}).get("recent") or {}
        oldest = min(recent.get("filingDate") or ["9999-12-31"])
        if oldest > event_start.isoformat():
            for page in (payload.get("filings") or {}).get("files") or []:
                if (page.get("filingTo") or "9999") >= event_start.isoformat():
                    try:
                        extras.append(client.get_json("https://data.sec.gov/submissions/" + page["name"]))
                    except SecFetchError:
                        pass
        store.add_submissions(cik, payload, extras)
        count += 1
        if count % 200 == 0:
            log("submissions %d/%d requests=%d" % (count, len(pool_ciks), client.requests_sent))
    return count


def stage_prospectus(client: SecClient, store: EventStore, pool_ciks: Sequence[int], event_start: date,
                     atm_terms: Sequence[str], log: Callable[[str], None], limit: Optional[int] = None) -> dict:
    """池内 424B5：读主文档头部，标出 ATM / 普通增发 / 债券等其他发行。需要先跑过 submissions（要主文档名）。"""
    rows = store.db.execute(
        "SELECT f.accession, f.cik, m.primary_document FROM filings f LEFT JOIN filing_meta m ON m.accession = f.accession "
        "WHERE f.form = '424B5' AND f.filed >= ? ORDER BY f.filed", (event_start.isoformat(),)).fetchall()
    counts = label_424b5(client, store, [(r[0], r[1], r[2]) for r in rows], atm_terms, log, limit)
    log("prospectus labels: %s" % counts)
    return counts


def shares_periods(start: date, end: date) -> list[str]:
    periods, year, quarter = [], start.year, (start.month - 1) // 3 + 1
    while (year, quarter) <= (end.year, (end.month - 1) // 3 + 1):
        periods.append("CY%dQ%dI" % (year, quarter))
        year, quarter = (year + 1, 1) if quarter == 4 else (year, quarter + 1)
    return periods


def stage_shares(client: SecClient, store: EventStore, pool_ciks: Sequence[int], start: date, as_of: date,
                 log: Callable[[str], None]) -> int:
    """dei 封面流通股按季度 frames 一次取全市场；每个季度桶一次请求。start 往前推一年，好算同比。"""
    pool = frozenset(int(c) for c in pool_ciks)
    total = 0
    for period in shares_periods(start - timedelta(days=400), as_of):
        try:
            frame = client.frames(*SHARES_FRAME_CONCEPT, period)
        except SecNotFound:
            continue
        rows = [(int(i["cik"]), i["end"], float(i["val"]), i["accn"]) for i in frame.get("data", [])
                if int(i["cik"]) in pool and i.get("val")]
        total += store.add_shares(rows)
    log("shares: %d observations" % total)
    return total


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="signal_lattice.evidence.event_collect")
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--universe", required=True, type=Path)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--event-start", default="2024-10-01")
    parser.add_argument("--max-cap", type=float, default=5e9)
    parser.add_argument("--min-amount", type=float, default=25_000.0)
    parser.add_argument("--stages", default="index,dera,form4,owners,submissions,shares")
    parser.add_argument("--db", default="events.sqlite")
    parser.add_argument("--cache", default="ev-cache")
    parser.add_argument("--limit", type=int, default=None, help="每阶段只处理前 N 项（调试）")
    args = parser.parse_args(argv)

    def log(message: str) -> None:
        print(datetime.now().strftime("%H:%M:%S"), message, flush=True)

    entries, meta = load_pool(args.universe, max_cap_usd=args.max_cap)
    pool = [int(e["cik"]) for e in entries]
    log("pool %d companies (cap <= %.1fB) from snapshot %s" % (len(pool), args.max_cap / 1e9, meta))
    as_of, event_start = date.fromisoformat(args.as_of), date.fromisoformat(args.event_start)
    client = make_client(args.run_dir / args.cache)
    store = EventStore(args.run_dir / args.db)
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    if "index" in stages:
        stage_index(client, store, pool, event_start, as_of, log)
    if "dera" in stages:
        stage_dera(client, store, pool, log)
    if "form4" in stages:
        log("form4 stats: %s" % stage_form4(client, store, pool, event_start, as_of, args.min_amount, log, args.limit))
    if "owners" in stages:
        log("owners checked: %d" % stage_owners(client, store, log, args.min_amount, args.limit))
    if "submissions" in stages:
        log("submissions fetched: %d" % stage_submissions(client, store, pool, event_start, log, args.limit))
    if "prospectus" in stages:
        from .prospectus import ATM  # noqa: F401  (标签常量在 prospectus 模块)
        atm_terms = json.loads((Path(__file__).resolve().parents[3] / "Stock_Skill" / "equity-event-atlas" / "runtime" / "params.json").read_text("utf-8"))["dilution"]["atm_terms"]
        stage_prospectus(client, store, pool, event_start, atm_terms, log, args.limit)
    if "shares" in stages:
        stage_shares(client, store, pool, event_start, as_of, log)
    if "prices" in stages:
        targets = [(BENCHMARK[0], BENCHMARK[1])] + [(e["symbol"], e["exchange"]) for e in entries]
        result = fetch_history(BarStore(args.run_dir / "ev-bars"), targets[:args.limit] if args.limit else targets, log=log)
        log("prices: ok=%d failed=%d skipped=%d %s" % (result["ok"], len(result["failed"]), result["skipped"], result["failed"][:5]))
    log("done. SEC requests this run: %d (304 hits %d); store rows: %s" % (
        client.requests_sent, client.cache_hits_304,
        {t: store.count(t) for t in ("filings", "filing_meta", "form4_fetch", "form4_buys", "insider_p", "owner_first")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
