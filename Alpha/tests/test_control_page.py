"""ALPHA-LIVE-040:控制页——鉴权、停机/恢复、授权确认、『永不下单』边界。"""

import json

from fastapi.testclient import TestClient

from backend.app.control_page.app import assert_no_trading_routes, build_control_app
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch

TOKEN = "test-token-0123456789"


def make_client(tmp_path):
    ks = KillSwitch(tmp_path / "KILL_SWITCH")
    hb = HeartbeatStore(create_session_factory(init_engine(f"sqlite:///{tmp_path / 'cp.sqlite'}")))
    app = build_control_app(kill_switch=ks, heartbeats=hb,
                            token_reader=lambda: TOKEN,
                            ack_path=tmp_path / "ACK.json")
    return TestClient(app), ks


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_auth_required_everywhere(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/status").status_code == 401
    assert client.post("/halt").status_code == 401
    assert client.post("/resume").status_code == 401
    assert client.post("/halt", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_missing_token_config_fails_closed(tmp_path):
    ks = KillSwitch(tmp_path / "KS2")
    app = build_control_app(kill_switch=ks, token_reader=lambda: None)
    client = TestClient(app)
    assert client.get("/status", headers=auth()).status_code == 503


def test_halt_and_resume_cycle(tmp_path):
    client, ks = make_client(tmp_path)
    assert client.post("/halt", headers=auth()).json()["kill_switch_active"] is True
    assert ks.active()
    status = client.get("/status", headers=auth()).json()
    assert status["kill_switch"]["active"] is True
    assert client.post("/resume", headers=auth()).json()["kill_switch_active"] is False
    assert not ks.active()


def test_authorization_ack_recorded(tmp_path):
    client, _ = make_client(tmp_path)
    resp = client.post("/authorization/ack", headers=auth(),
                       json={"confirm_phrase": "我确认 3000 AUD 授权内容"})
    assert resp.json()["recorded"] is True
    record = json.loads((tmp_path / "ACK.json").read_text())
    assert record["confirm_phrase"].startswith("我确认")
    assert client.post("/authorization/ack", headers=auth(), json={}).status_code == 400


def test_never_able_to_trade(tmp_path):
    """红线:控制页不存在任何交易语义端点;自检函数在测试与启动都跑。"""
    client, _ = make_client(tmp_path)
    assert_no_trading_routes(client.app)
    for path in ("/order", "/orders", "/place", "/trade", "/buy", "/sell", "/submit", "/cancel"):
        assert client.post(path, headers=auth()).status_code in (404, 405)


def seed_trading_db(tmp_path):
    """种子:2 笔成交(QQQ 2股/GLD 1股)+ 1 笔风控拦截,复刻真实三日盘面形状。"""
    from decimal import Decimal

    from backend.app.domain.state_machine import OrderState
    from backend.app.store.orders import OrderStore

    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'dash2.sqlite'}"))
    store = OrderStore(factory)
    for key, sym, qty, px in [("S1-T-QQQ-BUY-2", "QQQ", 2, "707.74"),
                              ("S1-T-GLD-BUY-1", "GLD", 1, "381.25")]:
        oid = store.create_intent(idempotency_key=key, symbol=sym, side="BUY",
                                  quantity=qty, currency="USD",
                                  strategy_source="S1_GOLD_BLEND", order_type="LIMIT",
                                  limit_price=Decimal(px))
        store.record_risk_decision(oid, allowed=True, triggered_rules=[], exposure_snapshot={})
        store.apply_transition(oid, OrderState.SUBMITTING, event_type="GATEWAY_SUBMIT")
        store.apply_transition(oid, OrderState.SUBMITTED, event_type="BROKER_SYNC_ACK",
                               broker_order_id=f"SIM-{sym}")
        store.apply_fill_event(oid, quantity=qty, price=Decimal(px),
                               broker_execution_id=f"SIMFILL-{key}")
    rej = store.create_intent(idempotency_key="S1-T-GLD-BUY-REJ", symbol="GLD", side="BUY",
                              quantity=1, currency="USD", strategy_source="S1_GOLD_BLEND",
                              order_type="LIMIT", limit_price=Decimal("372.30"))
    store.record_risk_decision(rej, allowed=False,
                               triggered_rules=["RULE_MARKET_DATA_STALE"], exposure_snapshot={})
    return factory


class FakeQuotes:
    """测试行情源:固定现价与日线收盘,只读断言用。"""

    def __init__(self, prices, closes=None):
        self.prices, self.closes = prices, closes or {}

    def snapshots(self, symbols):
        return {s: {"price": self.prices[s], "at": "2026-07-22 16:00:00"}
                for s in symbols if s in self.prices}

    def daily_closes(self, symbol, start, end):
        return self.closes.get(symbol, [])


def make_v2_client(tmp_path, factory, quotes):
    import json as _json

    rep = tmp_path / "reports" / "2026-07-22"
    rep.mkdir(parents=True)
    (rep / "report.json").write_text(_json.dumps({
        "promotion": {"days_qualified": 3, "days_required": 3, "auto_promote": False,
                      "decision": "未全绿:保持 Paper,进入调参循环并邮件报告差距",
                      "PROMO-2": {"passed": True, "reason": "行为样本齐备"},
                      "PROMO-3": {"passed": False, "pace_month_pct": -2.48, "target_pct": 0.36},
                      "PROMO-4": {"passed": True, "uptime_pct": 99.91,
                                  "notify_p95_seconds": 4.98}}}, ensure_ascii=False))
    hb = HeartbeatStore(factory)
    hb.beat("trading-worker", status="RUNNING", detail="{'mode': 'PAPER'}")
    hb.beat("notify-worker", status="RUNNING", detail="")
    app = build_control_app(kill_switch=KillSwitch(tmp_path / "KSV2"), heartbeats=hb,
                            token_reader=lambda: TOKEN, ack_path=tmp_path / "ACKV2.json",
                            session_factory=factory, quotes=quotes,
                            reports_dir=tmp_path / "reports",
                            runtime_dir=tmp_path / "runtime", fx_aud_usd=0.65)
    return TestClient(app)


def test_dashboard_v2_full_page_and_api(tmp_path):
    """重构版:英雄净值/持仓盈亏/考核四灯/风控人话/机器可读接口,全部只读可公开。"""
    factory = seed_trading_db(tmp_path)
    client = make_v2_client(tmp_path, factory,
                            FakeQuotes({"QQQ": 710.00, "GLD": 380.00}))

    page = client.get("/")
    assert page.status_code == 200
    body = page.text
    # 英雄区与持仓(现价 710/380 → 市值 1800 美元,净值 3005.03 澳元)
    assert "管理资金净值" in body and "3,005.03" in body
    assert "纳指100" in body and "黄金" in body and "710.00" in body
    # 考核四灯 + 结论人话
    assert "三日模拟盘考核" in body and "收益速度" in body and "未达标" in body
    assert "保持 Paper" in body
    # 风控拦截说人话
    assert "行情数据太旧,拒单保护" in body
    # 只读边界不变:无表单;黑话不出现在正文(折叠技术细节除外)
    assert "<form" not in body
    assert "RUNNING" not in body.split("技术细节")[0]

    api = client.get("/api/overview")
    assert api.status_code == 200
    data = api.json()
    assert data["hero"]["equity_aud"] == 3005.03
    assert data["hero"]["cash_usd"] == 153.27
    assert {p["symbol"]: p["qty"] for p in data["positions"]} == {"QQQ": 2, "GLD": 1}
    qqq = next(p for p in data["positions"] if p["symbol"] == "QQQ")
    assert abs(qqq["upl_usd"] - 4.52) < 0.01 and qqq["priced"] is True
    assert data["exam"]["lights"][2]["ok"] is False      # 收益速度红灯
    assert data["curve"][-1]["equity_aud"] == 3005.03
    # 机器接口同样公开只读:不含任何令牌/秘密字段
    assert "token" not in api.text.lower() and "Bearer" not in api.text


def test_ops_and_strategy_pages(tmp_path):
    """一级入口:运维记录(台账/事件/邮件状态/待处理)与投资策略(档案/风控/门禁/研究史)。"""
    import json as _json
    from datetime import datetime, timedelta, timezone

    from backend.app.domain.models import OutboxEvent

    factory = seed_trading_db(tmp_path)
    # 台账 + 一条已送达的失联告警 + 一条其后的恢复(应判定"已自愈")
    ledger = tmp_path / "downtime_ledger.json"
    ledger.write_text(_json.dumps({
        "2026-07-23": {"seconds": 23400, "原因": "网关闪断后卡死,全时段停机(事故)"}},
        ensure_ascii=False))
    t0 = datetime.now(timezone.utc) - timedelta(hours=2)
    with factory() as s, s.begin():
        s.add(OutboxEvent(event_type="WORKER_HEARTBEAT_LOST", payload="{}",
                          delivery_status="DELIVERED", created_at=t0,
                          delivered_at=t0 + timedelta(seconds=3)))
        s.add(OutboxEvent(event_type="WORKER_RECOVERED", payload="{}",
                          delivery_status="DELIVERED", created_at=t0 + timedelta(hours=1),
                          delivered_at=t0 + timedelta(hours=1, seconds=3)))

    hb = HeartbeatStore(factory)
    hb.beat("trading-worker", status="RUNNING", detail="")
    app = build_control_app(kill_switch=KillSwitch(tmp_path / "KSOPS"), heartbeats=hb,
                            token_reader=lambda: TOKEN, ack_path=tmp_path / "AOPS.json",
                            session_factory=factory, quotes=FakeQuotes({}),
                            reports_dir=tmp_path / "norep", runtime_dir=tmp_path / "rt",
                            fx_aud_usd=0.65)
    client = TestClient(app)

    from backend.app.control_page.dashboard_data import build_ops_view
    ops = build_ops_view(session_factory=factory, heartbeats=hb,
                         kill_switch=KillSwitch(tmp_path / "KSOPS"),
                         ledger_path=ledger)
    assert ops["ledger"][0]["date"] == "2026-07-23" and "6 小时" in ops["ledger"][0]["downtime_human"]
    lost = next(e for e in ops["events"] if "失联" in e["title"])
    assert "已邮件" in lost["mail"] and lost["resolved"] is True   # 之后有恢复记录 → 已自愈
    assert ops["open_faults"] == 0

    page = client.get("/ops")
    assert page.status_code == 200
    assert "运维记录" in page.text and "停机事故台账" in page.text and "<form" not in page.text

    sp = client.get("/strategy")
    assert sp.status_code == 200
    body = sp.text
    assert "黄金对冲动量" in body and "3000 澳元" in body
    assert "晋级实盘的四道门" in body and "候选策略研究史" in body
    assert "不向任何人承诺回报" in body and "<form" not in body
    # 导航三入口出现在驾驶舱
    assert "运维记录" in client.get("/").text


def test_dashboard_v2_quote_outage_fails_soft(tmp_path):
    """行情源整体失效:页面照常打开,持仓按成本估值并如实标注,绝不编价。"""
    factory = seed_trading_db(tmp_path)
    client = make_v2_client(tmp_path, factory, FakeQuotes({}))
    page = client.get("/")
    assert page.status_code == 200
    assert "行情暂不可用,按成本估值" in page.text
    data = client.get("/api/overview").json()
    assert all(p["priced"] is False for p in data["positions"])
    # 成本口径:市值=成本 → 浮动盈亏 0,净值=本金-零头(无编造)
    assert all(p["upl_usd"] == 0.0 for p in data["positions"])


def test_dashboard_readonly_html(tmp_path):
    """仪表盘:无令牌 401;?token= 可看;含关键区块;绝无动作按钮。"""
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'dash.sqlite'}"))
    hb = HeartbeatStore(factory)
    hb.beat("trading-worker", status="RUNNING", detail="{'mode': 'PAPER'}")
    ks = KillSwitch(tmp_path / "KS2")
    app = build_control_app(kill_switch=ks, heartbeats=hb,
                            token_reader=lambda: TOKEN,
                            ack_path=tmp_path / "ACK2.json",
                            session_factory=factory)
    client = TestClient(app)
    page = client.get("/")             # owner 裁定:看盘公开,零令牌零输入
    assert page.status_code == 200
    body = page.text
    assert "系统正常运行中" in body     # 人话状态横幅
    assert "空仓" in body and "下一次决策" in body
    assert "悉尼" in body              # 时间必须说人话(悉尼时间)
    assert "<form" not in body         # 纯只读:无任何表单/按钮
    assert "RUNNING" not in body.split("技术细节")[0]  # 黑话只许出现在折叠的技术细节里
    # 动作端点仍然锁死:无令牌 401
    assert client.post("/halt").status_code == 401
    assert client.post("/resume").status_code == 401


def test_strategy_csv_registry_single_source(tmp_path):
    """研究史 CSV 唯一真源:恰一条现役、列齐全;/strategy 与下载路由同源一致(白色主题)。"""
    import csv as _csv

    from backend.app.control_page.dashboard_data import (RESEARCH_CSV, RESEARCH_COLS,
                                                         build_strategy_view)

    # 1) CSV 存在且可解析,恰有一条现役,列齐全
    with open(RESEARCH_CSV, encoding="utf-8") as f:
        rows = list(_csv.DictReader(f))
    assert len(rows) >= 10, "策略登记应涵盖全部研究史"
    live = [r for r in rows if r.get("现役") == "是"]
    assert len(live) == 1, "有且仅有一条现役实盘策略"
    for col in RESEARCH_COLS:
        assert col in rows[0], f"缺列 {col}"

    # 2) 装配层读到同一份,冠军名 == 现役策略
    view = build_strategy_view()
    assert view["champion"]["name_cn"] == live[0]["策略"]
    assert view["research"][0]["现役"] == "是"          # 现役置顶
    # 诚实:固定规则连续复盘真数字 + 保留WFO动态流程口径出处,明示不混用
    rec = view["champion"]["record"]
    assert "连续复盘" in rec and "1.108" in rec and ("不混用" in rec or "口径不同" in rec)

    # 3) 页面:白色主题 + 现役醒目 + 宽表 + CSV 下载入口
    ks = KillSwitch(tmp_path / "KS_STRAT")
    app = build_control_app(kill_switch=ks, token_reader=lambda: TOKEN,
                            ack_path=tmp_path / "ACK_STRAT.json")
    client = TestClient(app)
    sp = client.get("/strategy")
    assert sp.status_code == 200
    body = sp.text
    assert "background:#f4f5f7" in body and "#0a0e17" not in body   # 白色,无残留深色
    assert "● 现役" in body and "当前实盘策略" in body
    assert "table class=wide" in body and "/strategy/history.csv" in body
    assert live[0]["策略"] in body

    # 4) 下载路由:text/csv,内容与仓内 CSV 逐字节一致
    dl = client.get("/strategy/history.csv")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("text/csv")
    assert dl.text == open(RESEARCH_CSV, encoding="utf-8").read()
    assert "attachment" in dl.headers.get("content-disposition", "")

    # 5) 下载路由不带任何交易语义(仍受全站禁词自检约束)
    assert_no_trading_routes(app)
