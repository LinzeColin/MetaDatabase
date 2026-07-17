"""控制页应用(configs/notify.yaml inbound 契约)。

红线:本应用能做的只有 查询/停机/恢复/授权确认 四件事——代码里根本不存在
任何下单、改单、撤单端点;它与执行网关之间没有任何提交通道。
鉴权:私有令牌(环境变量 ALPHA_CONTROL_TOKEN),常量时间比较,未带或错误一律 401。
"""

from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import Depends, FastAPI, HTTPException, Request

from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch


def build_control_app(
    *,
    kill_switch: KillSwitch,
    heartbeats: Optional[HeartbeatStore] = None,
    token_reader: Callable[[], Optional[str]] = lambda: os.environ.get("ALPHA_CONTROL_TOKEN"),
    ack_path: str | Path = "runtime/OWNER_AUTHORIZATION_ACK.json",
) -> FastAPI:
    app = FastAPI(title="Alpha 控制页", docs_url=None, redoc_url=None, openapi_url=None)

    def require_token(request: Request) -> None:
        expected = token_reader()
        if not expected:
            raise HTTPException(status_code=503, detail="控制页令牌未配置(失败关闭)")
        supplied = request.headers.get("authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[len("Bearer "):]
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="未授权")

    @app.get("/status")
    def status(_: None = Depends(require_token)) -> dict:
        return {
            "kill_switch": {"active": kill_switch.active(), "detail": kill_switch.detail()},
            "heartbeats": heartbeats.snapshot() if heartbeats else {},
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "note": "本页面只能查询/停机/恢复/授权确认,永远不能下单",
        }

    @app.post("/halt")
    def halt(_: None = Depends(require_token)) -> dict:
        kill_switch.engage(reason="owner 控制页一键停机", source="control_page")
        return {"kill_switch_active": True}

    @app.post("/resume")
    def resume(_: None = Depends(require_token)) -> dict:
        kill_switch.clear()
        return {"kill_switch_active": False}

    @app.post("/authorization/ack")
    def authorization_ack(request_body: dict, _: None = Depends(require_token)) -> dict:
        """部署日 owner 对预签授权内容的确认回执(只记录确认,不生成授权本身)。"""
        phrase = str(request_body.get("confirm_phrase", "")).strip()
        if not phrase:
            raise HTTPException(status_code=400, detail="缺 confirm_phrase")
        path = Path(ack_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "confirm_phrase": phrase,
            "acked_at": datetime.now(timezone.utc).isoformat(),
            "source": "control_page",
        }
        path.write_text(json.dumps(record, ensure_ascii=False))
        return {"recorded": True}

    return app


FORBIDDEN_CAPABILITIES = ("place", "order", "submit", "trade", "buy", "sell", "cancel", "modify")


def assert_no_trading_routes(app: FastAPI) -> None:
    """自检:路由表不得含任何交易语义端点(测试与启动时都跑)。"""
    for route in app.routes:
        path = getattr(route, "path", "").lower()
        for word in FORBIDDEN_CAPABILITIES:
            if word in path:
                raise AssertionError(f"控制页出现交易语义端点: {path}")
