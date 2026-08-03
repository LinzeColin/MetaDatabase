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

#: 契约资金常量(与 configs/trading_governor_policy.yaml 一致;env 可覆盖用于测试)
DEFAULT_CAPITAL_AUD = 3000.0
#: 契约保守汇率:资金上限只紧不松,**不随行情浮动**(实时汇率只用于净值显示)
DEFAULT_CONTRACT_FX = 0.65
POLICY_PATH = "configs/trading_governor_policy.yaml"


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
