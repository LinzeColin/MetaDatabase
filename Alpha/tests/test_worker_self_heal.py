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


def test_shadow_build_failure_returns_blocked_on_feed_and_retries_60s(shadow_env, monkeypatch):
    """门 #19:影子盘装配失败如实回 BLOCKED_ON_FEED(不冒充 OpenD),60 秒后自动重试并恢复。"""
    from backend.app.workers import shadow_cycle
    from backend.app.workers.main_trading import build_worker

    attempts = {"n": 0}

    def fake_build(**_):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("Yahoo 行情暂时取不到")
        return lambda: {"mode": "SHADOW", "evaluated": False}

    monkeypatch.setattr(shadow_cycle, "build_shadow_cycle", fake_build)
    clock = _Clock()
    cycle = build_worker(retry_seconds=60.0, clock=clock)._run_cycle

    r1 = cycle()
    assert r1["status"] == "BLOCKED_ON_FEED" and r1["retrying"] is True
    assert "Yahoo" in r1["note"]
    clock.advance(30)
    cycle()
    assert attempts["n"] == 1, "60 秒内不重复装配"
    clock.advance(31)
    assert cycle()["mode"] == "SHADOW" and attempts["n"] == 2


def test_missing_or_misspelled_mode_blocks_on_mode(shadow_env, monkeypatch):
    """ALPHA_MODE 缺失/拼错解析为 DISABLED,wiring 无条目:失败关闭(BLOCKED_ON_MODE),不落到 PAPER/OpenD。"""
    from backend.app.workers.main_trading import build_worker

    for value in (None, "", "SHAOW"):
        if value is None:
            monkeypatch.delenv("ALPHA_MODE", raising=False)
        else:
            monkeypatch.setenv("ALPHA_MODE", value)
        r = build_worker(retry_seconds=60.0, clock=_Clock())._run_cycle()
        assert r["status"] == "BLOCKED_ON_MODE", value
