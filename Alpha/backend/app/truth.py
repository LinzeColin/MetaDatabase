"""单一真源:同一事实只在这里算一次(二次部署门 #24)。

2026-07/08 连续两次被"同一事实多处各算"咬到:
- 页头徽章读 env 判实盘、考核卡另算一次 → "页头写微实盘、门禁写保持 Paper"自相矛盾;
- 本金用契约汇率折美元、净值用实时汇率折回澳元 → 凭空造出 -194.65 假亏损;
- 单笔比例 60%→90% 牵动七处,漏一处就让交易静默停摆 10 小时。

铁律:**同一事实单一真源。** 任何"实盘吗/汇率多少/本金多少/单笔上限多少"的问题,
全项目只准从本模块取答案,不准就地再写一遍 os.environ.get(...)。
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from typing import Mapping, NamedTuple, Optional
from zoneinfo import ZoneInfo

from backend.app.adapters.brokers.base import SystemMode

SYD = ZoneInfo("Australia/Sydney")

#: 契约资金常量(与 configs/trading_governor_policy.yaml 一致;env 可覆盖用于测试)
DEFAULT_CAPITAL_AUD = 3000.0
#: 契约保守汇率:资金上限只紧不松,**不随行情浮动**(实时汇率只用于净值显示)
DEFAULT_CONTRACT_FX = 0.65
POLICY_PATH = "configs/trading_governor_policy.yaml"
#: 生产策略配置(S1_GEM_PLUS_FINE)。此前 live_cycle 缺省指向已退役的 gold_blend。
DEFAULT_STRATEGY_CONFIG = "configs/strategies/s1_gem_plus.yaml"

#: 模式 -> (徽章, 一句话说明)。看盘页、摘要、体检只从这里取文案。
MODE_LABELS: dict[SystemMode, tuple[str, str]] = {
    SystemMode.SHADOW: (
        "影子盘：按真实行情模拟成交，未动真钱",
        "不连券商、不登录；用 Yahoo 实时行情在本机模拟成交，手续费按 moomoo AU 价目扣，账本真实记账。"
        "未计分红(BIL、IEF 的派息占回报大头)，净值偏保守，与回测的复权总回报口径不可直接比较。"),
    SystemMode.PAPER: (
        "模拟盘",
        "用券商模拟账户和真实行情演练,不动真钱;moomoo 手机应用里看不到这个模拟账户,本页就是唯一窗口。"),
    SystemMode.MICRO_LIVE: (
        "微实盘(真实资金)",
        "真实资金、真实订单,每一笔买卖都会原生出现在你的 moomoo 应用里;失败关闭。"),
    SystemMode.DISABLED: ("未启用（不交易）", "交易循环未启用:不评估、不下单。"),
    SystemMode.HALTED: ("未启用（不交易）", "系统已停机:不评估、不下单。"),
}


#: 模式 -> 页面上"策略"前的措辞(策略页标签、研究表现役标注)与升级门禁标题。文案只在这里定义。
STRATEGY_WORDS: dict[SystemMode, tuple[str, str]] = {
    SystemMode.SHADOW: ("影子盘", "升级门禁(影子盘不会自动升级;升级只能由 owner 触发)"),
    SystemMode.PAPER: ("模拟盘", "晋级实盘的四道门(实时读契约配置)"),
    SystemMode.MICRO_LIVE: ("实盘", "晋级实盘的四道门(实时读契约配置)"),
    SystemMode.DISABLED: ("实盘", "晋级实盘的四道门(实时读契约配置)"),
    SystemMode.HALTED: ("实盘", "晋级实盘的四道门(实时读契约配置)"),
}

#: 影子盘下看盘页"阶段卡"的说明(纸面三日考核与晋级门禁只适用于券商模拟盘)
SHADOW_STAGE_NOTE = (
    "影子盘用真实行情模拟成交、不动真钱;三日模拟盘考核与实盘晋级门禁只适用于券商模拟盘,本模式不适用。",
    "升级到券商模拟盘或微实盘只能由 owner 触发,系统绝不自动升级;升级必须换全新的账本与运行目录。",
)


def mode(environ: Optional[Mapping[str, str]] = None) -> SystemMode:
    """当前运行模式。**全项目唯一解析点。**

    读 ALPHA_MODE(不分大小写);缺失、空值、拼错一律 DISABLED——**没有缺省 PAPER**。
    DISABLED 在 wiring 里没有装配条目,于是交易循环失败关闭(BLOCKED_ON_MODE)。
    environ 缺省读进程环境;体检脚本校验环境文件时传入待检的映射。
    """
    raw = (os.environ if environ is None else environ).get("ALPHA_MODE", "").strip().upper()
    try:
        return SystemMode(raw)
    except ValueError:
        return SystemMode.DISABLED


def mode_label(m: Optional[SystemMode] = None) -> str:
    return MODE_LABELS[m or mode()][0]


def mode_explainer(m: Optional[SystemMode] = None) -> str:
    return MODE_LABELS[m or mode()][1]


def expects_evaluation(m: Optional[SystemMode] = None) -> bool:
    """该模式是否应当按节拍评估(漏评估判据据此判红)。"""
    return (m or mode()) in (SystemMode.SHADOW, SystemMode.PAPER, SystemMode.MICRO_LIVE)


def runtime_dir() -> Path:
    """运行期可写目录(标记、冻结本金、完成记录都在这里)。"""
    return Path(os.environ.get("ALPHA_RUNTIME_DIR", "runtime"))


def facts_dir() -> Path:
    """运行期事实文件目录(代码目录只读时也可写)。"""
    return runtime_dir() / "facts"


def strategy_config_path() -> str:
    return os.environ.get("ALPHA_STRATEGY_CONFIG") or DEFAULT_STRATEGY_CONFIG


def is_micro_live() -> bool:
    """是否处于微实盘(真实资金)。**全项目唯一判据。**

    两个条件都满足才算:模式=MICRO_LIVE 且实盘总开关=1。
    注意:此前 store/db.py 只看 ALPHA_MODE 而不看总开关,与其余三处定义不一致——
    虽然方向偏保守(失败关闭)不致命,但"同一事实两种定义"本身就是隐患。
    """
    return (os.environ.get("ALPHA_MODE", "").upper() == "MICRO_LIVE"
            and os.environ.get("LIVE_TRADING_ENABLED", "0") == "1")


def capital_aud(policy_path: str = POLICY_PATH) -> float:
    """管理切片本金(澳元)。期初本金与授权上限的唯一来源。

    优先级:env 覆盖(测试用) > 权威配置 capital_authorization.max_managed_gross_exposure > 兜底常量。
    """
    env = os.environ.get("ALPHA_CAPITAL_AUD")
    if env:
        try:
            return float(env)
        except (TypeError, ValueError):
            pass
    cap = _policy(policy_path).get("capital_authorization") or {}
    try:
        return float(cap["max_managed_gross_exposure"])
    except (KeyError, TypeError, ValueError):
        return DEFAULT_CAPITAL_AUD


def contract_fx_aud_usd() -> float:
    """契约保守汇率(澳元→美元)。用于授权额度/下单额度换算,**绝不用实时汇率**。

    实时汇率只用于把美元资产折成澳元显示;二者混用会造出汇率往返假盈亏。
    """
    try:
        return float(os.environ.get("ALPHA_FX_AUD_USD", DEFAULT_CONTRACT_FX))
    except (TypeError, ValueError):
        return DEFAULT_CONTRACT_FX


@lru_cache(maxsize=4)
def _policy(path: str) -> dict:
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text()) or {}
    except Exception:
        return {}


def fat_finger_ratio(policy_path: str = POLICY_PATH) -> float:
    """单笔上限比例。**从权威配置读**,不准在代码里写死。

    2026-07-28 教训:live_cycle 曾把 0.90 硬编码在下单额度计算里,与 policy.yaml 各写一遍;
    改比例时漏改任何一处,轻则额度不符,重则授权哈希失配导致交易静默停摆。
    """
    cap = _policy(policy_path).get("capital_authorization") or {}
    try:
        return float(cap["fat_finger_max_single_order_ratio"])
    except (KeyError, TypeError, ValueError):
        # 配置读不到时取最保守值(0.6 是历史初始值),绝不乐观放大额度
        return 0.6


def single_order_cap_usd(*, slippage_headroom: float = 0.97,
                         policy_path: str = POLICY_PATH) -> float:
    """单笔名义上限(美元)= 本金 × 单笔比例 × 契约汇率 × 滑点余量。下单额度的唯一算法。"""
    return capital_aud() * fat_finger_ratio(policy_path) * slippage_headroom * contract_fx_aud_usd()


def fx_usd_aud(fx_aud_usd: Optional[float] = None) -> Decimal:
    """契约汇率的倒数(美元→澳元),风控与两处装配共用的唯一折算系数。"""
    fx = contract_fx_aud_usd() if fx_aud_usd is None else fx_aud_usd
    return Decimal(str(round(1.0 / fx, 6)))


def equity_aud(*, capital_aud: float, trading_pnl_usd: float, fx_aud_usd: float) -> float:
    """策略净值(澳元)= 澳元本金 + 交易盈亏(美元)按汇率折回。看盘页与净值快照共用的唯一公式。

    本金以澳元记账,只有交易盈亏过汇率;否则本金先折美元再折回,会凭空造出汇率往返假盈亏。
    """
    return capital_aud + trading_pnl_usd / fx_aud_usd


class RequiredLine(NamedTuple):
    """滚动复利要求线:本月应达、本日历年年末应达、已过月数、月回报率(小数)。"""

    month_target_aud: float
    year_target_aud: float
    months_elapsed: int
    rate: float


def required_line(capital_aud: float, *, anchor: Optional[datetime], now: datetime,
                  traded: bool) -> RequiredLine:
    """要求线的唯一算法(看盘页与每日摘要共用)。

    起算月 = 本账本冻结月(anchor,即开始记账的时刻);账本没有起点(anchor=None)或首笔成交前
    (traded=False)一律 0 个月——策略还没出手,就没有相对要求线的盈亏。
    月回报率取 ALPHA_TARGET_MONTHLY_PCT(缺省 1.245,按回测月均推算的要求线,不是收益承诺)。
    """
    rate = float(os.environ.get("ALPHA_TARGET_MONTHLY_PCT", "1.245")) / 100.0
    n = now.astimezone(SYD)
    a = (anchor or now).astimezone(SYD)
    elapsed = max(0, (n.year - a.year) * 12 + (n.month - a.month)) if traded else 0
    to_year_end = max(elapsed, (n.year - a.year) * 12 + (12 - a.month))
    return RequiredLine(capital_aud * (1.0 + rate) ** elapsed,
                        capital_aud * (1.0 + rate) ** to_year_end, elapsed, rate)
