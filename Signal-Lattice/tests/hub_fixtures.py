"""中枢、实时层、回测测试共用的合成研究产物。

不碰网络、不碰真实数据：用少量合成公司搭出「研究层产物」的样子（ResearchView，或者落盘成真实的目录结构），
每个测试只改自己关心的那一处。
"""

from __future__ import annotations

import json
import zlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from signal_lattice import hub
from signal_lattice.research_cycle import shortlist_from_records
from signal_lattice.research_view import ALL_BRANCHES, ENVIRONMENT_BRANCH, STOCK_BRANCHES, ResearchView, _rank_table, _slim

EVENT, BOTTLENECK, COMMERCIAL, FORESIGHT = STOCK_BRANCHES
NOW = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)
SNAPSHOT = "a" * 64


def sec_link(accession: str, *, cik: int = 1, supports: str = "INSIDER_BUY_OPPORTUNISTIC", date: str = "2026-09-20",
             summary: str = "内部人公开市场买入", dashed: bool = True) -> dict:
    url = "https://www.sec.gov/Archives/edgar/data/%d/%s/%s-index.htm" % (cik, accession.replace("-", ""), accession)
    link = {"url": url, "supports": supports, "published_date": date, "summary": summary}
    if dashed:
        link["accession"] = accession
    return link


def record(symbol: str, verdict: str = "ABSTAIN", *, label: str = "X", score: Optional[float] = 0.0, links: Sequence[Mapping] = (),
           reasons: Sequence[str] = ("理由",), name: Optional[str] = None, cap: float = 1.2e9, evidence: Optional[Mapping] = None) -> dict:
    return {"symbol": symbol, "cik": zlib.crc32(symbol.encode()) % 10_000_000, "name": name or symbol + " Inc", "market_cap_usd": cap, "verdict": verdict,
            "label": label, "score": score, "rank_key": score or 0.0, "reasons": list(reasons), "links": [dict(x) for x in links],
            "evidence": dict(evidence or {})}


def pool_entry(symbol: str, *, cap: float = 1.2e9, dollar_volume: float = 8e6, price: float = 10.0, exchange: str = "NYSE") -> dict:
    return {"symbol": symbol, "cik": zlib.crc32(symbol.encode()) % 10_000_000, "name": symbol + " Inc", "exchange": exchange, "market_cap_usd": cap,
            "price_usd": price, "shares_outstanding": cap / price, "median_dollar_volume_20d_usd": dollar_volume, "last_bar_day": "2026-09-29"}


def filler(prefix: str, n: int, *, base: float = 10.0) -> List[dict]:
    """给「全池前 10%」凑分母：n 个分数很低的无关公司。"""
    return [record("%s%02d" % (prefix, i), score=base - i * 0.01) for i in range(n)]


def build_view(records_by_branch: Mapping[str, Sequence[dict]], *, statuses: Optional[Mapping[str, str]] = None,
               pool_extra: Iterable[str] = (), generated_at: Optional[datetime] = None, checked_at: Optional[datetime] = None,
               fundamentals: Optional[Mapping[str, Any]] = None, shortlist: Optional[Sequence[str]] = None,
               problems: Sequence[str] = (), environment: Optional[Mapping] = None) -> ResearchView:
    """records_by_branch：分支 -> 逐股完整结论（record(...) 的列表）。缺省的分支视为「没有任何结论」。"""
    statuses = dict(statuses or {})
    view = ResearchView(directory=Path("."), as_of="2026-09-29", snapshot_sha256=SNAPSHOT,
                        generated_at=generated_at or (NOW - timedelta(hours=1)), checked_at=checked_at)
    symbols = set(pool_extra)
    for branch in ALL_BRANCHES:
        rows = list(records_by_branch.get(branch, []))
        symbols |= {r["symbol"] for r in rows}
        default = "ABSTAIN" if branch == FORESIGHT else "PASS"
        status = statuses.get(branch, default)
        view.receipts[branch] = {"branch_id": branch, "status": status, "reason": None if status == "PASS" else "test", "snapshot_hash": SNAPSHOT,
                                 "params_version": "1", "params_sha256": "b" * 64, "skill_version": "1",
                                 "verdict_counts": {"PASS": sum(r["verdict"] == "PASS" for r in rows),
                                                    "ABSTAIN": sum(r["verdict"] == "ABSTAIN" for r in rows),
                                                    "FAILED": sum(r["verdict"] == "FAILED" for r in rows)}}
        by_symbol = {r["symbol"]: r for r in rows}
        view.verdicts[branch] = {s: _slim(r) for s, r in by_symbol.items()}
        if branch in STOCK_BRANCHES:
            view.ranks[branch] = _rank_table(by_symbol)
    view.pool = {s: pool_entry(s) for s in sorted(symbols)}
    if shortlist is None:
        picked = {b: list(records_by_branch.get(b, [])) for b in STOCK_BRANCHES if statuses.get(b, "ABSTAIN" if b == FORESIGHT else "PASS") == "PASS"}
        view.shortlist = shortlist_from_records(picked)
    else:
        view.shortlist = [{"symbol": s, "name": s + " Inc", "market_cap_usd": view.pool[s]["market_cap_usd"], "cik": view.pool[s]["cik"]} for s in shortlist]
    view.fundamentals = dict(fundamentals or {})
    view.environment = dict(environment or {"regime": "NO_CONFIRMED_LEAD_LAG", "note": "test"})
    view.problems = list(problems)
    return view


def fresh_market(symbols: Iterable[str], price: float = 10.0) -> Dict[str, dict]:
    return {s: {"price": price, "quote_status": "FRESH", "source_time": "2026-09-30T10:59:00-04:00"} for s in symbols}


def standard_pool() -> Dict[str, List[dict]]:
    """一个能出建议的最小世界：ALPHA 事件航图 PASS + 商业机会排序支持；BETA 只有事件航图 PASS；其余是分母。"""
    a_event = sec_link("0000000001-26-000001", cik=11, date="2026-09-25")
    a_comm = sec_link("0000000002-26-000002", cik=11, supports="research_edge_speed", date="2026-08-05", summary="10-Q 营收")
    b_event = sec_link("0000000003-26-000003", cik=12, date="2026-09-10")
    event = [record("ALPHA", "PASS", label="POSITIVE_EVENT", score=70.0, links=[a_event], reasons=["有正向事件且近 90 天无增发/ATM/招股"]),
             record("BETA", "PASS", label="POSITIVE_EVENT", score=60.0, links=[b_event])] + filler("E", 20)
    commercial = [record("ALPHA", "ABSTAIN", label="SCREEN_FLAG", score=90.0, links=[a_comm]),
                  record("BETA", "ABSTAIN", label="SCREEN_FLAG", score=5.0, links=[a_comm])] + filler("C", 20, base=50.0)
    bottleneck = [record("ALPHA", "ABSTAIN", label="WATCH_EVIDENCE", score=3.0)] + filler("B", 20, base=40.0)
    return {EVENT: event, COMMERCIAL: commercial, BOTTLENECK: bottleneck}


def write_research_dir(root: Path, view_records: Mapping[str, Sequence[dict]], *, pool: Optional[Mapping[str, dict]] = None,
                       statuses: Optional[Mapping[str, str]] = None, generated_at: Optional[datetime] = None,
                       checked_at: Optional[datetime] = None, fundamentals: Optional[Mapping] = None,
                       as_of: str = "2026-09-29", snapshot: str = SNAPSHOT, hubinputs: bool = True) -> Path:
    """把合成结论落成研究层产物的真实目录结构（signal-lattice research 写出来的样子）。返回 out_dir。"""
    statuses = dict(statuses or {})
    day = root / as_of
    (day / "branches").mkdir(parents=True, exist_ok=True)
    digest = snapshot[:12]
    generated_at = generated_at or (NOW - timedelta(hours=1))
    receipts = []
    symbols = set()
    for branch in ALL_BRANCHES:
        rows = list(view_records.get(branch, []))
        symbols |= {r["symbol"] for r in rows}
        status = statuses.get(branch, "ABSTAIN" if branch == FORESIGHT else "PASS")
        folder = day / "branches" / branch
        folder.mkdir(parents=True, exist_ok=True)
        verdicts_file = folder / ("verdicts-%s.json" % digest)
        verdicts_file.write_text(json.dumps({"branch_id": branch, "snapshot_sha256": snapshot, "verdicts": rows, "meta": {
            "regime": "NO_CONFIRMED_LEAD_LAG", "note": "test"} if branch == ENVIRONMENT_BRANCH else {}}), "utf-8")
        counts = {"PASS": 0, "ABSTAIN": 0, "FAILED": 0}
        for r in rows:
            counts[r["verdict"]] += 1
        receipts.append({"branch_id": branch, "status": status, "reason": None if status == "PASS" else "test", "snapshot_hash": snapshot,
                         "params_version": "1", "params_sha256": "b" * 64, "skill_version": "1", "verdict_counts": counts,
                         "verdicts_file": str(verdicts_file), "started_at": "2026-09-30T00:00:00+00:00", "finished_at": "2026-09-30T00:10:00+00:00",
                         "duration_seconds": 600.0})
    picked = {b: list(view_records.get(b, [])) for b in STOCK_BRANCHES if statuses.get(b, "ABSTAIN" if b == FORESIGHT else "PASS") == "PASS"}
    shortlist = shortlist_from_records(picked)
    (day / ("cycle-%s.json" % digest)).write_text(json.dumps({"as_of": as_of, "snapshot_sha256": snapshot, "universe_count": len(symbols),
                                                             "receipts": receipts}), "utf-8")
    (day / ("shortlist-%s.json" % digest)).write_text(json.dumps({"as_of": as_of, "snapshot_sha256": snapshot, "generated_at": generated_at.isoformat(),
                                                                 "count": len(shortlist), "entries": shortlist}), "utf-8")
    pointer = {"as_of": as_of, "snapshot_sha256": snapshot, "cycle": "cycle-%s.json" % digest, "shortlist": "shortlist-%s.json" % digest,
               "hubinputs": "hubinputs-%s.json" % digest}
    if checked_at is not None:
        pointer["checked_at"] = checked_at.isoformat()
    if hubinputs:
        (day / ("hubinputs-%s.json" % digest)).write_text(json.dumps({
            "schema": "signal-lattice-hubinputs/1", "as_of": as_of, "snapshot_sha256": snapshot,
            "pool": list((pool or {s: pool_entry(s) for s in sorted(symbols)}).values()), "fundamentals": dict(fundamentals or {})}), "utf-8")
    (day / "latest.json").write_text(json.dumps(pointer), "utf-8")
    return root


def run_decision(view: ResearchView, *, market: Optional[Mapping] = None, weights: Optional[Mapping] = None, state: Optional[Mapping] = None,
                 now: datetime = NOW, liquidity_fn=None, quotes_available: bool = True) -> dict:
    market = market if market is not None else fresh_market([e["symbol"] for e in view.shortlist])
    return hub.decide(view, market, now=now, weights=weights, state=state, liquidity_fn=liquidity_fn, quotes_available=quotes_available)
