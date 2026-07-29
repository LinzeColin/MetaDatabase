"""隔离铁律(owner 2026-07-24):系统只认自己成交,绝不把 owner 交易/持仓/收益当成自己的。"""

import json
import tempfile
from pathlib import Path

from backend.app.control_page.dashboard_data import _read_start_capital, build_overview
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.killswitch import KillSwitch


class _KS:
    def active(self): return False
    def detail(self): return ""


def _factory(tmp):
    return create_session_factory(init_engine(f"sqlite:///{tmp}/iso.sqlite"))


def test_net_positions_only_counts_system_fills(tmp_path):
    """空系统库(owner 在券商另有 TQQQ/SPCG)→ 系统净持仓为空,绝不误认。"""
    from backend.app.store.orders import OrderStore
    store = OrderStore(_factory(tmp_path))
    assert store.net_positions() == {}          # 系统没成交 → 空,哪怕账户里有 owner 的仓


def test_frozen_start_capital_isolates_equity_from_owner_cash(tmp_path):
    """已冻结初始本金后,净值只随系统现金流+持仓走,券商购买力(含 owner 出入金)变化不影响。"""
    rt = tmp_path / "rt"
    rt.mkdir()
    (rt / "LIVE_START_CAPITAL.json").write_text(json.dumps({"start_capital_usd": 1587.09}))
    assert _read_start_capital(rt) == 1587.09

    ks = KillSwitch(tmp_path / "KS")
    # owner 往账户里塞了一大笔自有现金 → real_power_usd 飙到 9999,净值绝不能跟着涨
    o = build_overview(session_factory=None, heartbeats=None, kill_switch=ks,
                       runtime_dir=rt, reports_dir=tmp_path / "nore",
                       real_power_usd=9999.0, fx_aud_usd=0.65)
    # 系统无成交:净值 = 冻结本金 1587.09(不是 9999+),现金 = 冻结本金
    assert abs(o["hero"]["cash_usd"] - 1587.09) < 0.01
    assert abs(o["hero"]["equity_usd"] - 1587.09) < 0.01 if "equity_usd" in o["hero"] else True
    # 澳元净值 = 1587.09/0.65,绝不含 owner 的 9999
    assert abs(o["hero"]["equity_aud"] - 1587.09 / 0.65) < 0.01


def test_never_counts_owner_money_as_strategy_return(tmp_path):
    """2026-07-28 事故回归门:owner 自己动账户现金,绝不能变成策略的收益。

    真实事故:owner 账户现金 1587→2744,页面据此报"累计盈亏 +947.89 澳元 / +31.6%",
    而策略一次交易都没做过。策略净值必须只由策略自己的账算出。
    """
    ks = KillSwitch(tmp_path / "KS2")
    for account_cash in (1587.09, 2744.57, 9999.0):     # owner 反复动自己的钱
        o = build_overview(session_factory=None, heartbeats=None, kill_switch=ks,
                           runtime_dir=tmp_path / "empty", reports_dir=tmp_path / "nore",
                           real_power_usd=account_cash, fx_aud_usd=0.65)
        h = o["hero"]
        # 策略没交易过 → 净值恰为期初本金 3000 澳元,盈亏 0
        assert abs(h["equity_aud"] - 3000.0) < 0.01, f"账户现金 {account_cash} 污染了策略净值"
        assert abs(h["total_pnl_aud"]) < 0.01, "策略没交易过却报出了盈亏"
        assert h["traded_yet"] is False
        # 你的账户余额仍可见,但只作"资金是否到位"提示
        assert abs(h["account_cash_usd"] - account_cash) < 0.01
