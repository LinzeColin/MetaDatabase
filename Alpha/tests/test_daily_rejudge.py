"""每日收盘复判:纯函数口径(工作日/保守可用性/最大回撤/邮件纪律)。"""

import scripts.daily_rejudge as dr


def test_weekdays_between_skips_weekend():
    days = dr.weekdays_between("2026-07-20", "2026-07-27")
    assert days == ["2026-07-20", "2026-07-21", "2026-07-22",
                    "2026-07-23", "2026-07-24", "2026-07-27"]


def test_uptime_from_downtime_seconds():
    days = ["2026-07-20", "2026-07-21", "2026-07-22"]
    assert dr.uptime_pct(days, {}) == 100.0
    # 一次盘中重启保守 60 秒:与人工核算口径一致(70200-60)/70200
    assert dr.uptime_pct(days, {"2026-07-22": 60}) == 99.91
    # 全天卡死按窗口封顶:三日窗一天全停 → 66.67%
    assert dr.uptime_pct(days, {"2026-07-22": 999999}) == 66.67


def test_downtime_from_gaps_sees_hangs_not_just_restarts():
    start, end = 1000.0, 1000.0 + 23400.0
    # 全程无节拍(2026-07-23 事故形态)= 全窗口停机
    assert dr.downtime_from_gaps([], start, end) == 23400.0
    # 每 30 秒一拍的健康日 = 0 停机
    healthy = [start + i * 30 for i in range(781)]
    assert dr.downtime_from_gaps(healthy, start, end) == 0.0
    # 中段静默 2 小时:计入超出容忍(180s)的部分
    ts = [start + i * 30 for i in range(100)] + [start + 100 * 30 + 7200 + i * 30 for i in range(50)]
    down = dr.downtime_from_gaps(ts, start, ts[-1] + 10)
    assert 7000 < down < 7200


def test_day_downtime_takes_worst_of_ledger_gaps_restarts():
    ledger = {"2026-07-23": {"seconds": 23400, "原因": "事故"}}
    # 日志行不足(旧口径日)→ 台账与重启计数取大
    assert dr.day_downtime_seconds("2026-07-23", journal_ts=[], restarts=0,
                                   ledger=ledger) == 23400
    assert dr.day_downtime_seconds("2026-07-22", journal_ts=[], restarts=1,
                                   ledger={}) == 60


def test_max_drawdown_from_daily_equities():
    assert dr.max_drawdown_pct([3000.0, 3000.0, 2989.37]) == 0.35
    assert dr.max_drawdown_pct([3000.0, 3010.0, 3005.0]) == 0.17
    assert dr.max_drawdown_pct([]) == 0.0


def test_email_discipline():
    lights_red = (True, False, True)
    lights_green = (True, True, True)
    # 首次运行:不全绿只记档不发;全绿必发
    assert dr.should_email(None, lights_red, all_green=False) is False
    assert dr.should_email(None, lights_green, all_green=True) is True
    # 灯色不变不发,变了才发
    prev = {"lights": [True, False, True]}
    assert dr.should_email(prev, lights_red, all_green=False) is False
    assert dr.should_email(prev, (False, False, True), all_green=False) is True
