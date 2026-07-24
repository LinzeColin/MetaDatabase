"""控制页入口(systemd: alpha-control-page):默认只绑回环,经反代暴露 443。"""

from __future__ import annotations

import os

from backend.app.control_page.app import assert_no_trading_routes, build_control_app
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch


def build_app():
    from backend.app.control_page.dashboard_data import (
        OpenDQuoteSource, OpenDRealFunds, YahooFxSource)

    factory = create_session_factory(init_engine())
    app = build_control_app(
        kill_switch=KillSwitch(os.environ.get("ALPHA_KILL_SWITCH_PATH", "runtime/KILL_SWITCH")),
        heartbeats=HeartbeatStore(factory),
        session_factory=factory,
        quotes=OpenDQuoteSource(
            host=os.environ.get("ALPHA_OPEND_HOST", "127.0.0.1"),
            port=int(os.environ.get("ALPHA_OPEND_PORT", "11111")),
        ),
        # 资金真相:读券商真实购买力,页面不再拿授权额度冒充现金(owner 2026-07-24 抓到)
        real_funds=OpenDRealFunds(),
        # 实时汇率:每 30 秒刷新一次,页面显示汇率与取得时间(owner 2026-07-24 要求)
        fx_source=YahooFxSource(ttl=30.0),
    )
    assert_no_trading_routes(app)  # 启动自检:出现交易端点直接拒绝启动
    return app


def main() -> None:  # pragma: no cover - 长驻进程入口
    import uvicorn

    bind = os.environ.get("ALPHA_CONTROL_BIND", "127.0.0.1:8443")
    host, _, port = bind.partition(":")
    uvicorn.run(build_app(), host=host, port=int(port or "8443"))


if __name__ == "__main__":  # pragma: no cover
    main()
