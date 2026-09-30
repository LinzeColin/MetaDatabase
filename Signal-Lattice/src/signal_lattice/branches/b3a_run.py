"""B3a 跑批：对真实候选池运行瓶颈与商业机会两个分支，落盘收据并打印验收摘要。

用法（产物目录都在仓库之外）：
  python -m signal_lattice.branches.b3a_run --run-dir <目录> [--as-of YYYY-MM-DD] [--text-max 250]

前置：目录里已有候选池快照 snap/universe-*.json、事实库 facts-b3a.sqlite（sec_inputs 入账）、
日线历史缓存 cache/bars800（sec_inputs.collect_history）。本脚本不再请求 SEC 的结构化接口，
只在瓶颈分支需要时按「候选短名单」逐家读一份申报原文（限速 ≤5 次/秒，总量有硬上限）。
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..evidence.factstore import FactStore
from ..evidence.sec_client import SecClient
from . import bottleneck as B
from . import commercial as C
from .fundamentals import Fundamentals, MarketInput, PeerContext, compute_fundamentals
from .sec_inputs import collect_history
from .textmarkers import TextMarkers, fetch_markers_for_row, latest_periodic_with_document


def load_snapshot(run_dir: Path) -> dict:
    paths = sorted(glob.glob(str(run_dir / "snap" / "universe-*.json")))
    if not paths:
        raise SystemExit("no universe snapshot under %s/snap" % run_dir)
    return json.loads(Path(paths[-1]).read_text("utf-8")) | {"_path": paths[-1]}


def needs_text(receipt, gates: dict) -> bool:
    """只有「除结构性约束外其余门都过了」的名字才值得读原文：原文标记不能替失败的门翻案。"""
    d = receipt.detail
    if receipt.verdict == "FAILED":
        return False
    dims = d["dimensions"]
    g = gates
    need = {"capture": g["capture_min"], "investability": g["investability_min"], "evidence": g["evidence_min"],
            "mispricing": g["mispricing_min"]}
    for dim, threshold in need.items():
        if not dims[dim]["verifiable"] or dims[dim]["score"] < threshold:
            return False
    return d["hard_flags"]["no_material_revenue_bridge"] is False and not d["hard_flags"]["unfunded_financing_gap"]


def run(run_dir: Path, as_of: Optional[str], text_max: int, cache_dir: Optional[Path] = None, log=print,
        reuse_fundamentals: bool = False) -> dict:
    cache_dir = Path(cache_dir) if cache_dir else run_dir / "cache"
    snapshot = load_snapshot(run_dir)
    as_of = as_of or snapshot["as_of_date"]
    entries = snapshot["entries"]
    store = FactStore(run_dir / "facts-b3a.sqlite")
    history = collect_history(entries, cache_dir / "bars800")
    log("universe %d names as_of %s; history for %d" % (len(entries), as_of, sum(1 for v in history.values() if v)))

    funds: Dict[str, Fundamentals] = {}
    cache_file = run_dir / ("fundamentals-%s-%s.pkl" % (as_of, snapshot["content_sha256"][:12]))
    if reuse_fundamentals and cache_file.is_file():
        import pickle
        funds = pickle.loads(cache_file.read_bytes())   # 仅本机调试复用：键含 as_of 与快照 hash
        log("fundamentals reused from %s" % cache_file.name)
    else:
        for index, entry in enumerate(entries, 1):
            market = MarketInput.from_entry(entry, [(d, c) for d, c in history.get(entry["symbol"], []) if d <= as_of])
            funds[entry["symbol"]] = compute_fundamentals(store, market, as_of)
            if index % 200 == 0:
                log("fundamentals %d/%d" % (index, len(entries)))
        if reuse_fundamentals:
            import pickle
            cache_file.write_bytes(pickle.dumps(funds))
    peers = PeerContext.build(funds.values(), C.DEFAULT_PARAMS["peers"]["min_group"])

    b_params, b_findings = B.load_bottleneck_params()
    c_params, c_findings = C.load_commercial_params()

    pass1 = {sym: B.score_bottleneck(store, f.market, as_of, b_params, b_findings, peers, None, f) for sym, f in funds.items()}
    shortlist = sorted((sym for sym, r in pass1.items() if needs_text(r, b_params["gates"])),
                       key=lambda sym: -(pass1[sym].detail["indicative_score"] or 0.0))
    log("bottleneck pass 1 done; %d names need original-text markers (limit %d)" % (len(shortlist), text_max))
    shortlist = shortlist[:text_max]

    markers: Dict[str, TextMarkers] = {}
    client = SecClient(cache_dir / "sec-text")

    rows = {sym: latest_periodic_with_document(store, funds[sym].cik, as_of) for sym in shortlist}   # SQLite 只在主线程读
    shortlist = [sym for sym in shortlist if rows[sym] is not None]

    def fetch(sym: str):
        return sym, fetch_markers_for_row(client, funds[sym].cik, rows[sym])

    with ThreadPoolExecutor(max_workers=4) as pool:
        for index, (sym, mk) in enumerate(pool.map(fetch, shortlist), 1):
            if mk is not None:
                markers[sym] = mk
            if index % 50 == 0:
                log("text markers %d/%d (SEC requests %d)" % (index, len(shortlist), client.requests_sent))
    (run_dir / "text-markers.json").write_text(json.dumps({s: m.to_dict() for s, m in markers.items()}, ensure_ascii=False, indent=1), "utf-8")

    bottleneck = {sym: (B.score_bottleneck(store, funds[sym].market, as_of, b_params, b_findings, peers, markers[sym], funds[sym])
                        if sym in markers else pass1[sym]) for sym in funds}
    commercial = {sym: C.score_commercial(store, f.market, as_of, c_params, c_findings, peers, f) for sym, f in funds.items()}
    (run_dir / "receipts-bottleneck.json").write_text(json.dumps([r.to_dict() for r in bottleneck.values()], ensure_ascii=False, indent=1), "utf-8")
    (run_dir / "receipts-commercial.json").write_text(json.dumps([r.to_dict() for r in commercial.values()], ensure_ascii=False, indent=1), "utf-8")
    return {"as_of": as_of, "universe": len(entries), "bottleneck": bottleneck, "commercial": commercial,
            "text_scanned": len(markers), "sec_requests_text": client.requests_sent, "snapshot": snapshot["_path"]}


def _first_link(receipt) -> str:
    links = receipt.detail.get("primary_links") or []
    return links[0]["url"] if links else "-"


def summarize(result: dict, out=print) -> None:
    out("as_of %s | snapshot %s" % (result["as_of"], result["snapshot"]))
    out("universe %d | text scanned %d (SEC requests for text %d)" % (result["universe"], result["text_scanned"], result["sec_requests_text"]))
    for name, receipts in (("bottleneck", result["bottleneck"]), ("commercial", result["commercial"])):
        values = list(receipts.values())
        counts = Counter(r.verdict for r in values)
        out("")
        out("== %s == 参与 %d 只 | PASS %d / ABSTAIN %d / FAILED %d" % (name, len(values), counts["PASS"], counts["ABSTAIN"], counts["FAILED"]))
        labels = Counter(r.label for r in values)
        out("labels: " + json.dumps(dict(labels.most_common()), ensure_ascii=False))
        reason_counts = Counter()
        for r in values:
            for reason in r.reasons:
                reason_counts[reason.split(":")[0] + (":" + reason.split(":")[1] if reason.startswith("DIMENSION_UNVERIFIABLE") else "")] += 1
        out("top reasons: " + json.dumps(dict(reason_counts.most_common(8)), ensure_ascii=False))
        if name == "bottleneck":
            ne: Dict[str, Dict[str, int]] = {}
            for r in values:
                for dim, fs in r.detail["factors"].items():
                    for factor, fr in fs.items():
                        bucket = ne.setdefault(dim, {}).setdefault(factor, 0)
                        ne[dim][factor] = bucket + (fr["rating"] == "NO_EVIDENCE")
            out("NO_EVIDENCE 比例（按维度，因子级；分母=%d 只）" % len(values))
            for dim, factors in ne.items():
                total = len(values) * len(factors)
                out("  %-13s 维度均值 %5.1f%% | " % (dim, 100.0 * sum(factors.values()) / total) + ", ".join(
                    "%s %.0f%%" % (k, 100.0 * v / len(values)) for k, v in factors.items()))
            dimv = Counter()
            for r in values:
                for dim, d in r.detail["dimensions"].items():
                    dimv[dim] += d["verifiable"]
            out("五维可核实只数: " + json.dumps({k: v for k, v in dimv.items()}, ensure_ascii=False))
        else:
            ne_base: Dict[str, int] = {}
            ne_risk: Dict[str, int] = {}
            for r in values:
                for k, fr in r.detail["base_dimensions"].items():
                    ne_base[k] = ne_base.get(k, 0) + (fr["rating"] == "NO_EVIDENCE")
                for k, fr in r.detail["risk_factors"].items():
                    ne_risk[k] = ne_risk.get(k, 0) + (fr["rating"] == "NO_EVIDENCE")
            out("NO_EVIDENCE 比例（分母=%d 只）" % len(values))
            out("  base: " + ", ".join("%s %.0f%%" % (k, 100.0 * v / len(values)) for k, v in ne_base.items()))
            out("  risk: " + ", ".join("%s %.0f%%" % (k, 100.0 * v / len(values)) for k, v in ne_risk.items()))
            out("E 级分布: " + json.dumps(dict(Counter(r.detail["maturity_code"] for r in values)), ensure_ascii=False))
        ranked = sorted(values, key=lambda r: -r.detail["rank_key"])[:10]
        out("前 10 名（PASS 在前；其余按%s）" % ("「最差的门离通过多远」gate_margin（非补偿排序，1.0=五个门都过）" if name == "bottleneck"
                                               else "decision_score"))
        for i, r in enumerate(ranked, 1):
            if name == "bottleneck":
                score = r.detail["final_score"] if r.detail["final_score"] is not None else "n/a"
                extra = "margin=%.2f final=%s block=%s" % (r.detail["gate_margin"], score, (r.reasons or ["-"])[0][:60])
            else:
                extra = "score=%s E=%s conf=%s" % (r.detail["decision_score"], r.detail["maturity_code"], r.detail["evidence_confidence"])
            out("%2d. %-6s %-30.30s cap $%.2fB  %-7s %-16s %s\n      %s" % (
                i, r.symbol, r.name, r.detail["market_cap_usd"] / 1e9, r.verdict, r.label, extra, _first_link(r)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--text-max", type=int, default=250)
    parser.add_argument("--reuse-fundamentals", action="store_true", help="调试用：按 as_of+快照 hash 缓存/复用基本面计算结果")
    parser.add_argument("--cache-dir", type=Path, default=None, help="日线/原文缓存目录，默认 <run-dir>/cache")
    args = parser.parse_args(argv)
    result = run(args.run_dir, args.as_of, args.text_max, args.cache_dir, reuse_fundamentals=args.reuse_fundamentals)
    summarize(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
