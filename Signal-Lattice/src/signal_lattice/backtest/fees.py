# 来源: Alpha/backend/app/backtest/fees.py; 原路径: Alpha/backend/app/backtest/fees.py.
"""费用模型(configs/fees.yaml 为准)。

fees.yaml 只锁定佣金 0.99 USD/单;SEC/CAT 费官方费率随期调整、文件注明
「实现时取官方当期费率」——本实现取保守高估占位值并在报告里明确标注
「估计值待部署期官方核验」:宁可把成本算重,不给回测占便宜。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# 保守占位(高估方向):SEC 费按卖出额 0.004%(近年官方在 0.0008%-0.003% 区间浮动),
# CAT 费按每股 0.0001 USD。两者对结论的影响 << 佣金,但必须存在且偏保守。
SEC_FEE_RATE_ESTIMATE = 0.00004
CAT_FEE_PER_SHARE_ESTIMATE = 0.0001

# 来源：Alpha/configs/fees.yaml（已在本轮读取）。本回测只使用其中明确给出的
# 美股/ETF 每笔佣金；SEC/CAT 保守估计值保留 Alpha 原实现，报告会逐项披露。
DEFAULT_FEE_CONFIG = {
    "commission_usd_per_order": 0.99,
    "sec_fee_rate_on_sell": SEC_FEE_RATE_ESTIMATE,
    "cat_fee_per_share": CAT_FEE_PER_SHARE_ESTIMATE,
}


@dataclass(frozen=True)
class FeeModel:
    commission_usd_per_order: float
    sec_fee_rate_on_sell: float = SEC_FEE_RATE_ESTIMATE
    cat_fee_per_share: float = CAT_FEE_PER_SHARE_ESTIMATE
    estimates_pending_official: bool = True

    @classmethod
    def default(cls, override: Mapping[str, float] | None = None) -> "FeeModel":
        """返回显式默认费用模型，可用同形状映射覆盖。

        默认值逐项来自 Alpha/configs/fees.yaml；不依赖 Alpha 目录或 YAML
        运行时依赖，避免本仓回测在目录布局变化后静默退化为无摩擦。
        """
        values = {**DEFAULT_FEE_CONFIG, **dict(override or {})}
        return cls(
            commission_usd_per_order=float(values["commission_usd_per_order"]),
            sec_fee_rate_on_sell=float(values["sec_fee_rate_on_sell"]),
            cat_fee_per_share=float(values["cat_fee_per_share"]),
        )

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
