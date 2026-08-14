"""业务级健康红灯:该评估的日子过了窗口却没评估(2026-07-28 事故根因 R3)。

事故:worker 空转 15.9 小时、1904 次心跳、页面"✅ 系统正常运行中",交易窗静默流逝。
心跳只证明进程在转,不证明业务在做事——健康检查必须绑业务产出。
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.workers.live_cycle import missed_evaluation

ET = ZoneInfo("America/New_York")

TUE_AFTER_WINDOW = datetime(2026, 7, 28, 12, 0, tzinfo=ET)   # 周二,窗口(11:00)已过
TUE_IN_WINDOW = datetime(2026, 7, 28, 10, 30, tzinfo=ET)     # 周二,窗口内
TUE_BEFORE = datetime(2026, 7, 28, 9, 0, tzinfo=ET)          # 周二,开盘前
WED = datetime(2026, 7, 29, 12, 0, tzinfo=ET)                # 周三:本就不该评估


def test_reproduces_the_incident_red_light():
    """复现事故:周二窗口已过、标记还停在 07-22 → 必须红灯。"""
    missed, why = missed_evaluation(TUE_AFTER_WINDOW, last_eval_tag="2026-07-22", is_live=True)
    assert missed is True
    assert "2026-07-28" in why and "没有当日评估记录" in why
    assert "BLOCKED_ON_OPEND" in why, "原因里要直接给出排查方向"


def test_no_red_when_evaluated_today():
    """今天已评估过 → 绿。"""
    assert missed_evaluation(TUE_AFTER_WINDOW, last_eval_tag="2026-07-28",
                             is_live=True)[0] is False


def test_no_false_alarm_before_or_during_window():
    """窗口还没过完不算漏(开盘前、窗口内都不报)。"""
    for t in (TUE_BEFORE, TUE_IN_WINDOW):
        assert missed_evaluation(t, last_eval_tag="2026-07-22", is_live=True)[0] is False


def test_non_eval_day_never_red():
    """周三本来就不该评估,绝不误报。"""
    assert missed_evaluation(WED, last_eval_tag="2026-07-22", is_live=True)[0] is False


def test_paper_mode_never_red():
    """未上实盘时不判红(纸面/未部署不误报)。"""
    assert missed_evaluation(TUE_AFTER_WINDOW, last_eval_tag="2026-07-22",
                             is_live=False)[0] is False


def test_never_evaluated_reports_honestly():
    """从未评估过时,原因里如实写"从未"而不是空白。"""
    _, why = missed_evaluation(TUE_AFTER_WINDOW, last_eval_tag="", is_live=True)
    assert "从未" in why
