"""复审修复的回归:自有账成本、要求线、敞口口径、看盘页模式文案、缺省模式、取数预算、
守护/健康/发件箱的边界。全部离线,假件与注入时钟。"""

import dataclasses
import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from backend.app import truth
from backend.app.adapters.brokers.base import SystemMode
from backend.app.control_page.dashboard_data import (
    _next_decision, build_overview, build_strategy_view,
)
from backend.app.control_page.render import render_dashboard_html, render_strategy_html
from backend.app.domain.models import BrokerOrder, Execution, OrderIntent, OutboxEvent
from backend.app.health import evaluate_health
from backend.app.notify.outbox import Outbox
from backend.app.store.db import create_session_factory, init_engine
from backend.app.store.orders import fold_own_executions
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.supervisor import Supervisor

UTC = timezone.utc


# ---------- 自有账成本:加权平均成本结转 ----------

def test_fold_round_trip_resets_cost_after_flat():
    """清仓后再买回同一标的:成本按新买入价算,不带着旧的卖出额。"""
    book = fold_own_executions([("QQQ", "BUY", 4, D("400.20"), D("0.99")),
                                ("QQQ", "SELL", 4, D("450"), D("1.06")),
                                ("QQQ", "BUY", 4, D("420"), D("0.99"))])
    assert book.net == {"QQQ": 4}
    assert book.cost["QQQ"] / 4 == pytest.approx(420.0)


def test_fold_partial_reduce_keeps_average_cost():
    book = fold_own_executions([("QQQ", "BUY", 4, D("400"), D("0")),
                                ("QQQ", "SELL", 2, D("500"), D("0"))])
    assert book.net == {"QQQ": 2} and book.cost["QQQ"] / 2 == pytest.approx(400.0)
    assert book.cash_flow_usd == pytest.approx(-1600 + 1000)


def test_fold_adds_average_and_full_close_drops_symbol():
    book = fold_own_executions([("SPY", "BUY", 2, D("300"), D("0")),
                                ("SPY", "BUY", 2, D("320"), D("0")),
                                ("QQQ", "BUY", 1, D("400"), D("0")),
                                ("QQQ", "SELL", 1, D("410"), D("0"))])
    assert book.net == {"SPY": 4} and book.cost == {"SPY": pytest.approx(1240.0)}


# ---------- 要求线 / 净值公式 / 契约汇率折算 ----------

def test_required_line_anchored_at_ledger_freeze_month():
    anchor = datetime(2026, 9, 30, 1, 0, tzinfo=UTC)
    now = datetime(2026, 9, 30, 6, 0, tzinfo=UTC)
    fresh = truth.required_line(3000.0, anchor=anchor, now=now, traded=False)
    assert fresh.months_elapsed == 0 and fresh.month_target_aud == 3000.0
    later = truth.required_line(3000.0, anchor=anchor, now=datetime(2026, 12, 15, tzinfo=UTC),
                                traded=True)
    assert later.months_elapsed == 3
    assert later.month_target_aud == pytest.approx(3000 * 1.01245 ** 3)
    assert later.year_target_aud == pytest.approx(3000 * 1.01245 ** 3)      # 起算 9 月,年末还是 12 月
    idle = truth.required_line(3000.0, anchor=anchor, now=datetime(2026, 12, 15, tzinfo=UTC),
                               traded=False)
    assert idle.month_target_aud == 3000.0                                  # 没出手过就没有要求线盈亏
    none = truth.required_line(3000.0, anchor=None, now=now, traded=True)
    assert none.months_elapsed == 0


def test_shared_equity_and_fx_helpers():
    assert truth.equity_aud(capital_aud=3000.0, trading_pnl_usd=-13.0, fx_aud_usd=0.65) == \
        pytest.approx(2980.0)
    assert truth.fx_usd_aud() == D("1.538462") and truth.fx_usd_aud(0.5) == D("2.0")


def _overview(shadow_env, now, **kw):
    factory = create_session_factory(init_engine())
    hb = HeartbeatStore(factory, now_fn=lambda: now)
    return factory, build_overview(session_factory=factory, heartbeats=hb,
                                   kill_switch=KillSwitch(shadow_env / "KS"), now=now, **kw)


def test_dashboard_fresh_shadow_ledger_has_no_deficit_or_exam_card(shadow_env):
    """全新影子账本、还没有任何交易:不显示相对要求线的亏损,不渲染纸面三日考核卡。"""
    (shadow_env / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": "2026-09-30T01:00:00+00:00"}))
    _, d = _overview(shadow_env, datetime(2026, 10, 1, 3, 0, tzinfo=UTC))
    assert d["hero"]["traded_yet"] is False
    assert d["hero"]["total_pnl_aud"] == 0.0 and d["hero"]["month_target_aud"] == 3000.0
    assert d["exam"] is None and d["live_stage"]["card_title"] == "影子盘运行阶段"
    html = render_dashboard_html(d)
    assert 'class="card span2 lossbg"' not in html and "尚未进行任何交易" in html
    assert "<h2>三日模拟盘考核</h2>" not in html and "合格交易日" not in html and "保持 Paper" not in html
    assert "考核不适用" in html or "本模式不适用" in html
    # owner 验收口径:影子盘看盘页任何位置都不许出现"实盘/券商模拟账户"字样(免得被误读成动真钱)
    assert "实盘" not in html and "券商模拟账户" not in html


def test_strategy_page_uses_mode_wording(shadow_env):
    view = build_strategy_view()
    html = render_strategy_html(view)
    assert "当前影子盘策略" in html and "当前实盘策略" not in html
    assert "现役实盘" not in html and "现役影子盘" in html
    assert "晋级实盘的四道门" not in html and "不会自动升级" in html


def test_shadow_label_discloses_missing_dividends():
    assert "未计分红" in truth.mode_explainer(SystemMode.SHADOW)


def _plant_execs(factory, rows):
    with factory() as s, s.begin():
        for i, (sym, side, qty, px) in enumerate(rows):
            intent = OrderIntent(idempotency_key=f"T-{i}", symbol=sym, side=side, quantity=qty,
                                 currency="USD", strategy_source="t")
            s.add(intent)
            s.flush()
            order = BrokerOrder(intent_id=intent.intent_id, state="FILLED")
            s.add(order)
            s.flush()
            s.add(Execution(order_id=order.order_id, quantity=qty, price=D(str(px)),
                            fees=D("0"), executed_at=datetime(2026, 10, 1, 14, i, tzinfo=UTC)))


class _Fx:
    def rate(self):
        return 0.66, datetime(2026, 10, 1, 15, tzinfo=UTC)


class _Quotes:
    def snapshots(self, symbols):
        return {s: {"price": 300.0, "at": "x"} for s in symbols}

    def daily_closes(self, *a):
        return []


def test_exposure_pct_uses_contract_fx_like_risk(shadow_env):
    """持 6 股 SPY 市值 1800 美元:敞口按契约汇率 0.65 折算 = 92.3%(风控同口径),不是实时汇率的 90.9%。"""
    factory = create_session_factory(init_engine())
    _plant_execs(factory, [("SPY", "BUY", 6, 300)])
    d = build_overview(session_factory=factory, heartbeats=HeartbeatStore(factory),
                       kill_switch=KillSwitch(shadow_env / "KS"), quotes=_Quotes(),
                       fx_source=_Fx(), now=datetime(2026, 10, 1, 16, tzinfo=UTC))
    assert d["hero"]["exposure_pct"] == 92.3


def test_build_overview_defaults_come_from_truth(shadow_env, monkeypatch):
    monkeypatch.setenv("ALPHA_CAPITAL_AUD", "5000")
    _, d = _overview(shadow_env, datetime(2026, 10, 1, 3, 0, tzinfo=UTC))
    assert d["hero"]["capital_aud"] == 5000.0 and d["hero"]["equity_aud"] == 5000.0


# ---------- 缺省模式:没有缺省 PAPER ----------

def test_no_default_paper_in_cycle_deps():
    from backend.app.workers.live_cycle import LiveCycleDeps, resolve_mode

    field = next(f for f in dataclasses.fields(LiveCycleDeps) if f.name == "mode")
    assert field.default is dataclasses.MISSING
    for empty in ("", None):
        with pytest.raises(RuntimeError, match="缺失"):
            resolve_mode(empty, "SIMULATE", live_flag="0", auth_ok=False, auth_reasons=[])


# ---------- 取数预算 < 守护心跳陈旧阈值 ----------

def test_yahoo_snapshot_budget_caps_worst_case():
    from backend.app.marketdata.yahoo_live import YahooQuoteSource

    t = {"now": 0.0}

    def hang(url, *, timeout, retries):          # 每次尝试耗满超时,并按 _http_json 的退避睡 1.5*(n+1)
        for n in range(retries):
            t["now"] += timeout + 1.5 * (n + 1)
        raise ConnectionError("hang")

    src = YahooQuoteSource(fetch_json=hang, clock=lambda: t["now"])
    assert src.get_snapshot(["SPY", "QQQ", "EFA", "GLD", "IEF", "BIL"]) == {}
    assert t["now"] == pytest.approx(2 * 20.5)               # 预算 40 秒:只开了 2 只的请求,不是 6 只的 123 秒


def test_worst_case_cycle_stays_under_heartbeat_stale_threshold():
    from backend.app.marketdata import yahoo_live as y
    from backend.app.workers.live_cycle import FETCH_BUDGET_SECONDS
    from backend.app.workers.supervisor import DEFAULT_STALE_SECONDS

    one_quote = y.SNAPSHOT_BUDGET_SECONDS + (8 * 2 + 1.5 + 3.0)        # 预算 + 最后一只在途请求
    one_bars = FETCH_BUDGET_SECONDS + (y.DAILY_TIMEOUT_SECONDS * y.DAILY_RETRIES + 1.5)
    worst_fetch = max(one_quote, one_bars)
    assert worst_fetch + 30.0 + 15.0 < DEFAULT_STALE_SECONDS        # + 节拍间隔 + 评估其余耗时余量


# ---------- 守护 / 健康 ----------

TUE_1105_ET = datetime(2026, 9, 29, 15, 5, tzinfo=UTC)


def _sup(tmp_path, clock, runtime, name="s", **kw):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / f'{name}.sqlite'}"))
    hb = HeartbeatStore(factory, now_fn=lambda: clock["t"])
    ob = Outbox(factory, now_fn=lambda: clock["t"])
    sup = Supervisor(heartbeats=hb, outbox=ob, kill_switch=KillSwitch(tmp_path / f"KS_{name}"),
                     expected_workers=("trading-worker",), now_fn=lambda: clock["t"],
                     runtime_dir=runtime, **kw)
    return sup, hb, ob, factory


def test_stale_makeup_marker_does_not_block_new_arming(shadow_env, tmp_path):
    (shadow_env / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": "2026-09-01T00:00:00+00:00"}))
    (shadow_env / "makeup_eval.txt").write_text("2026-09-22")
    clock = {"t": TUE_1105_ET}
    sup, hb, _, _ = _sup(tmp_path, clock, shadow_env)
    hb.beat("trading-worker", status="RUNNING", detail="{'mode': 'SHADOW'}")
    for _ in range(3):
        sup.check_once()
        clock["t"] += timedelta(seconds=30)
        hb.beat("trading-worker", status="RUNNING", detail="{'mode': 'SHADOW'}")
    assert (shadow_env / "makeup_eval.txt").read_text() == "2026-09-29"


def test_crash_loop_heartbeat_error_alerts(shadow_env, tmp_path):
    """交易进程反复崩溃(心跳一直是 ERROR 但很新鲜):不能静默,超过阈值发告警。"""
    (shadow_env / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": "2026-09-01T00:00:00+00:00"}))
    clock = {"t": datetime(2026, 9, 30, 0, 0, tzinfo=UTC)}      # 周三(悉尼),非评估窗
    sup, hb, ob, _ = _sup(tmp_path, clock, shadow_env)
    for _ in range(40):                                          # 20 分钟
        hb.beat("trading-worker", status="ERROR", detail="OperationalError: database is locked")
        sup.check_once()
        clock["t"] += timedelta(seconds=30)
    assert "crash_loop:trading-worker" in [a["key"] for a in sup._alerts.open_alerts()]
    assert ob.pending_count() >= 1


def test_unfrozen_first_deploy_raises_no_false_alarms(shadow_env, tmp_path):
    """首次部署、本金还没冻结:漏评估与净值停更都不误报;冻结后无净值点超阈值才红。"""
    clock = {"t": datetime(2026, 9, 30, 15, 0, tzinfo=UTC)}      # 周三 11:00 ET
    _, hb, ob, factory = _sup(tmp_path, clock, shadow_env)
    items = {i.key: i for i in evaluate_health(
        session_factory=factory, heartbeats=hb, kill_switch=None, now=clock["t"],
        runtime_dir=shadow_env)}
    assert not items["eval_missed:2026-09-29"].bad and not items["equity_stale"].bad
    (shadow_env / "LIVE_START_CAPITAL.json").write_text(json.dumps(
        {"start_capital_usd": 1950.0, "frozen_at": (clock["t"] - timedelta(hours=2)).isoformat()}))
    items = {i.key: i for i in evaluate_health(
        session_factory=factory, heartbeats=hb, kill_switch=None, now=clock["t"],
        runtime_dir=shadow_env)}
    assert items["equity_stale"].bad


# ---------- 看盘页「下一次评估」 ----------

def test_next_decision_follows_marker_and_makeup_date(tmp_path):
    rt = tmp_path
    tue = lambda h, m: datetime(2026, 9, 29, h, m, tzinfo=timezone.utc) + timedelta(hours=4)  # ET->UTC(EDT)
    assert _next_decision(tue(9, 45), rt)["at_iso"].startswith("2026-09-29T10:00")   # 窗口前
    (rt / "last_s1_eval.txt").write_text("2026-09-29")                                # 本周已评估
    assert _next_decision(tue(10, 30), rt)["at_iso"].startswith("2026-10-06T10:00")
    (rt / "last_s1_eval.txt").unlink()
    (rt / "makeup_eval.txt").write_text("2026-09-29")                                 # 11:05 武装补评估
    nd = _next_decision(tue(11, 5), rt)
    assert nd["at_iso"].startswith("2026-09-29T10:30") and "补评估" in nd["kind"]
    (rt / "makeup_eval.txt").write_text("2026-09-22")                                 # 旧标记忽略
    wed = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
    nd = _next_decision(wed, rt)
    assert "补评估" not in nd["kind"] and nd["at_iso"].startswith("2026-10-06T10:00")


# ---------- 冻结本金:原子写 ----------

def test_freeze_start_capital_is_atomic(shadow_env, monkeypatch):
    import os

    from backend.app.workers.live_cycle import _freeze_start_capital

    def boom(*a, **k):
        raise OSError("crash between write and rename")

    with monkeypatch.context() as m:
        m.setattr(os, "replace", boom)
        _freeze_start_capital(1950.0)
    assert not (shadow_env / "LIVE_START_CAPITAL.json").exists()        # 不会留下截断文件
    _freeze_start_capital(1950.0)
    assert json.loads((shadow_env / "LIVE_START_CAPITAL.json").read_text())["start_capital_usd"] == 1950.0


# ---------- 发件箱 ----------

class _Ok:
    def __init__(self, on_send=None):
        self.sent, self.on_send = [], on_send

    def send(self, *, subject, body):
        if self.on_send:
            self.on_send()
        self.sent.append(subject)


def _outbox(tmp_path, clock):
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'ob.sqlite'}"))
    return factory, Outbox(factory, now_fn=lambda: clock["t"])


def test_send_does_not_hold_write_lock(tmp_path):
    """发信期间别的连接(交易进程的心跳)能立刻写库,不会等 busy_timeout 后抛错。"""
    clock = {"t": datetime(2026, 9, 30, 0, 0, tzinfo=UTC)}
    factory, ob = _outbox(tmp_path, clock)
    hb = HeartbeatStore(factory, now_fn=lambda: clock["t"])
    for i in range(8):                                   # 制造折叠汇总路径(每小时上限 6)
        ob.enqueue(event_type="ALERT_RAISED", payload={"title": f"t{i % 2}", "detail": "d"})
    ob.process_once(_Ok())
    clock["t"] += timedelta(minutes=61)
    ob.enqueue(event_type="ALERT_RAISED", payload={"title": "new", "detail": "d"})
    started = time.monotonic()
    sender = _Ok(on_send=lambda: hb.beat("trading-worker"))
    report = ob.process_once(sender)
    assert report.delivered >= 1 and time.monotonic() - started < 3.0
    assert any("被合并" in s for s in sender.sent)


class _Down:
    def send(self, *, subject, body):
        raise ConnectionRefusedError("smtp bridge down")


def test_failed_events_are_revived_when_relay_recovers(tmp_path):
    """中继停摆超过退避总长(约 13 分钟)导致 FAILED 的告警,恢复后重新排队送出,不永久丢。"""
    clock = {"t": datetime(2026, 9, 30, 0, 0, tzinfo=UTC)}
    factory, ob = _outbox(tmp_path, clock)
    lost_id = ob.enqueue(event_type="ALERT_RAISED", payload={"title": "关键告警", "detail": "d"})
    for _ in range(8):
        ob.process_once(_Down())
        clock["t"] += timedelta(minutes=12)
    with factory() as s:
        assert s.get(OutboxEvent, lost_id).delivery_status == "FAILED"
    ob.enqueue(event_type="ALERT_RECOVERED", payload={"title": "别的", "since": "", "repeat_count": 0})
    ok = _Ok()
    ob.process_once(ok)                                   # 中继恢复:别的邮件送出,同时把 FAILED 重新排队
    ob.process_once(ok)
    with factory() as s:
        assert s.get(OutboxEvent, lost_id).delivery_status == "DELIVERED"
    assert any("关键告警" in x for x in ok.sent)
    assert s is not None


def test_process_once_returns_report_counts(tmp_path):
    clock = {"t": datetime(2026, 9, 30, 0, 0, tzinfo=UTC)}
    _, ob = _outbox(tmp_path, clock)
    ob.enqueue(event_type="DAILY_DIGEST", payload={"text": "x"})
    ok = _Ok()
    r = ob.process_once(ok)
    assert (r.delivered, r.retried, r.failed_permanently) == (1, 0, 0) and len(ok.sent) == 1
    r = ob.process_once(_Down())
    assert r.delivered == 0
    with ob.session_factory() as s:
        assert s.scalar(select(OutboxEvent.delivery_status)) == "DELIVERED"
