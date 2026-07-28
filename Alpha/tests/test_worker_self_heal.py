"""2026-07-28 事故回归门:装配失败后必须持续重试,不得永久空转把交易窗口空过。

事故:开机时 OpenD 未就绪 → build_live_cycle 抛「账户不在券商列表」→ worker 落入
idle_cycle 后再也不重建,喂了 15 小时心跳、一次评估都没做,当天交易窗整个错过。
"""

from backend.app.workers.main_trading import make_self_healing_cycle


class _Clock:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def advance(self, s): self.t += s


def test_retries_until_opend_ready_then_trades():
    """OpenD 前两次没就绪,第三次好了 → 自动恢复真实循环,无需人工重启。"""
    clock = _Clock()
    attempts = {"n": 0}

    def build():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RuntimeError("账户 284008280622194851 不在券商列表")
        return lambda: {"mode": "MICRO_LIVE", "evaluated": True}

    cycle = make_self_healing_cycle(build, retry_seconds=60.0, clock=clock)

    r1 = cycle()
    assert r1["status"] == "BLOCKED_ON_OPEND" and r1["retrying"] is True
    assert "不在券商列表" in r1["note"], "必须如实报出原因"

    cycle()                       # 冷却期内:不重复尝试
    assert attempts["n"] == 1, "重试应受间隔节流,不得每拍猛敲 OpenD"

    clock.advance(61)
    r3 = cycle()
    assert r3["status"] == "BLOCKED_ON_OPEND" and attempts["n"] == 2

    clock.advance(61)
    r4 = cycle()
    assert r4["mode"] == "MICRO_LIVE", "OpenD 就绪后必须自动恢复实盘循环"
    assert attempts["n"] == 3


def test_no_rebuild_once_healthy():
    """装配成功后不再反复重建(避免抢租约/重连风暴)。"""
    clock = _Clock()
    attempts = {"n": 0}

    def build():
        attempts["n"] += 1
        return lambda: {"mode": "MICRO_LIVE"}

    cycle = make_self_healing_cycle(build, retry_seconds=60.0, clock=clock)
    for _ in range(5):
        clock.advance(120)
        assert cycle()["mode"] == "MICRO_LIVE"
    assert attempts["n"] == 1


def test_runtime_error_propagates_not_swallowed():
    """已装配成功后运行期抛错照旧上抛,交给看门狗/守护,绝不在此吞掉。"""
    clock = _Clock()

    def boom():
        raise RuntimeError("券商连接闪断")

    cycle = make_self_healing_cycle(lambda: boom, retry_seconds=60.0, clock=clock)
    try:
        cycle()
        raise AssertionError("运行期异常必须上抛")
    except RuntimeError as exc:
        assert "闪断" in str(exc)
