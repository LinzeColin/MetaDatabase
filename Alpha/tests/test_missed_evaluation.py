"""业务级健康红灯:最近一个评估窗已结束的周二没有完成记录(2026-07-28 事故根因 R3)。

事故:worker 空转 15.9 小时、1904 次心跳、页面"✅ 系统正常运行中",交易窗静默流逝。
心跳只证明进程在转,不证明业务在做事——健康检查必须绑业务产出(完成记录),
且三种交易模式都判、周三仍红、部署前的周二不误报。
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from backend.app.workers.live_cycle import missed_evaluation

ET = ZoneInfo("America/New_York")

TUE_AFTER_WINDOW = datetime(2026, 7, 28, 12, 0, tzinfo=ET)   # 周二,窗口(11:00)已过
TUE_IN_WINDOW = datetime(2026, 7, 28, 10, 30, tzinfo=ET)     # 周二,窗口内
TUE_BEFORE = datetime(2026, 7, 28, 9, 0, tzinfo=ET)          # 周二,开盘前
LONG_AGO = datetime(2026, 1, 1, tzinfo=ET)                   # 部署早于所有被测周二


def _missed(now, tag, *, expects=True, since=LONG_AGO):
    return missed_evaluation(now, last_completed_tag=tag, expects=expects, since=since)


def test_reproduces_the_incident_red_light():
    """复现事故:周二窗口已过、完成记录还停在 07-21 → 必须红灯,且给出排查方向。"""
    missed, why, due = _missed(TUE_AFTER_WINDOW, "2026-07-21")
    assert missed is True and due == "2026-07-28"
    assert "2026-07-28" in why and "没有完成记录" in why
    assert "BLOCKED_" in why, "原因里要直接给出排查方向"


def test_no_red_when_completed_today():
    assert _missed(TUE_AFTER_WINDOW, "2026-07-28")[0] is False


def test_no_false_alarm_before_or_during_window():
    """当天窗口还没过完:due 是上一个周二;上周已完成就不红。"""
    for t in (TUE_BEFORE, TUE_IN_WINDOW):
        missed, _, due = _missed(t, "2026-07-21")
        assert missed is False and due == "2026-07-21"


def test_shadow_tuesday_after_window_red_and_wednesday_still_red():
    """影子盘周二 11:01 无完成记录判红;周三 12:00 仍红,due_tag 仍是周二(不再"周三本来就不评估"放过)。"""
    tue_1101 = datetime(2026, 9, 29, 11, 1, tzinfo=ET)
    missed, _, due = _missed(tue_1101, "2026-09-22")
    assert missed is True and due == "2026-09-29"
    assert _missed(datetime(2026, 9, 29, 11, 0, tzinfo=ET), "2026-09-22")[0] is False  # 11:00 整仍在窗内
    wed = datetime(2026, 9, 30, 12, 0, tzinfo=ET)
    missed, _, due = _missed(wed, "2026-09-22")
    assert missed is True and due == "2026-09-29"
    assert _missed(datetime(2026, 10, 1, 9, 0, tzinfo=ET), "2026-09-29")[0] is False  # 补上即绿


def test_start_marker_without_completion_is_red(tmp_path, monkeypatch):
    """只有开始标记(last_s1_eval.txt)、没有完成记录(last_eval_result.json)= 评估中途崩溃 → 红。"""
    from backend.app.health import evaluate_health
    from backend.app.store.db import create_session_factory, init_engine

    rt = tmp_path / "rt"
    rt.mkdir()
    monkeypatch.setenv("ALPHA_MODE", "SHADOW")
    monkeypatch.setenv("ALPHA_RUNTIME_DIR", str(rt))
    (rt / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": "2026-09-01T00:00:00+00:00"}))
    (rt / "last_s1_eval.txt").write_text("2026-09-29")
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'h.sqlite'}"))
    now = datetime(2026, 9, 29, 11, 30, tzinfo=ET)
    items = evaluate_health(session_factory=factory, heartbeats=None, kill_switch=None, now=now)
    missed = next(i for i in items if i.key.startswith("eval_missed:"))
    assert missed.key == "eval_missed:2026-09-29" and missed.bad is True

    (rt / "last_eval_result.json").write_text(json.dumps({"date": "2026-09-29", "plan": []}))
    items = evaluate_health(session_factory=factory, heartbeats=None, kill_switch=None, now=now)
    assert next(i for i in items if i.key.startswith("eval_missed:")).bad is False


def test_since_suppresses_pre_deploy_tuesdays():
    """部署(本金冻结)之后才结束评估窗的周二才会判红;部署当天窗口已过也不算漏。"""
    wed = datetime(2026, 9, 30, 12, 0, tzinfo=ET)
    deployed_wed = datetime(2026, 9, 30, 8, 0, tzinfo=ET)
    assert _missed(wed, "", since=deployed_wed)[0] is False
    deployed_tue_noon = datetime(2026, 9, 29, 12, 0, tzinfo=ET)
    assert _missed(wed, "", since=deployed_tue_noon)[0] is False
    deployed_tue_morning = datetime(2026, 9, 29, 9, 0, tzinfo=ET)
    assert _missed(wed, "", since=deployed_tue_morning)[0] is True
    # 部署后的下一个周二照常判
    next_wed = datetime(2026, 10, 7, 12, 0, tzinfo=ET)
    assert _missed(next_wed, "", since=deployed_wed)[0] is True


def test_disabled_never_red():
    """expects=False(DISABLED/HALTED)永远不红。"""
    for t in (TUE_AFTER_WINDOW, datetime(2026, 7, 29, 12, 0, tzinfo=ET)):
        assert _missed(t, "", expects=False)[0] is False


def test_never_evaluated_reports_honestly():
    """从未完成过时,原因里如实写"从未"而不是空白。"""
    _, why, _ = _missed(TUE_AFTER_WINDOW, "")
    assert "从未" in why
