"""费用模型(configs/fees.yaml 为准)。

fees.yaml 只锁定佣金 0.99 USD/单;SEC/CAT 费官方费率随期调整、文件注明
「实现时取官方当期费率」——本实现取保守高估占位值并在报告里明确标注
「估计值待部署期官方核验」:宁可把成本算重,不给回测占便宜。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from pathlib import Path

import yaml

# 保守占位(高估方向):SEC 费按卖出额 0.004%(近年官方在 0.0008%-0.003% 区间浮动),
# CAT 费按每股 0.0001 USD。两者对结论的影响 << 佣金,但必须存在且偏保守。
SEC_FEE_RATE_ESTIMATE = 0.00004
CAT_FEE_PER_SHARE_ESTIMATE = 0.0001


@dataclass(frozen=True)
class FeeModel:
    commission_usd_per_order: float
    sec_fee_rate_on_sell: float = SEC_FEE_RATE_ESTIMATE
    cat_fee_per_share: float = CAT_FEE_PER_SHARE_ESTIMATE
    estimates_pending_official: bool = True
    #: 每边滑点(基点),取 fees.yaml slippage_model.default_bps。**滑点的唯一出处。**
    #: 目前只有影子盘模拟成交调用 slipped_price;回测仍是 0 滑点(现存差距,另行立项)。
    slippage_bps: float = 0.0

    @classmethod
    def from_yaml(cls, path: str | Path = "configs/fees.yaml") -> "FeeModel":
        cfg = yaml.safe_load(Path(path).read_text())
        us = cfg["us_stocks_etf"]
        slip = (cfg.get("slippage_model") or {}).get("default_bps", 0.0)
        return cls(commission_usd_per_order=float(us["commission_usd_per_order"]),
                   slippage_bps=float(slip))

    def slipped_price(self, side: str, price: float) -> float:
        """含滑点成交价:买向上、卖向下取整到分(对自己不利的方向,保守)。"""
        k = Decimal(str(self.slippage_bps)) / Decimal("10000")
        p = Decimal(str(price))
        if side == "BUY":
            return float((p * (1 + k)).quantize(Decimal("0.01"), rounding=ROUND_CEILING))
        return float((p * (1 - k)).quantize(Decimal("0.01"), rounding=ROUND_FLOOR))

    def order_cost_usd(self, *, side: str, quantity: int, price: float) -> float:
        if quantity <= 0:
            return 0.0
        cost = self.commission_usd_per_order + self.cat_fee_per_share * quantity
        if side == "SELL":
            cost += self.sec_fee_rate_on_sell * quantity * price
        return cost

    def round_trip_cost_usd(self, *, quantity: int, price: float) -> float:
        return (self.order_cost_usd(side="BUY", quantity=quantity, price=price)
                + self.order_cost_usd(side="SELL", quantity=quantity, price=price))
