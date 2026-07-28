"""立即评估开关(owner 2026-07-26:"不能用真实时间等待浪费")。

铁律:FORCE_EVAL 只放宽"什么时候评估",绝不放宽任何风控;用后即焚,只生效一次。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.workers.live_cycle import eval_trigger, in_eval_window, market_open_now

ET = ZoneInfo("America/New_York")

MON_OPEN = datetime(2026, 7, 27, 10, 15, tzinfo=ET)     # 周一 10:15 ET(执行窗内)
MON_PREMKT = datetime(2026, 7, 27, 8, 0, tzinfo=ET)     # 周一盘前
MON_CLOSED = datetime(2026, 7, 27, 17, 0, tzinfo=ET)    # 周一盘后
SUN = datetime(2026, 7, 26, 12, 0, tzinfo=ET)           # 周日
TUE_WINDOW = datetime(2026, 7, 28, 10, 15, tzinfo=ET)   # 周二常规窗


def test_force_fires_immediately_on_any_open_day():
    """放了 FORCE_EVAL:周一开市即评估,不必等到周二。"""
    trig, forced = eval_trigger(MON_OPEN, force_exists=True, makeup_today=False)
    assert trig is True and forced is True
    assert in_eval_window(MON_OPEN) is False, "周一本不在常规窗,证明确实是被强制触发的"


def test_force_only_in_validated_exec_window():
    """强制评估只在回测验证过的执行窗(开盘后30-90分钟)触发,避开开盘竞价宽点差。"""
    bell = datetime(2026, 7, 27, 9, 31, tzinfo=ET)      # 刚开盘:点差最烂,不该触发
    late = datetime(2026, 7, 27, 14, 0, tzinfo=ET)      # 午后:窗口外
    for t in (bell, late):
        assert eval_trigger(t, force_exists=True, makeup_today=False)[0] is False, t


def test_force_does_not_fire_when_market_closed():
    """休市时不触发:盘前/盘后/周末都不行——行情不新鲜,下单也会被风控拒。"""
    for t in (MON_PREMKT, MON_CLOSED, SUN):
        trig, forced = eval_trigger(t, force_exists=True, makeup_today=False)
        assert (trig, forced) == (False, False), f"{t} 不该触发"
        assert market_open_now(t) is False


def test_normal_tuesday_cadence_unchanged():
    """没有 FORCE_EVAL 时,行为与从前完全一致:只有周二窗内触发。"""
    assert eval_trigger(TUE_WINDOW, force_exists=False, makeup_today=False) == (True, False)
    assert eval_trigger(MON_OPEN, force_exists=False, makeup_today=False) == (False, False)


def test_force_is_reported_as_forced_not_routine():
    """强制触发必须如实标记 forced=True,便于报告区分『例行』与『手动催单』。"""
    _, forced_tue = eval_trigger(TUE_WINDOW, force_exists=False, makeup_today=False)
    _, forced_mon = eval_trigger(MON_OPEN, force_exists=True, makeup_today=False)
    assert forced_tue is False and forced_mon is True


def test_makeup_path_still_works():
    """补评估通路不受影响(开盘后 60-120 分钟)。"""
    makeup_t = datetime(2026, 7, 27, 10, 45, tzinfo=ET)
    assert eval_trigger(makeup_t, force_exists=False, makeup_today=True)[0] is True
    assert eval_trigger(datetime(2026, 7, 27, 13, 0, tzinfo=ET),
                        force_exists=False, makeup_today=True)[0] is False
