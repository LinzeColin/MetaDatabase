"""确定性风控引擎——configs/trading_governor_policy.yaml 的每一条在此可复算。

纯函数:evaluate(ctx) -> RiskVerdict。不短路:所有规则全部评估,
触发列表完整落审计(风控拒绝路径全部有审计记录的验收要求由 store 层配合)。

规则口径:
- 总敞口:成交后 现敞口+买单预留+本单 ≤ 3000 AUD;等于线放行,超一分拒。
- 胖手指:单笔 ≤ 总授权×60% = 1800 AUD(买卖都防,防错单不防方向)。
- 频控:任意滚动 60 分钟窗口内订单数 ≤ 5;第 6 笔拒。
- 白名单:BUY 仅 US_STOCK/US_ETF;SELL(减仓)不受白名单限制。
- 辖区:BUY 需最近一次探针 ALLOW;SELL 放行(退出永远可行)。
- 新鲜度:行情陈旧一律停新单(含止损单——失败关闭优先,宁停不乱)。
- 断路器:STOP_NEW/COOLDOWN 拒 BUY 放 SELL;DEMOTED 全拒(已降回 Paper)。
- 杀开关/对账未清:全拒。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_UP, Decimal
from enum import Enum
from typing import Optional, Sequence


class BreakerLevel(str, Enum):
    NONE = "NONE"
    STOP_NEW = "STOP_NEW"                  # 单日 -2%:当日停新仓
    FLATTEN_COOLDOWN = "FLATTEN_COOLDOWN"  # 3 日 -4%:退防现金 + 48h 冷静
    DEMOTED_PAPER = "DEMOTED_PAPER"        # 月内 -8%:降回 Paper


@dataclass(frozen=True)
class BreakerThresholds:
    daily_stop_new_pct: float = 2.0
    three_day_flatten_pct: float = 4.0
    monthly_demote_pct: float = 8.0
    cooldown_hours: int = 48


def evaluate_breakers(
    *,
    daily_pnl_pct: float,
    three_day_cum_pnl_pct: float,
    month_drawdown_pct: float,
    last_flatten_at: Optional[datetime],
    now: datetime,
    thresholds: BreakerThresholds = BreakerThresholds(),
) -> BreakerLevel:
    """亏损输入为负数;回撤输入为正数(自高点回落幅度)。等于阈值即触发。"""
    if month_drawdown_pct >= thresholds.monthly_demote_pct:
        return BreakerLevel.DEMOTED_PAPER
    in_cooldown = (
        last_flatten_at is not None
        and now - last_flatten_at < timedelta(hours=thresholds.cooldown_hours)
    )
    if -three_day_cum_pnl_pct >= thresholds.three_day_flatten_pct or in_cooldown:
        return BreakerLevel.FLATTEN_COOLDOWN
    if -daily_pnl_pct >= thresholds.daily_stop_new_pct:
        return BreakerLevel.STOP_NEW
    return BreakerLevel.NONE


@dataclass(frozen=True)
class RiskContext:
    side: str                       # BUY / SELL
    symbol: str
    market: str                     # US_STOCK / US_ETF / HK_STOCK / ...
    quantity: int
    price_usd: Decimal
    fx_usd_aud: Decimal
    now: datetime
    current_gross_exposure_aud: Decimal = Decimal("0")
    pending_buy_reserved_aud: Decimal = Decimal("0")
    max_gross_exposure_aud: Decimal = Decimal("3000")
    fat_finger_ratio: Decimal = Decimal("0.90")   # owner 2026-07-24 书面放宽(原 0.60);权威值见 configs/trading_governor_policy.yaml
    recent_order_times: Sequence[datetime] = field(default_factory=tuple)
    rate_limit_max_orders: int = 5
    rate_limit_window_minutes: int = 60
    allowed_markets: frozenset[str] = frozenset({"US_STOCK", "US_ETF"})
    quote_age_seconds: Optional[float] = None
    freshness_threshold_seconds: float = 5.0
    breaker_level: BreakerLevel = BreakerLevel.NONE
    kill_switch_active: bool = False
    reconciliation_open: bool = False
    jurisdiction_verdict: str = "DENY"   # 缺省 DENY:没跑探针就不许买(失败关闭)


@dataclass(frozen=True)
class RiskVerdict:
    allowed: bool
    triggered_rules: tuple[str, ...]
    snapshot: dict


def order_notional_aud(ctx: RiskContext) -> Decimal:
    """敞口口径:数量×价格×汇率,按分向上取整(保守)。"""
    return (Decimal(ctx.quantity) * ctx.price_usd * ctx.fx_usd_aud).quantize(
        Decimal("0.01"), rounding=ROUND_UP
    )


def evaluate(ctx: RiskContext) -> RiskVerdict:
    if ctx.side not in ("BUY", "SELL"):
        raise ValueError(f"未知方向: {ctx.side}")
    if ctx.quantity <= 0 or ctx.price_usd <= 0:
        raise ValueError("数量与价格必须为正")

    triggered: list[str] = []
    notional = order_notional_aud(ctx)
    is_buy = ctx.side == "BUY"

    # 全局停止类
    if ctx.kill_switch_active:
        triggered.append("RULE_KILL_SWITCH_ACTIVE")
    if ctx.reconciliation_open:
        triggered.append("RULE_RECONCILIATION_OPEN")
    if ctx.breaker_level is BreakerLevel.DEMOTED_PAPER:
        triggered.append("RULE_BREAKER_DEMOTED_PAPER")

    # 新鲜度:陈旧行情停一切新单(含止损——宁停不乱,由对账/人工恢复)
    if ctx.quote_age_seconds is None:
        triggered.append("RULE_MARKET_DATA_MISSING")
    elif not (0.0 <= ctx.quote_age_seconds <= ctx.freshness_threshold_seconds):
        triggered.append("RULE_MARKET_DATA_STALE")

    # 频控:任意滚动窗口 ≤ 5 笔
    window_start = ctx.now - timedelta(minutes=ctx.rate_limit_window_minutes)
    recent = [t for t in ctx.recent_order_times if window_start < t <= ctx.now]
    if len(recent) >= ctx.rate_limit_max_orders:
        triggered.append("RULE_BUSINESS_RATE_LIMIT")

    # 胖手指:买卖都防
    fat_finger_cap = (ctx.max_gross_exposure_aud * ctx.fat_finger_ratio).quantize(Decimal("0.01"))
    if notional > fat_finger_cap:
        triggered.append("RULE_FAT_FINGER_SINGLE_ORDER")

    # 仅 BUY 的规则
    if is_buy:
        if ctx.market not in ctx.allowed_markets:
            triggered.append("RULE_MARKET_WHITELIST")
        if ctx.jurisdiction_verdict != "ALLOW":
            triggered.append("RULE_JURISDICTION_DENY")
        exposure_after = ctx.current_gross_exposure_aud + ctx.pending_buy_reserved_aud + notional
        if exposure_after > ctx.max_gross_exposure_aud:
            triggered.append("RULE_GROSS_EXPOSURE_CAP")
        if ctx.breaker_level in (BreakerLevel.STOP_NEW, BreakerLevel.FLATTEN_COOLDOWN):
            triggered.append("RULE_BREAKER_STOP_NEW")
    else:
        exposure_after = ctx.current_gross_exposure_aud  # SELL 不增敞口

    snapshot = {
        "notional_aud": str(notional),
        "fat_finger_cap_aud": str(fat_finger_cap),
        "current_gross_exposure_aud": str(ctx.current_gross_exposure_aud),
        "pending_buy_reserved_aud": str(ctx.pending_buy_reserved_aud),
        "exposure_after_aud": str(exposure_after),
        "max_gross_exposure_aud": str(ctx.max_gross_exposure_aud),
        "orders_in_window": len(recent),
        "quote_age_seconds": ctx.quote_age_seconds,
        "breaker_level": ctx.breaker_level.value,
        "jurisdiction_verdict": ctx.jurisdiction_verdict,
        "market": ctx.market,
        "side": ctx.side,
    }
    return RiskVerdict(allowed=not triggered, triggered_rules=tuple(triggered), snapshot=snapshot)
