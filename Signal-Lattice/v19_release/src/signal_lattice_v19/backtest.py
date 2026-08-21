from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PriceRow:
    day: date
    symbol: str
    close: float


@dataclass(frozen=True)
class EpisodeRow:
    effective_day: date
    symbol: str


def _parse_day(value: Any) -> date:
    text = str(value).strip()
    return datetime.fromisoformat(text.replace("Z", "+00:00")).date()


def load_prices(path: Path) -> list[PriceRow]:
    suffix = path.suffix.lower()
    rows: list[dict[str, Any]]
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, dict):
            raw = value.get("prices", value.get("items", []))
        else:
            raw = value
        if not isinstance(raw, list):
            raise ValueError("PRICE_ROWS_REQUIRED")
        rows = [row for row in raw if isinstance(row, dict)]
    result: list[PriceRow] = []
    for row in rows:
        day_value = row.get("date", row.get("time_key", row.get("time")))
        symbol = str(row.get("symbol", row.get("code", row.get("provider_code", "")))).strip()
        close = row.get("close", row.get("price"))
        if day_value is None or not symbol or close is None:
            continue
        result.append(PriceRow(_parse_day(day_value), symbol, float(close)))
    result.sort(key=lambda item: (item.day, item.symbol))
    if not result:
        raise ValueError("NO_VALID_PRICE_ROWS")
    return result


def load_episodes(path: Path) -> list[EpisodeRow]:
    value = json.loads(path.read_text(encoding="utf-8"))
    raw = value.get("episodes", value.get("items", value)) if isinstance(value, dict) else value
    if not isinstance(raw, list):
        raise ValueError("EPISODE_ROWS_REQUIRED")
    result: list[EpisodeRow] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        day_value = row.get("effective_date", row.get("opened_at", row.get("date")))
        symbol = str(row.get("symbol", row.get("winner_code", row.get("code", "")))).strip()
        if day_value is None or not symbol:
            continue
        result.append(EpisodeRow(_parse_day(day_value), symbol))
    result.sort(key=lambda item: item.effective_day)
    if not result:
        raise ValueError("NO_VALID_EPISODES")
    return result


def _drawdown(path: list[float]) -> float:
    if not path:
        return 0.0
    high = path[0]
    worst = 0.0
    for value in path:
        high = max(high, value)
        if high > 0:
            worst = max(worst, (high - value) / high * 100.0)
    return worst


def _rolling_returns(values: list[float], window: int) -> list[float]:
    if len(values) <= window:
        return []
    return [(values[index] / values[index - window] - 1.0) * 100.0 for index in range(window, len(values))]


def run_walk_forward(
    prices: list[PriceRow],
    episodes: list[EpisodeRow],
    *,
    benchmark_symbol: str,
    cash_rate_annual_pct: float,
    switch_cost_pct: float,
    nominal_aud: float = 10000.0,
) -> dict[str, Any]:
    by_symbol: dict[str, dict[date, float]] = defaultdict(dict)
    for row in prices:
        by_symbol[row.symbol][row.day] = row.close
    if benchmark_symbol not in by_symbol:
        raise ValueError("BENCHMARK_PRICE_SERIES_MISSING")

    all_days = sorted(by_symbol[benchmark_symbol])
    if len(all_days) < 2:
        raise ValueError("INSUFFICIENT_BENCHMARK_SERIES")

    # Decision becomes tradable on the next available benchmark day after it opens.
    effective: list[EpisodeRow] = []
    for episode in episodes:
        next_days = [day for day in all_days if day > episode.effective_day]
        if next_days:
            effective.append(EpisodeRow(next_days[0], episode.symbol))
    if not effective:
        raise ValueError("NO_EPISODE_HAS_FORWARD_BAR")

    current_symbol: str | None = None
    episode_index = 0
    strategy = float(nominal_aud)
    benchmark = float(nominal_aud)
    cash = float(nominal_aud)
    strategy_path = [strategy]
    benchmark_path = [benchmark]
    cash_path = [cash]
    observations = 0
    switches = 0
    unavailable_days = 0
    daily_cash = (1.0 + cash_rate_annual_pct / 100.0) ** (1.0 / 252.0) - 1.0

    for index in range(1, len(all_days)):
        day = all_days[index]
        previous_day = all_days[index - 1]
        while episode_index < len(effective) and effective[episode_index].effective_day <= day:
            next_symbol = effective[episode_index].symbol
            if current_symbol is not None and next_symbol != current_symbol:
                strategy *= 1.0 - switch_cost_pct / 100.0
                switches += 1
            elif current_symbol is None:
                strategy *= 1.0 - switch_cost_pct / 200.0
            current_symbol = next_symbol
            episode_index += 1

        benchmark_previous = by_symbol[benchmark_symbol].get(previous_day)
        benchmark_current = by_symbol[benchmark_symbol].get(day)
        if benchmark_previous and benchmark_current:
            benchmark *= benchmark_current / benchmark_previous

        if current_symbol:
            previous = by_symbol.get(current_symbol, {}).get(previous_day)
            current = by_symbol.get(current_symbol, {}).get(day)
            if previous and current:
                strategy *= current / previous
                observations += 1
            else:
                unavailable_days += 1
        cash *= 1.0 + daily_cash
        strategy_path.append(strategy)
        benchmark_path.append(benchmark)
        cash_path.append(cash)

    if current_symbol is not None:
        strategy *= 1.0 - switch_cost_pct / 200.0
        strategy_path[-1] = strategy

    strategy_return = (strategy / nominal_aud - 1.0) * 100.0
    benchmark_return = (benchmark / nominal_aud - 1.0) * 100.0
    cash_return = (cash / nominal_aud - 1.0) * 100.0
    drawdown = _drawdown(strategy_path)
    rolling_20 = _rolling_returns(strategy_path, 20)
    rolling_60 = _rolling_returns(strategy_path, 60)
    median_60 = sorted(rolling_60)[len(rolling_60) // 2] if rolling_60 else None

    reasons: list[str] = []
    if observations < 120:
        reasons.append("少于120个真实前向交易日观测")
    if strategy_return <= cash_return:
        reasons.append("扣费后未超过现金基线")
    # A strategy holding the benchmark itself still incurs its own entry/exit costs.
    # It therefore must be compared with the cost-free benchmark on every run.
    if strategy_return <= benchmark_return:
        reasons.append("扣费后未超过可比宽基")
    if drawdown >= 20.0:
        reasons.append("最大回撤达到或超过20%")
    if median_60 is None or median_60 <= 0.0:
        reasons.append("60日滚动扣费后中位收益未为正")
    if unavailable_days:
        reasons.append(f"{unavailable_days}个交易日缺少所选标的价格")

    gate = "PASS" if not reasons else "FAIL"
    return {
        "status": "EXECUTED",
        "gate_status": gate,
        "observations": observations,
        "calendar_days": len(all_days),
        "switches": switches,
        "switch_cost_pct": switch_cost_pct,
        "strategy_net_return_pct": round(strategy_return, 6),
        "benchmark_net_return_pct": round(benchmark_return, 6),
        "cash_return_pct": round(cash_return, 6),
        "max_drawdown_pct": round(drawdown, 6),
        "rolling_20_count": len(rolling_20),
        "rolling_60_count": len(rolling_60),
        "median_60_return_pct": round(median_60, 6) if median_60 is not None else None,
        "benchmark_symbol": benchmark_symbol,
        "last_symbol": current_symbol,
        "reasons": reasons,
        "profitability_claim": "NOT_ISSUED" if gate != "PASS" else "BACKTEST_GATE_ONLY",
        "warning": "PASS只代表给定历史数据与已冻结Episode通过回测门，不代表未来收益或生产验收。",
    }
