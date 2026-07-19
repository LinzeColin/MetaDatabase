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
) -> FastAPI:
    app = FastAPI(title="Alpha 控制页", docs_url=None, redoc_url=None, openapi_url=None)

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


    @app.get("/")
    def dashboard(request: Request):
        """只读仪表盘(HTML)。无令牌/错令牌 -> 401 + 令牌输入页(零数据泄漏);
        令牌正确 -> 数据页。停机/恢复仍是独立 POST+Bearer,本页永远只读。"""
        from fastapi.responses import HTMLResponse

        supplied = request.headers.get("authorization", "")
        if supplied.startswith("Bearer "):
            supplied = supplied[len("Bearer "):]
        if not supplied:
            supplied = request.query_params.get("token", "")
        expected = token_reader()
        if not expected:
            raise HTTPException(status_code=503, detail="控制页令牌未配置(失败关闭)")
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            hint = "<p style='color:#f85149'>令牌不对,再试一次。</p>" if supplied else ""
            login = f"""<meta name=viewport content="width=device-width,initial-scale=1">
<title>Alpha 登录</title><style>body{{font-family:-apple-system,sans-serif;background:#0e1117;
color:#e6e6e6;display:flex;align-items:center;justify-content:center;height:90vh;margin:0}}
input{{font-size:16px;padding:10px;border-radius:8px;border:1px solid #2a2f3a;background:#1c2333;
color:#e6e6e6;width:260px}}button{{font-size:16px;padding:10px 18px;border-radius:8px;border:0;
background:#2f6feb;color:#fff;margin-left:6px}}</style>
<div style="text-align:center"><h1 style="font-size:22px">🤖 Alpha 模拟盘</h1>{hint}
<form method=get action=/><input name=token placeholder="粘贴你的控制令牌" autofocus>
<button>进入</button></form>
<p style="color:#8b949e;font-size:12px">令牌在服务器 /opt/alpha/env 里;进入后可把带令牌的完整网址存成书签</p></div>"""
            return HTMLResponse(login, status_code=401)

        hb = heartbeats.snapshot() if heartbeats else {}
        now = datetime.now(timezone.utc)
        rows_hb = ""
        for name, h in sorted(hb.items()):
            age = int((now - datetime.fromisoformat(h["beat_at"])).total_seconds())
            ok = "🟢" if age < 120 and h["status"] in ("RUNNING",) else ("🟡" if h["status"] == "HALTED" else "🔴")
            rows_hb += (f"<tr><td>{ok} {name}</td><td>{h['status']}</td>"
                        f"<td>{age}s前</td><td class=d>{h['detail'][:110]}</td></tr>")

        orders_html, fills_html, pos_html = "", "", ""
        if session_factory is not None:
            from sqlalchemy import select

            from backend.app.domain.models import BrokerOrder, Execution, OrderIntent
            with session_factory() as s:
                intents = {i.intent_id: i for i in s.scalars(select(OrderIntent)).all()}
                orders = s.scalars(select(BrokerOrder)).all()
                orders.sort(key=lambda o: o.created_at, reverse=True)
                for o in orders[:20]:
                    i = intents.get(o.intent_id)
                    if i is None:
                        continue
                    orders_html += (f"<tr><td>{i.created_at:%m-%d %H:%M}</td><td>{i.symbol}</td>"
                                    f"<td>{i.side}</td><td>{i.quantity}</td>"
                                    f"<td>{i.limit_price or '-'}</td><td>{o.state}</td>"
                                    f"<td>{o.filled_quantity}@{o.avg_fill_price or '-'}</td></tr>")
                execs = s.scalars(select(Execution)).all()
                execs.sort(key=lambda e: e.executed_at, reverse=True)
                order_by_id = {o.order_id: o for o in orders}
                net: dict[str, int] = {}
                cost: dict[str, float] = {}
                for e in execs:
                    o = order_by_id.get(e.order_id)
                    i = intents.get(o.intent_id) if o else None
                    if i is None:
                        continue
                    sign = 1 if i.side == "BUY" else -1
                    net[i.symbol] = net.get(i.symbol, 0) + sign * e.quantity
                    cost[i.symbol] = cost.get(i.symbol, 0.0) + sign * e.quantity * float(e.price)
                for e in execs[:20]:
                    o = order_by_id.get(e.order_id)
                    i = intents.get(o.intent_id) if o else None
                    sym = i.symbol if i else "?"
                    side = i.side if i else "?"
                    fills_html += (f"<tr><td>{e.executed_at:%m-%d %H:%M}</td><td>{sym}</td>"
                                   f"<td>{side}</td><td>{e.quantity}</td><td>{e.price}</td>"
                                   f"<td>{e.fees}</td></tr>")
                for sym, q in sorted(net.items()):
                    if q == 0:
                        continue
                    avg = abs(cost[sym] / q) if q else 0
                    pos_html += f"<tr><td>{sym}</td><td>{q}</td><td>{avg:.2f}</td></tr>"

        ks = kill_switch.active()
        html = f"""<meta name=viewport content="width=device-width,initial-scale=1">
<title>Alpha 模拟盘</title><style>
body{{font-family:-apple-system,sans-serif;margin:14px;background:#0e1117;color:#e6e6e6}}
h2{{font-size:17px;margin:18px 0 6px}}table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border-bottom:1px solid #2a2f3a;padding:5px 7px;text-align:left}}th{{color:#8b949e}}
.d{{color:#8b949e;font-size:11px}}.b{{padding:9px 12px;border-radius:9px;display:inline-block;margin:3px 6px 3px 0;background:#1c2333}}
</style>
<h1 style="font-size:20px">🤖 Alpha 模拟盘(PAPER)</h1>
<div class=b>杀开关:{"🔴 已触发" if ks else "🟢 未触发"}</div>
<div class=b>模式:SIMULATE 模拟账户,实盘开关关</div>
<div class=b>刷新时间:{now:%m-%d %H:%M:%S} UTC</div>
<h2>进程心跳</h2><table><tr><th>进程</th><th>状态</th><th>心跳</th><th>详情</th></tr>{rows_hb or '<tr><td colspan=4>无</td></tr>'}</table>
<h2>净持仓(由成交推导)</h2><table><tr><th>代码</th><th>数量</th><th>均价USD</th></tr>{pos_html or '<tr><td colspan=3>空仓(首单待周二评估窗口)</td></tr>'}</table>
<h2>订单(最近20)</h2><table><tr><th>时间UTC</th><th>代码</th><th>方向</th><th>数量</th><th>限价</th><th>状态</th><th>成交</th></tr>{orders_html or '<tr><td colspan=7>暂无订单</td></tr>'}</table>
<h2>成交(最近20)</h2><table><tr><th>时间UTC</th><th>代码</th><th>方向</th><th>数量</th><th>价格</th><th>费用</th></tr>{fills_html or '<tr><td colspan=6>暂无成交</td></tr>'}</table>
<p class=d>本页只读。停机/恢复为独立受令牌保护的动作端点,页面无按钮。真实账户零接触。</p>"""
        return HTMLResponse(html)

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
