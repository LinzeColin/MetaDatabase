"""控制页入口(systemd: alpha-control-page):默认只绑回环,经反代暴露 443。"""

from __future__ import annotations

import os

from backend.app.control_page.app import assert_no_trading_routes, build_control_app
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch


def build_app():
    factory = create_session_factory(init_engine())
    app = build_control_app(
        kill_switch=KillSwitch(os.environ.get("ALPHA_KILL_SWITCH_PATH", "runtime/KILL_SWITCH")),
        heartbeats=HeartbeatStore(factory),
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
