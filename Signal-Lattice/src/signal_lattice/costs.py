"""交易成本模型：回测（backtest/hub_backtest.py）与前向记分簿（ledger.py）共用同一份，前向与回测的口径才是对齐的。

假设（写明，不藏）
  · 每边成本按该股 20 日成交额中位数分档估计（买卖价差的一半 + 冲击），再加 Alpha 费用模型的固定费用（佣金、SEC、CAT）。
  · 仓位假设 1 万美元：>=5000 万美元 10bp，1000–5000 万 25bp，300–1000 万 50bp，更低（含取不到）80bp。往返 = 两边之和。
  · 取不到成交额时按最差一档（80bp）算：宁可把成本算重，不给结果占便宜。
"""

from __future__ import annotations

from typing import Optional

from .backtest.fees import FeeModel

POSITION_USD = 10_000.0
COST_TIERS_BPS_PER_SIDE = ((50e6, 10.0), (10e6, 25.0), (3e6, 50.0))
COST_BELOW_TIERS_BPS = 80.0
# IWM 流动性极好：只算固定费用（回测和前向都这样）。
BENCHMARK_DOLLAR_VOLUME = 1e12


def cost_bps_per_side(median_dollar_volume: Optional[float]) -> float:
    for threshold, bps in COST_TIERS_BPS_PER_SIDE:
        if median_dollar_volume is not None and median_dollar_volume >= threshold:
            return bps
    return COST_BELOW_TIERS_BPS


def round_trip_cost(median_dollar_volume: Optional[float], price: float) -> float:
    """往返成本占仓位的比例：两边的分档成本 + 固定费用（佣金、SEC、CAT）。"""
    quantity = max(1, int(POSITION_USD / price)) if price > 0 else 1
    fixed = FeeModel.default().round_trip_cost_usd(quantity=quantity, price=price) / POSITION_USD
    return 2.0 * cost_bps_per_side(median_dollar_volume) / 1e4 + fixed
