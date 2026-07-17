"""S1 全球动量轮动(核心仓)——纯函数实现,逐条对应 configs/strategies/s1_momentum.yaml。

同输入同输出;输出目标权重与全套诊断(每个数字可用白盒规范手工复算)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from backend.app.strategies.bars import Bar, assert_ascending, closes, slice_until
from backend.app.strategies.indicators import realized_vol_annual_pct, sma, trailing_return


MOMENTUM_FAMILY_IDS = {"S1_MOMENTUM_ROTATION", "S1_GOLD_BLEND"}


def load_s1_config(path: str | Path = "configs/strategies/s1_momentum.yaml") -> dict:
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg.get("strategy_id") not in MOMENTUM_FAMILY_IDS:
        raise ValueError(f"非动量族配置: {cfg.get('strategy_id')}")
    return cfg


@dataclass(frozen=True)
class S1Result:
    as_of: date
    target_weights: Mapping[str, float]      # 含波动率调节后的最终权重(现金差额即空余)
    position_scalar: float                    # min(1, 目标波动/实际波动)
    scores: Mapping[str, float] = field(default_factory=dict)
    eligible: Mapping[str, bool] = field(default_factory=dict)
    selected: Sequence[str] = field(default_factory=tuple)
    diagnostics: Mapping[str, dict] = field(default_factory=dict)


def evaluate_s1(
    bars_by_symbol: Mapping[str, Sequence[Bar]],
    cfg: dict,
    as_of: date,
) -> S1Result:
    universe: list[str] = list(cfg["universe"])
    cash = cfg["cash_proxy"]
    lookbacks: list[int] = list(cfg["score"]["lookbacks_trading_days"])
    weights: list[float] = list(cfg["score"]["weights"])
    sma_period: int = int(cfg["absolute_momentum_filter"]["sma_period"])
    top_n: int = int(cfg["selection"]["top_n"])
    weight_each: float = float(cfg["selection"]["weight_each"])
    vt = cfg["volatility_targeting"]
    vt_enabled = bool(vt.get("enabled", True))
    high_prox_cfg = cfg.get("high_proximity_filter") or {}
    high_prox: float | None = high_prox_cfg.get("threshold")
    overlay = cfg.get("defensive_overlay") or {}
    overlay_symbol: str | None = overlay.get("symbol")
    overlay_weight: float = float(overlay.get("weight", 0.0)) if overlay_symbol else 0.0
    risk_budget = 1.0 - overlay_weight

    scores: dict[str, float] = {}
    eligible: dict[str, bool] = {}
    diagnostics: dict[str, dict] = {}

    for symbol in universe:
        bars = slice_until(bars_by_symbol.get(symbol, ()), as_of)
        if bars:
            assert_ascending(bars)
        c = closes(bars)
        rs = [trailing_return(c, lb) for lb in lookbacks]
        sma200 = sma(c, sma_period)
        data_ok = all(r is not None for r in rs) and sma200 is not None and bool(c)
        if not data_ok:
            eligible[symbol] = False
            diagnostics[symbol] = {"data_ok": False}
            continue
        score = sum(w * r for w, r in zip(weights, rs))  # type: ignore[arg-type]
        above = c[-1] > sma200
        near_high = True
        high252 = max(c[-252:]) if len(c) >= 252 else None
        if high_prox is not None:
            near_high = high252 is not None and c[-1] >= high_prox * high252
        scores[symbol] = score
        eligible[symbol] = above and near_high
        diagnostics[symbol] = {
            "data_ok": True,
            "close": c[-1],
            "sma200": sma200,
            "returns": dict(zip([f"r{lb}" for lb in lookbacks], rs)),
            "score": score,
            "above_sma200": above,
            "high252": high252,
            "near_high": near_high,
        }

    candidates = [s for s in universe if s != cash and eligible.get(s)]
    ranked = sorted(candidates, key=lambda s: (-scores[s], universe.index(s)))
    selected = tuple(ranked[:top_n])

    # 波动率调节:用「入选标的等权组合」的近 20 日已实现波动(可经配置关闭)
    scalar = 1.0
    if selected and vt_enabled:
        vols = []
        for symbol in selected:
            c = closes(slice_until(bars_by_symbol[symbol], as_of))
            v = realized_vol_annual_pct(c, int(vt["realized_vol_window_days"]))
            if v is not None:
                vols.append(v)
        if vols:
            portfolio_vol = sum(vols) / len(vols)
            if portfolio_vol > 0:
                scalar = min(1.0, float(vt["target_annual_vol_pct"]) / portfolio_vol)

    # 防御叠加:恒持 overlay_weight,动量只分配剩余 risk_budget
    target: dict[str, float] = {}
    if overlay_symbol and overlay_weight > 0:
        target[overlay_symbol] = overlay_weight
    if selected:
        for symbol in selected:
            target[symbol] = target.get(symbol, 0.0) + weight_each * scalar * risk_budget
    else:
        target[cash] = target.get(cash, 0.0) + risk_budget  # 无人合格 -> 风险仓退现金替身

    return S1Result(
        as_of=as_of,
        target_weights=target,
        position_scalar=scalar,
        scores=scores,
        eligible=eligible,
        selected=selected,
        diagnostics=diagnostics,
    )
