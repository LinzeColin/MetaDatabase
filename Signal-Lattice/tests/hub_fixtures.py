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


# 固定夹具里研究层收据的参数版本与 sha256（build_view / write_research_dir 写的都是这一对）；夹具回测报告绑定的就是它们。
FIXTURE_PARAMS = {"params_version": "1", "params_sha256": "b" * 64}
FIXTURE_BINDING = hub.rule_binding({b: FIXTURE_PARAMS for b in hub.BACKTEST_BOUND_BRANCHES})
MONTHS_2025 = ["2024-12-31", "2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30", "2025-05-30", "2025-06-30", "2025-07-31", "2025-08-29",
               "2025-09-30", "2025-10-31", "2025-11-28", "2025-12-31", "2026-01-30", "2026-02-27", "2026-03-31", "2026-04-30", "2026-05-29",
               "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"]


def backtest_report(*, windows: int = 20, formal_iwm: float = 0.03, formal_control: float = 0.02, placebo_iwm: float = -0.01,
                    hit_rate: float = 0.6, generated_at: str = "2026-09-30T00:00:00+00:00", binding: Optional[dict] = "FIXTURE",
                    placebo_windows: Optional[int] = None, placebo_offset: int = 0) -> dict:
    """私有完整回测报告里中枢自证门读的那几个字段（默认：全部达标、绑定夹具里的规则版本与参数、刚生成）。
    months：每个月一行，正式与安慰剂各有一个已成熟 20 日结果的唯一建议——自证门要在「对齐的月份」上比安慰剂。
    placebo_windows：安慰剂只有这么多个月有结果；placebo_offset：安慰剂的月份整体往后错这么多个月（不与正式对齐）。"""
    def block(iwm, control, rate):
        return {"windows": windows, "excess_vs_iwm": {"n": windows, "mean": iwm, "hit_rate": rate},
                "excess_vs_control": {"n": windows, "mean": control, "hit_rate": rate}}
    placebo_windows = windows if placebo_windows is None else placebo_windows
    months = []
    for index, day in enumerate(MONTHS_2025):
        row = {"as_of": day}
        if index < windows:
            row["actual"] = {"pick": {"outcomes": {"20": {"excess_vs_iwm": formal_iwm, "excess_vs_control": formal_control}}}}
        placebo_index = index - placebo_offset
        if 0 <= placebo_index < placebo_windows:
            row["placebo"] = {"pick": {"outcomes": {"20": {"excess_vs_iwm": placebo_iwm, "excess_vs_control": placebo_iwm}}}}
        months.append(row)
    return {"schema": "signal-lattice-hub-backtest/1", "generated_at": generated_at, "oos_windows": windows,
            "binding": FIXTURE_BINDING if binding == "FIXTURE" else binding, "months": months,
            "summary": {"actual": {"pick_20": block(formal_iwm, formal_control, hit_rate)}, "placebo": {"pick_20": block(placebo_iwm, placebo_iwm, 0.4)}}}


def gate(report: Optional[Mapping] = None, stats: Optional[Mapping] = None, *, now: datetime = NOW, binding: Optional[Mapping] = FIXTURE_BINDING) -> dict:
    """带着「当前规则绑定」和「当前时间」调用规则自证门（线上就是这样调的）。"""
    return hub.proof_gate(report, stats, expected_binding=binding, now=now)


def forward_stats(*, settled: int = 10, hits: int = 7, mean_excess: float = 0.02, formal: int = 0) -> dict:
    return {"settled": settled, "shadow_settled": settled - formal, "formal_settled": formal, "hits": hits, "mean_excess": mean_excess}


def seed_shadow_evidence(ledger_path, *, settled: int = 8, hits: Optional[int] = None, excess: float = 0.03) -> None:
    """往记分簿里直接写入 settled 条已结算（20 日）的影子候选，用来让规则自证门的 (b) 前向证据达标（或按参数不达标）。

    这些是「独立样本」：每条一只不同的股票，持有窗口（入场日到出场日）互相错开 30 个日历日、互不重叠，
    并且带着新口径（下一交易日入场、扣成本）的 entry_day——前向证据只数这样的行。"""
    from signal_lattice.ledger import Ledger
    hits = settled if hits is None else hits
    ledger = Ledger(ledger_path)
    try:
        with ledger.db:
            for i in range(settled):
                decision = datetime(2026, 1, 5) + timedelta(days=30 * i)
                day, entry, exit_ = ((decision + timedelta(days=d)).date().isoformat() for d in (0, 1, 29))
                ledger.db.execute(
                    "INSERT INTO shadow_record (trading_day, recorded_at, symbol, name, market_cap_usd, decision_json, supporters_json, snapshot_sha256, "
                    "close_price, iwm_close) VALUES (?,?,?,?,?,?,?,?,?,?)", (day, day + "T21:00:00+00:00", "SH%02d" % i, "Shadow %d" % i, 1.2e9, "{}", "[]", "a" * 64, 10.0, 200.0))
                record_id = ledger.db.execute("SELECT id FROM shadow_record WHERE trading_day = ?", (day,)).fetchone()[0]
                hit = i < hits
                ledger.db.execute(
                    "INSERT INTO shadow_settlement (record_id, horizon, exit_day, settled_at, exit_close, iwm_exit_close, stock_return, iwm_return, "
                    "excess_vs_iwm, hit, entry_day, entry_close, iwm_entry_close) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (record_id, 20, exit_, "2026-09-30T21:00:00+00:00", 10.5, 201.0, 0.05, 0.005, excess if hit else -excess, 1 if hit else 0,
                     entry, 10.0, 200.0))
    finally:
        ledger.close()


def open_proof() -> dict:
    """一个打开着的规则自证门（回测证据达标）。"""
    opened = gate(backtest_report(), None)
    assert opened["open"] and opened["opened_by"] == ["BACKTEST"]
    return opened


def closed_proof() -> dict:
    """与真实产物同一形状：回测 20 个窗口、正式 20 日 -3.9%、安慰剂反而 +2.4%；影子候选 0 条。"""
    return gate(backtest_report(formal_iwm=-0.0393, formal_control=-0.0319, placebo_iwm=0.0238, hit_rate=0.3), forward_stats(settled=0, hits=0, mean_excess=0.0))


def run_decision(view: ResearchView, *, market: Optional[Mapping] = None, weights: Optional[Mapping] = None, state: Optional[Mapping] = None,
                 now: datetime = NOW, liquidity_fn=None, quotes_available: bool = True, proof: Optional[Mapping] = "OPEN") -> dict:
    """默认给一个打开的规则自证门：这些测试要验的是逐股规则，不是自证门（自证门的测试在 test_proof_gate.py）。"""
    market = market if market is not None else fresh_market([e["symbol"] for e in view.shortlist])
    return hub.decide(view, market, now=now, weights=weights, state=state, liquidity_fn=liquidity_fn, quotes_available=quotes_available,
                      proof=open_proof() if proof == "OPEN" else proof)
