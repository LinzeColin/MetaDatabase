"""事件研究：每类事件发生后 20/60 个交易日相对 IWM 的超额收益分布，给出 Bull/Base/Bear 概率。

方法（写死，由 tests/test_event_study.py 钉住）：
  - 入场价 = 申报公开日的「下一个交易日」收盘价（申报可能在收盘后才受理，当日价格不可得；不抢跑）。
  - 超额收益 = 个股同期收益 − IWM 同期收益（按个股自己的交易日对齐）。
  - 同一公司同一类事件，间隔不足 dedupe_trading_days 个交易日的只保留第一条（避免一个故事被重复计数）。
  - Bull/Base/Bear 的分界 = 随机对照（全池随机「公司 × 日期」，同样的持有期）超额收益分布的三分位点：
    低于下三分位 = Bear，高于上三分位 = Bull，其余 = Base。对照随机时三档各 1/3，
    事件类的偏离才是信息。概率的区间用 Wilson 置信区间。
  - 每档另给超额收益的 25/50/75 分位（low/mid/high），满足 low <= mid <= high。
  - 样本 < min_sample 的事件类标「样本不足」，不出概率。
局限（输出里原样带上）：候选池是当前快照，退市股不在里面（幸存者偏差）；同一天的事件互相不独立；
研究窗口不长，市场环境变化时基准会漂。
"""

from __future__ import annotations

import bisect
import math
import random
import statistics
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

INSUFFICIENT = "样本不足"
LIMITATIONS = (
    "候选池取当前快照，退市/被并购的公司不在其中（幸存者偏差）",
    "同一交易日的多个事件受同一市场环境影响，不完全独立",
    "研究窗口约两年，市场环境变化时历史基准会漂移",
)

Bars = Tuple[List[str], List[float]]  # (交易日升序, 收盘价)


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """线性插值分位数；输入已升序。"""
    if not sorted_values:
        raise ValueError("empty")
    position = (len(sorted_values) - 1) * q
    low = int(math.floor(position))
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def wilson_interval(successes: int, n: int, confidence: float) -> Tuple[float, float]:
    if n <= 0:
        return (0.0, 1.0)
    z = statistics.NormalDist().inv_cdf((1 + confidence) / 2)
    p = successes / n
    denominator = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def entry_index(days: Sequence[str], published: str, lag: int = 1) -> Optional[int]:
    """公开日之后第 lag 个交易日的下标（严格晚于公开日）。"""
    index = bisect.bisect_right(days, published) + (lag - 1)
    return index if index < len(days) else None


def excess_return(stock: Bars, bench: Bars, start_index: int, horizon: int) -> Optional[float]:
    days, closes = stock
    end_index = start_index + horizon
    if end_index >= len(days):
        return None
    bench_days, bench_closes = bench
    start_b = bisect.bisect_right(bench_days, days[start_index]) - 1
    end_b = bisect.bisect_right(bench_days, days[end_index]) - 1
    if start_b < 0 or end_b < 0 or bench_days[start_b] != days[start_index] or bench_days[end_b] != days[end_index]:
        return None  # 基准缺这两天的价格就不算，宁缺勿凑
    if closes[start_index] <= 0 or bench_closes[start_b] <= 0:
        return None
    return (closes[end_index] / closes[start_index] - 1) - (bench_closes[end_b] / bench_closes[start_b] - 1)


def dedupe(events: Iterable[dict], days_by_symbol: Mapping[str, Sequence[str]], gap: int) -> List[dict]:
    """同 (公司, 类) 按公开日排序，间隔不足 gap 个交易日的丢掉。"""
    kept: List[dict] = []
    last_index: Dict[Tuple[int, str], int] = {}
    for event in sorted(events, key=lambda e: (e["published_date"], e["event_id"])):
        days = days_by_symbol.get(event["symbol"])
        if not days:
            continue
        position = bisect.bisect_right(days, event["published_date"])
        key = (event["cik"], event["kind"])
        if key in last_index and position - last_index[key] < gap:
            continue
        last_index[key] = position
        kept.append(event)
    return kept


def control_cutpoints(bars: Mapping[str, Bars], bench: Bars, horizon: int, window: Tuple[str, str],
                      samples: int, seed: int) -> Optional[dict]:
    """随机「公司 × 日期」的超额收益三分位点。日期限定在事件研究窗口内。"""
    rng = random.Random(seed + horizon)
    symbols = sorted(s for s, (d, _c) in bars.items() if len(d) > horizon + 5)
    if not symbols:
        return None
    values: List[float] = []
    attempts = 0
    while len(values) < samples and attempts < samples * 6:
        attempts += 1
        symbol = symbols[rng.randrange(len(symbols))]
        days, _closes = bars[symbol]
        low = bisect.bisect_left(days, window[0])
        high = len(days) - horizon - 1
        if high <= low:
            continue
        result = excess_return(bars[symbol], bench, rng.randrange(low, high), horizon)
        if result is not None:
            values.append(result)
    if len(values) < 200:
        return None
    values.sort()
    return {"bear_below": quantile(values, 1 / 3), "bull_above": quantile(values, 2 / 3), "n": len(values),
            "median": quantile(values, 0.5)}


def study(events: Sequence[dict], bars: Mapping[str, Bars], bench: Bars, params: Mapping,
          window: Tuple[str, str]) -> Dict[str, dict]:
    """events: [{event_id, cik, symbol, kind, published_date}]。返回 {kind: 统计}。"""
    cfg = params["study"]
    horizons = list(cfg["horizons_trading_days"])
    lag = int(cfg["entry_lag_trading_days"])
    confidence = float(cfg["interval_confidence"])
    days_by_symbol = {symbol: series[0] for symbol, series in bars.items()}
    by_kind: Dict[str, List[dict]] = defaultdict(list)
    for event in events:
        if event["symbol"] in bars:
            by_kind[event["kind"]].append(event)
    controls = {h: control_cutpoints(bars, bench, h, window, int(cfg["control_samples"]), int(cfg["control_seed"]))
                for h in horizons}
    result: Dict[str, dict] = {}
    for kind, items in sorted(by_kind.items()):
        kept = dedupe(items, days_by_symbol, int(cfg["dedupe_trading_days"]))
        entry: dict = {"n_events": len(items), "n_after_dedupe": len(kept), "horizons": {},
                       "limitations": list(LIMITATIONS)}
        for horizon in horizons:
            excess: List[float] = []
            for event in kept:
                days, _ = bars[event["symbol"]]
                start = entry_index(days, event["published_date"], lag)
                if start is None:
                    continue
                value = excess_return(bars[event["symbol"]], bench, start, horizon)
                if value is not None:
                    excess.append(value)
            n = len(excess)
            block: dict = {"n": n}
            cut = controls.get(horizon)
            if n < int(cfg["min_sample"]) or cut is None:
                block.update(status=INSUFFICIENT if n < int(cfg["min_sample"]) else "NO_CONTROL",
                             note="样本 %d < %d，不出概率" % (n, int(cfg["min_sample"])) if n < int(cfg["min_sample"]) else "缺随机对照")
                entry["horizons"][str(horizon)] = block
                continue
            ordered = sorted(excess)
            buckets = {"bear": [v for v in ordered if v < cut["bear_below"]],
                       "bull": [v for v in ordered if v > cut["bull_above"]]}
            buckets["base"] = [v for v in ordered if cut["bear_below"] <= v <= cut["bull_above"]]
            probability = {name: len(values) / n for name, values in buckets.items()}
            interval = {name: wilson_interval(len(values), n, confidence) for name, values in buckets.items()}
            tier = "HIGH" if n >= int(cfg["high_confidence_sample"]) else \
                "MEDIUM" if n >= int(cfg["medium_confidence_sample"]) else "LOW"
            block.update(
                status="OK", confidence=tier, interval_confidence=confidence,
                mean_excess=statistics.fmean(ordered), median_excess=quantile(ordered, 0.5),
                excess_p33=quantile(ordered, 1 / 3), excess_p67=quantile(ordered, 2 / 3),
                probability=probability,
                probability_interval={k: [round(v[0], 4), round(v[1], 4)] for k, v in interval.items()},
                scenario_range={name: {"low": quantile(values, 0.25), "mid": quantile(values, 0.5),
                                       "high": quantile(values, 0.75)} for name, values in buckets.items() if values},
                control={"bear_below": cut["bear_below"], "bull_above": cut["bull_above"], "n": cut["n"]},
            )
            entry["horizons"][str(horizon)] = block
        result[kind] = entry
    return result
