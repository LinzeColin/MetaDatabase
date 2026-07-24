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


def test_supervisor_alarm_dedup_and_recovery(tmp_path):
    """去重:持续故障只告警一次;6小时后重提醒;恢复发一封平安信。杀开关行为不变。"""
    from datetime import datetime, timedelta, timezone

    from backend.app.notify.outbox import Outbox
    from backend.app.store.db import create_session_factory, init_engine
    from backend.app.workers.heartbeat import HeartbeatStore
    from backend.app.workers.killswitch import KillSwitch
    from backend.app.workers.supervisor import Supervisor

    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path/'d.sqlite'}"))
    clock = {"t": datetime(2026, 7, 21, 0, 0, tzinfo=timezone.utc)}
    hb = HeartbeatStore(factory, now_fn=lambda: clock["t"])
    ob = Outbox(factory, now_fn=lambda: clock["t"])
    ks = KillSwitch(tmp_path / "KS")
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=ks,
                     expected_workers=("trading-worker",),
                     engage_kill_switch_on_loss=True, now_fn=lambda: clock["t"])

    # 从未心跳 = missing:第一拍告警 1 条 + 拉闸
    sup.check_once()
    assert ob.pending_count() == 1 and ks.active()
    # 之后连续 10 拍同一故障:不再新增(旧行为会 +10)
    for _ in range(10):
        clock["t"] += timedelta(seconds=30)
        sup.check_once()
    assert ob.pending_count() == 1
    # 过 6 小时仍未修:补一条提醒
    clock["t"] += timedelta(hours=6, seconds=1)
    sup.check_once()
    assert ob.pending_count() == 2
    # 心跳恢复:发『已恢复』;后续健康拍不再发
    hb.beat("trading-worker", status="RUNNING", detail="回来了")
    sup.check_once()
    assert ob.pending_count() == 3
    for _ in range(5):
        clock["t"] += timedelta(seconds=30)
        hb.beat("trading-worker", status="RUNNING", detail="稳")
        sup.check_once()
    assert ob.pending_count() == 3


def test_supervisor_limited_restart_after_persistent_loss(tmp_path):
    """受限自愈:失联持续超阈值才动手、按序先网关后进程、冷却期内绝不再动。"""
    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'sup2.sqlite'}"))
    clock = {"t": NOW}
    hb = HeartbeatStore(f, now_fn=lambda: clock["t"])
    ob = Outbox(f, now_fn=lambda: clock["t"])
    ks = KillSwitch(tmp_path / "KS_R")
    restarted: list[str] = []
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=ks,
                     expected_workers=("trading-worker",),
                     now_fn=lambda: clock["t"],
                     restart_fn=lambda u: (restarted.append(u), True)[1],
                     restart_after_seconds=300, restart_cooldown_seconds=1800)
    hb.beat("trading-worker")
    clock["t"] = NOW + timedelta(seconds=120)      # 失联,但未满 300 秒
    sup.check_once()
    assert restarted == []
    clock["t"] = NOW + timedelta(seconds=500)      # 失联持续 380 秒 → 动用重启权
    sup.check_once()
    assert restarted == ["alpha-opend", "alpha-trading-worker"]
    clock["t"] = NOW + timedelta(seconds=700)      # 冷却期内不再重启
    sup.check_once()
    assert len(restarted) == 2


def test_supervisor_auto_clears_only_own_brake(tmp_path):
    """自动收闸:只解守护自己拍的闸,且须连续健康;owner 拍的闸永不自动解。"""
    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'sup3.sqlite'}"))
    clock = {"t": NOW}
    hb = HeartbeatStore(f, now_fn=lambda: clock["t"])
    ob = Outbox(f, now_fn=lambda: clock["t"])
    ks = KillSwitch(tmp_path / "KS_C")
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=ks,
                     expected_workers=("trading-worker",),
                     now_fn=lambda: clock["t"], auto_clear_after_checks=3)
    ks.engage(reason="心跳丢失: 测试", source="supervisor")
    for i in range(3):
        hb.beat("trading-worker")
        clock["t"] = clock["t"] + timedelta(seconds=30)
        sup.check_once()
    assert not ks.active()                          # 连续 3 拍健康 → 自动解闸
    ks.engage(reason="owner 手动停机", source="control_page")
    for i in range(4):
        hb.beat("trading-worker")
        clock["t"] = clock["t"] + timedelta(seconds=30)
        sup.check_once()
    assert ks.active()                              # owner 拍的闸永不自动解


def test_worker_feeds_watchdog_and_beats_log(tmp_path, capsys):
    """看门狗:装配完成报 READY,每拍喂 WATCHDOG 并打一行节拍日志。"""
    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'wd.sqlite'}"))
    hb = HeartbeatStore(f)
    ks = KillSwitch(tmp_path / "KS_W")
    notes: list[str] = []
    worker = TradingWorker(heartbeats=hb, kill_switch=ks,
                           run_cycle=lambda: {"ok": 1},
                           interval_seconds=0, sleep_fn=lambda s: None,
                           max_cycles=3, notify_fn=lambda m: notes.append(m))
    worker.run()
    assert notes[0] == "READY=1"
    assert notes.count("WATCHDOG=1") == 3
    out = capsys.readouterr().out
    assert out.count("节拍 RUNNING") == 3
