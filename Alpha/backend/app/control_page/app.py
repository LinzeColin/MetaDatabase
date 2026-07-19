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
    def dashboard():
        """公开只读看盘页(owner 裁定 2026-07-20:取消令牌,打开即看)。

        本页零输入零秘密:只展示模拟盘状态,说人话、用悉尼时间。停机/恢复等动作
        仍是独立的令牌保护端点,与本页无关——公开的只是"看",永远不是"动"。"""
        from zoneinfo import ZoneInfo

        from fastapi.responses import HTMLResponse

        SYD = ZoneInfo("Australia/Sydney")
        ET = ZoneInfo("America/New_York")
        now = datetime.now(timezone.utc)
        now_syd = now.astimezone(SYD)

        state_cn = {
            "INTENT_CREATED": "已创建", "RISK_APPROVED": "风控通过", "RISK_REJECTED": "被风控拦下",
            "SUBMITTING": "提交中", "SUBMITTED": "已提交", "SUBMIT_FAILED": "提交失败",
            "ACCEPTED": "券商已挂单", "PARTIALLY_FILLED": "部分成交", "FILLED": "已成交",
            "CANCELLED": "已撤单", "EXPIRED": "已过期",
            "UNKNOWN_RECONCILIATION_REQUIRED": "待人工核对",
        }
        side_cn = {"BUY": "买入", "SELL": "卖出"}

        # 系统健康(人话):全部组件近 2 分钟内报过平安 = 正常
        hb = heartbeats.snapshot() if heartbeats else {}
        ages = {}
        for name, h in hb.items():
            beat = datetime.fromisoformat(h["beat_at"])
            ages[name] = (int((now - beat).total_seconds()), h["status"], h["detail"])
        trading = ages.get("trading-worker", (99999, "无", ""))
        all_fresh = ages and all(a[0] < 150 for a in ages.values())
        halted = kill_switch.active() or trading[1] == "HALTED"
        if halted:
            banner, banner_bg = "⏸️ 系统已暂停(紧急刹车拉下,不会再下任何单)", "#5a3a00"
        elif all_fresh and trading[1] == "RUNNING":
            banner, banner_bg = "✅ 系统正常运行中", "#0f3d20"
        else:
            banner, banner_bg = "⚠️ 系统部分组件没报平安,我会自动处理;持续异常会邮件通知你", "#5a1e1e"

        # 下一次决策时间(策略固定周二美股开盘后 30-90 分钟)-> 换算成悉尼时间说给人听
        et_now = now.astimezone(ET)
        days_ahead = (1 - et_now.weekday()) % 7
        candidate = et_now.replace(hour=10, minute=0, second=0, microsecond=0)
        from datetime import timedelta as _td
        candidate = candidate + _td(days=days_ahead)
        if days_ahead == 0 and et_now.hour >= 11:
            candidate = candidate + _td(days=7)
        next_eval_syd = candidate.astimezone(SYD)
        next_line = f"{next_eval_syd:%m月%d日 %H:%M} 前后(悉尼时间)"

        pos_rows, order_rows, fill_rows = "", "", ""
        spent_usd = 0.0
        if session_factory is not None:
            from sqlalchemy import select

            from backend.app.domain.models import BrokerOrder, Execution, OrderIntent
            with session_factory() as s:
                intents = {i.intent_id: i for i in s.scalars(select(OrderIntent)).all()}
                orders = sorted(s.scalars(select(BrokerOrder)).all(),
                                key=lambda o: o.created_at, reverse=True)
                order_by_id = {o.order_id: o for o in orders}
                execs = sorted(s.scalars(select(Execution)).all(),
                               key=lambda e: e.executed_at, reverse=True)

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
                for sym, q in sorted(net.items()):
                    if q == 0:
                        continue
                    avg = abs(cost[sym] / q)
                    spent_usd += cost[sym]
                    pos_rows += (f"<tr><td><b>{sym}</b></td><td>{q} 股</td>"
                                 f"<td>{avg:.2f} 美元</td><td>{cost[sym]:.2f} 美元</td></tr>")

                for o in orders[:15]:
                    i = intents.get(o.intent_id)
                    if i is None:
                        continue
                    t = i.created_at
                    t = (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(SYD)
                    filled = f",已成 {o.filled_quantity} 股" if o.filled_quantity else ""
                    order_rows += (f"<tr><td>{t:%m-%d %H:%M}</td>"
                                   f"<td>{side_cn.get(i.side, i.side)} <b>{i.symbol}</b> {i.quantity} 股</td>"
                                   f"<td>{state_cn.get(o.state, o.state)}{filled}</td></tr>")
                for e in execs[:15]:
                    o = order_by_id.get(e.order_id)
                    i = intents.get(o.intent_id) if o else None
                    if i is None:
                        continue
                    t = e.executed_at
                    t = (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(SYD)
                    fill_rows += (f"<tr><td>{t:%m-%d %H:%M}</td>"
                                  f"<td>{side_cn.get(i.side, i.side)} <b>{i.symbol}</b> {e.quantity} 股</td>"
                                  f"<td>{float(e.price):.2f} 美元</td></tr>")

        tech = "".join(
            f"<div>{n}:{st}({a}秒前)<span style='color:#666'> {d[:90]}</span></div>"
            for n, (a, st, d) in sorted(ages.items()))
        html = f"""<meta name=viewport content="width=device-width,initial-scale=1">
<meta name=robots content="noindex,nofollow"><meta http-equiv=refresh content="60">
<title>Alpha 模拟盘</title><style>
body{{font-family:-apple-system,'PingFang SC',sans-serif;margin:0;background:#0e1117;color:#e9edf2}}
.wrap{{max-width:560px;margin:0 auto;padding:16px}}
.banner{{padding:14px 16px;border-radius:12px;font-size:16px;font-weight:600;background:{banner_bg}}}
.card{{background:#171c26;border-radius:12px;padding:13px 15px;margin-top:12px}}
.card h2{{font-size:14px;color:#8b949e;margin:0 0 8px;font-weight:500}}
.big{{font-size:22px;font-weight:700}}
table{{border-collapse:collapse;width:100%;font-size:14px}}
td{{border-bottom:1px solid #242b38;padding:7px 4px;text-align:left}}
tr:last-child td{{border-bottom:0}}
.muted{{color:#8b949e;font-size:12px;line-height:1.6}}
details{{margin-top:14px}}summary{{color:#4a5568;font-size:11px}}
</style><div class=wrap>
<h1 style="font-size:19px;margin:6px 0 12px">🤖 Alpha 模拟盘</h1>
<div class=banner>{banner}</div>
<div class=card><h2>现在持有</h2>
{f'<table>{pos_rows}</table>' if pos_rows else '<div class=big>空仓</div><div class=muted>钱都在手里,还没出手——按纪律,下一个决策时间才会买。</div>'}
{f'<div class=muted>已投入约 {spent_usd:.0f} 美元(上限约 1950 美元 = 3000 澳元)</div>' if pos_rows else ''}</div>
<div class=card><h2>下一次决策</h2><div class=big>{next_line}</div>
<div class=muted>策略每周固定这一个时间做决定(美股周二开盘后一小时内),其余时间只盯不动。到点后有动作会出现在下面,并邮件通知你。</div></div>
<div class=card><h2>动作记录</h2>
{f'<table>{order_rows}</table>' if order_rows else '<div class=muted>还没有任何动作。第一次买入后,这里会像流水账一样一条条记。</div>'}</div>
{f'<div class=card><h2>成交流水</h2><table>{fill_rows}</table></div>' if fill_rows else ''}
<div class=muted style="margin-top:14px">· 这是<b>模拟盘</b>:用券商的模拟账户和真实行情演练,不动真钱。<br>
· 你的真实账户 Alpha 碰不到;要动真钱必须先过三天模拟考核 + 你亲笔授权。<br>
· 页面每分钟自动刷新;悉尼时间 {now_syd:%m月%d日 %H:%M}。</div>
<details><summary>技术细节(给维护者看的)</summary><div class=muted>{tech or '无'}</div></details>
</div>"""
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
