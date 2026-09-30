"""五个分支在子进程里的入口：输入只有一份证据快照，输出是 {branch_status, branch_reasons, verdicts, meta}。

每个入口都只经 snapshot 读数据（事实库/事件库只读 immutable 打开），参数只读快照钉住的那一份 params 文件。
逐标的 verdict 统一为：symbol, cik, name, market_cap_usd, verdict(PASS/ABSTAIN/FAILED), label, score, rank_key, reasons, links, evidence[, detail]。
detail（全部因子）只给排名靠前与 PASS 的名字，其余只留精简 evidence，文件体量才可控。
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from .branches import bottleneck as B
from .branches import commercial as C
from .branches import event_atlas as EA
from .branches import foresight as F
from .branches import lead_lag as LL
from .branches.fundamentals import Fundamentals, MarketInput, PeerContext, compute_fundamentals
from .branches.structure_factors import StructureEvidence

BOTTLENECK, COMMERCIAL, EVENT_ATLAS, FORESIGHT, LEAD_LAG = (
    "bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas", "equity-foresight-signal",
    "global-equity-lead-lag-atlas")
FULL_DETAIL_TOP_N = 40


def _links(detail_links: Sequence[Mapping], limit: int = 6) -> List[dict]:
    return [dict(link) for link in list(detail_links)[:limit]]


def fundamentals_for_entries(facts: Any, bar_store: Any, entries: Sequence[Mapping], as_of: str,
                             log: Callable[[str], None] = lambda message: None) -> Dict[str, Fundamentals]:
    """逐只算 as_of 那一天可见的基本面。实盘（as_of = 快照日）与回测（as_of = 历史月末）走同一个函数。"""
    funds: Dict[str, Fundamentals] = {}
    for index, entry in enumerate(entries, 1):
        rows = bar_store.load(entry["symbol"]) or []
        history = [(row[0], float(row[1])) for row in rows if row[0] <= as_of]
        funds[entry["symbol"]] = compute_fundamentals(facts, MarketInput.from_entry(entry, history), as_of)
        if index % 300 == 0:
            log("fundamentals %d/%d" % (index, len(entries)))
    return funds


def compute_pool_fundamentals(snapshot: Any, log: Callable[[str], None]) -> Dict[str, Fundamentals]:
    facts = snapshot.facts()
    try:
        return fundamentals_for_entries(facts, snapshot.bar_store(), snapshot.entries, snapshot.as_of, log)
    finally:
        facts.close()


def _receipt_verdict(receipt: Any, score: Optional[float], slim: Mapping) -> dict:
    d = receipt.detail
    return {"symbol": receipt.symbol, "cik": receipt.cik, "name": receipt.name, "market_cap_usd": d["market_cap_usd"],
            "verdict": receipt.verdict, "label": receipt.label, "score": score, "rank_key": d["rank_key"],
            "reasons": list(receipt.reasons), "links": _links(d.get("primary_links") or []), "evidence": dict(slim)}


def _attach_full_detail(records: List[dict], receipts: Mapping[str, Any]) -> None:
    ranked = sorted(records, key=lambda r: -r["rank_key"])
    keep = {r["symbol"] for r in ranked[:FULL_DETAIL_TOP_N]} | {r["symbol"] for r in records if r["verdict"] == "PASS"}
    for record in records:
        if record["symbol"] in keep:
            record["detail"] = receipts[record["symbol"]].detail


def _branch_envelope(verdicts: List[dict], meta: Mapping, params_findings: Sequence[Mapping]) -> dict:
    reasons = [item["code"] for item in params_findings]
    return {"branch_status": "PASS", "branch_reasons": reasons, "verdicts": verdicts, "meta": dict(meta)}


def bottleneck_receipts(facts: Any, funds: Mapping[str, Fundamentals], structure: Mapping[int, Sequence[Any]], params: Mapping,
                        findings: Sequence[Mapping], as_of: str) -> Dict[str, Any]:
    peers = PeerContext.build(funds.values(), C.DEFAULT_PARAMS["peers"]["min_group"])
    receipts: Dict[str, Any] = {}
    for symbol, f in funds.items():
        filings = [x for x in structure.get(f.cik, []) if x.filed <= as_of]     # 结构性原文只用 as_of 之前已申报的
        receipts[symbol] = B.score_bottleneck(facts, f.market, as_of, params, findings, peers, None, f,
                                              StructureEvidence(filings) if filings else None)
    return receipts


def bottleneck_records(receipts: Mapping[str, Any]) -> List[dict]:
    verdicts = []
    for symbol, r in receipts.items():
        d = r.detail
        score = d["final_score"] if d["final_score"] is not None else d["indicative_score"]
        slim = {"final_score": d["final_score"], "indicative_score": d["indicative_score"], "gate_margin": d["gate_margin"],
                "gates": d["gates"], "hard_flags": d["hard_flags"], "core_quality": d["core_quality"],
                "dimensions": {k: {"score": v["score"], "coverage": v["coverage"], "verifiable": v["verifiable"]} for k, v in d["dimensions"].items()},
                "no_evidence_ratio": d["no_evidence_ratio"], "duration": d["duration"]["status"],
                "structure": None if d["structure_text"] is None else {"counts": d["structure_text"]["counts"], "risks": d["structure_text"]["risks"]}}
        verdicts.append(_receipt_verdict(r, score, slim))
    return verdicts


def run_bottleneck(snapshot: Any, log: Callable[[str], None]) -> dict:
    params_path = snapshot.params_file(BOTTLENECK)
    params, findings = B.load_bottleneck_params(params_path)
    funds = compute_pool_fundamentals(snapshot, log)
    structure = snapshot.structure()
    facts = snapshot.facts()
    receipts = bottleneck_receipts(facts, funds, structure, params, findings, snapshot.as_of)
    facts.close()
    verdicts = bottleneck_records(receipts)
    _attach_full_detail(verdicts, receipts)
    meta = {"params_version": params["params_version"], "params_findings": findings, "universe": len(funds),
            "structure_companies": len([1 for f in funds.values() if structure.get(f.cik)]),
            "factor_no_evidence": _factor_no_evidence(receipts)}
    return _branch_envelope(verdicts, meta, findings)


def _factor_no_evidence(receipts: Mapping[str, Any]) -> dict:
    """按维度/因子统计 NO_EVIDENCE 占比（分母 = 全池）。"""
    table: Dict[str, Dict[str, int]] = {}
    for r in receipts.values():
        for dim, factors in r.detail["factors"].items():
            for name, fr in factors.items():
                table.setdefault(dim, {}).setdefault(name, 0)
                table[dim][name] += fr["rating"] == "NO_EVIDENCE"
    n = len(receipts)
    return {dim: {name: round(count / n, 4) for name, count in factors.items()} for dim, factors in table.items()}


def commercial_receipts(facts: Any, funds: Mapping[str, Fundamentals], params: Mapping, findings: Sequence[Mapping],
                        as_of: str) -> Dict[str, Any]:
    peers = PeerContext.build(funds.values(), params["peers"]["min_group"])
    return {symbol: C.score_commercial(facts, f.market, as_of, params, findings, peers, f) for symbol, f in funds.items()}


def commercial_records(receipts: Mapping[str, Any]) -> List[dict]:
    verdicts = []
    for symbol, r in receipts.items():
        d = r.detail
        slim = {"decision_score": d["decision_score"], "base_score": d["base_score"], "evidence_confidence": d["evidence_confidence"],
                "risk_deduction": d["risk_deduction"], "maturity_code": d["maturity_code"], "status": d["status"],
                "no_evidence_ratio": d["no_evidence_ratio"], "falsifiers": d["falsifiers"]}
        verdicts.append(_receipt_verdict(r, d["decision_score"], slim))
    return verdicts


def run_commercial(snapshot: Any, log: Callable[[str], None]) -> dict:
    params_path = snapshot.params_file(COMMERCIAL)
    params, findings = C.load_commercial_params(params_path)
    funds = compute_pool_fundamentals(snapshot, log)
    facts = snapshot.facts()
    receipts = commercial_receipts(facts, funds, params, findings, snapshot.as_of)
    facts.close()
    verdicts = commercial_records(receipts)
    _attach_full_detail(verdicts, receipts)
    meta = {"params_version": params["params_version"], "params_findings": findings, "universe": len(funds)}
    return _branch_envelope(verdicts, meta, findings)


def event_atlas_records(company_verdicts: Sequence[Mapping]) -> List[dict]:
    """事件航图 evaluate_company 的结果 -> 分支统一的逐股结论。实盘与回测共用。"""
    verdicts = []
    for v in company_verdicts:
        links = [{"url": e["url"], "supports": e["kind"], "published_date": e["published_date"], "summary": e["summary"]}
                 for e in v["evidence"] if e.get("url")]
        seen, unique = set(), []
        for link in links:
            if link["url"] not in seen:
                seen.add(link["url"])
                unique.append(link)
        verdict = v["verdict"]
        positives = [e for e in v["evidence"] if e["kind"] in ("INSIDER_BUY_OPPORTUNISTIC", "INSIDER_CLUSTER", "ACTIVIST_13D")]
        label = {"PASS": "POSITIVE_EVENT", "FAILED": "DILUTION_VETO"}.get(verdict, "NO_QUALIFYING_EVENT")
        verdicts.append({"symbol": v["symbol"], "cik": v["cik"], "name": v["name"], "market_cap_usd": v["market_cap_usd"],
                         "verdict": verdict, "label": label, "score": v["score"],
                         "rank_key": (3000.0 if verdict == "PASS" else 1000.0 if verdict == "ABSTAIN" else 0.0) + v["score"]
                                     + min(len(v["events_recent"]), 12) * 0.01,
                         "reasons": [v["reason"]], "links": _links(unique),
                         "evidence": {"invalidation_risk": v["invalidation_risk"], "invalidation_conditions": v["invalidation_conditions"],
                                      "insider_window": v["insider_window"], "baseline": v["baseline"],
                                      "positive_events": [{"kind": e["kind"], "summary": e["summary"], "url": e["url"]} for e in positives],
                                      "events_recent": v["events_recent"]}})
    return verdicts


def run_event_atlas(snapshot: Any, log: Callable[[str], None]) -> dict:
    params_path = snapshot.params_file(EVENT_ATLAS)
    params = EA.load_params(params_path) if params_path else EA.load_params()
    store, bar_store = snapshot.events(), snapshot.bar_store()
    event_start = snapshot.document.get("collection", {}).get("event_start", "2024-10-01")
    result = EA.run(store, snapshot.entries, bar_store, snapshot.as_of, params, event_start)
    store.close()
    verdicts = event_atlas_records(result["verdicts"])
    meta = {"params_version": params["params_version"], "event_start": event_start, "events": len(result["events"]),
            "events_by_kind": EA.counts_by_family(result["events"], event_start)["by_kind"],
            "study": result["study"], "bars_loaded": result["bars_loaded"], "benchmark_available": result["benchmark_available"]}
    return _branch_envelope(verdicts, meta, [])


def run_foresight(snapshot: Any, log: Callable[[str], None]) -> dict:
    params_path = snapshot.params_file(FORESIGHT)
    params, findings = F.load_params(params_path)
    output = F.run(snapshot, params, log)
    output["meta"]["params_version"] = params["params_version"]
    output["meta"]["params_findings"] = findings
    if findings and output["branch_status"] == "PASS":
        output["branch_reasons"] = [f["code"] for f in findings]
    return output


def run_lead_lag(snapshot: Any, log: Callable[[str], None]) -> dict:
    bars = snapshot.market_environment_bars()
    if not bars.get(LL.SOURCE_SYMBOL):
        return {"branch_status": "ABSTAIN", "branch_reasons": ["SOURCE_BARS_MISSING:%s" % LL.SOURCE_SYMBOL], "verdicts": [], "meta": {}}
    verdicts = LL.evaluate_lead_lag_verdicts(bars)
    records, directional = [], {}
    for v in verdicts:
        confirmed = v.participation_status == "COLD_START_ELIGIBLE"
        records.append({"symbol": v.symbol, "cik": None, "name": v.symbol, "market_cap_usd": None,
                        "verdict": "PASS" if confirmed else "ABSTAIN", "label": v.participation_status, "score": round(v.confidence, 4),
                        "rank_key": v.confidence, "reasons": [v.counter_evidence], "links": [],
                        "evidence": {"direction": v.direction, "confidence": v.confidence, "window_used": v.window_used,
                                     "invalidation": v.invalidation, "details": v.evidence}})
        if v.symbol in LL.TARGETS:
            directional[v.symbol] = {"direction": v.direction, "participation": v.participation_status}
    confirmed_any = any(d["participation"] == "COLD_START_ELIGIBLE" for d in directional.values())
    meta = {"role": "MARKET_ENVIRONMENT_INPUT_NOT_STOCK_PICKING",
            "regime": "CONFIRMED_LEAD_LAG_DIRECTION" if confirmed_any else "NO_CONFIRMED_LEAD_LAG", "targets": directional,
            "note": "全球联动只作市场环境输入（风险偏好开关），不单独选股；统计相关不证明因果"}
    return {"branch_status": "PASS", "branch_reasons": [], "verdicts": records, "meta": meta}


ENTRIES: Dict[str, str] = {
    BOTTLENECK: "signal_lattice.branch_entries:run_bottleneck",
    COMMERCIAL: "signal_lattice.branch_entries:run_commercial",
    EVENT_ATLAS: "signal_lattice.branch_entries:run_event_atlas",
    FORESIGHT: "signal_lattice.branch_entries:run_foresight",
    LEAD_LAG: "signal_lattice.branch_entries:run_lead_lag",
}
# 每个分支读快照哪些大数据项（子进程读之前会核对 hash）与资源上限
DATA_NEEDS: Dict[str, tuple] = {
    BOTTLENECK: ("facts_db", "bars", "structure"),
    COMMERCIAL: ("facts_db", "bars"),
    EVENT_ATLAS: ("events_db", "bars"),
    FORESIGHT: ("facts_db", "events_db", "bars"),
    LEAD_LAG: (),
}
LIMITS: Dict[str, dict] = {
    BOTTLENECK: {"memory_mb": 1536, "cpu_seconds": 3000, "timeout_seconds": 4000},
    COMMERCIAL: {"memory_mb": 1536, "cpu_seconds": 3000, "timeout_seconds": 4000},
    EVENT_ATLAS: {"memory_mb": 1536, "cpu_seconds": 3000, "timeout_seconds": 4000},
    FORESIGHT: {"memory_mb": 1536, "cpu_seconds": 5400, "timeout_seconds": 7200},
    LEAD_LAG: {"memory_mb": 512, "cpu_seconds": 600, "timeout_seconds": 900},
}


def default_specs() -> list:
    from .branch_runner import BranchSpec
    return [BranchSpec(branch_id, ENTRIES[branch_id], DATA_NEEDS[branch_id], **LIMITS[branch_id]) for branch_id in ENTRIES]
