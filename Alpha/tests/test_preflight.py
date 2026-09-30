"""盘前自检:每项过告警状态簿(转红一封、重复不发),影子盘不碰 OpenD 与授权,报红也返回 0。"""

import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

import scripts.preflight_check as pf
from backend.app.domain.models import OutboxEvent
from backend.app.marketdata.yahoo_live import LiveQuote, QuoteUnavailable
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)      # 周一;最近应评估的周二是 09-22


class Quotes:
    def __init__(self, broken=()):
        self.broken = set(broken)

    def get_quote(self, sym):
        if sym in self.broken:
            raise QuoteUnavailable(sym)
        return LiveQuote(symbol=sym, price=100.0, ts_utc=NOW)


@pytest.fixture
def healthy(shadow_env):
    """除行情外全部健康:三组件心跳新鲜且模式一致,上周二已完成评估,刹车待命。"""
    factory = create_session_factory(init_engine())
    hb = HeartbeatStore(factory, now_fn=lambda: NOW)
    for w in ("trading-worker", "notify-worker", "supervisor"):
        hb.beat(w, status="RUNNING", detail="{'mode': 'SHADOW'}")
    (shadow_env / "last_eval_result.json").write_text(json.dumps({"date": "2026-09-22", "plan": []}))
    return factory


def events(factory, event_type):
    with factory() as s:
        return int(s.scalar(select(func.count()).select_from(OutboxEvent)
                            .where(OutboxEvent.event_type == event_type)))


def test_red_enqueues_once_exit_zero(healthy, shadow_env):
    assert pf.main(quotes=Quotes(), now=NOW) == 0
    assert events(healthy, "ALERT_RAISED") == 0                     # 全绿不发信(不再有 PREFLIGHT_OK 绿灯信)
    assert events(healthy, "PREFLIGHT_OK") == 0
    assert pf.main(quotes=Quotes(broken={"QQQ"}), now=NOW) == 0     # 报红也返回 0
    assert events(healthy, "ALERT_RAISED") == 1
    assert pf.main(quotes=Quotes(broken={"QQQ"}), now=NOW) == 0     # 重复运行不再发
    assert events(healthy, "ALERT_RAISED") == 1
    facts = json.loads((shadow_env / "facts" / "preflight_status.json").read_text())
    assert facts["all_ok"] is False and facts["mode"] == "SHADOW"
    assert pf.main(quotes=Quotes(), now=NOW) == 0                   # 恢复:发一封已恢复
    assert events(healthy, "ALERT_RECOVERED") == 1


def test_shadow_skips_opend_and_auth(healthy, shadow_env, monkeypatch):
    """影子盘不调用 OpenD 探针与授权校验(调用即失败)。"""
    def boom(*a, **k):
        raise AssertionError("影子盘不应触碰 OpenD / 授权")

    monkeypatch.setattr(pf, "_opend_power", boom)
    monkeypatch.setattr("backend.app.execution.gates.validate_authorization", boom)
    assert pf.main(quotes=Quotes(), now=NOW) == 0
    facts = json.loads((shadow_env / "facts" / "preflight_status.json").read_text())
    assert {"quotes"} <= {c["slug"] for c in facts["checks"]}
    assert not {"opend", "auth", "auth_expiry"} & {c["slug"] for c in facts["checks"]}

