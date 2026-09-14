"""S1 全球动量轮动。

来源：``Alpha/backend/app/strategies/s1_momentum.py``；参数逐值来自
``Alpha/configs/strategies/s1_momentum.yaml``。本副本以显式默认字典和可选
覆盖替代 Alpha 的 YAML 路径依赖。
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date
from typing import Mapping, Sequence

from .bars import assert_ascending, closes, slice_until
from .indicators import realized_vol_annual_pct, sma, trailing_return
from ..marketdata.models import Bar


DEFAULT_S1_CONFIG: dict[str, object] = {
    "strategy_id": "S1_MOMENTUM_ROTATION",
    "version": "1.0.0",
    "universe": ["SPY", "QQQ", "IWM", "EFA", "EEM", "GLD", "TLT", "BIL"],
    "cash_proxy": "BIL",
    "score": {
        "formula": "0.4*r63 + 0.3*r126 + 0.3*r252",
        "lookbacks_trading_days": [63, 126, 252],
        "weights": [0.4, 0.3, 0.3],
    },
    "absolute_momentum_filter": {"rule": "close > SMA200", "sma_period": 200},
    "selection": {"top_n": 2, "weight_each": 0.5},
    "volatility_targeting": {
        "target_annual_vol_pct": 12,
        "realized_vol_window_days": 20,
        "position_scalar": "min(1, target/realized)",
    },
    "rebalance_threshold_pct": 5,
}


def default_s1_config(overrides: Mapping[str, object] | None = None) -> dict[str, object]:
    """返回 Alpha 参数的可覆盖副本。"""
    config = deepcopy(DEFAULT_S1_CONFIG)
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, Mapping) and isinstance(config.get(key), dict):
                config[key].update(value)  # type: ignore[index,union-attr]
            else:
                config[key] = value
    return config


@dataclass(frozen=True)
class S1Result:
    as_of: date
    target_weights: Mapping[str, float]
    position_scalar: float
    scores: Mapping[str, float] = field(default_factory=dict)
    eligible: Mapping[str, bool] = field(default_factory=dict)
    selected: Sequence[str] = field(default_factory=tuple)
    diagnostics: Mapping[str, dict] = field(default_factory=dict)


def evaluate_s1(
    bars_by_symbol: Mapping[str, Sequence[Bar]], config: Mapping[str, object], as_of: date
) -> S1Result:
    universe = list(config["universe"])  # type: ignore[index]
    cash = str(config["cash_proxy"])
    score_config = config["score"]  # type: ignore[index]
    lookbacks = list(score_config["lookbacks_trading_days"])  # type: ignore[index]
    weights = list(score_config["weights"])  # type: ignore[index]
    sma_period = int(config["absolute_momentum_filter"]["sma_period"])  # type: ignore[index]
    top_n = int(config["selection"]["top_n"])  # type: ignore[index]
    weight_each = float(config["selection"]["weight_each"])  # type: ignore[index]
    volatility = config["volatility_targeting"]  # type: ignore[index]

    scores: dict[str, float] = {}
    eligible: dict[str, bool] = {}
    diagnostics: dict[str, dict] = {}
    for symbol in universe:
        symbol_bars = slice_until(bars_by_symbol.get(symbol, ()), as_of)
        if symbol_bars:
            assert_ascending(symbol_bars)
        close_values = closes(symbol_bars)
        returns = [trailing_return(close_values, int(lookback)) for lookback in lookbacks]
        average = sma(close_values, sma_period)
        data_ok = all(value is not None for value in returns) and average is not None and bool(close_values)
        if not data_ok:
            eligible[symbol] = False
            diagnostics[symbol] = {"data_ok": False}
            continue
        score = sum(weight * value for weight, value in zip(weights, returns))  # type: ignore[operator]
        scores[symbol] = score
        eligible[symbol] = close_values[-1] > average
        diagnostics[symbol] = {
            "data_ok": True,
            "close": close_values[-1],
            "sma200": average,
            "returns": {f"r{lookback}": value for lookback, value in zip(lookbacks, returns)},
            "score": score,
            "above_sma200": close_values[-1] > average,
        }

    candidates = [symbol for symbol in universe if symbol != cash and eligible.get(symbol)]
    ranked = sorted(candidates, key=lambda symbol: (-scores[symbol], universe.index(symbol)))
    selected = tuple(ranked[:top_n])
    scalar = 1.0
    if selected:
        volatility_values = []
        for symbol in selected:
            volatility_value = realized_vol_annual_pct(
                closes(slice_until(bars_by_symbol[symbol], as_of)),
                int(volatility["realized_vol_window_days"]),  # type: ignore[index]
            )
            if volatility_value is not None:
                volatility_values.append(volatility_value)
        if volatility_values:
            portfolio_volatility = sum(volatility_values) / len(volatility_values)
            if portfolio_volatility > 0:
                scalar = min(1.0, float(volatility["target_annual_vol_pct"]) / portfolio_volatility)  # type: ignore[index]

    target_weights: dict[str, float] = {}
    if selected:
        for symbol in selected:
            target_weights[symbol] = weight_each * scalar
    else:
        target_weights[cash] = 1.0
    return S1Result(as_of, target_weights, scalar, scores, eligible, selected, diagnostics)
