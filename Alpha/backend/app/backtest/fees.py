"""费用模型(configs/fees.yaml 为准)。

fees.yaml 只锁定佣金 0.99 USD/单;SEC/CAT 费官方费率随期调整、文件注明
「实现时取官方当期费率」——本实现取保守高估占位值并在报告里明确标注
「估计值待部署期官方核验」:宁可把成本算重,不给回测占便宜。
"""

from __future__ import annotations

from dataclasses import dataclass
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

    @classmethod
    def from_yaml(cls, path: str | Path = "configs/fees.yaml") -> "FeeModel":
        cfg = yaml.safe_load(Path(path).read_text())
        us = cfg["us_stocks_etf"]
        return cls(commission_usd_per_order=float(us["commission_usd_per_order"]))

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
