"""组合引擎:多策略信号 -> 唯一目标仓位 -> 订单草案(ALPHA-LIVE-030)。

规则(configs/portfolio.yaml):
- 资金分配 S1/S2 按 base_allocation(月度评审可在 review_bounds 内调整);
- 同标的冲突取净目标(各策略 sleeve 目标相加);
- 现金缓冲永远 ≥ 0:目标总市值超过权益时按比例缩水;
- 调仓阈值:目标与现仓差额(AUD)小于 权益×阈值% 时不动(省过路费);
- 整股:目标数量向下取整,绝不向上凑。

钱一律 Decimal;股数整数。本引擎纯函数,不触任何 I/O。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Mapping, Sequence


@dataclass(frozen=True)
class OrderDraft:
    symbol: str
    side: str           # BUY / SELL
    quantity: int
    strategy_source: str
    reference_price_usd: Decimal


@dataclass(frozen=True)
class SynthesisResult:
    target_quantities: Mapping[str, int]
    drafts: Sequence[OrderDraft]
    scaled_down: bool               # 是否因现金缓冲触发过整体缩水
    diagnostics: Mapping[str, dict]


def _to_aud(usd: Decimal, fx_usd_aud: Decimal) -> Decimal:
    """保守换算:敞口按分向上取整。"""
    return (usd * fx_usd_aud).quantize(Decimal("0.01"), rounding=ROUND_UP)


def synthesize(
    *,
    s1_weights: Mapping[str, float],
    s2_symbols: Sequence[str],
    allocation: Mapping[str, float],          # {"S1_...": 0.80, "S2_...": 0.20}
    s2_max_open_trades: int,
    equity_aud: Decimal,
    prices_usd: Mapping[str, Decimal],
    fx_usd_aud: Decimal,
    current_quantities: Mapping[str, int],
    rebalance_threshold_pct: float = 5.0,
    s1_id: str = "S1_MOMENTUM_ROTATION",
    s2_id: str = "S2_OVERSOLD_REBOUND",
) -> SynthesisResult:
    if equity_aud <= 0:
        raise ValueError("权益必须为正")
    if fx_usd_aud <= 0:
        raise ValueError("汇率必须为正")

    s1_sleeve = equity_aud * Decimal(str(allocation.get(s1_id, 0)))
    s2_sleeve = equity_aud * Decimal(str(allocation.get(s2_id, 0)))

    # 1) 各策略 sleeve 内目标市值(AUD),同标的净合成
    target_notional: dict[str, Decimal] = {}
    source: dict[str, set[str]] = {}
    for symbol, weight in s1_weights.items():
        notional = s1_sleeve * Decimal(str(weight))
        target_notional[symbol] = target_notional.get(symbol, Decimal("0")) + notional
        source.setdefault(symbol, set()).add(s1_id)
    if s2_symbols:
        per_trade = s2_sleeve / Decimal(s2_max_open_trades)
        for symbol in s2_symbols:
            target_notional[symbol] = target_notional.get(symbol, Decimal("0")) + per_trade
            source.setdefault(symbol, set()).add(s2_id)

    # 2) 现金缓冲 >= 0:总目标超权益则整体等比缩水
    total = sum(target_notional.values(), Decimal("0"))
    scaled_down = False
    if total > equity_aud and total > 0:
        ratio = equity_aud / total
        target_notional = {s: (v * ratio) for s, v in target_notional.items()}
        scaled_down = True

    # 3) 换整股目标数量(AUD -> USD -> 股,向下取整)
    target_qty: dict[str, int] = {}
    diagnostics: dict[str, dict] = {}
    for symbol, notional_aud in target_notional.items():
        price = prices_usd.get(symbol)
        if price is None or price <= 0:
            raise ValueError(f"缺少价格: {symbol}")
        price_aud = _to_aud(price, fx_usd_aud)
        qty = int((notional_aud / price_aud).to_integral_value(rounding=ROUND_DOWN))
        target_qty[symbol] = qty
        diagnostics[symbol] = {
            "target_notional_aud": str(notional_aud.quantize(Decimal("0.01"))),
            "price_aud": str(price_aud),
            "target_qty": qty,
            "sources": sorted(source.get(symbol, set())),
        }

    # 4) 与现仓求差,应用调仓阈值,产出订单草案
    threshold_aud = equity_aud * Decimal(str(rebalance_threshold_pct)) / Decimal("100")
    drafts: list[OrderDraft] = []
    all_symbols = set(target_qty) | set(current_quantities)
    for symbol in sorted(all_symbols):
        cur = int(current_quantities.get(symbol, 0))
        tgt = int(target_qty.get(symbol, 0))
        delta = tgt - cur
        if delta == 0:
            continue
        price = prices_usd.get(symbol)
        if price is None or price <= 0:
            raise ValueError(f"缺少价格: {symbol}")
        delta_aud = _to_aud(price * abs(delta), fx_usd_aud)
        if delta_aud < threshold_aud:
            diagnostics.setdefault(symbol, {})["skipped_below_threshold_aud"] = str(delta_aud)
            continue
        strategy = "+".join(sorted(source.get(symbol, {"PORTFOLIO"})))
        drafts.append(
            OrderDraft(
                symbol=symbol,
                side="BUY" if delta > 0 else "SELL",
                quantity=abs(delta),
                strategy_source=strategy,
                reference_price_usd=price,
            )
        )

    return SynthesisResult(
        target_quantities=target_qty,
        drafts=tuple(drafts),
        scaled_down=scaled_down,
        diagnostics=diagnostics,
    )
