"""中枢回测：把线上的中枢规则，放到历史每个月末重放一遍，看它当时会发布什么、之后 20/60 个交易日表现如何。

「同一份规则」怎么保证
  每个月末 d，用同一批函数重建当时能看到的东西：
    · 事件航图：events.sqlite 只取申报日 <= d 的申报（Form 4 / 424B / 8-K / 13D），逐股 evaluate_company；
    · 瓶颈、商业机会：事实库只取申报日 <= d 的事实，逐股 score_*，与线上是同一份评分代码；
    · shortlist：research_cycle.shortlist_from_records（线上建 shortlist 的同一个函数）；
    · 中枢：hub.rank_candidates（线上 decide 调的同一个函数）。
  行情只用 d 及以前的日线。

时点正确与不能复现的部分（写进报告，不藏）
  · 候选池：用「今天仍在池内的 1232 家」按 d 当天的价格/成交额/市值重新过一遍门槛。期间退市、并购、
    或涨出 50 亿的公司不在里面——存在幸存者偏差，方向偏乐观。
  · 市值 = 当前流通股 x d 当天价格（当时的流通股本没有逐日历史），公司增发过的会有偏差。
  · 瓶颈分支的「原文结构性证据」只取到了各公司最近几份申报，历史月份缺这部分，瓶颈分数在历史上偏低、
    更多因子记「无证据」；这会让「瓶颈排序支持」在回测里比线上更难出现（方向偏保守）。
  · 股势前瞻：线上整分支 ABSTAIN（样本外 Brier 不如常数基准），回测同样按 ABSTAIN，不给支持。
  · 权重：记分簿从零开始，全部等权（与线上冷启动一致）。
  · 发布后的失效条件（提前退出）不模拟，固定持有 20/60 日。

成交与成本（假设，写明）
  · 月末 d 收盘后出结论，d 的下一个交易日收盘价买入，再持有 20 / 60 个交易日，收盘价卖出。
  · 每边成本按该股 20 日成交额中位数分档估计（买卖价差的一半 + 冲击），再加 Alpha 费用模型的固定费用（佣金、SEC、CAT），
    仓位假设 1 万美元：≥5000 万美元 10bp，1000–5000 万 25bp，300–1000 万 50bp，更低 80bp。往返 = 两边之和。
  · 容量：每天最多占该股 20 日成交额中位数的 1%。
基准：IWM（小盘），以及同市值档随机对照（同一天、同一档的随机 200 只均值，种子 = 日期 + 档位，可复现，同样扣成本）。
安慰剂：把事件航图的事件日期整体后移 60 个交易日（即结论只用 d 之前 60 个交易日时能看到的事件），其它分支与成交都不变，
  重跑同一套规则；如果规则真有信息，安慰剂的超额应当明显变差。

不公布收益数字的规则（沿用旧规则）
  样本外窗口（有已成熟 20 日结果的建议月份）< 6，公开视图里不含任何收益数字，只写窗口数和为什么不公布。
  完整数字仍写在私有报告里，供内部复核。
"""

from __future__ import annotations

import json
import statistics
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import branch_entries, hub
from ..ledger import cap_tier, control_order
from ..research_cycle import shortlist_from_records
from ..research_view import ENVIRONMENT_BRANCH, STOCK_BRANCHES, ResearchView, _rank_table, _slim
from ..costs import (BENCHMARK_DOLLAR_VOLUME, COST_BELOW_TIERS_BPS, COST_TIERS_BPS_PER_SIDE, POSITION_USD,  # noqa: F401  重新导出：既有调用与测试沿用这些名字
                     cost_bps_per_side as _cost_bps_per_side, round_trip_cost)

MIN_OOS_WINDOWS = 6
HORIZONS = (20, 60)
PLACEBO_SHIFT_TRADING_DAYS = 60
CAPACITY_FRACTION_OF_DOLLAR_VOLUME = 0.01
CONTROL_DRAWS = 200
MIN_HISTORY_BARS = 60
EVENT_ATLAS, BOTTLENECK, COMMERCIAL, FORESIGHT = ("equity-event-atlas", "bottleneck-serenity-skill", "stock-commercial-opportunities",
                                                  "equity-foresight-signal")
ASSUMPTIONS = [
    "候选池：今天仍在池内的公司按月末当天价格/成交额/市值重新过门槛；期间退市或并购的公司不在其中（幸存者偏差，偏乐观）。",
    "市值 = 当前流通股 x 月末价格；当时的流通股本没有逐日历史，增发过的公司有偏差。",
    "瓶颈分支的原文结构性证据只有各公司最近几份申报，历史月份缺失，瓶颈排序支持在回测里比线上更难出现（偏保守）。",
    "股势前瞻线上整分支 ABSTAIN，回测同样按 ABSTAIN，不给支持；分支权重按记分簿冷启动全部等权。",
    "月末收盘后出结论，下一个交易日收盘价买入，固定持有 20/60 个交易日；不模拟发布后失效条件触发的提前退出。",
    "成本按 20 日成交额中位数分档：>=5000万 10bp、1000–5000万 25bp、300–1000万 50bp、更低 80bp（每边）+ 固定费用（仓位 1 万美元）。",
    "行情为前复权日线（含分红调整）；同档随机对照 = 同一天同一市值档随机 200 只均值（种子=日期+档位），同样扣成本。",
    "安慰剂 = 事件日期整体后移 60 个交易日重跑，只改事件航图的可见事件，其它分支与成交不变。",
]


# ---- 日历与行情 -------------------------------------------------------------------------------
def month_ends(days: Sequence[str], start: str, end: str) -> List[str]:
    """交易日历（IWM 日线的日期）里每个月的最后一个交易日，落在 [start, end]。"""
    last: Dict[str, str] = {}
    for day in days:
        last[day[:7]] = day
    return [d for d in sorted(last.values()) if start <= d <= end]


def shift_trading_days(days: Sequence[str], day: str, offset: int) -> Optional[str]:
    if day not in days:
        return None
    index = list(days).index(day) + offset
    return days[index] if 0 <= index < len(days) else None


def _bars_upto(rows: Sequence[Sequence[Any]], day: str) -> List[Sequence[Any]]:
    return [r for r in rows if r[0] <= day]


def pool_at(entries: Sequence[Mapping], bar_store: Any, day: str, *, min_cap: float = 3e8, max_cap: float = 5e9,
            min_price: float = 3.0, min_dollar_volume: float = 3e6) -> List[dict]:
    """按 day 当天的价格/成交额/市值把今天的候选池重新过一遍门槛。"""
    pool: List[dict] = []
    for entry in entries:
        rows = _bars_upto(bar_store.load(entry["symbol"]) or [], day)
        if len(rows) < MIN_HISTORY_BARS or (date.fromisoformat(day) - date.fromisoformat(rows[-1][0])).days > 7:
            continue                                     # 历史不够，或当天前后一周没有交易（停牌/退市）
        price = float(rows[-1][1])
        recent = [float(r[1]) * float(r[2]) for r in rows[-20:] if r[2] is not None]
        if len(recent) < 15:
            continue
        median_dv = statistics.median(recent)
        cap = price * float(entry["shares_outstanding"])
        if not (min_cap <= cap <= max_cap) or price < min_price or median_dv < min_dollar_volume:
            continue
        pool.append({**entry, "price_usd": price, "market_cap_usd": cap, "median_dollar_volume_20d_usd": median_dv, "last_bar_day": rows[-1][0]})
    return pool


# ---- 单个月末：重建当时的四个分支（重活，在子进程里做） --------------------------------------------
def compute_date_pack(args: Tuple[str, str, Optional[str], str]) -> dict:
    """返回可 JSON 化的一包：当天候选池、三个分支的逐股结论、安慰剂用的事件航图逐股结论。"""
    snapshot_path, day, shifted_day, event_start = args
    from ..branches import bottleneck as B
    from ..branches import commercial as C
    from ..branches import event_atlas as EA
    from ..evidence_snapshot import load_snapshot

    started = time.time()
    snapshot = load_snapshot(Path(snapshot_path))
    bar_store, facts, events = snapshot.bar_store(), snapshot.facts(), snapshot.events()
    try:
        entries = pool_at(snapshot.entries, bar_store, day)
        params_ea = EA.load_params(snapshot.params_file(branch_entries.EVENT_ATLAS))

        def event_records(as_of: str) -> List[dict]:
            built = EA.build_events(events, entries, as_of, params_ea, since=event_start)
            by_cik: Dict[int, list] = {}
            for event in built:
                by_cik.setdefault(event.cik, []).append(event)
            verdicts = [EA.evaluate_company(e, by_cik.get(int(e["cik"]), []), events, as_of, params_ea, {}) for e in entries]
            return branch_entries.event_atlas_records(verdicts)

        ea_records = event_records(day)
        placebo_records = event_records(shifted_day) if shifted_day else []
        funds = branch_entries.fundamentals_for_entries(facts, bar_store, entries, day)
        b_params, b_findings = B.load_bottleneck_params(snapshot.params_file(branch_entries.BOTTLENECK))
        c_params, c_findings = C.load_commercial_params(snapshot.params_file(branch_entries.COMMERCIAL))
        structure = snapshot.structure()
        b_records = branch_entries.bottleneck_records(branch_entries.bottleneck_receipts(facts, funds, structure, b_params, b_findings, day))
        c_records = branch_entries.commercial_records(branch_entries.commercial_receipts(facts, funds, c_params, c_findings, day))
    finally:
        facts.close()
        events.close()
    return {"as_of": day, "shifted_as_of": shifted_day, "seconds": round(time.time() - started, 1),
            "pool": [{k: e.get(k) for k in ("symbol", "cik", "name", "exchange", "market_cap_usd", "price_usd", "shares_outstanding",
                                             "median_dollar_volume_20d_usd", "last_bar_day")} for e in entries],
            "records": {EVENT_ATLAS: [_pack(r) for r in ea_records], BOTTLENECK: [_pack(r) for r in b_records],
                        COMMERCIAL: [_pack(r) for r in c_records]},
            "placebo_event_atlas": [_pack(r) for r in placebo_records]}


def _pack(record: Mapping) -> dict:
    evidence = record.get("evidence") or {}
    keep = {k: evidence[k] for k in ("invalidation_risk", "hard_flags") if k in evidence}
    return {"symbol": record["symbol"], "cik": record["cik"], "name": record["name"], "market_cap_usd": record["market_cap_usd"],
            "verdict": record["verdict"], "label": record.get("label"), "score": record.get("score"), "rank_key": record.get("rank_key") or 0.0,
            "reasons": list(record.get("reasons") or [])[:1], "links": [dict(x) for x in (record.get("links") or [])[:6]], "evidence": keep}


# ---- 中枢规则重放（纯函数，测试用合成数据就能跑） --------------------------------------------------
def view_from_pack(pack: Mapping, *, placebo: bool = False) -> ResearchView:
    records = {b: list(pack["records"][b]) for b in (EVENT_ATLAS, BOTTLENECK, COMMERCIAL)}
    if placebo:
        records[EVENT_ATLAS] = list(pack["placebo_event_atlas"])
    view = ResearchView(directory=Path("."), as_of=pack["as_of"], snapshot_sha256="backtest")
    for branch in STOCK_BRANCHES:
        if branch == FORESIGHT:
            view.receipts[branch] = {"status": "ABSTAIN", "reason": "回测不重放：线上整分支 ABSTAIN"}
            view.verdicts[branch] = {}
            view.ranks[branch] = _rank_table({})
            continue
        view.receipts[branch] = {"status": "PASS", "reason": None}
        by_symbol = {r["symbol"]: r for r in records[branch]}
        view.verdicts[branch] = {s: _slim(r) for s, r in by_symbol.items()}
        view.ranks[branch] = _rank_table(by_symbol)
    view.receipts[ENVIRONMENT_BRANCH] = {"status": "PASS", "reason": None}
    view.shortlist = shortlist_from_records({b: records[b] for b in (EVENT_ATLAS, BOTTLENECK, COMMERCIAL)})
    view.pool = {e["symbol"]: dict(e) for e in pack["pool"]}
    return view


def decide_month(pack: Mapping, *, placebo: bool = False) -> dict:
    """返回 {pick: 唯一建议(或 None), basket: 全部满足发布条件的候选, candidates: shortlist 数}。"""
    view = view_from_pack(pack, placebo=placebo)
    market = {e["symbol"]: {"price": view.pool[e["symbol"]]["price_usd"], "quote_status": "FRESH"} for e in view.shortlist if e["symbol"] in view.pool}
    rows, summaries, winner = hub.rank_candidates(view, market, hub.branch_weights(None), None, None)
    qualifying = [r for r in rows if all(r["gates"][k]["ok"] for k in ("pool", "quote", "liquidity", "veto", "support"))]

    def describe(row: Mapping) -> dict:
        symbol = row["symbol"]
        summary = summaries[symbol]
        entry = view.pool.get(symbol) or {}
        return {"symbol": symbol, "name": entry.get("name"), "market_cap_usd": entry.get("market_cap_usd"),
                "median_dollar_volume_20d_usd": entry.get("median_dollar_volume_20d_usd"),
                "support_total": summary["total"], "branches": [(i["branch_id"], i["kind"]) for i in summary["counted"]],
                "sources": [x["url"] for i in summary["counted"] for x in i["links"][:1]]}

    return {"pick": describe(winner) if winner else None, "basket": [describe(r) for r in qualifying],
            "shortlist": len(view.shortlist)}


# ---- 成交与结算 ---------------------------------------------------------------------------------
class CachedBars:
    """日线目录的内存缓存：随机对照会反复读同一批文件。"""

    def __init__(self, store: Any) -> None:
        self.store, self._cache = store, {}

    def load(self, symbol: str):
        if symbol not in self._cache:
            self._cache[symbol] = self.store.load(symbol)
        return self._cache[symbol]


def _close_series(rows: Sequence[Sequence[Any]]) -> Dict[str, float]:
    return {r[0]: float(r[1]) for r in rows}


def trade_return(symbol_rows: Sequence[Sequence[Any]], calendar: Sequence[str], decision_day: str, horizon: int,
                 median_dollar_volume: Optional[float]) -> Optional[dict]:
    """d 的下一个交易日收盘买入、再持有 horizon 个交易日。取不到价格（含尚未成熟）返回 None。"""
    entry_day = shift_trading_days(calendar, decision_day, 1)
    exit_day = shift_trading_days(calendar, decision_day, 1 + horizon)
    if entry_day is None or exit_day is None:
        return None
    closes = _close_series(symbol_rows)
    if entry_day not in closes or exit_day not in closes:
        return None
    gross = closes[exit_day] / closes[entry_day] - 1.0
    cost = round_trip_cost(median_dollar_volume, closes[entry_day])
    return {"entry_day": entry_day, "exit_day": exit_day, "gross": gross, "cost": cost, "net": gross - cost}


def control_return(pool: Sequence[Mapping], bar_store: Any, calendar: Sequence[str], decision_day: str, horizon: int,
                   symbol: str, market_cap_usd: float) -> Optional[dict]:
    """同一天同一市值档、随机 CONTROL_DRAWS 只的净收益均值（种子 = 日期 + 档位）。"""
    tier = cap_tier(market_cap_usd)
    same = [e["symbol"] for e in pool if e["symbol"] != symbol and cap_tier(e.get("market_cap_usd")) == tier]
    if tier is None or not same:
        return None
    order, _seed = control_order(decision_day, tier, same)
    by_symbol = {e["symbol"]: e for e in pool}
    nets: List[float] = []
    for candidate in order:
        result = trade_return(bar_store.load(candidate) or [], calendar, decision_day, horizon,
                              by_symbol[candidate].get("median_dollar_volume_20d_usd"))
        if result is not None:
            nets.append(result["net"])
        if len(nets) >= CONTROL_DRAWS:
            break
    return {"net": statistics.fmean(nets), "draws": len(nets)} if nets else None


def _stats(values: Sequence[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": statistics.fmean(values), "median": statistics.median(values),
            "hit_rate": sum(1 for v in values if v > 0) / len(values), "worst": min(values), "best": max(values)}


def evaluate(packs: Sequence[Mapping], bar_store: Any, calendar: Sequence[str]) -> dict:
    """对每个月末重放规则（正式 + 安慰剂），配上成交结果，汇总。"""
    iwm_rows = bar_store.load("IWM") or []
    months: List[dict] = []
    for pack in packs:
        day = pack["as_of"]
        row: Dict[str, Any] = {"as_of": day, "pool": len(pack["pool"])}
        for name, placebo in (("actual", False), ("placebo", bool(pack.get("placebo_event_atlas") is not None and pack.get("shifted_as_of")))):
            if name == "placebo" and not placebo:
                row["placebo"] = {"pick": None, "basket": [], "shortlist": 0, "skipped": "没有足够早的日期做后移"}
                continue
            decided = decide_month(pack, placebo=(name == "placebo"))
            row[name] = decided
            for group, picks in (("pick", [decided["pick"]] if decided["pick"] else []), ("basket", decided["basket"])):
                for pick in picks:
                    outcomes = {}
                    for horizon in HORIZONS:
                        stock = trade_return(bar_store.load(pick["symbol"]) or [], calendar, day, horizon, pick["median_dollar_volume_20d_usd"])
                        iwm = trade_return(iwm_rows, calendar, day, horizon, BENCHMARK_DOLLAR_VOLUME)      # IWM 流动性极好：只算固定费用
                        control = control_return(pack["pool"], bar_store, calendar, day, horizon, pick["symbol"], pick["market_cap_usd"])
                        if stock is None or iwm is None:
                            outcomes[str(horizon)] = None
                            continue
                        outcomes[str(horizon)] = {
                            **stock, "iwm_net": iwm["net"], "excess_vs_iwm": stock["net"] - iwm["net"],
                            "control_net": None if control is None else control["net"], "control_draws": None if control is None else control["draws"],
                            "excess_vs_control": None if control is None else stock["net"] - control["net"]}
                    pick["outcomes"] = outcomes
                    pick["capacity_usd_per_day"] = CAPACITY_FRACTION_OF_DOLLAR_VOLUME * (pick["median_dollar_volume_20d_usd"] or 0.0)
        months.append(row)
    return {"months": months, "summary": summarise(months)}


def summarise(months: Sequence[Mapping]) -> dict:
    out: Dict[str, Any] = {}
    for name in ("actual", "placebo"):
        block: Dict[str, Any] = {"months": len(months), "months_with_pick": sum(1 for m in months if (m.get(name) or {}).get("pick"))}
        for group in ("pick", "basket"):
            for horizon in HORIZONS:
                excess_iwm, excess_control, months_with = [], [], set()
                for m in months:
                    entries = [(m[name]["pick"] if m[name].get("pick") else None)] if group == "pick" else list(m[name].get("basket") or [])
                    per_month_iwm, per_month_ctrl = [], []
                    for entry in entries:
                        outcome = ((entry or {}).get("outcomes") or {}).get(str(horizon))
                        if outcome:
                            per_month_iwm.append(outcome["excess_vs_iwm"])
                            if outcome["excess_vs_control"] is not None:
                                per_month_ctrl.append(outcome["excess_vs_control"])
                    if per_month_iwm:
                        months_with.add(m["as_of"])
                        excess_iwm.append(statistics.fmean(per_month_iwm))          # 每个月一个观测：该月建议（或篮子）的平均净超额
                    if per_month_ctrl:
                        excess_control.append(statistics.fmean(per_month_ctrl))
                block["%s_%d" % (group, horizon)] = {"windows": len(months_with), "excess_vs_iwm": _stats(excess_iwm),
                                                     "excess_vs_control": _stats(excess_control)}
        out[name] = block
    return out


# ---- 报告 ------------------------------------------------------------------------------------------
def public_view(summary: Mapping, windows: int) -> dict:
    """公开视图：窗口 < 6 不含任何收益数字，只有窗口数和为什么不公布。"""
    sufficient = windows >= MIN_OOS_WINDOWS
    label = "OOS_HISTORY_%s: %d/%d" % ("SUFFICIENT" if sufficient else "INSUFFICIENT", windows, MIN_OOS_WINDOWS)
    message = ("样本外历史足够，下列为含亏损的全部结果。" if sufficient
               else "样本外历史不足，仅供研究参考，不构成收益证据。")
    why = None if sufficient else (
        "样本外窗口 %d < %d：中枢每个月最多发布一只，规则很严，回放的两年里只有 %d 个月出现了满足发布条件且 20 日结果已成熟的建议。"
        "样本这么少，任何收益数字都可能只是运气，所以沿用「窗口不足 6 个不公布」的规则，只公布窗口数。" % (windows, MIN_OOS_WINDOWS, windows))
    branch: Dict[str, Any] = {
        "branch_id": "hub", "status": "OOS_READY", "sample_sufficiency": label, "sample_sufficiency_message": message,
        "profitability_evidence": "SUFFICIENT" if sufficient else "INSUFFICIENT",
        "profitability_evidence_note": why or "窗口数达到门槛", "oos_windows": windows, "walk_forward": {"windows": windows},
    }
    if sufficient:
        branch["stitched"] = {"pick_20": summary["actual"]["pick_20"], "pick_60": summary["actual"]["pick_60"],
                              "placebo_pick_20": summary["placebo"]["pick_20"]}
        branch["benchmark_symbol"] = "IWM"
    return {"status": "OOS_READY", "why_not_published": why, "sample_sufficiency": label, "sample_sufficiency_message": message, "profitability_status": label,
            "method": {"minimum_oos_windows_for_profitability": MIN_OOS_WINDOWS, "assumptions": ASSUMPTIONS},
            "branches": {"hub": branch}}


def build_report(months_result: Mapping, *, snapshot_sha256: str, start: str, end: str, dates: Sequence[str],
                 binding: Optional[Mapping] = None) -> dict:
    """binding：hub.rule_binding(...)——这份回测对应的中枢规则版本与各分支参数 sha256。规则自证门读取时核对，
    对不上（规则或参数变了）就不再把它当证据；生成后 35 天过期。"""
    summary = months_result["summary"]
    windows = summary["actual"]["pick_20"]["windows"]
    return {
        "schema": "signal-lattice-hub-backtest/1", "generated_at": datetime.now(timezone.utc).isoformat(), "snapshot_sha256": snapshot_sha256,
        "binding": None if binding is None else dict(binding), "valid_days": hub.PROOF_BACKTEST_MAX_AGE_DAYS,
        "window": {"start": start, "end": end, "decision_dates": list(dates), "count": len(dates)},
        "oos_windows": windows, "published": windows >= MIN_OOS_WINDOWS, "minimum_oos_windows": MIN_OOS_WINDOWS,
        "assumptions": ASSUMPTIONS, "summary": summary, "months": months_result["months"], "public": public_view(summary, windows),
    }


def render_summary(report: Mapping) -> str:
    s = report["summary"]
    lines = ["== 中枢回测 | %s .. %s | 月末决策 %d 个 | 快照 %s ==" % (report["window"]["start"], report["window"]["end"],
                                                              report["window"]["count"], report["snapshot_sha256"][:12]),
             "样本外窗口（有已成熟 20 日结果的建议月份）：%d / 门槛 %d -> %s" % (
                 report["oos_windows"], report["minimum_oos_windows"], "公布收益数字" if report["published"] else "不公布收益数字")]
    if not report["published"]:
        lines.append("为什么不公布：" + (report["public"]["why_not_published"] or ""))
    for name, label in (("actual", "正式"), ("placebo", "安慰剂(事件后移60日)")):
        block = s[name]
        lines.append("[%s] 有建议的月份 %d/%d" % (label, block["months_with_pick"], block["months"]))
        for group, gl in (("pick", "唯一建议"), ("basket", "篮子(诊断)")):
            for horizon in HORIZONS:
                item = block["%s_%d" % (group, horizon)]
                ex = item["excess_vs_iwm"]
                ctrl = item["excess_vs_control"]
                lines.append("   %s %d日：窗口 %d | 相对IWM净超额 %s | 相对同档随机 %s" % (
                    gl, horizon, item["windows"],
                    "n/a" if not ex.get("n") else "均值 %+.2f%% 中位 %+.2f%% 命中 %.0f%% 最差 %+.2f%%" % (ex["mean"] * 100, ex["median"] * 100, ex["hit_rate"] * 100, ex["worst"] * 100),
                    "n/a" if not ctrl.get("n") else "均值 %+.2f%% 命中 %.0f%%" % (ctrl["mean"] * 100, ctrl["hit_rate"] * 100)))
    return "\n".join(lines)


# ---- 主流程 ----------------------------------------------------------------------------------------
@dataclass
class BacktestConfig:
    snapshot_path: Path
    out_dir: Path
    cache_dir: Path
    start: str = "2024-12-31"
    end: str = "2026-08-31"
    workers: int = 6
    event_start: str = "2024-10-01"


def run(cfg: BacktestConfig, log: Any = print) -> dict:
    from ..evidence_snapshot import load_snapshot

    snapshot = load_snapshot(cfg.snapshot_path)
    bar_store = snapshot.bar_store()
    calendar = [r[0] for r in (bar_store.load("IWM") or [])]
    dates = month_ends(calendar, cfg.start, cfg.end)
    cfg.cache_dir.mkdir(parents=True, exist_ok=True)
    jobs: List[Tuple[str, str, Optional[str], str]] = []
    packs: Dict[str, dict] = {}
    for day in dates:
        cache = cfg.cache_dir / ("pack-%s-%s.json" % (day, snapshot.sha256[:12]))
        if cache.is_file():
            packs[day] = json.loads(cache.read_text("utf-8"))
        else:
            jobs.append((str(cfg.snapshot_path), day, shift_trading_days(calendar, day, -PLACEBO_SHIFT_TRADING_DAYS), cfg.event_start))
    log("backtest: %d decision dates, %d cached, %d to compute (workers=%d)" % (len(dates), len(packs), len(jobs), cfg.workers))
    if jobs:
        import multiprocessing
        with ProcessPoolExecutor(max_workers=cfg.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
            for pack in pool.map(compute_date_pack, jobs):
                (cfg.cache_dir / ("pack-%s-%s.json" % (pack["as_of"], snapshot.sha256[:12]))).write_text(
                    json.dumps(pack, ensure_ascii=False, separators=(",", ":")), "utf-8")
                packs[pack["as_of"]] = pack
                log("  %s done in %.0fs (pool %d)" % (pack["as_of"], pack["seconds"], len(pack["pool"])))
    ordered = [packs[d] for d in dates]
    result = evaluate(ordered, CachedBars(bar_store), calendar)
    binding = hub.rule_binding({branch: snapshot.params_info(branch) for branch in hub.BACKTEST_BOUND_BRANCHES})
    report = build_report(result, snapshot_sha256=snapshot.sha256, start=cfg.start, end=cfg.end, dates=dates, binding=binding)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)
    path = cfg.out_dir / "hub-backtest.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True, default=str), "utf-8")
    temporary.replace(path)
    return report
