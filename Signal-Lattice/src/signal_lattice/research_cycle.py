"""研究层管线：universe 快照 -> 事实/事件增量采集 -> 不可变证据快照 -> 5 个分支各自在隔离子进程里运行 -> 收据与结论落盘 -> shortlist。

    signal-lattice research --work-dir DIR --out-dir DIR [--offline] [--force] ...

顺序（北极星合同的研究层部分）：
 1. 读 Stock_Skill Registry 与各 params：校验版本与 hash，坏了/断网用 Last-Known-Good（params_registry）；
 2. 候选池快照（<= 50 亿美元本土申报人，已有足够新的快照就复用，不重复请求）；
 3. 增量采集（只取上次之后新出现的申报/Form 4/正文，全程 SEC <= 4 次/秒、请求数打进日志）；
 4. 生成不可变证据快照 evidence-<日期>-<hash>.json（候选池、Lazy Prices、市场环境日线、参数版本与 hash、数据文件 hash）；
 5. 向所有 Active Skill 分发同一份快照，每个分支独立子进程（branch_runner），收集 PASS/ABSTAIN/FAILED 收据；
 6. shortlist：任一分支 PASS 的并集，加各分支非 FAILED、分数 > 0 的前 30 名，最多 60 只，供实时层使用。
幂等：同一份快照（内容 hash 相同）已经跑完就直接复用结果，不再启动分支、不再重复计数；同一天数据没变，采集阶段的 SEC 请求数为 0。
全球联动分支沿用 lead_lag.py，只提供市场环境（风险偏好），不选股。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from . import branch_entries
from .branch_runner import BranchReceipt, BranchSpec, run_branches
from .evidence.eventstore import EventStore
from .evidence.factstore import FactStore
from .evidence.history_prices import BENCHMARK, BarStore
from .evidence.sec_client import RateLimiter, SecClient
from .evidence.structure_text import FilingExtraction
from .evidence_snapshot import BENCHMARK_SYMBOL, build_body, load_snapshot, write_snapshot, write_structure_file
from .params_registry import ParamsResolver, Resolution, http_fetcher

SEC_MAX_REQUESTS_PER_SECOND = 4
SEC_INTERVAL_SECONDS = 1.0 / SEC_MAX_REQUESTS_PER_SECOND
SHORTLIST_TOP_N = 30
SHORTLIST_MAX = 60
STOCK_BRANCHES = ("bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas", "equity-foresight-signal")
MARKET_ENV_SYMBOLS = ("usSPY", "sh000300", "hk02800")


@dataclass
class CycleConfig:
    project_root: Path
    work_dir: Path                       # 状态：params/ universe/ snapshots/ tmp/
    out_dir: Path                        # 产物：<out_dir>/<as_of>/
    facts_db: Path
    events_db: Path
    bars_dir: Path
    text_cache_dir: Path
    structure_cache_dir: Path
    sec_cache_dir: Path
    text_similarity_path: Optional[Path] = None
    universe_snapshot: Optional[Path] = None
    universe_max_age_hours: float = 20.0
    ref: str = "main"
    offline: bool = False
    event_start: str = "2024-10-01"
    max_parallel: int = 1
    force: bool = False
    skip_collect: bool = False
    max_structure_requests: int = 3000
    sec_interval: float = SEC_INTERVAL_SECONDS
    min_insider_purchase_usd: float = 25_000.0
    branch_specs: Optional[List[BranchSpec]] = None
    python: Optional[str] = None


@dataclass
class Collected:
    universe_path: Path
    universe: dict
    structure_by_cik: Dict[int, List[FilingExtraction]]
    text_similarity: dict
    market_environment: Dict[str, list]
    stats: Dict[str, Any]


class Hooks:
    """网络相关的步骤放在这里，测试可以替换成合成数据。"""

    def universe(self, cfg: CycleConfig, log: Callable[[str], None]) -> Tuple[Path, dict]:
        raise NotImplementedError

    def collect(self, cfg: CycleConfig, universe_path: Path, universe: dict, log: Callable[[str], None]) -> Collected:
        raise NotImplementedError


# ---- 真实数据的采集 ------------------------------------------------------------------
def latest_universe_snapshot(directory: Path) -> Optional[Path]:
    paths = sorted(Path(directory).glob("universe-*.json"), key=lambda p: p.stat().st_mtime)
    return paths[-1] if paths else None


def snapshot_age_hours(snapshot: Mapping) -> float:
    generated = datetime.fromisoformat(snapshot["generated_at"])
    return (datetime.now(timezone.utc) - generated).total_seconds() / 3600.0


class LiveHooks(Hooks):
    def universe(self, cfg: CycleConfig, log: Callable[[str], None]) -> Tuple[Path, dict]:
        if cfg.universe_snapshot is not None:
            path = Path(cfg.universe_snapshot)
            return path, json.loads(path.read_text("utf-8"))
        directory = cfg.work_dir / "universe"
        newest = latest_universe_snapshot(directory)
        if newest is not None:
            snapshot = json.loads(newest.read_text("utf-8"))
            if snapshot_age_hours(snapshot) <= cfg.universe_max_age_hours:
                log("universe: reuse %s (age %.1fh <= %.0fh)" % (newest.name, snapshot_age_hours(snapshot), cfg.universe_max_age_hours))
                return newest, snapshot
        if cfg.offline:
            raise RuntimeError("离线模式且没有足够新的候选池快照")
        from . import universe as universe_module
        store = FactStore(cfg.facts_db)
        try:
            path, snapshot, report = universe_module.build(directory, cfg.work_dir / "universe-cache", log=log, store=store)
        finally:
            store.close()
        log("universe: built %s (%d names)" % (path.name, snapshot["count"]))
        return path, snapshot

    # -- 采集 ----------------------------------------------------------------
    def collect(self, cfg: CycleConfig, universe_path: Path, universe: dict, log: Callable[[str], None]) -> Collected:
        from .evidence import event_collect as EC
        from .evidence.structure_collect import collect_structure
        from .evidence.structure_text import ExtractionCache
        from .evidence.text_similarity import TextCache
        from .branches.sec_inputs import prune_companyfacts

        as_of = date.fromisoformat(universe["as_of_date"])
        entries = universe["entries"]
        pool = [int(e["cik"]) for e in entries]
        client = SecClient(cfg.sec_cache_dir, limiter=RateLimiter(min_interval=cfg.sec_interval), compress_cache=True)
        stats: Dict[str, Any] = {"as_of": as_of.isoformat(), "pool": len(pool)}
        facts, events = FactStore(cfg.facts_db), EventStore(cfg.events_db)
        bar_store = BarStore(cfg.bars_dir)
        try:
            if not cfg.skip_collect and not cfg.offline:
                stats.update(self._incremental_sec(cfg, client, facts, events, pool, as_of, prune_companyfacts, EC, log))
                stats["prices"] = self._refresh_bars(cfg, bar_store, entries, as_of, log)
            text_cache, extraction_cache = TextCache(cfg.text_cache_dir), ExtractionCache(cfg.structure_cache_dir)
            if cfg.offline:
                structure_stats = {"skipped": "offline"}
                by_cik = _structure_from_cache(facts, pool, universe["as_of_date"], extraction_cache)
            else:
                result = collect_structure(client, facts, pool, universe["as_of_date"], text_cache, extraction_cache,
                                           fetch_workers=4, parse_workers=3, max_requests=cfg.max_structure_requests, log=log)
                by_cik, structure_stats = result["by_cik"], result["stats"]
            stats["structure"] = structure_stats
            market_env = self._market_environment(cfg, log)
        finally:
            facts.close()
            events.close()
        stats["sec_requests_total"] = client.requests_sent
        stats["sec_max_requests_per_second"] = SEC_MAX_REQUESTS_PER_SECOND
        return Collected(universe_path, universe, by_cik, _load_text_similarity(cfg, log), market_env, stats)

    def _incremental_sec(self, cfg, client, facts, events, pool, as_of, prune, EC, log) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        last = events.db.execute("SELECT MAX(filed) FROM filings").fetchone()[0]
        start = (date.fromisoformat(last) + timedelta(days=1)) if last else date.fromisoformat(cfg.event_start)
        new_ciks: set = set()
        new_periodic: set = set()
        if start <= as_of:
            by_form = EC.stage_index(client, events, pool, start, as_of, log)
            out["index_new_by_form"] = by_form
            rows = events.db.execute("SELECT cik, form FROM filings WHERE filed >= ?", (start.isoformat(),)).fetchall()
            new_ciks = {r["cik"] for r in rows}
            new_periodic = {r["cik"] for r in rows if r["form"] in ("10-K", "10-Q")}
        else:
            out["index_new_by_form"] = {}
        out["companies_with_new_filings"] = len(new_ciks)
        for cik in sorted(new_periodic):                       # 只有出了新 10-K/10-Q 的公司才重取 companyfacts
            facts.ingest_companyfacts(cik, prune(client.companyfacts(cik)), as_of)
        for cik in sorted(new_ciks):                           # 任何新申报都刷新 submissions（主文档名、8-K 事项）
            payload = client.submissions(cik)
            facts.ingest_submissions(cik, payload, as_of)
            events.add_submissions(cik, payload)
        out["companyfacts_refreshed"] = len(new_periodic)
        out["submissions_refreshed"] = len(new_ciks)
        form4 = EC.stage_form4(client, events, pool, date.fromisoformat(cfg.event_start), as_of, cfg.min_insider_purchase_usd, log)
        out["form4"] = dict(form4)
        if form4.get("OK", 0) > 0:
            out["owners_checked"] = EC.stage_owners(client, events, log, cfg.min_insider_purchase_usd)
        if new_ciks:
            atm = json.loads((cfg.project_root / "Stock_Skill" / "equity-event-atlas" / "runtime" / "params.json").read_text("utf-8"))["dilution"]["atm_terms"]
            out["prospectus"] = EC.stage_prospectus(client, events, pool, date.fromisoformat(cfg.event_start), atm, log)
        if new_periodic:
            out["shares_observations"] = EC.stage_shares(client, events, pool, as_of - timedelta(days=120), as_of, log)
        facts.db.commit()
        events.commit()
        return out

    def _refresh_bars(self, cfg, bar_store: BarStore, entries, as_of: date, log) -> Dict[str, Any]:
        from .evidence.history_prices import fetch_history
        stale = []
        for symbol, exchange in [(BENCHMARK[0], BENCHMARK[1])] + [(e["symbol"], e["exchange"]) for e in entries]:
            rows = bar_store.load(symbol)
            if not rows or rows[-1][0] < as_of.isoformat():
                stale.append((symbol, exchange))
        if not stale:
            return {"stale": 0}
        for symbol, _ in stale:                                # fetch_history 只跳过「已有文件」的，这里要重取过期的
            path = bar_store.path(symbol)
            if path.is_file():
                path.unlink()
        result = fetch_history(bar_store, stale, log=log)
        return {"stale": len(stale), "ok": result["ok"], "failed": len(result["failed"])}

    def _market_environment(self, cfg: CycleConfig, log) -> Dict[str, list]:
        """与实时层同一取数口径：美股/沪深用新浪日线，港股用腾讯日线；新浪失败再退腾讯。"""
        from .live_config import LiveSettings, default_universe
        from .marketdata import DiskCache, HttpClient, SinaKlineProvider, TencentKlineProvider
        settings = LiveSettings.from_env(cfg.project_root)
        client, cache = HttpClient(timeout_seconds=20.0, attempts=3), DiskCache(cfg.work_dir / "market-env-cache")
        sina = SinaKlineProvider(client, cache, settings.sina_us_kline_url, settings.sina_cn_kline_url)
        tencent = TencentKlineProvider(client, cache, settings.tencent_kline_url)
        bars: Dict[str, list] = {}
        for instrument in [i for i in default_universe() if i.symbol in MARKET_ENV_SYMBOLS]:
            order = (sina, tencent) if instrument.market in ("US", "CN") else (tencent,)
            for provider in order:
                try:
                    bars[instrument.symbol] = provider.fetch(instrument)
                    break
                except Exception as exc:             # 取不到只让全球联动分支 ABSTAIN，不拖垮整轮
                    log("market env %s via %s unavailable: %s" % (instrument.symbol, type(provider).__name__, exc))
        return bars


def _structure_from_cache(facts: FactStore, pool: Sequence[int], as_of: str, extraction_cache: Any) -> Dict[int, List[FilingExtraction]]:
    from .evidence.structure_collect import ANNUAL_FORMS, QUARTERLY_FORMS, pick_filings
    out: Dict[int, List[FilingExtraction]] = {}
    for cik in pool:
        rows = [dict(r) for r in facts.filings_as_of(int(cik), as_of, ANNUAL_FORMS + QUARTERLY_FORMS)]
        found = [x for x in (extraction_cache.get(r["accession"]) for r in pick_filings(rows)) if x is not None]
        if found:
            out[int(cik)] = found
    return out


def _load_text_similarity(cfg: CycleConfig, log) -> dict:
    """Lazy Prices 记录：读已算好的文件（按 as_of 之前申报的最新一期）；没有就空着并写明。"""
    path = cfg.text_similarity_path
    if path is None or not Path(path).is_file():
        log("text similarity: no records file (Lazy Prices feature will be absent)")
        return {"coverage": {"computed": 0}, "thresholds": {}, "records": []}
    payload = json.loads(Path(path).read_text("utf-8"))
    return {"coverage": payload.get("coverage"), "thresholds": payload.get("thresholds"), "source_file": Path(path).name,
            "records": [{k: v for k, v in r.items() if k not in ("sections",)} for r in payload["records"]]}


# ---- shortlist -----------------------------------------------------------------------
def _load_verdicts(receipt: BranchReceipt) -> List[dict]:
    if not receipt.verdicts_file:
        return []
    return json.loads(Path(receipt.verdicts_file).read_text("utf-8"))["verdicts"]


def build_shortlist(receipts: Sequence[BranchReceipt], top_n: int = SHORTLIST_TOP_N, cap: int = SHORTLIST_MAX) -> List[dict]:
    """任一分支 PASS 的并集，加各分支（非 FAILED、分数 > 0）的前 top_n；按「PASS 分支数、名次分位之和」排序，最多 cap 只。
    全球联动只提供市场环境，不进 shortlist；分支整体 ABSTAIN/FAILED 时它不贡献任何名字。"""
    by_symbol: Dict[str, dict] = {}
    for receipt in receipts:
        if receipt.branch_id not in STOCK_BRANCHES or receipt.status != "PASS":
            continue
        verdicts = _load_verdicts(receipt)
        ranked = sorted((v for v in verdicts if v["verdict"] != "FAILED" and (v.get("score") or 0) > 0),
                        key=lambda v: (-(v["score"] or 0), -v["rank_key"], v["symbol"]))
        percentile = {v["symbol"]: 1.0 - i / max(len(ranked), 1) for i, v in enumerate(ranked)}
        top = {v["symbol"] for v in ranked[:top_n]}
        for v in verdicts:
            passed = v["verdict"] == "PASS"
            if not passed and v["symbol"] not in top:
                continue
            item = by_symbol.setdefault(v["symbol"], {"symbol": v["symbol"], "cik": v["cik"], "name": v["name"],
                                                      "market_cap_usd": v["market_cap_usd"], "passed_by": [], "top_in": [],
                                                      "scores": {}, "links": {}, "rank_percentile_sum": 0.0})
            if passed:
                item["passed_by"].append(receipt.branch_id)
            if v["symbol"] in top:
                item["top_in"].append(receipt.branch_id)
                item["rank_percentile_sum"] += percentile[v["symbol"]]
            item["scores"][receipt.branch_id] = v.get("score")
            if v.get("links"):
                item["links"][receipt.branch_id] = v["links"][0]
    ordered = sorted(by_symbol.values(), key=lambda i: (-len(i["passed_by"]), -i["rank_percentile_sum"], i["symbol"]))
    for rank, item in enumerate(ordered[:cap], 1):
        item["rank"] = rank
        item["rank_percentile_sum"] = round(item["rank_percentile_sum"], 4)
    return ordered[:cap]


# ---- 主流程 ----------------------------------------------------------------------------
def _strip_findings(params: dict) -> dict:
    """进入快照 hash 的只有版本与内容 hash；findings 与 source（本轮参数来自 REMOTE/LKG/LOCAL）是运行事件，
    第一次有「已更新」、第二次变成 LKG——同样内容的参数不能让快照 hash 不同。它们完整保存在 run_info 里。"""
    clean = json.loads(json.dumps(params))
    clean.pop("findings", None)
    clean.pop("registry_source", None)
    for skill in clean["skills"].values():
        skill.pop("findings", None)
        skill.pop("source", None)
    return clean


def run_cycle(cfg: CycleConfig, hooks: Optional[Hooks] = None, log: Callable[[str], None] = print) -> dict:
    hooks = hooks or LiveHooks()
    started = time.time()
    cfg.work_dir.mkdir(parents=True, exist_ok=True)
    resolution = ParamsResolver(cfg.project_root, cfg.work_dir / "params", ref=cfg.ref,
                                fetcher=None if cfg.offline else http_fetcher).resolve()
    active = resolution.active_skills()
    log("registry: %s ref=%s active skills %s" % (resolution.registry_source, cfg.ref, active))
    universe_path, universe = hooks.universe(cfg, log)
    collected = hooks.collect(cfg, universe_path, universe, log)
    as_of = universe["as_of_date"]

    structure_info = write_structure_file(collected.structure_by_cik, cfg.work_dir / "snapshots" / "data")
    bar_store = BarStore(cfg.bars_dir)
    body = build_body(as_of=as_of, universe=universe, facts_db=cfg.facts_db, events_db=cfg.events_db, bar_store=bar_store,
                      structure=structure_info, text_similarity=collected.text_similarity, market_environment=collected.market_environment,
                      params=_strip_findings(resolution.to_dict()), collection={"event_start": cfg.event_start})
    snapshot_path = write_snapshot(body, cfg.work_dir / "snapshots", run_info={"collect_stats": collected.stats, "params_findings": resolution.to_dict()})
    snapshot = load_snapshot(snapshot_path)
    digest12 = snapshot.sha256[:12]
    day_dir = Path(cfg.out_dir) / as_of
    day_dir.mkdir(parents=True, exist_ok=True)
    cycle_file = day_dir / ("cycle-%s.json" % digest12)
    if cycle_file.is_file() and not cfg.force:
        summary = json.loads(cycle_file.read_text("utf-8"))
        summary["reused"] = True
        summary["branch_runs_this_invocation"] = 0
        summary["collection_this_invocation"] = collected.stats
        log("cycle: snapshot %s already processed -> reused (no branch re-run, no double counting)" % digest12)
        return summary

    specs = cfg.branch_specs or branch_entries.default_specs()
    specs = [s for s in specs if s.branch_id in active]
    receipts = run_branches(snapshot_path, specs, day_dir / "branches", work_root=cfg.work_dir / "tmp", python=cfg.python,
                            max_parallel=cfg.max_parallel, log=log)
    shortlist = build_shortlist(receipts)
    shortlist_doc = {"schema": "signal-lattice-shortlist/1", "as_of": as_of, "snapshot_sha256": snapshot.sha256,
                     "generated_at": datetime.now(timezone.utc).isoformat(), "count": len(shortlist), "cap": SHORTLIST_MAX,
                     "rule": "任一分支 PASS 的并集 + 各分支（非 FAILED、分数>0）前 %d 名，最多 %d 只" % (SHORTLIST_TOP_N, SHORTLIST_MAX),
                     "entries": shortlist}
    _write_json(day_dir / ("shortlist-%s.json" % digest12), shortlist_doc)
    summary = {
        "as_of": as_of, "snapshot": str(snapshot_path), "snapshot_sha256": snapshot.sha256, "universe_count": universe["count"],
        "params": {sid: {"registry_version": s.registry_version, "params_version": s.params_version, "params_sha256": s.params_sha256,
                         "source": s.source, "active": s.registry_current} for sid, s in resolution.skills.items()},
        "params_findings": resolution.findings + [f for s in resolution.skills.values() for f in s.findings],
        "receipts": [r.to_dict() for r in receipts],
        "shortlist_file": str(day_dir / ("shortlist-%s.json" % digest12)), "shortlist_count": len(shortlist),
        "collection": collected.stats, "elapsed_seconds": round(time.time() - started, 1), "reused": False,
        "branch_runs_this_invocation": len(receipts), "collection_this_invocation": collected.stats,
    }
    _write_json(cycle_file, summary)
    _write_json(day_dir / "latest.json", {"as_of": as_of, "snapshot_sha256": snapshot.sha256, "cycle": cycle_file.name,
                                            "shortlist": "shortlist-%s.json" % digest12})
    return summary


def _write_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True, default=str), "utf-8")
    temporary.replace(path)


# ---- 报告 -------------------------------------------------------------------------------
def render_report(summary: Mapping, top: int = 15) -> str:
    lines: List[str] = []
    add = lines.append
    add("== research cycle | as_of %s | snapshot %s | %s ==" % (summary["as_of"], summary["snapshot_sha256"][:12],
                                                               "REUSED (幂等复用，未重新运行分支)" if summary.get("reused") else "fresh run"))
    add("pool %s | elapsed %ss | SEC requests (collection this invocation) %s (limit %d/s)" % (
        summary["universe_count"], summary["elapsed_seconds"],
        (summary.get("collection_this_invocation") or {}).get("sec_requests_total", "n/a"), SEC_MAX_REQUESTS_PER_SECOND))
    add("")
    add("-- 五个分支：逐标的 PASS/ABSTAIN/FAILED 计数与收据 --")
    for r in summary["receipts"]:
        counts = r["verdict_counts"]
        add("%-32s status=%-7s PASS %d / ABSTAIN %d / FAILED %d | %.0fs, peak %s MB" % (
            r["branch_id"], r["status"], counts.get("PASS", 0), counts.get("ABSTAIN", 0), counts.get("FAILED", 0),
            r["duration_seconds"], r["peak_rss_mb"]))
        add("    receipt: snapshot_hash=%s params_version=%s params_sha256=%s skill_version=%s" % (
            r["snapshot_hash"][:12], r["params_version"], (r["params_sha256"] or "-")[:12], r["skill_version"]))
        add("             started=%s finished=%s exit=%s verdicts_sha256=%s" % (
            r["started_at"], r["finished_at"], r["exit_code"], (r["verdicts_sha256"] or "-")[:12]))
        if r["status"] != "PASS":
            add("             reason: %s" % r["reason"])
    hashes = {r["snapshot_hash"] for r in summary["receipts"]}
    add("所有收据的 snapshot_hash 相同：%s" % ("是" if len(hashes) == 1 else "否 %s" % sorted(hashes)))
    add("")
    add("-- 股势前瞻：样本外 Brier（全模型 vs 基线模型 vs 常数基准）--")
    for r in summary["receipts"]:
        if r["branch_id"] == "equity-foresight-signal" and r.get("verdicts_file"):
            meta = json.loads(Path(r["verdicts_file"]).read_text("utf-8")).get("meta", {})
            s = meta.get("summary") or {}
            if s.get("brier"):
                b = s["brier"]
                add("OOS rows %d, months %d | Brier: full=%.5f  baseline(波动率+52周折价)=%.5f  constant(基准概率)=%.5f | selected=%s" % (
                    s["oos_rows"], s["oos_dates"], b["full_model"], b["baseline_model"], b["const"], s.get("selected_model")))
                add("AUC full=%.3f baseline=%.3f | full 是否优于基线: %s | 选出模型是否优于常数基准: %s" % (
                    s["auc"]["full_model"] or 0, s["auc"]["baseline_model"] or 0, s.get("full_beats_baseline_model"), s.get("selected_beats_constant")))
                add("选出模型 - 常数基准 的 Brier 差 %.5f，日期块自助 95%% 区间 %s（负数=模型更好）" % (
                    s["selected_minus_constant_brier"]["mean"], [round(x, 5) for x in s["selected_minus_constant_brier"]["ci95"]]))
            add("branch: %s %s" % (r["status"], r["reason"] or ""))
            fm = meta.get("final_model")
            if fm:
                add("final model: %s train_rows=%d dates=%d base_rate=%.3f dropped=%s" % (fm["which"], fm["train_rows"], fm["train_dates"], fm["base_rate"], fm["dropped_features"]))
    add("")
    add("-- shortlist 前 %d（共 %d 只）--" % (top, summary["shortlist_count"]))
    shortlist = json.loads(Path(summary["shortlist_file"]).read_text("utf-8"))["entries"]
    for item in shortlist[:top]:
        cap = item["market_cap_usd"] / 1e9 if item["market_cap_usd"] else 0.0
        add("%2d. %-6s %-32.32s cap $%.2fB | PASS in: %s | top-list in: %s" % (
            item["rank"], item["symbol"], item["name"], cap, ",".join(b.split("-")[0] for b in item["passed_by"]) or "-",
            ",".join(b.split("-")[0] for b in item["top_in"]) or "-"))
        for branch, link in list(item["links"].items())[:2]:
            add("      [%s] %s" % (branch.split("-")[0], link["url"]))
    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------------------
def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--work-dir", type=Path, required=True, help="状态目录（参数 LKG、候选池、证据快照、私有临时目录）")
    parser.add_argument("--out-dir", type=Path, required=True, help="产物目录：<out-dir>/<as_of>/{branches,shortlist,cycle}")
    parser.add_argument("--facts-db", type=Path, default=None)
    parser.add_argument("--events-db", type=Path, default=None)
    parser.add_argument("--bars-dir", type=Path, default=None)
    parser.add_argument("--text-cache", type=Path, default=None)
    parser.add_argument("--structure-cache", type=Path, default=None)
    parser.add_argument("--sec-cache", type=Path, default=None)
    parser.add_argument("--text-similarity", type=Path, default=None, help="Lazy Prices 记录文件（text_similarity 产物）")
    parser.add_argument("--universe-snapshot", type=Path, default=None, help="直接指定候选池快照（默认：work-dir/universe 里足够新的，否则重建）")
    parser.add_argument("--universe-max-age-hours", type=float, default=20.0)
    parser.add_argument("--ref", default="main", help="从 GitHub 哪个 ref 拉 Registry/params（默认 main）")
    parser.add_argument("--offline", action="store_true", help="不联网：只用 LKG/本地参数与已缓存的数据")
    parser.add_argument("--skip-collect", action="store_true", help="跳过 SEC/行情增量采集（只用现有库）")
    parser.add_argument("--event-start", default="2024-10-01")
    parser.add_argument("--max-parallel", type=int, default=1, help="同时运行的分支数（默认 1：任一分支运行时磁盘上没有别的分支输出）")
    parser.add_argument("--force", action="store_true", help="同一快照已处理过也重新运行分支")
    parser.add_argument("--top", type=int, default=15)


def config_from_args(args: argparse.Namespace, project_root: Path) -> CycleConfig:
    work = args.work_dir
    return CycleConfig(
        project_root=project_root, work_dir=work, out_dir=args.out_dir,
        facts_db=args.facts_db or work / "facts.sqlite", events_db=args.events_db or work / "events.sqlite",
        bars_dir=args.bars_dir or work / "bars", text_cache_dir=args.text_cache or work / "text-cache",
        structure_cache_dir=args.structure_cache or work / "structure-cache", sec_cache_dir=args.sec_cache or work / "sec-cache",
        text_similarity_path=args.text_similarity, universe_snapshot=args.universe_snapshot,
        universe_max_age_hours=args.universe_max_age_hours, ref=args.ref, offline=args.offline, event_start=args.event_start,
        max_parallel=args.max_parallel, force=args.force, skip_collect=args.skip_collect)


def cli_main(args: argparse.Namespace, project_root: Path) -> int:
    cfg = config_from_args(args, project_root)
    summary = run_cycle(cfg)
    print(render_report(summary, top=args.top))
    failed = [r["branch_id"] for r in summary["receipts"] if r["status"] == "FAILED"]
    return 2 if failed else 0
