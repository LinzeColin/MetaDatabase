"""微实盘自动切换器:环境改写、前提复核、复判侧切换闸——纯函数全覆盖。"""

from datetime import datetime, timedelta, timezone

import scripts.activate_micro_live as am
import scripts.daily_rejudge as dr

NOW = datetime(2026, 7, 24, 20, 15, tzinfo=timezone.utc)


def _req(minutes_ago: int = 5) -> dict:
    return {"requested_at": (NOW - timedelta(minutes=minutes_ago))
            .isoformat().replace("+00:00", "Z")}


def test_set_env_keys_replaces_and_appends_preserving_comments():
    text = ("# 注释行保留\nALPHA_MODE=PAPER\nALPHA_EXPECTED_ACC_ID=138648\n"
            "LIVE_TRADING_ENABLED=0\nOTHER=x\n")
    out = am.set_env_keys(text, {"ALPHA_MODE": "MICRO_LIVE",
                                 "ALPHA_EXPECTED_ACC_ID": "999",
                                 "LIVE_TRADING_ENABLED": "1",
                                 "NEW_KEY": "v"})
    assert "# 注释行保留" in out and "OTHER=x" in out
    assert "ALPHA_MODE=MICRO_LIVE" in out and "ALPHA_MODE=PAPER" not in out
    assert "ALPHA_EXPECTED_ACC_ID=999" in out
    assert "LIVE_TRADING_ENABLED=1" in out and "LIVE_TRADING_ENABLED=0" not in out
    assert out.rstrip().endswith("NEW_KEY=v")


def test_preconditions_all_pass():
    ok, why = am.check_preconditions(
        request=_req(), now=NOW, auth_ok=True, auth_reasons=[],
        live_flag="0", real_acc_id="2840", report_auto_promote=True)
    assert ok, why


def test_preconditions_fail_closed_each_gate():
    base = dict(request=_req(), now=NOW, auth_ok=True, auth_reasons=[],
                live_flag="0", real_acc_id="2840", report_auto_promote=True)
    for patch, expect in [
        (dict(request=_req(minutes_ago=25 * 60)), "过期"),
        (dict(live_flag="1"), "已经是 1"),
        (dict(real_acc_id=""), "真实账户"),
        (dict(report_auto_promote=False), "非全绿"),
        (dict(auth_ok=False, auth_reasons=["签名无效"]), "授权"),
    ]:
        ok, why = am.check_preconditions(**{**base, **patch})
        assert not ok and expect in why, (patch, why)


def test_rejudge_activation_gate():
    # 三前提齐备 → 无阻塞
    assert dr.activation_gate(auth_ok=True, auth_reasons=[], live_flag_on=False,
                              real_acc="2840", power=2400.0, min_power=1890.0) == []
    # 各缺一项 → 对应阻塞且不请求切换
    assert any("授权" in b for b in dr.activation_gate(
        auth_ok=False, auth_reasons=["过期"], live_flag_on=False,
        real_acc="2840", power=2400.0, min_power=1890.0))
    assert any("购买力" in b for b in dr.activation_gate(
        auth_ok=True, auth_reasons=[], live_flag_on=False,
        real_acc="2840", power=500.0, min_power=1890.0))
    assert any("核验暂不可用" in b for b in dr.activation_gate(
        auth_ok=True, auth_reasons=[], live_flag_on=False,
        real_acc="2840", power=None, min_power=1890.0))
    assert any("已在实盘" in b for b in dr.activation_gate(
        auth_ok=True, auth_reasons=[], live_flag_on=True,
        real_acc="2840", power=2400.0, min_power=1890.0))
