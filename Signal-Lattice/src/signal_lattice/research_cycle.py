"""研究层管线：universe 快照 -> 事实/事件增量采集 -> 不可变证据快照 -> 5 个分支各自在隔离子进程里运行 -> 收据与结论落盘 -> shortlist。

    signal-lattice research --work-dir DIR --out-dir DIR [--offline] [--force] ...

顺序（北极星合同的研究层部分）：
 1. 读 Stock_Skill Registry 与各 params：校验版本与 hash，坏了/断网用 Last-Known-Good（params_registry）；
 2. 候选池快照（<= 50 亿美元本土申报人，已有足够新的快照就复用，不重复请求）；
 3. 增量采集（只取上次之后新出现的申报/Form 4/正文，全程 SEC <= 4 次/秒、请求数打进日志）；
 4. 生成不可变证据快照 evidence-<日期>-<hash>.json（候选池、Lazy Prices、市场环境日线、参数版本与 hash、数据文件 hash）；
 5. 向所有 Active Skill 分发同一份快照，每个分支独立子进程（branch_runner），收集 PASS/ABSTAIN/FAILED 收据；
 6. shortlist：任一分支 PASS 的并集，加各分支非 FAILED、分数 > 0 的前 30 名，最多 60 只，供实时层使用；
    同时写中枢输入 hubinputs-<hash>.json（候选池全表 + shortlist 的营收同比与最新定期报告），实时层只读这些产物。
幂等：同一份快照（内容 hash 相同）已经跑完就直接复用结果，不再启动分支、不再重复计数；同一天数据没变，采集阶段的 SEC 请求数为 0。
  例外：上次收据是 FAILED 的分支不缓存——同一份快照再跑时只重跑这些分支（PASS / ABSTAIN 的原样复用）。
候选池守门：候选池（universe）只取到不足 600 只、或不足最近 5 次成功运行中位数的 70%，说明上游取数不全——拒绝产出快照，
研究层报失败（退出码 3），并写 <out_dir>/research-failure.json，实时层据此 SYSTEM_BLOCKED；下一次正常跑完会撤掉这个标记。
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

from . import branch_entries, cache_cap, hub_inputs, nyse_calendar
from .branch_runner import BranchReceipt, BranchSpec, run_branches
from .evidence.eventstore import EventStore
from .evidence.factstore import FactStore
from .evidence.history_prices import BENCHMARK, BarStore
from .evidence.sec_client import RateLimiter, SecClient, SecFetchError, SecUserAgentMissing, user_agent_from_env
from .evidence.structure_text import FilingExtraction
from .evidence_snapshot import BENCHMARK_SYMBOL, build_body, load_snapshot, write_snapshot, write_structure_file
from .params_registry import ParamsResolver, Resolution, http_fetcher
from .research_view import FAILURE_FILE

SEC_MAX_REQUESTS_PER_SECOND = 4
SEC_INTERVAL_SECONDS = 1.0 / SEC_MAX_REQUESTS_PER_SECOND
SHORTLIST_TOP_N = 30
SHORTLIST_MAX = 60
STOCK_BRANCHES = ("bottleneck-serenity-skill", "stock-commercial-opportunities", "equity-event-atlas", "equity-foresight-signal")
MARKET_ENV_SYMBOLS = ("usSPY", "sh000300", "hk02800")
UNIVERSE_MIN_COUNT = 600                    # 线上候选池约 1200 只；低于这个绝对值一定是取数不全
UNIVERSE_MIN_RATIO_OF_RECENT_MEDIAN = 0.7
UNIVERSE_HISTORY_RUNS = 5
EXIT_UNIVERSE_INCOMPLETE = 3
EXIT_SEC_USER_AGENT_MISSING = 4


class UniverseIncompleteError(RuntimeError):
    """候选池缩水或为空：这一轮不产出快照。"""

    def __init__(self, count: int, minimum: int, reason: str) -> None:
        self.count, self.minimum, self.reason = count, minimum, reason
        super().__init__("候选池数据不完整（只取到 %d 只），本轮不出结论：%s" % (count, reason))


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
    universe_min_count: int = UNIVERSE_MIN_COUNT


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
        client = None if cfg.offline else SecClient(cfg.sec_cache_dir, limiter=RateLimiter(min_interval=cfg.sec_interval), compress_cache=True)
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
        stats["sec_requests_total"] = client.requests_sent if client is not None else 0
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
        # 先装 SEC 官方内部人交易季度数据集（DERA）：只有它筛出的「买入」才去取 Form 4 原文。不装就要把窗口内全部 Form 4
        # （候选池两年约 9.5 万份）逐份取原文，首跑要 6 个多小时；数据集不可用且库里从没装过时宁可失败，也不退化成全量原文。
        try:
            EC.stage_dera(client, events, pool, log)
        except SecFetchError as exc:
            log("dera: 取数据集失败 %s" % exc)
            if EC.dera_coverage_end(events) is None:
                raise
        form4 = EC.stage_form4(client, events, pool, date.fromisoformat(cfg.event_start), as_of, cfg.min_insider_purchase_usd, log)
        out["form4"] = dict(form4)
        if form4.get("OK", 0) > 0:
            out["owners_checked"] = EC.stage_owners(client, events, log, cfg.min_insider_purchase_usd)
        if new_ciks:
            atm = _event_atlas_params(cfg)["dilution"]["atm_terms"]
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


def _event_atlas_params(cfg: "CycleConfig") -> dict:
    """事件航图参数：本轮 Registry 校验后落在 work_dir/params/active 的那一份；没有才退回源码树里的文件。
    已安装的 release 里没有 Stock_Skill 目录，不能只认 project_root。"""
    for path in (Path(cfg.work_dir) / "params" / "active" / "equity-event-atlas.json",
                 Path(cfg.project_root) / "Stock_Skill" / "equity-event-atlas" / "runtime" / "params.json"):
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
    raise FileNotFoundError("equity-event-atlas 参数文件不在 %s/params/active，也不在源码树" % cfg.work_dir)


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
    records = {r.branch_id: _load_verdicts(r) for r in receipts if r.branch_id in STOCK_BRANCHES and r.status == "PASS"}
    return shortlist_from_records(records, top_n, cap)


def shortlist_from_records(records_by_branch: Mapping[str, Sequence[dict]], top_n: int = SHORTLIST_TOP_N, cap: int = SHORTLIST_MAX) -> List[dict]:
    """纯函数版：输入是「整体 PASS 的选股分支 -> 它的逐股结论」。回测按历史月末重建 shortlist 时调用同一个函数。"""
    by_symbol: Dict[str, dict] = {}
    for branch_id, verdicts in records_by_branch.items():
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
                item["passed_by"].append(branch_id)
            if v["symbol"] in top:
                item["top_in"].append(branch_id)
                item["rank_percentile_sum"] += percentile[v["symbol"]]
            item["scores"][branch_id] = v.get("score")
            if v.get("links"):
                item["links"][branch_id] = v["links"][0]
    ordered = sorted(by_symbol.values(), key=lambda i: (-len(i["passed_by"]), -i["rank_percentile_sum"], i["symbol"]))
    for rank, item in enumerate(ordered[:cap], 1):
        item["rank"] = rank
        item["rank_percentile_sum"] = round(item["rank_percentile_sum"], 4)
    return ordered[:cap]


# ---- 候选池守门 --------------------------------------------------------------------------
def recent_universe_counts(out_dir: Path, runs: int = UNIVERSE_HISTORY_RUNS) -> List[int]:
    """最近 runs 次成功运行（有 cycle-*.json 的）的候选池大小，按时间先后。"""
    files = sorted(Path(out_dir).glob("*/cycle-*.json"), key=lambda p: (p.stat().st_mtime, p.name))
    counts: List[int] = []
    for path in reversed(files):
        try:
            value = json.loads(path.read_text("utf-8")).get("universe_count")
        except (OSError, ValueError):
            continue
        if isinstance(value, int) and value > 0:
            counts.append(value)
        if len(counts) >= runs:
            break
    return list(reversed(counts))


def check_universe_size(count: int, history: Sequence[int], minimum: int) -> Optional[str]:
    """候选池够大返回 None；否则返回人话原因。"""
    if count < minimum:
        return "低于绝对下限 %d 只" % minimum
    if history:
        ordered = sorted(history)
        middle = len(ordered) // 2
        median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2.0
        if count < UNIVERSE_MIN_RATIO_OF_RECENT_MEDIAN * median:
            return "低于近 %d 次成功运行中位数 %.0f 只的 %d%%" % (len(history), median, int(UNIVERSE_MIN_RATIO_OF_RECENT_MEDIAN * 100))
    return None


def _failure_path(out_dir: Path) -> Path:
    return Path(out_dir) / FAILURE_FILE


def _record_universe_failure(out_dir: Path, error: UniverseIncompleteError) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    _write_json(_failure_path(out_dir), {"code": "UNIVERSE_INCOMPLETE", "count": error.count, "minimum": error.minimum, "reason": error.reason,
                                         "message": str(error), "recorded_at": datetime.now(timezone.utc).isoformat()})


def _clear_failure(out_dir: Path) -> None:
    try:
        _failure_path(out_dir).unlink()
    except OSError:
        pass


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
    pool_size = len(universe.get("entries") or [])
    reason = check_universe_size(pool_size, recent_universe_counts(cfg.out_dir), cfg.universe_min_count)
    if reason is not None:                                   # 不采集、不建快照、不启动分支
        error = UniverseIncompleteError(pool_size, cfg.universe_min_count, reason)
        _record_universe_failure(cfg.out_dir, error)
        log("cycle: REFUSED %s" % error)
        raise error
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
    specs = cfg.branch_specs or branch_entries.default_specs()
    specs = [s for s in specs if s.branch_id in active]
    kept: List[BranchReceipt] = []
    rerun_only = False
    if cycle_file.is_file() and not cfg.force:
        summary = json.loads(cycle_file.read_text("utf-8"))
        failed = {r["branch_id"] for r in summary["receipts"] if r["status"] == "FAILED"}
        if not failed:
            shortlist_file = day_dir / ("shortlist-%s.json" % digest12)
            _ensure_hub_inputs(day_dir, digest12, snapshot, json.loads(shortlist_file.read_text("utf-8"))["entries"])
            _write_json(day_dir / "latest.json", _latest_pointer(as_of, snapshot.sha256, cycle_file.name, digest12))
            _clear_failure(cfg.out_dir)
            summary["reused"] = True
            summary["branch_runs_this_invocation"] = 0
            summary["collection_this_invocation"] = collected.stats
            log("cycle: snapshot %s already processed -> reused (no branch re-run, no double counting)" % digest12)
            return summary
        # FAILED 的收据不缓存：只重跑失败的分支，PASS / ABSTAIN 的收据与结论原样保留
        log("cycle: snapshot %s processed but %s FAILED -> rerun only those (others reused)" % (digest12, sorted(failed)))
        rerun_only = True
        kept = [BranchReceipt(**r) for r in summary["receipts"] if r["branch_id"] not in failed]
        specs = [s for s in specs if s.branch_id in failed]
    rerun = run_branches(snapshot_path, specs, day_dir / "branches", work_root=cfg.work_dir / "tmp", python=cfg.python,
                         max_parallel=cfg.max_parallel, log=log)
    order = {spec.branch_id: index for index, spec in enumerate(cfg.branch_specs or branch_entries.default_specs())}
    receipts = sorted(kept + rerun, key=lambda r: order.get(r.branch_id, len(order)))
    shortlist = build_shortlist(receipts)
    shortlist_doc = {"schema": "signal-lattice-shortlist/1", "as_of": as_of, "snapshot_sha256": snapshot.sha256,
                     "generated_at": datetime.now(timezone.utc).isoformat(), "count": len(shortlist), "cap": SHORTLIST_MAX,
                     "rule": "任一分支 PASS 的并集 + 各分支（非 FAILED、分数>0）前 %d 名，最多 %d 只" % (SHORTLIST_TOP_N, SHORTLIST_MAX),
                     "entries": shortlist}
    _write_json(day_dir / ("shortlist-%s.json" % digest12), shortlist_doc)
    if rerun_only:                                           # 重跑过分支：shortlist 变了，中枢输入要跟着重写
        hub_inputs.write(day_dir / ("hubinputs-%s.json" % digest12), hub_inputs.build(snapshot, shortlist))
    else:
        _ensure_hub_inputs(day_dir, digest12, snapshot, shortlist)
    summary = {
        "as_of": as_of, "snapshot": str(snapshot_path), "snapshot_sha256": snapshot.sha256, "universe_count": universe["count"],
        "params": {sid: {"registry_version": s.registry_version, "params_version": s.params_version, "params_sha256": s.params_sha256,
                         "source": s.source, "active": s.registry_current} for sid, s in resolution.skills.items()},
        "params_findings": resolution.findings + [f for s in resolution.skills.values() for f in s.findings],
        "receipts": [r.to_dict() for r in receipts],
        "shortlist_file": str(day_dir / ("shortlist-%s.json" % digest12)), "shortlist_count": len(shortlist),
        "collection": collected.stats, "elapsed_seconds": round(time.time() - started, 1), "reused": False,
        "branch_runs_this_invocation": len(rerun), "collection_this_invocation": collected.stats,
    }
    _write_json(cycle_file, summary)
    _write_json(day_dir / "latest.json", _latest_pointer(as_of, snapshot.sha256, cycle_file.name, digest12))
    _clear_failure(cfg.out_dir)
    return summary


def _latest_pointer(as_of: str, sha256: str, cycle_name: str, digest12: str) -> dict:
    """latest.json 是实时层找研究产物的唯一入口。checked_at = 研究层最后一次确认「这份快照就是当前数据」的时刻：
    周末没有新申报时快照内容不变（hash 相同、分支不重跑），但研究层仍在按时运行，数据并没有过期——
    实时层用 max(生成时间, checked_at) 判断研究快照是否过期，不会在周末误报 SYSTEM_BLOCKED。"""
    return {"as_of": as_of, "snapshot_sha256": sha256, "cycle": cycle_name, "shortlist": "shortlist-%s.json" % digest12,
            "hubinputs": "hubinputs-%s.json" % digest12, "checked_at": datetime.now(timezone.utc).isoformat()}


def _ensure_hub_inputs(day_dir: Path, digest12: str, snapshot: Any, shortlist: Sequence[Mapping]) -> Path:
    path = day_dir / ("hubinputs-%s.json" % digest12)
    if not path.is_file():
        hub_inputs.write(path, hub_inputs.build(snapshot, shortlist))
    return path


def hub_inputs_only(out_dir: Path, log: Callable[[str], None] = print) -> Path:
    """不重跑任何分支：为已有的研究产物补写中枢输入文件（旧版研究层产物升级用）。"""
    days = sorted(p for p in Path(out_dir).iterdir() if (p / "latest.json").is_file())
    if not days:
        raise RuntimeError("找不到研究产物：%s" % out_dir)
    day_dir = days[-1]
    latest = json.loads((day_dir / "latest.json").read_text("utf-8"))
    cycle = json.loads((day_dir / latest["cycle"]).read_text("utf-8"))
    from .evidence_snapshot import load_snapshot
    snapshot = load_snapshot(Path(cycle["snapshot"]))
    shortlist = json.loads((day_dir / latest["shortlist"]).read_text("utf-8"))["entries"]
    digest12 = snapshot.sha256[:12]
    path = _ensure_hub_inputs(day_dir, digest12, snapshot, shortlist)
    _write_json(day_dir / "latest.json", _latest_pointer(latest["as_of"], snapshot.sha256, latest["cycle"], digest12))
    log("hub inputs: %s" % path)
    return path


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
    parser.add_argument("--hub-inputs-only", action="store_true", help="只为已有研究产物补写中枢输入文件，不采集、不重跑分支")
    parser.add_argument("--skip-if-market-closed", action="store_true",
                        help="美东当天不是 NYSE 交易日就直接退出（退出码 0，不请求任何数据）；systemd timer 做不了日历判断，由程序自己判")
    parser.add_argument("--cache-max-bytes", type=int, default=cache_cap.DEFAULT_MAX_BYTES,
                        help="SEC 原文缓存 + 正文缓存合计上限（字节，默认 1 GiB）；研究层结束时按最近使用淘汰，0 = 不清理")


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


def _prune_caches(cfg: CycleConfig, max_bytes: int) -> None:
    """结束时把可再生的原文缓存压到上限以内；清理失败不影响研究结果。"""
    if max_bytes <= 0:
        return
    try:
        stats = cache_cap.prune_lru([cfg.sec_cache_dir, cfg.text_cache_dir], max_bytes)
    except OSError as exc:
        print("cache-cap: 清理失败 %s" % exc, file=sys.stderr)
        return
    print("cache-cap: 上限 %d 字节；清理前 %d，清理后 %d，删除 %d 个文件" % (max_bytes, stats["before"], stats["after"], stats["removed_files"]))


def cli_main(args: argparse.Namespace, project_root: Path) -> int:
    if getattr(args, "hub_inputs_only", False):
        hub_inputs_only(args.out_dir)
        return 0
    if getattr(args, "skip_if_market_closed", False):
        today = datetime.now(nyse_calendar.NEW_YORK).date()
        if not nyse_calendar.is_trading_day(today):
            print("研究层跳过：美东 %s 是 NYSE 休市日（%s）" % (today, nyse_calendar.holiday_name(today) or "周末"))
            return 0
    cfg = config_from_args(args, project_root)
    if not cfg.offline:                                      # 要联网就先确认 SEC User-Agent 已配置：缺失就报清楚的错误并退出，不发任何请求
        try:
            user_agent_from_env()
        except SecUserAgentMissing as exc:
            print("研究层失败：%s" % exc, file=sys.stderr)
            return EXIT_SEC_USER_AGENT_MISSING
    try:
        summary = run_cycle(cfg)
    except UniverseIncompleteError as exc:
        print("研究层失败：%s" % exc, file=sys.stderr)
        return EXIT_UNIVERSE_INCOMPLETE
    finally:
        _prune_caches(cfg, args.cache_max_bytes)
    print(render_report(summary, top=args.top))
    failed = [r["branch_id"] for r in summary["receipts"] if r["status"] == "FAILED"]
    return 2 if failed else 0
