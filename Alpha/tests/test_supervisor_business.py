"""守护的业务级动作:漏评估自动补做(R2)、无 sudo 也能自动解自己拍的刹车。"""

import json
from datetime import datetime, timedelta, timezone

from backend.app.notify.outbox import Outbox
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.supervisor import Supervisor

UTC = timezone.utc
TUE_1105_ET = datetime(2026, 9, 29, 15, 5, tzinfo=UTC)     # 周二 11:05 ET,评估窗刚结束


def build(tmp_path, clock, name="sup", **kw):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / f'{name}.sqlite'}"))
    hb = HeartbeatStore(factory, now_fn=lambda: clock["t"])
    ob = Outbox(factory, now_fn=lambda: clock["t"])
    ks = KillSwitch(tmp_path / f"KS_{name}")
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=ks, expected_workers=("trading-worker",),
                     now_fn=lambda: clock["t"], **kw)
    hb.beat("trading-worker", status="RUNNING", detail="{'mode': 'SHADOW'}")
    return sup, hb, ob, ks


def test_missed_eval_writes_makeup_once(shadow_env, tmp_path):
    """周二 11:05 漏评估 → 写补评估标记一次;当天已有开始标记(评估中途崩溃)不写,不重复下单。"""
    (shadow_env / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": "2026-09-01T00:00:00+00:00"}))
    clock = {"t": TUE_1105_ET}
    sup, _, ob, _ = build(tmp_path, clock)
    sup.check_once()
    makeup = shadow_env / "makeup_eval.txt"
    assert makeup.read_text() == "2026-09-29"
    makeup.unlink()
    clock["t"] += timedelta(seconds=30)
    sup.check_once()                                    # 同一故障状态未变:不再触发,不再写
    assert not makeup.exists()
    assert any(a["key"] == "eval_missed:2026-09-29" for a in _open(sup))

    # 当天开始标记已写(评估中途崩溃):告警照发,但绝不补评估
    rt2 = shadow_env.parent / "rt2"
    rt2.mkdir()
    (rt2 / "last_s1_eval.txt").write_text("2026-09-29")
    sup2, _, _, _ = build(tmp_path, {"t": TUE_1105_ET}, name="sup2", runtime_dir=rt2)
    sup2.check_once()
    assert not (rt2 / "makeup_eval.txt").exists()


def _open(sup):
    return sup._alerts.open_alerts()


def test_auto_clear_without_restart_fn(tmp_path):
    """restart_fn=None(VPS-3 不开 sudo)时,守护自己拍的刹车仍在连续 6 拍健康后自动解除。"""
    clock = {"t": datetime(2026, 9, 30, 0, 0, tzinfo=UTC)}
    sup, hb, ob, ks = build(tmp_path, clock, restart_fn=None, auto_clear_after_checks=6,
                            health_fn=lambda **_: [])
    clock["t"] += timedelta(seconds=200)                # 心跳停摆
    sup.check_once()
    assert ks.active() and ks.detail()["source"] == "supervisor"
    for i in range(6):
        hb.beat("trading-worker", status="RUNNING", detail="{'mode': 'SHADOW'}")
        clock["t"] += timedelta(seconds=30)
        sup.check_once()
        assert ks.active() is (i < 5), i
    # 人拍的闸永不自动解
    ks.engage(reason="owner 手动停机", source="owner")
    for _ in range(8):
        hb.beat("trading-worker", status="RUNNING", detail="ok")
        clock["t"] += timedelta(seconds=30)
        sup.check_once()
    assert ks.active()
