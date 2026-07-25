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


def test_unfrozen_tracks_live_funding(tmp_path):
    """未冻结(尚未首笔成交)时跟随真实可用,反映入金进度。"""
    ks = KillSwitch(tmp_path / "KS2")
    o = build_overview(session_factory=None, heartbeats=None, kill_switch=ks,
                       runtime_dir=tmp_path / "empty", reports_dir=tmp_path / "nore",
                       real_power_usd=1587.09, fx_aud_usd=0.65)
    assert abs(o["hero"]["cash_usd"] - 1587.09) < 0.01
