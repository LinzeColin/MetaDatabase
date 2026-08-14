from __future__ import annotations

import math
import statistics
from collections import OrderedDict
from datetime import date

from .models import Candidate, Metrics

WINDOWS = (20, 60, 120)


def price_rows(candidate: Candidate) -> list[tuple[str, float]]:
    result: list[tuple[str, float]] = []
    for row in candidate.bars:
        if not isinstance(row, dict):
            continue
        raw_time = str(row.get("time") or row.get("date") or "")[:10]
        try:
            date.fromisoformat(raw_time)
            close = float(row.get("close", 0.0))
        except (ValueError, TypeError):
            continue
        if close > 0:
            result.append((raw_time, close))
    rows = list(OrderedDict(result).items())
    if candidate.price and candidate.price > 0 and rows:
        rows[-1] = (rows[-1][0], float(candidate.price))
    return rows


def daily_returns(prices: list[float]) -> list[float]:
    return [b / a - 1.0 for a, b in zip(prices, prices[1:]) if a > 0]


def period_return(prices: list[float], window: int) -> float | None:
    if len(prices) <= window or prices[-window - 1] <= 0:
        return None
    return (prices[-1] / prices[-window - 1] - 1.0) * 100.0


def annualized_volatility(prices: list[float], window: int) -> float | None:
    if len(prices) <= window:
        return None
    returns = daily_returns(prices[-window - 1 :])
    if len(returns) < 2:
        return None
    return statistics.pstdev(returns) * math.sqrt(252.0) * 100.0


def max_drawdown(prices: list[float], window: int) -> float | None:
    if len(prices) <= window:
        return None
    sample = prices[-window - 1 :]
    peak = sample[0]
    worst = 0.0
    for value in sample:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return abs(worst) * 100.0


def absolute_metrics(candidate: Candidate) -> Metrics:
    prices = [value for _, value in price_rows(candidate)]
    return Metrics(
        provider_code=candidate.provider_code,
        returns_pct={str(window): period_return(prices, window) for window in WINDOWS},
        volatility_pct={str(window): annualized_volatility(prices, window) for window in WINDOWS},
        max_drawdown_pct={str(window): max_drawdown(prices, window) for window in WINDOWS},
        data_points=len(prices),
    )


def aligned_prices(left_candidate: Candidate, right_candidate: Candidate) -> tuple[list[float], list[float]]:
    left = dict(price_rows(left_candidate))
    right = dict(price_rows(right_candidate))
    dates = sorted(set(left).intersection(right))
    return [left[key] for key in dates], [right[key] for key in dates]


def relative_path(candidate: Candidate, reference: Candidate, window: int) -> tuple[float | None, float | None]:
    candidate_prices, reference_prices = aligned_prices(candidate, reference)
    if len(candidate_prices) <= window or len(reference_prices) <= window:
        return None, None
    candidate_return = candidate_prices[-1] / candidate_prices[-window - 1] - 1.0
    reference_return = reference_prices[-1] / reference_prices[-window - 1] - 1.0
    relative_pct = (candidate_return - reference_return) * 100.0
    candidate_daily = daily_returns(candidate_prices[-window - 1 :])
    reference_daily = daily_returns(reference_prices[-window - 1 :])
    relative_daily = [left - right for left, right in zip(candidate_daily, reference_daily)]
    pressure_pct = (
        statistics.pstdev(relative_daily) * math.sqrt(window) * 100.0
        if len(relative_daily) >= 2
        else 0.0
    )
    return relative_pct, relative_pct - pressure_pct


def add_relative_metrics(metrics: Metrics, candidate: Candidate, incumbent: Candidate) -> Metrics:
    relative_returns: dict[str, float | None] = {}
    stress: dict[str, float | None] = {}
    for window in WINDOWS:
        relative_returns[str(window)], stress[str(window)] = relative_path(candidate, incumbent, window)
    metrics.relative_returns_pct = relative_returns
    metrics.relative_stress_lower_pct = stress
    return metrics


def build_metrics(candidates: list[Candidate], incumbent_code: str) -> dict[str, Metrics]:
    by_code = {item.provider_code: item for item in candidates}
    incumbent = by_code.get(incumbent_code)
    result = {item.provider_code: absolute_metrics(item) for item in candidates}
    if incumbent is None:
        return result
    for item in candidates:
        if item.provider_code != incumbent_code:
            add_relative_metrics(result[item.provider_code], item, incumbent)
        else:
            result[item.provider_code].relative_returns_pct = {str(window): 0.0 for window in WINDOWS}
            result[item.provider_code].relative_stress_lower_pct = {str(window): 0.0 for window in WINDOWS}
    return result
