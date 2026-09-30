"""影子盘装配与交易循环:经 wiring 走真实装配链,假行情 + 注入时钟,不联网、不等真实周二。"""

import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.app.adapters.brokers.base import SystemMode
from backend.app.adapters.brokers.sim_broker import SimBroker
from backend.app.backtest.fees import FeeModel
from backend.app.domain.models import Execution, RiskDecision
from backend.app.domain.state_machine import OrderState
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import OrderStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.live_cycle import build_live_cycle
from backend.app.workers.shadow_cycle import FORBIDDEN_ENV, build_shadow_cycle

UTC = timezone.utc
ROOT = pathlib.Path(__file__).resolve().parents[1]
TUE = datetime(2026, 7, 21, 14, 15, tzinfo=UTC)          # 周二 10:15 ET(评估窗内)
NEXT_TUE = datetime(2026, 7, 28, 14, 15, tzinfo=UTC)
WED_EXEC = datetime(2026, 7, 22, 14, 45, tzinfo=UTC)     # 周三 10:45 ET(强制/补评估执行窗内)


def _shadow_env(monkeypatch, runtime):
    monkeypatch.setenv("ALPHA_MODE", "SHADOW")
    monkeypatch.setenv("ALPHA_RUNTIME_DIR", str(runtime))
    for k in FORBIDDEN_ENV + ("LIVE_TRADING_ENABLED", "ALPHA_STRATEGY_CONFIG"):
        monkeypatch.delenv(k, raising=False)


class Shadow:
    def __init__(self, tmp_path, monkeypatch, make_clock, make_market, start=TUE):
        self.runtime = tmp_path / "rt"
        _shadow_env(monkeypatch, self.runtime)
        self.factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'shadow.sqlite'}"))
        self.clock = make_clock(start)
        self.market = make_market(self.clock)
        self.cycle = build_live_cycle(factory=self.factory,
                                      kill_switch=KillSwitch(tmp_path / "KILL_SWITCH"),
                                      quotes=self.market, now_fn=self.clock)
        self.store = OrderStore(self.factory)
        self.sim = SimBroker(self.factory, quotes=self.market, fee_model=FeeModel.from_yaml(),
                             start_capital_usd=1950.0, now_fn=self.clock)

    def tick(self, **advance):
        if advance:
            self.clock.advance(**advance)
        return self.cycle()

    def result(self):
        return json.loads((self.runtime / "last_eval_result.json").read_text())

    def executions(self):
        with self.factory() as s:
            return list(s.scalars(select(Execution)))

    def all_rules(self):
        with self.factory() as s:
            return [r for d in s.scalars(select(RiskDecision)) for r in json.loads(d.triggered_rules)]


@pytest.fixture
def shadow(tmp_path, monkeypatch, make_clock, make_market):
    return lambda **kw: Shadow(tmp_path, monkeypatch, make_clock, make_market, **kw)


def test_end_to_end_tuesday_tick(shadow):
    """门 #25 的影子版闭环:第 1 拍提交 Top-1 买单,第 2 拍回灌出带费用的成交,账与簿一致。"""
    sh = shadow()
    r1 = sh.tick()
    assert r1["mode"] == "SHADOW" and r1["evaluated"] is True
    assert r1["plan"] == ["BUY QQQx4"] and r1["submitted"] == 1 and r1["rejected"] == 0
    assert sh.executions() == []                        # 成交在下一拍回灌
    r2 = sh.tick(seconds=30)
    assert r2["fills"] == 1 and r2["evaluated"] is False
    [ex] = sh.executions()
    assert ex.quantity == 4 and ex.fees > 0 and ex.broker_execution_id.startswith("DEAL-SIM-")
    assert sh.store.net_positions() == sh.sim.positions() == {"QQQ": 4}
    frozen = json.loads((sh.runtime / "LIVE_START_CAPITAL.json").read_text())
    assert frozen["start_capital_usd"] == 1950.0          # 3000 AUD × 0.65
    res = sh.result()
    assert (res["date"], res["as_of"], res["mode"]) == ("2026-07-21", "2026-07-20", "SHADOW")
    assert res["selected"] == ["QQQ"] and res["submitted"] == 1
    assert (sh.runtime / "last_s1_eval.txt").read_text() == "2026-07-21"
    book = sh.store.own_book()
    assert book.net == {"QQQ": 4}
    assert abs(1950.0 + book.cash_flow_usd - float(sh.sim.cash())) < 0.01


def test_rotation_week_sell_then_buy_same_tick(shadow):
    """换仓周:持有 QQQ、目标 SPY,同一拍卖单与买单都成交,不撞总敞口上限。"""
    sh = shadow()
    sh.tick()
    sh.tick(seconds=30)
    assert sh.store.net_positions() == {"QQQ": 4}
    sh.clock.set(NEXT_TUE)
    sh.market.slopes.update({"SPY": 0.002, "QQQ": -0.0005})
    r = sh.tick()
    assert r["plan"] == ["SELL QQQx4", "BUY SPYx5", "BUY SPYx1"]
    assert r["submitted"] == 3 and r["rejected"] == 0 and r["skipped"] == 0
    assert "RULE_GROSS_EXPOSURE_CAP" not in sh.all_rules()
    assert sh.sim.positions() == {"SPY": 6}
    sh.tick(seconds=30)
    assert sh.store.net_positions() == {"SPY": 6}


def test_cash_proxy_bil_bought_when_none_eligible(shadow):
    """全部低于 SMA200:退到现金替身 BIL(快照必须带上 BIL 才买得进)。"""
    sh = shadow()
    sh.market.slopes.update({s: -0.0005 for s in ("SPY", "QQQ")})
    r = sh.tick()
    assert r["plan"] == ["BUY BILx18", "BUY BILx3"] and r["submitted"] == 2
    assert sh.sim.positions() == {"BIL": 21}
    assert sh.result()["target_weights"] == {"BIL": 1.0}


def test_signal_uses_t_minus_1(shadow):
    """当天未收盘日线被改成足以翻转排名的值,选股结果不变(信号只用 T-1)。"""
    sh = shadow()
    sh.market.today_close["SPY"] = 3000.0
    r = sh.tick()
    assert sh.result()["selected"] == ["QQQ"] and r["plan"] == ["BUY QQQx4"]


def test_data_gap_no_marker_then_retry(shadow):
    """R1:日线抓取失败不落标记、不消耗 FORCE;间隔到期重试成功,当天照常评估。"""
    sh = shadow(start=WED_EXEC)
    force = sh.runtime / "FORCE_EVAL.txt"
    force.parent.mkdir(parents=True, exist_ok=True)
    force.write_text("go")
    marker = sh.runtime / "last_s1_eval.txt"
    sh.market.fail_daily = True
    r1 = sh.tick()
    assert "data_error" in r1 and r1["evaluated"] is False
    assert not marker.exists() and force.exists()
    sh.market.fail_daily = False
    r2 = sh.tick(seconds=60)                              # 未到 120 秒:不重试
    assert "data_error" in r2 and not marker.exists()
    r3 = sh.tick(seconds=61)
    assert r3["evaluated"] is True and r3.get("forced_eval") is True
    assert marker.read_text() == "2026-07-22" and not force.exists()
    assert r3["submitted"] == 1


def test_stale_quote_retries_then_evaluates_when_fresh(shadow):
    """快照行情 6 秒:窗内不落标记、按间隔重试(否则整周作废);行情恢复后照常评估。"""
    sh = shadow()
    sh.market.snapshot_lag = sh.market.quote_lag = 6.0
    r = sh.tick()
    assert r["evaluated"] is False and "行情过旧" in r["data_error"]
    assert not (sh.runtime / "last_s1_eval.txt").exists()
    sh.market.snapshot_lag = sh.market.quote_lag = 1.0
    r = sh.tick(seconds=121)
    assert r["evaluated"] is True and r["submitted"] == 1


def test_stale_quote_last_chance_rejected_by_risk(shadow):
    """窗口最后一次机会(周二 10:58:30 ET)行情仍过旧:才落标记,由风控拒并留下拦截原因。"""
    sh = shadow(start=datetime(2026, 7, 21, 14, 58, 30, tzinfo=UTC))
    sh.market.snapshot_lag = sh.market.quote_lag = 6.0
    r = sh.tick()
    assert r["evaluated"] is True and r["submitted"] == 0 and r["rejected"] == 1
    assert "RULE_MARKET_DATA_STALE" in sh.result()["reject_rules"]
    sh.tick(seconds=30)
    assert sh.executions() == []


def test_stale_quote_no_fill_marks_blocked(shadow):
    """快照新鲜但模拟券商下单时新取的行情已 6 秒:不成交,订单 SUBMIT_FAILED 且留有原因。"""
    sh = shadow()
    sh.market.quote_lag = 6.0
    r = sh.tick()
    assert r["submitted"] == 0 and r["skipped"] == 1
    assert r["skip_reasons"] == ["QQQ:BrokerError:QUOTE_STALE"]
    order_id = sh.store.find_order_by_idempotency_key("S1-2026-07-21-QQQ-BUY-4")
    assert sh.store.get_state(order_id) is OrderState.SUBMIT_FAILED
    errs = [e for e in sh.store.list_events(order_id) if e["event_type"] == "GATEWAY_SUBMIT_ERROR"]
    assert "QUOTE_STALE" in errs[0]["payload"]["error"]
    res = sh.result()
    assert res["submitted"] == 0 and res["skip_reasons"] == ["QQQ:BrokerError:QUOTE_STALE"]
    sh.tick(seconds=30)
    assert sh.executions() == []


def test_forbidden_env_fails_closed(tmp_path, monkeypatch):
    runtime = tmp_path / "rt"
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'f.sqlite'}"))
    ks = KillSwitch(tmp_path / "KS")
    cases = [("ALPHA_EXPECTED_ACC_ID", "284008"), ("MOOMOO_UNLOCK_PASSWORD", "x"),
             ("ALPHA_CAPITAL_AUD", "3000"), ("LIVE_TRADING_ENABLED", "1")]
    for key, val in cases:
        _shadow_env(monkeypatch, runtime)
        monkeypatch.setenv(key, val)
        with pytest.raises(RuntimeError, match=key):
            build_shadow_cycle(factory=factory, kill_switch=ks)
    _shadow_env(monkeypatch, runtime)
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "LIVE_AUTHORIZATION.json").write_text("{}")
    with pytest.raises(RuntimeError, match="LIVE_AUTHORIZATION"):
        build_shadow_cycle(factory=factory, kill_switch=ks)
    assert not (runtime / "LIVE_START_CAPITAL.json").exists(), "拒绝启动前不得冻结本金"


def test_wiring_shadow_has_no_broker():
    from backend.app.wiring import MODE_WIRING, blocked_status, resolve

    shadow = MODE_WIRING[SystemMode.SHADOW]
    assert "funds" not in shadow
    assert not any(t in v.lower() for v in shadow.values() for t in ("moomoo", "opend"))
    for m in (SystemMode.DISABLED, SystemMode.HALTED):
        assert m not in MODE_WIRING
        assert resolve(m, "cycle") is None and blocked_status(m) == "BLOCKED_ON_MODE"
    assert resolve(SystemMode.SHADOW, "funds") is None
    assert blocked_status(SystemMode.SHADOW) == "BLOCKED_ON_FEED"
    assert blocked_status(SystemMode.PAPER) == "BLOCKED_ON_OPEND"


# ---------- 子进程:import 拦截器钉死"影子链不碰券商 SDK" ----------

_BLOCKER = '''
import importlib.abc, sys
class _Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "moomoo" or name.startswith("backend.app.adapters.brokers.moomoo"):
            raise ImportError("blocked: " + name)
        return None
sys.meta_path.insert(0, _Block())
def _assert_clean():
    bad = [m for m in sys.modules
           if m.split(".")[0] == "moomoo" or m.startswith("backend.app.adapters.brokers.moomoo")]
    assert not bad, bad
'''


def _run_isolated(tmp_path, body, extra_env):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("ALPHA_", "MOOMOO_", "OPEND_")) and k != "LIVE_TRADING_ENABLED"}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT),
               ALPHA_DATABASE_URL=f"sqlite:///{tmp_path / 'iso.sqlite'}",
               ALPHA_KILL_SWITCH_PATH=str(tmp_path / "KILL_SWITCH"),
               ALPHA_RUNTIME_DIR=str(tmp_path / "rt"), **extra_env)
    proc = subprocess.run([sys.executable, "-c", _BLOCKER + body], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.strip().endswith("OK")


def test_shadow_never_imports_moomoo_subprocess(tmp_path):
    body = f'''
sys.path.insert(0, "tests")
from datetime import datetime, timezone
from conftest import Clock, FakeMarket
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.live_cycle import build_live_cycle
clock = Clock(datetime(2026, 7, 21, 14, 15, tzinfo=timezone.utc))
factory = create_session_factory(init_engine())
cycle = build_live_cycle(factory=factory, kill_switch=KillSwitch({str(tmp_path / "KS")!r}),
                         quotes=FakeMarket(clock), now_fn=clock)
s = cycle()
assert s["mode"] == "SHADOW" and s["submitted"] == 1, s
_assert_clean()
print("OK")
'''
    _run_isolated(tmp_path, body, {"ALPHA_MODE": "SHADOW"})


def test_missing_mode_blocks_never_paper(tmp_path):
    """不设 ALPHA_MODE:worker 首拍 BLOCKED_ON_MODE,且从未 import 券商 SDK(没有缺省连 PAPER)。"""
    body = '''
from backend.app.workers.main_trading import build_worker
s = build_worker()._run_cycle()
assert s["status"] == "BLOCKED_ON_MODE", s
assert "DISABLED" in s["note"], s
_assert_clean()
print("OK")
'''
    _run_isolated(tmp_path, body, {})


# ---------- 复审修复:租约/取数预算/休市/余量/账本模式戳 ----------

def _slow_fetch(sh, *, snapshot_s=0.0, bars_s=0.0):
    """让假行情的取数变慢:每次快照/日线调用把注入时钟推进指定秒数,并记录调用次数。"""
    m = sh.market
    calls = {"snapshot": 0, "bars": 0}
    orig_snap, orig_bars = m.get_snapshot, m.get_daily_bars

    def snap(symbols):
        calls["snapshot"] += 1
        sh.clock.advance(seconds=snapshot_s)
        return orig_snap(symbols)

    def bars(*a):
        calls["bars"] += 1
        sh.clock.advance(seconds=bars_s)
        return orig_bars(*a)

    m.get_snapshot, m.get_daily_bars = snap, bars
    return calls


def test_slow_fetch_does_not_lose_lease(shadow):
    """取数共 33 秒(超过租约 TTL 30 秒):提交前续约,单子照常提交,当周不作废。"""
    sh = shadow()
    _slow_fetch(sh, snapshot_s=18.0, bars_s=3.0)
    r = sh.tick()
    assert r["evaluated"] is True and r["submitted"] == 1 and r["skipped"] == 0


def test_fetch_over_budget_is_data_gap_not_marker(shadow):
    """取数总预算 45 秒:超了按数据不齐处理(不落标记、稍后重试),不拖到守护判失联。"""
    sh = shadow()
    _slow_fetch(sh, bars_s=20.0)
    r = sh.tick()
    assert r["evaluated"] is False and "取数超过总预算" in r["data_error"]
    assert not (sh.runtime / "last_s1_eval.txt").exists()


def test_market_closed_tuesday_defers_without_marker_or_alarm(shadow):
    """休市的周二(2028-07-04):行情停在前一交易日 -> 不落标记、不算漏评估,顺延到周三补评估。"""
    sh = shadow(start=datetime(2028, 7, 4, 14, 15, tzinfo=UTC))
    sh.market.snapshot_lag = sh.market.quote_lag = 18 * 3600.0
    calls = _slow_fetch(sh)
    r = sh.tick()
    assert r["market_closed"] is True and r["deferred_to"] == "2028-07-05" and not r["evaluated"]
    assert not (sh.runtime / "last_s1_eval.txt").exists()
    assert (sh.runtime / "makeup_eval.txt").read_text() == "2028-07-05"
    res = sh.result()
    assert res["market_closed"] is True and res["plan"] == [] and res["date"] == "2028-07-04"
    n = calls["snapshot"]
    r2 = sh.tick(seconds=30)
    assert r2["market_closed"] is True and calls["snapshot"] == n       # 当天不再重复取数
    from backend.app.control_page.dashboard_data import last_eval_summary
    assert "休市" in last_eval_summary(sh.runtime, sh.factory)["text"]
    from backend.app.health import evaluate_health
    from backend.app.workers.heartbeat import HeartbeatStore
    items = evaluate_health(session_factory=sh.factory, heartbeats=HeartbeatStore(sh.factory),
                            kill_switch=None, now=datetime(2028, 7, 4, 15, 30, tzinfo=UTC),
                            runtime_dir=sh.runtime)
    assert next(i for i in items if i.key.startswith("eval_missed:")).bad is False


def test_stale_makeup_marker_is_cleared(shadow):
    """日期早于今天的旧补评估标记被清掉,不会一直留着挡住新的补评估。"""
    sh = shadow()
    (sh.runtime / "makeup_eval.txt").write_text("2026-07-14")
    r = sh.tick()
    assert r["evaluated"] is True and not (sh.runtime / "makeup_eval.txt").exists()


@pytest.mark.parametrize("price,expect_qty", [(650.0, 2), (97.4, 19)])
def test_plan_leaves_headroom_so_last_slice_is_not_rejected(shadow, price, expect_qty):
    """整股市值贴着本金:取整前扣留限价上浮+滑点+佣金余量,最后一笔不再被总敞口上限拒掉。"""
    sh = shadow()
    sh.market.prices["QQQ"] = price
    r = sh.tick()
    assert r["rejected"] == 0 and r["skipped"] == 0 and r["submitted"] == len(r["plan"])
    total = sum(int(item.rsplit("x", 1)[1]) for item in r["plan"])
    assert total == expect_qty
    sh.tick(seconds=30)
    assert sh.store.net_positions() == {"QQQ": expect_qty}


def _plant_orders(factory, *, sim=False, broker=False):
    from backend.app.domain.models import BrokerOrder, OrderIntent, SimOrder
    with factory() as s, s.begin():
        if broker:
            i = OrderIntent(idempotency_key="X-1", symbol="QQQ", side="BUY", quantity=1,
                            currency="USD", strategy_source="t")
            s.add(i)
            s.flush()
            s.add(BrokerOrder(intent_id=i.intent_id, state="FILLED"))
        if sim:
            s.add(SimOrder(sim_order_id="SIM-x", remark="X-1", symbol="QQQ", side="BUY",
                           quantity=1, status="FILLED_ALL"))


def test_ledger_stamp_forces_fresh_ledger_on_mode_change(shadow, tmp_path):
    """影子盘账本与运行目录带模式戳:改成 PAPER/MICRO_LIVE 沿用旧账一律拒绝装配;反向同理。"""
    from backend.app.store.ledger_stamp import claim_ledger
    sh = shadow()
    sh.tick()
    sh.tick(seconds=30)
    assert sh.store.net_positions() == {"QQQ": 4}
    for m in (SystemMode.PAPER, SystemMode.MICRO_LIVE):
        with pytest.raises(RuntimeError, match="SHADOW"):
            claim_ledger(sh.factory, m, sh.runtime)                     # 旧库 + 旧目录
        fresh_db = create_session_factory(init_engine(f"sqlite:///{tmp_path / f'f_{m.value}.sqlite'}"))
        with pytest.raises(RuntimeError, match="运行目录"):
            claim_ledger(fresh_db, m, sh.runtime)                       # 新库 + 旧目录
    claim_ledger(sh.factory, SystemMode.SHADOW, sh.runtime)             # 本模式重复认领没问题

    # 全新库 + 全新目录:券商模式可以认领,认领后影子盘反过来被拒
    db2 = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'live.sqlite'}"))
    claim_ledger(db2, SystemMode.MICRO_LIVE, tmp_path / "rt_live")
    with pytest.raises(RuntimeError, match="MICRO_LIVE"):
        claim_ledger(db2, SystemMode.SHADOW, tmp_path / "rt_live")
    with pytest.raises(RuntimeError, match="MICRO_LIVE"):
        build_shadow_cycle(factory=db2, kill_switch=KillSwitch(tmp_path / "KS2"),
                           quotes=sh.market)


def test_ledger_stamp_judges_unstamped_legacy_by_content(tmp_path):
    """没有戳的旧账本按内容判归属:含模拟订单只属影子盘;含券商订单只属券商类;空的谁都能认领。"""
    from backend.app.store.ledger_stamp import claim_ledger

    def fresh(name):
        return create_session_factory(init_engine(f"sqlite:///{tmp_path / name}.sqlite"))

    a = fresh("a")
    _plant_orders(a, sim=True, broker=True)
    for m in (SystemMode.PAPER, SystemMode.MICRO_LIVE):
        with pytest.raises(RuntimeError, match="影子盘"):
            claim_ledger(a, m, tmp_path / "rt_a")
    claim_ledger(a, SystemMode.SHADOW, tmp_path / "rt_a")

    b = fresh("b")
    _plant_orders(b, broker=True)
    with pytest.raises(RuntimeError, match="券商类"):
        claim_ledger(b, SystemMode.SHADOW, tmp_path / "rt_b")
    claim_ledger(b, SystemMode.PAPER, tmp_path / "rt_b")

    rt = tmp_path / "rt_c"
    rt.mkdir()
    (rt / "LIVE_START_CAPITAL.json").write_text("{}")                   # 无戳旧运行目录 + 空库
    with pytest.raises(RuntimeError, match="券商类"):
        claim_ledger(fresh("c"), SystemMode.SHADOW, rt)


def test_shadow_full_surface_never_imports_moomoo_subprocess(tmp_path):
    """影子盘整个外围面(真实装配的 Yahoo 行情源、控制页、净值快照、盘前自检、体检)也不碰券商 SDK。
    子进程内不联网:行情源的 HTTP 打桩,评估拍落在窗外不取数。"""
    body = '''
from datetime import datetime, timezone
from backend.app.backtest import data_sources
def _no_net(*a, **k):
    raise ConnectionError("子进程测试禁止联网")
data_sources._http_json = _no_net
from backend.app.workers.main_trading import build_worker
s = build_worker()._run_cycle()                 # 真实 build_live_cycle + 真实 YahooQuoteSource
assert s["mode"] == "SHADOW", s
from backend.app.marketdata.yahoo_live import YahooQuoteSource
assert YahooQuoteSource().get_snapshot(["SPY"]) == {}       # 取不到就省略,不编造
from backend.app.control_page.main import build_app
build_app()
class Q:
    def snapshots(self, syms):
        return {s: {"price": 400.0, "at": "x"} for s in syms}
    def get_quote(self, sym):
        return None
import scripts.snapshot_equity as se
assert se.main(quotes=Q(), fx=(0.66, False)) == 0
import scripts.preflight_check as pf
pf.main(quotes=Q())
import scripts.alpha_doctor as doc
doc.main(["--check-env"])
doc.collect(systemctl=lambda unit: "active")
_assert_clean()
print("OK")
'''
    _run_isolated(tmp_path, body, {"ALPHA_MODE": "SHADOW"})
