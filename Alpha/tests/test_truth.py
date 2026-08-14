"""单一真源(门 #24):同一事实只在一处算,且必须从权威配置读。"""

import backend.app.truth as truth
from backend.app.truth import (capital_aud, contract_fx_aud_usd, fat_finger_ratio,
                               is_micro_live, single_order_cap_usd)


def test_is_micro_live_needs_both_conditions(monkeypatch):
    """模式=MICRO_LIVE 且总开关=1 才算实盘;缺一不可。"""
    cases = [("MICRO_LIVE", "1", True), ("MICRO_LIVE", "0", False),
             ("PAPER", "1", False), ("", "", False)]
    for mode, flag, expect in cases:
        monkeypatch.setenv("ALPHA_MODE", mode)
        monkeypatch.setenv("LIVE_TRADING_ENABLED", flag)
        assert is_micro_live() is expect, f"{mode}/{flag}"


def test_ratio_and_capital_come_from_policy_not_hardcoded():
    """单笔比例与本金必须从权威配置读到(不是代码里写死的猜测值)。"""
    truth._policy.cache_clear()
    assert fat_finger_ratio() == 0.90, "应读到 policy.yaml 里 owner 授权的 90%"
    assert capital_aud() == 3000.0


def test_ratio_falls_back_conservative_when_policy_unreadable(tmp_path):
    """配置读不到时取最保守值,绝不乐观放大额度。"""
    truth._policy.cache_clear()
    assert fat_finger_ratio(str(tmp_path / "nope.yaml")) == 0.6


def test_single_order_cap_is_single_algorithm():
    """下单额度 = 本金 × 比例 × 滑点余量 × 契约汇率,全项目唯一算法。"""
    truth._policy.cache_clear()
    expected = 3000.0 * 0.90 * 0.97 * 0.65
    assert abs(single_order_cap_usd() - expected) < 0.01


def test_contract_fx_never_uses_live_rate(monkeypatch):
    """契约汇率只从 env/常量来,绝不吃实时行情(混用会造出汇率往返假盈亏)。"""
    monkeypatch.delenv("ALPHA_FX_AUD_USD", raising=False)
    assert contract_fx_aud_usd() == 0.65
    monkeypatch.setenv("ALPHA_FX_AUD_USD", "0.70")
    assert contract_fx_aud_usd() == 0.70


def test_no_duplicated_compound_live_check():
    """回归门:不得就地重新拼装"MICRO_LIVE 且 总开关=1"这个复合判定(必须调 is_micro_live)。

    注意只禁"复合判定的复制品",不禁合法的单点使用:
    - execution/gateway.py 把总开关作为 11 道闸中的**一道**单独检查 —— 合法;
    - workers/live_cycle.py 的 resolve_mode 是模式解析的**源头**(带失败关闭断言) —— 合法;
    - services/policy.py 只是从配置读该 env 的**键名** —— 合法;
    - scripts/activate_micro_live.py 是唯一有权**写**这些键的脚本 —— 合法。
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for f in list((root / "backend").rglob("*.py")) + list((root / "scripts").rglob("*.py")):
        if f.name in ("truth.py", "activate_micro_live.py") or "/tests/" in str(f):
            continue
        txt = f.read_text(encoding="utf-8", errors="ignore")
        # 复合判定的特征:同一文件里既比对 MICRO_LIVE 又比对总开关,且没走真源
        if ("MICRO_LIVE" in txt and "LIVE_TRADING_ENABLED" in txt
                and "is_micro_live" not in txt and "resolve_mode" not in txt):
            offenders.append(str(f.relative_to(root)))
    assert not offenders, f"这些文件在就地重拼复合实盘判定,应改用 is_micro_live():{offenders}"
