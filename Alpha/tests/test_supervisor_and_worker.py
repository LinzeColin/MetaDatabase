"""ALPHA-LIVE-040:监督进程心跳判活 + 交易 Worker 失败关闭行为。"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.notify.outbox import Outbox
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.supervisor import Supervisor
from backend.app.workers.trading_worker import WORKER_NAME, TradingWorker

NOW = datetime(2026, 7, 17, 16, 0, tzinfo=timezone.utc)


def make_stack(tmp_path):
    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'sup.sqlite'}"))
    clock = {"t": NOW}
    hb = HeartbeatStore(f, now_fn=lambda: clock["t"])
    ob = Outbox(f, now_fn=lambda: clock["t"])
    ks = KillSwitch(tmp_path / "KILL_SWITCH")
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=ks,
                     expected_workers=("trading-worker", "notify-worker"))
    return f, clock, hb, ob, ks, sup


def test_supervisor_all_healthy(tmp_path):
    _, clock, hb, ob, ks, sup = make_stack(tmp_path)
    hb.beat("trading-worker")
    hb.beat("notify-worker")
    clock["t"] = NOW + timedelta(seconds=30)
    report = sup.check_once()
    assert report.healthy == ("trading-worker", "notify-worker")
    assert not report.kill_switch_engaged
    assert ob.pending_count() == 0


def test_supervisor_stale_heartbeat_fails_closed(tmp_path):
    """心跳丢失自愈路径:告警邮件入队 + 杀开关拍下(=停新单);拉起交给 systemd。"""
    _, clock, hb, ob, ks, sup = make_stack(tmp_path)
    hb.beat("trading-worker")
    hb.beat("notify-worker")
    clock["t"] = NOW + timedelta(seconds=120)      # 超过 90s 容忍
    report = sup.check_once()
    assert set(report.stale) == {"trading-worker", "notify-worker"}
    assert report.kill_switch_engaged and ks.active()
    assert ks.detail()["source"] == "supervisor"
    assert ob.pending_count() == 1                 # WORKER_HEARTBEAT_LOST 告警


def test_supervisor_missing_worker_alerts(tmp_path):
    _, clock, hb, ob, ks, sup = make_stack(tmp_path)
    hb.beat("trading-worker")
    report = sup.check_once()
    assert report.missing == ("notify-worker",)
    assert ks.active()


def test_worker_beats_and_runs_cycles(tmp_path):
    f, clock, hb, ob, ks, _ = make_stack(tmp_path)
    calls = []
    w = TradingWorker(heartbeats=hb, kill_switch=ks,
                      run_cycle=lambda: calls.append(1) or {"ok": True},
                      interval_seconds=0, sleep_fn=lambda _s: None, max_cycles=3)
    w.run()
    assert len(calls) == 3
    assert hb.age_seconds(WORKER_NAME) is not None


def test_worker_halts_cycles_under_kill_switch(tmp_path):
    f, clock, hb, ob, ks, _ = make_stack(tmp_path)
    ks.engage(reason="测试", source="test")
    calls = []
    w = TradingWorker(heartbeats=hb, kill_switch=ks,
                      run_cycle=lambda: calls.append(1),
                      interval_seconds=0, sleep_fn=lambda _s: None, max_cycles=2)
    w.run()
    assert calls == []                             # 杀开关期间零决策
    assert hb.snapshot()[WORKER_NAME]["status"] == "HALTED"


def test_worker_crash_marks_error_and_reraises(tmp_path):
    f, clock, hb, ob, ks, _ = make_stack(tmp_path)

    def boom():
        raise RuntimeError("行情源炸了")

    w = TradingWorker(heartbeats=hb, kill_switch=ks, run_cycle=boom,
                      interval_seconds=0, sleep_fn=lambda _s: None, max_cycles=5)
    with pytest.raises(RuntimeError):
        w.run()                                    # 失败关闭:异常上抛由 systemd 拉起
    assert hb.snapshot()[WORKER_NAME]["status"] == "ERROR"
    assert w.cycles_run == 0
