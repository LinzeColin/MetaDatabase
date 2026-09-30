"""影子盘(SHADOW)装配:Yahoo 实时行情 + 本机模拟券商 + 原网关/原风控/原账本。

不连券商、不登录;复用 run_live_cycle / FeeModel / truth,整条链不 import 任何券商 SDK。
环境里出现券商账户、登录凭据、测试覆盖键、实盘开关或实盘授权文件 -> 拒绝启动(失败关闭)。
"""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Callable, Mapping, Optional

from backend.app import truth
from backend.app.adapters.brokers.base import SystemMode
from backend.app.adapters.brokers.sim_broker import SimBroker
from backend.app.backtest.fees import FeeModel
from backend.app.execution.gateway import ExecutionGateway
from backend.app.execution.lease import LeaseManager
from backend.app.marketdata.yahoo_live import YahooQuoteSource
from backend.app.store.ledger_stamp import claim_ledger
from backend.app.store.orders import OrderStore
from backend.app.workers.live_cycle import _freeze_start_capital, make_deps, run_live_cycle

#: 影子盘环境里不得出现的键(非空即拒)。末两个是测试专用覆盖键:生产出现就等于绕过 truth。
FORBIDDEN_ENV = (
    "ALPHA_EXPECTED_ACC_ID", "ALPHA_REAL_ACC_ID",
    "MOOMOO_LOGIN_ACCOUNT", "MOOMOO_LOGIN_PASSWORD", "MOOMOO_UNLOCK_PASSWORD",
    "OPEND_HOST", "OPEND_PORT", "OPEND_RSA_KEY_PATH",
    "ALPHA_CAPITAL_AUD", "ALPHA_FX_AUD_USD",
)


def check_shadow_env(environ: Mapping[str, str] = os.environ) -> list[str]:
    """影子盘环境体检;返回问题清单(空 = 可以启动)。install.sh 与体检也调用它。"""
    problems = []
    if truth.mode(environ) is not SystemMode.SHADOW:
        problems.append(f"ALPHA_MODE 必须为 SHADOW,实为 {environ.get('ALPHA_MODE', '')!r}")
    problems += [f"{k} 不应出现在影子盘环境" for k in FORBIDDEN_ENV if environ.get(k)]
    if environ.get("LIVE_TRADING_ENABLED", "") not in ("", "0"):
        problems.append("LIVE_TRADING_ENABLED 必须为 0")
    if (truth.runtime_dir() / "LIVE_AUTHORIZATION.json").exists():
        problems.append("运行目录里存在实盘授权文件 LIVE_AUTHORIZATION.json")
    return problems


def build_shadow_cycle(*, factory, kill_switch, quotes=None,
                       now_fn: Optional[Callable[[], datetime]] = None) -> Callable[[], dict]:
    problems = check_shadow_env()
    if problems:
        raise RuntimeError(f"影子盘拒绝启动(失败关闭): {problems}")
    now_fn = now_fn or (lambda: datetime.now(timezone.utc))
    # 账本与运行目录必须属于影子盘(或全新):券商模式的账不能被影子盘沿用,反之亦然
    claim_ledger(factory, SystemMode.SHADOW, truth.runtime_dir())

    # 本金 = 契约本金 × 契约汇率,首次装配即冻结并读回;读不回就不启动(不能带着猜的本金记账)
    fx_aud_usd = truth.contract_fx_aud_usd()
    _freeze_start_capital(truth.capital_aud() * fx_aud_usd)
    frozen = truth.runtime_dir() / "LIVE_START_CAPITAL.json"
    try:
        start_usd = float(json.loads(frozen.read_text())["start_capital_usd"])
    except Exception as exc:
        raise RuntimeError(f"期初本金冻结文件损坏或读不回(人工检查后删除再重启) {frozen}: {exc}") from exc

    quotes = quotes or YahooQuoteSource()
    fee_model = FeeModel.from_yaml()
    store = OrderStore(factory)
    lease = LeaseManager(factory, holder_id=f"trading-worker@{socket.gethostname()}",
                         now_fn=now_fn)
    sim = SimBroker(factory, quotes=quotes, fee_model=fee_model,
                    start_capital_usd=start_usd, now_fn=now_fn)
    gateway = ExecutionGateway(store=store, client=sim, lease=lease, mode=SystemMode.SHADOW,
                               kill_switch_check=kill_switch.active, now_fn=now_fn)
    gateway.recover_in_flight()
    lease.acquire()

    deps = make_deps(
        factory=factory, read_client=quotes, trade_client=sim, store=store, gateway=gateway,
        lease=lease, kill_switch=kill_switch, mode=SystemMode.SHADOW, capital_usd=start_usd,
        fee_model=fee_model, now_fn=now_fn, funds_fn=sim.get_funds)
    return lambda: run_live_cycle(deps)
