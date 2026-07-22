"""每日收盘复判:纯函数口径(工作日/保守可用性/最大回撤/邮件纪律)。"""

import scripts.daily_rejudge as dr


def test_weekdays_between_skips_weekend():
    days = dr.weekdays_between("2026-07-20", "2026-07-27")
    assert days == ["2026-07-20", "2026-07-21", "2026-07-22",
                    "2026-07-23", "2026-07-24", "2026-07-27"]


def test_uptime_conservative_60s_per_restart():
    days = ["2026-07-20", "2026-07-21", "2026-07-22"]
    assert dr.uptime_pct(days, {}) == 100.0
    # 一次盘中重启扣 60 秒:与人工核算口径一致(70200-60)/70200
    assert dr.uptime_pct(days, {"2026-07-22": 1}) == 99.91


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
