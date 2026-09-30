"""模式 -> 装配件的唯一映射(循环装配 / 行情源 / 资金源 / 空转标签)。

模式 -> 交易环境另在 adapters/brokers/base.MODE_TO_TRD_ENV,两张表各管一件事。
值用字符串懒加载:import 本模块不会带进任何券商 SDK。
DISABLED / HALTED 没有条目 -> resolve 返回 None -> 交易循环失败关闭(BLOCKED_ON_MODE)。
"""

from __future__ import annotations

import importlib
from typing import Callable, Optional

from backend.app.adapters.brokers.base import SystemMode

_BROKER = {
    "cycle": "backend.app.workers.live_cycle:build_broker_cycle",
    "quotes": "backend.app.control_page.dashboard_data:OpenDQuoteSource",
    "funds": "backend.app.control_page.dashboard_data:OpenDRealFunds",
    "blocked": "BLOCKED_ON_OPEND",
}

MODE_WIRING: dict[SystemMode, dict[str, str]] = {
    SystemMode.SHADOW: {
        "cycle": "backend.app.workers.shadow_cycle:build_shadow_cycle",
        "quotes": "backend.app.marketdata.yahoo_live:YahooQuoteSource",
        "blocked": "BLOCKED_ON_FEED",
    },
    SystemMode.PAPER: dict(_BROKER),
    SystemMode.MICRO_LIVE: dict(_BROKER),
}


def resolve(mode: SystemMode, role: str) -> Optional[Callable]:
    """按模式取装配件(懒加载);模式或角色无条目返回 None。"""
    target = MODE_WIRING.get(mode, {}).get(role)
    if target is None or role == "blocked":
        return None
    module, _, attr = target.partition(":")
    return getattr(importlib.import_module(module), attr)


def blocked_status(mode: SystemMode) -> str:
    """装配不上时心跳如实上报的空转标签。"""
    return MODE_WIRING.get(mode, {}).get("blocked", "BLOCKED_ON_MODE")
