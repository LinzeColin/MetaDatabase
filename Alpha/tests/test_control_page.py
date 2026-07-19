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
    login = client.get("/")
    assert login.status_code == 401
    assert "令牌" in login.text and "净持仓" not in login.text   # 登录页零数据
    wrong = client.get("/?token=wrong")
    assert wrong.status_code == 401 and "再试一次" in wrong.text
    page = client.get(f"/?token={TOKEN}")
    assert page.status_code == 200
    body = page.text
    assert "净持仓" in body and "订单" in body and "trading-worker" in body
    assert "空仓" in body            # 无成交时如实显示空仓
    assert "<form" not in body       # 数据页只读:无任何表单/按钮
