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
    session_factory=None,
    quotes=None,
    reports_dir: str | Path = "reports/paper_3day",
    runtime_dir: str | Path = "runtime",
    fx_aud_usd: Optional[float] = None,
) -> FastAPI:
    app = FastAPI(title="Alpha 控制页", docs_url=None, redoc_url=None, openapi_url=None)
    fx = fx_aud_usd if fx_aud_usd is not None else float(os.environ.get("ALPHA_FX_AUD_USD", "0.65"))

    def _check(supplied: str) -> None:
        expected = token_reader()
        if not expected:
            raise HTTPException(status_code=503, detail="控制页令牌未配置(失败关闭)")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="未授权")

    def require_token(request: Request) -> None:
        supplied = request.headers.get("authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[len("Bearer "):]
        _check(supplied)


    def _overview() -> dict:
        from backend.app.control_page.dashboard_data import build_overview

        return build_overview(
            session_factory=session_factory, heartbeats=heartbeats,
            kill_switch=kill_switch, quotes=quotes, fx_aud_usd=fx,
            reports_dir=reports_dir, runtime_dir=runtime_dir)

    @app.get("/")
    def dashboard():
        """公开只读看盘页(owner 裁定 2026-07-20:取消令牌,打开即看)。

        本页零输入零秘密:只展示模拟盘状态,说人话、用悉尼时间。停机/恢复等动作
        仍是独立的令牌保护端点,与本页无关——公开的只是"看",永远不是"动"。
        2026-07-23 按 owner 要求以公开竞品为基准整体重构(设计依据见 render.py)。"""
        from fastapi.responses import HTMLResponse

        from backend.app.control_page.render import render_dashboard_html

        return HTMLResponse(render_dashboard_html(_overview()))

    @app.get("/api/overview")
    def api_overview() -> dict:
        """公开只读机器可读版(与页面同一份装配数据;零秘密零动作)。"""
        return _overview()

    @app.get("/ops")
    def ops_page():
        """运维记录(公开只读):事故台账 + 修复事件 + 邮件送达状态 + 待处理标记。"""
        from fastapi.responses import HTMLResponse

        from backend.app.control_page.dashboard_data import build_ops_view
        from backend.app.control_page.render import render_ops_html

        return HTMLResponse(render_ops_html(build_ops_view(
            session_factory=session_factory, heartbeats=heartbeats,
            kill_switch=kill_switch)))

    @app.get("/strategy")
    def strategy_page():
        """投资策略(公开只读):生产策略档案 + 硬风控 + 晋级门禁 + 研究史。"""
        from fastapi.responses import HTMLResponse

        from backend.app.control_page.dashboard_data import build_strategy_view
        from backend.app.control_page.render import render_strategy_html

        return HTMLResponse(render_strategy_html(build_strategy_view()))

    @app.get("/strategy/history.csv")
    def strategy_history_csv():
        """全部策略研究史 CSV(公开只读下载):与公开仓 configs/strategies 同一份真源。"""
        from fastapi.responses import PlainTextResponse

        from backend.app.control_page.dashboard_data import RESEARCH_CSV

        try:
            text = Path(RESEARCH_CSV).read_text(encoding="utf-8")
        except Exception:
            raise HTTPException(status_code=404, detail="研究史 CSV 暂不可读")
        return PlainTextResponse(text, media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": 'attachment; filename="alpha_strategy_research_history.csv"',
            # CSV 按扩展名会被 CDN 缓存,导致策略更新后旧表滞留数小时;禁缓存 + 页面侧
            # 用内容哈希做版本号,双保险确保下载永远是最新一份。
            "Cache-Control": "no-store, max-age=0"})

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
