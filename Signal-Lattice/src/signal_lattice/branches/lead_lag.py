"""全球股市会话感知时延分支（global-equity-lead-lag-atlas 的可执行子集）。

方法来源：``Stock_Skill/global-equity-lead-lag-atlas`` 的 ``references/methodology.md`` 与
``src/gela/stats.py``。本分支只实现其中「会话感知时延」一类假设的一个固定切片：

- 来源市场：美股 ``usSPY``（本地上市、与美国现金市场同一交易时钟；GELA 默认对象是
  现金指数，SPY 是价格口径的本地 ETF 代理，这一偏离在 evidence 里如实写出）；
- 目标市场：``sh000300``（沪深300 现金指数）与 ``hk02800``（盈富基金，香港本地上市、
  跟踪恒生指数）；
- 收益尺度 ``horizon=1``、额外来源滞后 ``source_lag=0``，本地币种、价格收益。

对目标会话 t，只使用「收盘时刻严格早于 t 开盘」的最后一个来源会话收益，目标结果是
t 前一收盘到 t 收盘的对数收益。假设须依次通过 GELA 默认门：原始/有效样本、|r|≥0.15、
BH-FDR q≤0.05（两条假设之间校正）、循环区块 Bootstrap 95% 区间不跨 0、滚动符号稳定性
≥0.67、70/30 样本外线性预测 MSE 改进 > 0。全部通过才给方向，否则权重 0 并逐条写出
未通过的门。统计相关不证明因果，方向只表示线性预测的符号。
"""

from __future__ import annotations

import bisect
import math
import random
from datetime import datetime, time, timezone
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from ..marketdata.models import Bar
from .models import BranchVerdict

BRANCH_ID = "global-equity-lead-lag-atlas"
SOURCE_SYMBOL = "usSPY"
SOURCE_TIMEZONE = "America/New_York"
SOURCE_CLOSE = time(16, 0)
# 目标标的 -> (交易所时区, 开盘时刻)
TARGETS: dict[str, tuple[str, time]] = {
    "sh000300": ("Asia/Shanghai", time(9, 30)),
    "hk02800": ("Asia/Hong_Kong", time(9, 30)),
}
HORIZON = 1
SOURCE_LAG = 0
# 估计区间：最近约两年的配对样本。GELA 把 lookback 交给宿主决定，这里固定写死以便复算。
LOOKBACK_PAIRS = 500

# 以下阈值与 GELA AnalysisConfig 默认值一致。
ALPHA = 0.05
MIN_RAW_N = 80
MIN_EFFECTIVE_N = 20
MIN_ABS_EFFECT = 0.15
MIN_STABILITY = 0.67
MIN_OOS_IMPROVEMENT = 0.0
BOOTSTRAP_REPETITIONS = 300
BOOTSTRAP_BLOCK = 10
ROLLING_WINDOWS = 4
MAX_BASE_STALENESS_HOURS = 96.0
RANDOM_SEED = 20260726

DECISION_SYMBOLS = frozenset({SOURCE_SYMBOL, *TARGETS})


# ---- 统计原语（与 gela/stats.py 同公式，仅保留本分支用到的部分） ----

def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    mx, my = _mean(x), _mean(y)
    dx = [value - mx for value in x]
    dy = [value - my for value in y]
    denom = math.sqrt(sum(value * value for value in dx) * sum(value * value for value in dy))
    if denom <= 0:
        return None
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(dx, dy)) / denom))


def fisher_two_sided_p(r: float | None, n_effective: int) -> float | None:
    if r is None or n_effective <= 3:
        return None
    clipped = max(-0.999999999, min(0.999999999, r))
    z = abs(math.atanh(clipped) * math.sqrt(n_effective - 3))
    return math.erfc(z / math.sqrt(2.0))


def benjamini_hochberg(p_values: Sequence[float | None]) -> list[float | None]:
    valid = sorted(((index, value) for index, value in enumerate(p_values) if value is not None), key=lambda item: item[1])
    result: list[float | None] = [None] * len(p_values)
    m = len(valid)
    running = 1.0
    for rank in range(m, 0, -1):
        index, value = valid[rank - 1]
        running = min(running, min(1.0, value * m / rank))
        result[index] = running
    return result


def circular_block_bootstrap_ci(
    x: Sequence[float], y: Sequence[float], repetitions: int, block_size: int, seed: int
) -> tuple[float | None, float | None]:
    if len(x) != len(y) or len(x) < 8 or repetitions <= 0:
        return None, None
    n = len(x)
    block = max(1, min(block_size, n))
    rng = random.Random(seed)
    samples: list[float] = []
    for _ in range(repetitions):
        indices: list[int] = []
        while len(indices) < n:
            start = rng.randrange(n)
            indices.extend((start + offset) % n for offset in range(block))
        value = pearson([x[i] for i in indices[:n]], [y[i] for i in indices[:n]])
        if value is not None:
            samples.append(value)
    if len(samples) < max(20, repetitions // 4):
        return None, None
    samples.sort()
    low = max(0, math.floor(0.025 * (len(samples) - 1)))
    high = min(len(samples) - 1, math.ceil(0.975 * (len(samples) - 1)))
    return samples[low], samples[high]


def rolling_sign_stability(x: Sequence[float], y: Sequence[float], windows: int, reference: float) -> float | None:
    if len(x) != len(y) or len(x) < max(12, windows * 5) or reference == 0:
        return None
    width = len(x) // windows
    signs: list[bool] = []
    for index in range(windows):
        start = index * width
        end = len(x) if index == windows - 1 else (index + 1) * width
        value = pearson(x[start:end], y[start:end])
        if value is not None and value != 0:
            signs.append((value > 0) == (reference > 0))
    if not signs:
        return None
    return sum(1 for value in signs if value) / len(signs)


def linear_fit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float] | None:
    if len(x) != len(y) or len(x) < 3:
        return None
    mx, my = _mean(x), _mean(y)
    denominator = sum((value - mx) ** 2 for value in x)
    if denominator <= 0:
        return None
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y)) / denominator
    return my - slope * mx, slope


def out_of_sample_mse_improvement(x: Sequence[float], y: Sequence[float]) -> float | None:
    """前 70% 拟合、后 30% 评价；基准是训练段均值预测。"""
    if len(x) != len(y) or len(x) < 30:
        return None
    split = max(15, int(len(x) * 0.7))
    if len(x) - split < 8:
        return None
    fit = linear_fit(x[:split], y[:split])
    if fit is None:
        return None
    intercept, slope = fit
    baseline = _mean(y[:split])
    actual = y[split:]
    baseline_mse = _mean([(value - baseline) ** 2 for value in actual])
    model_mse = _mean([(value - (intercept + slope * feature)) ** 2 for feature, value in zip(x[split:], actual)])
    if baseline_mse <= 0:
        return None
    return (baseline_mse - model_mse) / baseline_mse


# ---- 会话对齐 ----

def _utc(day, at: time, zone: str) -> datetime:
    return datetime.combine(day, at, tzinfo=ZoneInfo(zone)).astimezone(timezone.utc)


def _log_returns(bars: Sequence[Bar]) -> list[float | None]:
    values: list[float | None] = [None]
    for previous, current in zip(bars, bars[1:]):
        values.append(math.log(current.close / previous.close))
    return values


def paired_samples(source: Sequence[Bar], target: Sequence[Bar], target_symbol: str) -> tuple[list[float], list[float], list[str]]:
    """返回 (来源收益, 目标收益, 目标会话日) 三列，严格无前视。"""
    zone, open_at = TARGETS[target_symbol]
    source_closes = [_utc(bar.day, SOURCE_CLOSE, SOURCE_TIMEZONE) for bar in source]
    source_returns = _log_returns(source)
    target_returns = _log_returns(target)
    x: list[float] = []
    y: list[float] = []
    days: list[str] = []
    for index, bar in enumerate(target):
        outcome = target_returns[index]
        if outcome is None:
            continue
        target_open = _utc(bar.day, open_at, zone)
        base = bisect.bisect_left(source_closes, target_open) - 1
        if base < 0:
            continue
        if (target_open - source_closes[base]).total_seconds() / 3600.0 > MAX_BASE_STALENESS_HOURS:
            continue
        feature_index = base - SOURCE_LAG
        if feature_index < 0 or source_returns[feature_index] is None:
            continue
        if not source_closes[feature_index] < target_open:
            raise AssertionError("LEAD_LAG_LOOKAHEAD_DETECTED")
        x.append(source_returns[feature_index])  # type: ignore[arg-type]
        y.append(outcome)
        days.append(bar.day.isoformat())
    return x[-LOOKBACK_PAIRS:], y[-LOOKBACK_PAIRS:], days[-LOOKBACK_PAIRS:]


def _test_hypothesis(target_symbol: str, x: list[float], y: list[float], q_value: float | None) -> dict[str, Any]:
    n_raw = len(x)
    n_effective = max(1, n_raw // HORIZON) if n_raw else 0
    r = pearson(x, y)
    result: dict[str, Any] = {
        "n_raw": n_raw,
        "n_effective": n_effective,
        "pearson_r": r,
        "p_value": fisher_two_sided_p(r, n_effective),
        "q_value": q_value,
        "ci_low": None,
        "ci_high": None,
        "rolling_sign_stability": None,
        "oos_mse_improvement": None,
        "failure_reasons": [],
    }
    reasons: list[str] = result["failure_reasons"]
    if n_raw < MIN_RAW_N:
        reasons.append("RAW_SAMPLE_BELOW_THRESHOLD")
    if n_effective < MIN_EFFECTIVE_N:
        reasons.append("EFFECTIVE_SAMPLE_BELOW_THRESHOLD")
    if r is None:
        reasons.append("CORRELATION_UNAVAILABLE")
    if reasons:
        result["status"] = "INSUFFICIENT_OR_INVALID"
        return result
    assert r is not None
    if abs(r) < MIN_ABS_EFFECT:
        reasons.append("EFFECT_BELOW_THRESHOLD")
    if q_value is None or q_value > ALPHA:
        reasons.append("FDR_THRESHOLD_NOT_MET")
    if reasons:
        result["status"] = "SCREEN_REJECTED"
        return result
    seed = RANDOM_SEED + sum(ord(char) for char in target_symbol)
    result["ci_low"], result["ci_high"] = circular_block_bootstrap_ci(x, y, BOOTSTRAP_REPETITIONS, max(BOOTSTRAP_BLOCK, HORIZON), seed)
    result["rolling_sign_stability"] = rolling_sign_stability(x, y, ROLLING_WINDOWS, r)
    result["oos_mse_improvement"] = out_of_sample_mse_improvement(x, y)
    if result["ci_low"] is None or result["ci_high"] is None or result["ci_low"] <= 0 <= result["ci_high"]:
        reasons.append("BOOTSTRAP_CI_INCLUDES_ZERO_OR_UNAVAILABLE")
    if result["rolling_sign_stability"] is None or result["rolling_sign_stability"] < MIN_STABILITY:
        reasons.append("ROLLING_STABILITY_BELOW_THRESHOLD")
    if result["oos_mse_improvement"] is None or result["oos_mse_improvement"] <= MIN_OOS_IMPROVEMENT:
        reasons.append("OOS_IMPROVEMENT_NOT_POSITIVE")
    result["status"] = "CONFIRMED" if not reasons else "CONFIRMATION_REJECTED"
    return result


_METHOD = {
    "source": SOURCE_SYMBOL,
    "horizon": HORIZON,
    "source_lag": SOURCE_LAG,
    "lookback_pairs": LOOKBACK_PAIRS,
    "alignment": "last source close strictly before target open",
    "return_type": "price (local currency)",
    "source_proxy_note": "来源用 SPY（美国本地上市 ETF，与美国现金市场同一时钟）代替 S&P 500 现金指数",
    "fdr_scope": "BH across the two targets of this branch only",
    "confidence_formula": "clamp(abs(pearson_r) * rolling_sign_stability)",
    "causal_claim": False,
}


def evaluate_lead_lag_verdicts(bars_by_symbol: Mapping[str, Sequence[Bar]]) -> list[BranchVerdict]:
    source = list(bars_by_symbol.get(SOURCE_SYMBOL, ()))
    samples = {symbol: paired_samples(source, list(bars_by_symbol.get(symbol, ())), symbol) for symbol in TARGETS}
    p_values = []
    for symbol in TARGETS:
        x, y, _days = samples[symbol]
        r = pearson(x, y)
        p_values.append(fisher_two_sided_p(r, len(x)) if len(x) >= MIN_RAW_N else None)
    q_values = dict(zip(TARGETS, benjamini_hochberg(p_values)))

    verdicts: list[BranchVerdict] = []
    for symbol, bars in bars_by_symbol.items():
        used = len(bars)
        if symbol not in TARGETS:
            verdicts.append(
                BranchVerdict(
                    branch_id=BRANCH_ID, symbol=symbol, direction="不适用", confidence=0.0,
                    evidence={"scope_status": "该标的不是本分支的目标市场", "bars_available": used},
                    counter_evidence="时延分支只对沪深300与盈富基金给出目标会话方向；美股来源本身不被预测。",
                    invalidation="把该标的作为目标市场纳入经审查的假设集后重新计算。",
                    window_used=used, implemented=True, weight=0.0, participation_status="OUT_OF_STRATEGY_UNIVERSE",
                )
            )
            continue
        x, y, days = samples[symbol]
        test = _test_hypothesis(symbol, x, y, q_values[symbol])
        evidence: dict[str, Any] = {**_METHOD, **test, "first_pair_day": days[0] if days else None, "last_pair_day": days[-1] if days else None}
        if test["status"] == "INSUFFICIENT_OR_INVALID":
            verdicts.append(
                BranchVerdict(
                    branch_id=BRANCH_ID, symbol=symbol, direction="不适用", confidence=0.0, evidence=evidence,
                    counter_evidence=f"配对样本 {len(x)} 条，未达 GELA 最低 {MIN_RAW_N} 条：{', '.join(test['failure_reasons'])}。",
                    invalidation=f"{SOURCE_SYMBOL} 与 {symbol} 的会话配对样本达到 {MIN_RAW_N} 条后重新计算。",
                    window_used=used, implemented=True, weight=0.0, participation_status="SAMPLE_INSUFFICIENT",
                )
            )
            continue
        if test["status"] != "CONFIRMED":
            verdicts.append(
                BranchVerdict(
                    branch_id=BRANCH_ID, symbol=symbol, direction="中性", confidence=0.0, evidence=evidence,
                    counter_evidence=f"时延假设未通过证据门：{', '.join(test['failure_reasons'])}。",
                    invalidation="下一次复算时全部证据门通过才会给出方向。",
                    window_used=used, implemented=True, weight=0.0, participation_status="EVIDENCE_GATE_NOT_PASSED",
                )
            )
            continue

        intercept, slope = linear_fit(x, y)  # type: ignore[misc]
        zone, open_at = TARGETS[symbol]
        last_target = list(bars)[-1]
        last_source_close = _utc(source[-1].day, SOURCE_CLOSE, SOURCE_TIMEZONE)
        fresh = last_source_close > _utc(last_target.day, open_at, zone)
        latest_feature = math.log(source[-1].close / source[-2].close)
        predicted = intercept + slope * latest_feature
        evidence.update(
            {
                "intercept": intercept,
                "slope": slope,
                "latest_source_day": source[-1].day.isoformat(),
                "latest_source_log_return": latest_feature,
                "predicted_next_target_log_return": predicted,
                "source_session_is_new_information": fresh,
            }
        )
        if not fresh or predicted == 0:
            verdicts.append(
                BranchVerdict(
                    branch_id=BRANCH_ID, symbol=symbol, direction="中性", confidence=0.0, evidence=evidence,
                    counter_evidence="最新美股收盘已被上一目标会话使用，目前没有新的来源信息。",
                    invalidation="下一个美股会话收盘后重新计算。",
                    window_used=used, implemented=True, weight=0.0, participation_status="NO_FRESH_SOURCE_SESSION",
                )
            )
            continue
        confidence = max(0.0, min(1.0, abs(test["pearson_r"]) * test["rolling_sign_stability"]))
        verdicts.append(
            BranchVerdict(
                branch_id=BRANCH_ID, symbol=symbol, direction="看涨" if predicted > 0 else "看跌", confidence=confidence,
                evidence=evidence,
                counter_evidence="相关不等于因果；共同全球因子、汇率或制度切换都可能让关系在下一会话失效。",
                invalidation=f"{symbol} 下一会话收盘收益符号与预测相反，或下一次复算任一证据门未通过。",
                window_used=used, implemented=True, weight=1.0, participation_status="COLD_START_ELIGIBLE",
            )
        )
    return verdicts
