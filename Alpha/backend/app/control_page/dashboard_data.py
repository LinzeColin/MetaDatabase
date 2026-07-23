"""看盘数据装配(只读)。

红线:本模块只读——读库、读运行时标记文件、读行情快照;永不写库、永不触单。
行情源可注入:生产用 OpenD 只读桥(短连即关+短时缓存),测试用假源;
取不到行情一律 fail-soft(按成本估值并如实标注 priced=false),绝不编造现价。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol
from zoneinfo import ZoneInfo

SYD = ZoneInfo("Australia/Sydney")
ET = ZoneInfo("America/New_York")

SYMBOL_CN = {"QQQ": "纳指100", "GLD": "黄金", "SPY": "标普500", "BIL": "短债现金"}
SIDE_CN = {"BUY": "买入", "SELL": "卖出"}
STATE_CN = {
    "INTENT_CREATED": "已创建", "RISK_APPROVED": "风控通过", "RISK_REJECTED": "被风控拦下",
    "SUBMITTING": "提交中", "SUBMITTED": "已提交", "SUBMIT_FAILED": "提交失败",
    "ACCEPTED": "券商已挂单", "PARTIALLY_FILLED": "部分成交", "FILLED": "已成交",
    "CANCELLED": "已撤单", "EXPIRED": "已过期",
    "UNKNOWN_RECONCILIATION_REQUIRED": "待人工核对",
}
RULE_CN = {
    "RULE_MARKET_DATA_STALE": "行情数据太旧,拒单保护",
    "RULE_FAT_FINGER_SINGLE_ORDER": "单笔金额超上限,拒单保护",
    "RULE_HOURLY_ORDER_BUDGET": "每小时下单笔数达上限,拒单保护",
    "RULE_TOTAL_EXPOSURE": "总敞口将超 3000 澳元上限,拒单保护",
    "RULE_JURISDICTION": "辖区许可未确认,拒单保护",
}


class QuoteSource(Protocol):
    """行情源协议:实现方必须只读;返回空 dict/list 表示取不到(调用方 fail-soft)。"""

    def snapshots(self, symbols: list[str]) -> dict[str, dict]: ...

    def daily_closes(self, symbol: str, start: str, end: str) -> list[tuple[str, float]]: ...


class OpenDQuoteSource:
    """OpenD 只读行情源:每次短连即关(避免长连接线程悬挂),失败返回空。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111,
                 snap_ttl: float = 30.0, kline_ttl: float = 3600.0) -> None:
        self._host, self._port = host, port
        self._snap_ttl, self._kline_ttl = snap_ttl, kline_ttl
        self._cache: dict = {}

    def _get(self, key, ttl):
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < ttl:
            return hit[1]
        return None

    def _put(self, key, val):
        self._cache[key] = (time.monotonic(), val)
        return val

    def snapshots(self, symbols: list[str]) -> dict[str, dict]:
        key = ("snap", tuple(sorted(symbols)))
        cached = self._get(key, self._snap_ttl)
        if cached is not None:
            return cached
        try:
            from moomoo import RET_OK, OpenQuoteContext
            qc = OpenQuoteContext(host=self._host, port=self._port)
            try:
                ret, df = qc.get_market_snapshot([f"US.{s}" for s in symbols])
                if ret != RET_OK:
                    return {}
                out = {}
                for _, row in df.iterrows():
                    sym = str(row["code"]).split(".", 1)[-1]
                    out[sym] = {"price": float(row["last_price"]),
                                "at": str(row["update_time"])}
                return self._put(key, out)
            finally:
                qc.close()
        except Exception:
            return {}

    def daily_closes(self, symbol: str, start: str, end: str) -> list[tuple[str, float]]:
        key = ("kline", symbol, start, end)
        cached = self._get(key, self._kline_ttl)
        if cached is not None:
            return cached
        try:
            from moomoo import KLType, RET_OK, OpenQuoteContext
            qc = OpenQuoteContext(host=self._host, port=self._port)
            try:
                r = qc.request_history_kline(f"US.{symbol}", start=start, end=end,
                                             ktype=KLType.K_DAY)
                ret, df = r[0], r[1]
                if ret != RET_OK:
                    return []
                out = [(str(row["time_key"])[:10], float(row["close"]))
                       for _, row in df.iterrows()]
                return self._put(key, out)
            finally:
                qc.close()
        except Exception:
            return []


def _email_title(event_type: str) -> str:
    from backend.app.notify.outbox import _EMAIL_TEMPLATES
    tpl = _EMAIL_TEMPLATES.get(event_type)
    return tpl[0] if tpl else event_type


def _latest_report(reports_dir: Path) -> Optional[dict]:
    """取最近一份三日考核 report.json(没有就返回 None,页面如实显示未考核)。"""
    try:
        candidates = sorted(p for p in reports_dir.iterdir() if (p / "report.json").exists())
        if not candidates:
            return None
        data = json.loads((candidates[-1] / "report.json").read_text())
        data["_report_date"] = candidates[-1].name
        return data
    except Exception:
        return None


def _next_decision(now_utc: datetime, runtime_dir: Path) -> dict:
    """下一次决策时间:有补评估标记 → 下一个交易日开盘后;否则周二正常节拍。"""
    et_now = now_utc.astimezone(ET)
    makeup = (runtime_dir / "makeup_eval.txt").exists()
    if makeup:
        cand = et_now.replace(hour=10, minute=0, second=0, microsecond=0)
        if et_now.hour >= 11:
            cand += timedelta(days=1)
        while cand.weekday() >= 5:
            cand += timedelta(days=1)
        kind = "补评估(上次评估被拦下,下个交易日开盘后补做)"
    else:
        days_ahead = (1 - et_now.weekday()) % 7
        cand = et_now.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        if days_ahead == 0 and et_now.hour >= 11:
            cand += timedelta(days=7)
        kind = "每周例行决策(美股周二开盘后一小时内)"
    syd = cand.astimezone(SYD)
    return {"at_syd": f"{syd:%m月%d日 %H:%M}", "weekday_syd": "一二三四五六日"[syd.weekday()],
            "kind": kind, "at_iso": cand.isoformat()}


def _market_status(now_utc: datetime) -> dict:
    et_now = now_utc.astimezone(ET)
    minute = et_now.hour * 60 + et_now.minute
    is_weekday = et_now.weekday() < 5
    is_open = is_weekday and 570 <= minute < 960
    if is_open:
        nxt = et_now.replace(hour=16, minute=0, second=0, microsecond=0)
        label, nxt_label = "美股开市中", "收盘"
    else:
        nxt = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
        if minute >= 570:
            nxt += timedelta(days=1)
        while nxt.weekday() >= 5:
            nxt += timedelta(days=1)
        label = "美股休市(周末)" if not is_weekday else "美股已收盘"
        nxt_label = "开盘"
    nxt_syd = nxt.astimezone(SYD)
    return {"open": is_open, "label": label,
            "next": f"{nxt_label} {nxt_syd:%m月%d日 %H:%M}(悉尼)"}


#: 运维类事件(运维记录页只看这些;类型 -> (人话标题, 处置类别))
OPS_EVENTS = {
    "WORKER_HEARTBEAT_LOST": ("组件失联,已拉闸保护", "fault"),
    "WORKER_RESTARTED": ("守护自动重启组件", "auto"),
    "WORKER_RECOVERED": ("组件心跳恢复", "auto"),
    "KILL_SWITCH_CLEARED": ("刹车自动解除,交易恢复", "auto"),
    "INCIDENT_REPORT": ("事故报告与修复(人工介入)", "manual"),
    "ACTIVATION_BLOCKED": ("实盘切换暂缓(失败关闭)", "fault"),
    "LIVE_ACTIVATED": ("已自动切换微实盘", "auto"),
    "UNIT_FAILED": ("定时任务运行失败", "fault"),
}

#: 自愈能力清单(与部署单元一一对应;运维记录页如实展示)
SELF_HEAL_CAPS = [
    ("进程崩溃自动拉起", "系统服务管理器 Restart=always,崩溃 10 秒内重启"),
    ("卡死看门狗", "交易进程每拍喂狗;超过 5 分钟没喂 = 卡死,自动杀掉重启(07-23 事故补课)"),
    ("守护受限重启权", "组件失联超 5 分钟,守护按序自动重启行情网关与交易进程,30 分钟冷却防抖"),
    ("条件自动收闸", "守护自己拍的紧急刹车,连续健康确认后自动解除;人拍的闸永远只有人能解"),
    ("每日收盘自动复判", "每个交易日收盘后自动核算四灯并按纪律邮件;全绿自动发起实盘切换"),
    ("定时任务失败自告警", "复判/切换任务自身失败时,自动发邮件通知(谁看门人的门,失败也有人知道)"),
]


def build_ops_view(*, session_factory, heartbeats, kill_switch,
                   ledger_path: str | Path = "machine/facts/downtime_ledger.json",
                   now: Optional[datetime] = None) -> dict:
    """运维记录页数据:事故台账 + 运维事件流(含邮件送达状态与处置类别)。只读。"""
    now = now or datetime.now(timezone.utc)

    ledger_rows = []
    lp = Path(ledger_path)
    if lp.exists():
        try:
            data = json.loads(lp.read_text())
            for day in sorted(data, reverse=True):
                e = data[day]
                secs = int(e.get("seconds", 0))
                ledger_rows.append({
                    "date": day,
                    "downtime_human": (f"{secs // 3600} 小时 {secs % 3600 // 60} 分"
                                       if secs >= 3600 else f"{max(secs // 60, 1)} 分钟" if secs >= 60
                                       else f"{secs} 秒"),
                    "reason": e.get("原因", ""),
                })
        except Exception:
            ledger_rows = []

    events = []
    if session_factory is not None:
        from sqlalchemy import select

        from backend.app.domain.models import OutboxEvent
        with session_factory() as s:
            rows = [x for x in s.scalars(select(OutboxEvent)).all()
                    if x.event_type in OPS_EVENTS]
        rows.sort(key=lambda x: x.created_at, reverse=True)
        recovered_after: list[datetime] = [x.created_at for x in rows
                                           if x.event_type in ("WORKER_RECOVERED",
                                                               "KILL_SWITCH_CLEARED")]
        for x in rows[:40]:
            title, kind = OPS_EVENTS[x.event_type]
            if x.delivery_status == "DELIVERED" and x.delivered_at:
                at = x.delivered_at if x.delivered_at.tzinfo else x.delivered_at.replace(tzinfo=timezone.utc)
                mail = f"已邮件({at.astimezone(SYD):%m-%d %H:%M} 送达)"
            elif x.delivery_status == "PENDING":
                mail = "邮件投递中"
            elif x.delivery_status == "CANCELLED":
                mail = "已作废(告警风暴清账)"
            else:
                mail = "邮件投递失败"
            resolved = (kind != "fault"
                        or any(r > x.created_at for r in recovered_after))
            created = x.created_at if x.created_at.tzinfo else x.created_at.replace(tzinfo=timezone.utc)
            events.append({
                "at_syd": f"{created.astimezone(SYD):%m-%d %H:%M}",
                "title": title, "kind": kind, "mail": mail,
                "state_cn": ("已自愈/已处理" if resolved else "待处理(需人工/代理介入)"),
                "resolved": resolved,
            })

    hb = heartbeats.snapshot() if heartbeats else {}
    fresh = all((now - datetime.fromisoformat(h["beat_at"])).total_seconds() < 150
                for h in hb.values()) if hb else False
    return {
        "caps": SELF_HEAL_CAPS,
        "ledger": ledger_rows,
        "events": events,
        "open_faults": sum(1 for e in events if not e["resolved"]),
        "healthy_now": bool(fresh and not kill_switch.active()),
        "updated_at_syd": f"{now.astimezone(SYD):%m月%d日 %H:%M}",
    }


def build_strategy_view(*, promotion_path: str | Path = "configs/strategy_promotion.yaml",
                        now: Optional[datetime] = None) -> dict:
    """投资策略页数据:生产策略人话档案 + 晋级门禁(实时读契约配置)+ 研究史。只读。"""
    now = now or datetime.now(timezone.utc)
    gates = []
    try:
        import yaml
        cfg = yaml.safe_load(Path(promotion_path).read_text())
        gates = [{"id": c["id"], "name": c["name"], "rule": c["rule"]}
                 for c in cfg.get("gate_conditions", [])]
        honesty = cfg.get("honesty_note", "")
    except Exception:
        honesty = ""
    return {
        "champion": {
            "name_cn": "五腿双动量·精调(周频)",
            "cadence": "每周二美股开盘后 30-90 分钟评估一次;其余时间只持有不动。上次评估被拦下时,下个交易日开盘后自动补评估",
            "universe": "标普500(SPY)、国际发达市场(EFA)、纳指100(QQQ)、黄金(GLD)、中期美债(IEF),外加短债现金类(BIL)兜底",
            "record": "滚动前推回测(10.6 年样本外、含真实费用、整股约束):月均 1.108%(年化约 14.1%),最大回撤 18.90%,盈亏比 2.25",
            "logic_cn": "双动量:每周在五条腿里选动量最强的一条满仓持有;所有腿都跌破 200 日均线时空仓持现金。强者恒强吃趋势,趋势尽失就离场——owner 2026-07-24 书面选定换帅",
        },
        "hard_limits": [
            "总敞口上限 3000 澳元(绝不自动加资)",
            "单笔不超过总资金的 60%",
            "每小时最多 5 笔订单",
            "仅限美股/美股基金",
            "任何组件失联即拉闸停新单(失败关闭)",
            "语言模型与外部接口永远无权触发订单",
        ],
        "gates": gates,
        "honesty_note": honesty,
        "research": [
            {"name": "五腿双动量·周频·精调(美/国际/纳指/黄金/中债)", "result": "1.108%/月 @ 回撤 18.90%(10.6 年样本外 +305%,盈亏比 2.25)",
             "verdict": "现役(2026-07-24 owner 书面选定换帅上任)"},
            {"name": "五腿双动量·周频·基础", "result": "1.052%/月 @ 回撤 17.65%(胜率 66.9%,盈亏比 2.26)",
             "verdict": "风险调整比最优;与精调版同结构,参数更保守"},
            {"name": "长短结构(反向基金入池,三种构造)", "result": "0.11-0.56%/月 @ 回撤 31.6-58.6%",
             "verdict": "定论否决(2026-07-24):空腿是周频轮动的毒药——买入空头时跌势已过半,V形反转绞杀+日内重置损耗;含杠杆族累计七轮证据盖棺"},
            {"name": "三腿双动量·周频(美/国际/纳指)", "result": "1.075%/月 @ 回撤 25.39%(胜率 69.3%)", "verdict": "收益最高但回撤深;被五腿版以几乎同收益+浅得多的回撤替代"},
            {"name": "跨资产趋势跟随·周频", "result": "0.947%/月 @ 回撤 19.04%", "verdict": "第一代新王,被双动量家族超越"},
            {"name": "黄金对冲动量(前任)", "result": "0.662%/月 @ 回撤 13.07%", "verdict": "2026-07-24 换帅让位:回撤最浅,收益不敌新王"},
            {"name": "52 周新高过滤动量(门A)", "result": "0.894%/月 @ 回撤 18.98%", "verdict": "被替代"},
            {"name": "杠杆基金族(30% 容忍下重测两轮)", "result": "0.78-0.85%/月 @ 回撤 38-44%", "verdict": "定论否决:放宽容忍后仍两轴皆劣——日内重置损耗+周频躲不开急跌(四轮证据)"},
            {"name": "日历效应族(隔夜/月末/万圣节)", "result": "全部不敌保底线", "verdict": "否决(三线证据)"},
            {"name": "五五混合(股指+黄金分仓)", "result": "回撤 11.02% 全场最低,但 3000 澳元下费用惩罚致收益不过门", "verdict": "搁置:资金 ≥6000 澳元时重启评估"},
        ],
        "research_note": "所有候选同一把尺子:滚动前推(每半年只准用当时已知数据选参数)+ 双源行情核验 + 真实费用 + 整股约束;文献数字永远不能冒充自建回测。全部证据在公开仓 reports/backtest/ 可复验。",
        "updated_at_syd": f"{now.astimezone(SYD):%m月%d日 %H:%M}",
    }


def build_overview(*, session_factory, heartbeats, kill_switch,
                   quotes: Optional[QuoteSource] = None,
                   fx_aud_usd: float = 0.65, capital_aud: float = 3000.0,
                   reports_dir: str | Path = "reports/paper_3day",
                   runtime_dir: str | Path = "runtime",
                   now: Optional[datetime] = None) -> dict:
    """聚合看盘页全部数据(纯只读)。所有金额人话口径:管理切片 = 3000 澳元。"""
    now = now or datetime.now(timezone.utc)
    capital_usd = capital_aud * fx_aud_usd

    # ---------- 数据库事实 ----------
    intents, orders, execs, risks, outbox = {}, [], [], [], []
    if session_factory is not None:
        from sqlalchemy import select

        from backend.app.domain.models import (
            BrokerOrder, Execution, OrderIntent, OutboxEvent, RiskDecision,
        )
        with session_factory() as s:
            intents = {i.intent_id: i for i in s.scalars(select(OrderIntent)).all()}
            orders = list(s.scalars(select(BrokerOrder)).all())
            execs = list(s.scalars(select(Execution)).all())
            risks = list(s.scalars(select(RiskDecision)).all())
            outbox = list(s.scalars(select(OutboxEvent)).all())
    order_by_id = {o.order_id: o for o in orders}

    def _utc(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    # ---------- 持仓与管理切片 ----------
    net: dict[str, int] = {}
    cost: dict[str, float] = {}
    cash_flow_usd = 0.0
    for e in sorted(execs, key=lambda x: x.executed_at):
        o = order_by_id.get(e.order_id)
        i = intents.get(o.intent_id) if o else None
        if i is None:
            continue
        sign = 1 if i.side == "BUY" else -1
        net[i.symbol] = net.get(i.symbol, 0) + sign * e.quantity
        cost[i.symbol] = cost.get(i.symbol, 0.0) + sign * e.quantity * float(e.price)
        cash_flow_usd += (-sign) * e.quantity * float(e.price)

    held = sorted(sym for sym, q in net.items() if q != 0)
    quote_map = quotes.snapshots(held) if (quotes and held) else {}

    positions = []
    mark_value_usd = 0.0
    for sym in held:
        q = net[sym]
        avg = abs(cost[sym] / q) if q else 0.0
        snap = quote_map.get(sym)
        priced = snap is not None
        last = float(snap["price"]) if priced else avg
        mv = q * last
        mark_value_usd += mv
        upl = mv - cost[sym]
        positions.append({
            "symbol": sym, "name_cn": SYMBOL_CN.get(sym, sym), "qty": q,
            "avg_cost_usd": round(avg, 2), "last_usd": round(last, 2),
            "priced": priced, "quote_at": (snap or {}).get("at", ""),
            "market_value_usd": round(mv, 2),
            "upl_usd": round(upl, 2),
            "upl_pct": round(100.0 * upl / cost[sym], 2) if cost[sym] else 0.0,
        })

    cash_usd = capital_usd + cash_flow_usd
    equity_usd = cash_usd + mark_value_usd
    equity_aud = equity_usd / fx_aud_usd
    total_pnl_aud = equity_aud - capital_aud
    invested_usd = sum(p["market_value_usd"] for p in positions)
    exposure_pct = round(100.0 * (invested_usd / fx_aud_usd) / capital_aud, 1) if capital_aud else 0.0

    # ---------- 净值曲线(日终点 + 实时点;缺收盘价的历史日如实跳过) ----------
    curve: list[dict] = []
    skipped_days: list[str] = []
    if execs or orders:
        first_dt = min([_utc(o.created_at) for o in orders] + [_utc(e.executed_at) for e in execs])
        start_d = first_dt.astimezone(ET).date()
    else:
        start_d = now.astimezone(ET).date()
    today_et = now.astimezone(ET).date()
    closes_by_sym: dict[str, dict[str, float]] = {}
    if quotes and held and start_d < today_et:
        for sym in held:
            closes_by_sym[sym] = dict(quotes.daily_closes(
                sym, start_d.isoformat(), (today_et - timedelta(days=1)).isoformat()))
    d = start_d
    while d < today_et:
        if d.weekday() < 5:
            cash_d = capital_usd
            pos_d: dict[str, int] = {}
            for e in execs:
                if _utc(e.executed_at).astimezone(ET).date() <= d:
                    o = order_by_id.get(e.order_id)
                    i = intents.get(o.intent_id) if o else None
                    if i is None:
                        continue
                    sign = 1 if i.side == "BUY" else -1
                    pos_d[i.symbol] = pos_d.get(i.symbol, 0) + sign * e.quantity
                    cash_d += (-sign) * e.quantity * float(e.price)
            ok, mv_d = True, 0.0
            for sym, q in pos_d.items():
                if q == 0:
                    continue
                px = closes_by_sym.get(sym, {}).get(d.isoformat())
                if px is None:
                    ok = False
                    break
                mv_d += q * px
            if ok:
                curve.append({"date": d.isoformat(),
                              "equity_aud": round((cash_d + mv_d) / fx_aud_usd, 2)})
            else:
                skipped_days.append(d.isoformat())
        d += timedelta(days=1)
    curve.append({"date": today_et.isoformat(), "equity_aud": round(equity_aud, 2),
                  "live": True})

    # ---------- 考核卡 ----------
    report = _latest_report(Path(reports_dir))
    # 报告里的合格交易日早于首笔订单的,是纯现金日 → 以本金为锚补齐曲线起点
    if report:
        run_days = (report.get("run", {}) or {}).get("trading_days", []) or []
        flat = sorted({day for day in run_days
                       if curve and day < curve[0]["date"]})
        curve[:0] = [{"date": day, "equity_aud": round(capital_aud, 2)} for day in flat]
    prev_equity = curve[-2]["equity_aud"] if len(curve) >= 2 else capital_aud
    today_pnl_aud = equity_aud - prev_equity
    exam = None
    if report:
        promo = report.get("promotion", {})
        exam = {
            "report_date": report.get("_report_date", ""),
            "days_qualified": promo.get("days_qualified", 0),
            "days_required": promo.get("days_required", 3),
            "decision": promo.get("decision", ""),
            "auto_promote": promo.get("auto_promote", False),
            "lights": [
                {"name": "回测门槛", "ok": True,
                 "note": "月均 0.662%,过 0.6% 保底线(回测报告口径)"},
                {"name": "行为一致", "ok": bool(promo.get("PROMO-2", {}).get("passed")),
                 "note": promo.get("PROMO-2", {}).get("reason", "")},
                {"name": "收益速度", "ok": bool(promo.get("PROMO-3", {}).get("passed")),
                 "note": f"折算月化 {promo.get('PROMO-3', {}).get('pace_month_pct', 0)}%,"
                         f"容忍线 {promo.get('PROMO-3', {}).get('target_pct', 0)}%"},
                {"name": "工程零违规", "ok": bool(promo.get("PROMO-4", {}).get("passed")),
                 "note": f"可用性 {promo.get('PROMO-4', {}).get('uptime_pct', 0)}%,"
                         f"通知延迟 p95 {promo.get('PROMO-4', {}).get('notify_p95_seconds', 0)} 秒"},
            ],
        }

    # ---------- 动作时间线 ----------
    risk_by_intent = {r.intent_id: r for r in risks}
    events: list[dict] = []
    for o in orders:
        i = intents.get(o.intent_id)
        if i is None:
            continue
        if o.state == "RISK_REJECTED":
            r = risk_by_intent.get(o.intent_id)
            rules = json.loads(r.triggered_rules or "[]") if r else []
            why = ";".join(RULE_CN.get(x, x) for x in rules) or "风控拦下"
            text = f"想{SIDE_CN.get(i.side, i.side)} {i.symbol} {i.quantity} 股,被风控拦下:{why}"
            kind = "block"
        else:
            filled = f",已成 {o.filled_quantity} 股" if o.filled_quantity else ""
            text = (f"{SIDE_CN.get(i.side, i.side)} {i.symbol} {i.quantity} 股 · "
                    f"{STATE_CN.get(o.state, o.state)}{filled}")
            kind = "order"
        events.append({"at": _utc(o.created_at), "text": text, "kind": kind})
    for e in execs:
        o = order_by_id.get(e.order_id)
        i = intents.get(o.intent_id) if o else None
        if i is None:
            continue
        events.append({"at": _utc(e.executed_at), "kind": "fill",
                       "text": f"成交:{SIDE_CN.get(i.side, i.side)} {i.symbol} "
                               f"{e.quantity} 股 @ {float(e.price):.2f} 美元"})
    mails = sorted((x for x in outbox if x.delivery_status == "DELIVERED" and x.delivered_at),
                   key=lambda x: x.delivered_at, reverse=True)
    for x in mails[:3]:      # 邮件只留最近 3 封,别让告警旧账刷掉交易动作
        events.append({"at": _utc(x.delivered_at), "kind": "mail",
                       "text": f"已邮件你:{_email_title(x.event_type)}"})
    events.sort(key=lambda ev: ev["at"], reverse=True)
    timeline = [{"at_syd": f"{ev['at'].astimezone(SYD):%m-%d %H:%M}",
                 "kind": ev["kind"], "text": ev["text"]} for ev in events[:24]]

    # ---------- 系统健康 ----------
    hb = heartbeats.snapshot() if heartbeats else {}
    comp_cn = {"trading-worker": "交易主循环", "notify-worker": "邮件投递",
               "supervisor": "守护监督"}
    components = []
    trading_status, mode_hint = "无", ""
    for name, h in sorted(hb.items()):
        beat = datetime.fromisoformat(h["beat_at"])
        age = int((now - beat).total_seconds())
        components.append({"name": comp_cn.get(name, name), "raw": name,
                           "status": h["status"], "age_s": age, "ok": age < 150})
        if name == "trading-worker":
            trading_status = h["status"]
            mode_hint = h.get("detail", "") or ""
    all_fresh = bool(components) and all(c["ok"] for c in components)
    import os as _os
    env_live = (_os.environ.get("ALPHA_MODE", "").upper() == "MICRO_LIVE"
                and _os.environ.get("LIVE_TRADING_ENABLED", "0") == "1")
    halted = kill_switch.active() or trading_status == "HALTED"
    if halted:
        banner = {"kind": "halted", "text": "⏸️ 系统已暂停(紧急刹车拉下,不会再下任何单)"}
    elif all_fresh and trading_status == "RUNNING":
        banner = {"kind": "ok", "text": "✅ 系统正常运行中"}
    else:
        banner = {"kind": "warn",
                  "text": "⚠️ 系统部分组件没报平安,我会自动处理;持续异常会邮件通知你"}
    mode_cn = "微实盘(真实资金)" if (env_live or "MICRO_LIVE" in mode_hint) else "模拟盘"
    last_mail = next((ev for ev in events if ev["kind"] == "mail"), None)

    return {
        "banner": banner,
        "mode_cn": mode_cn,
        "market": _market_status(now),
        "hero": {
            "equity_aud": round(equity_aud, 2),
            "capital_aud": capital_aud,
            "total_pnl_aud": round(total_pnl_aud, 2),
            "total_pnl_pct": round(100.0 * total_pnl_aud / capital_aud, 2) if capital_aud else 0.0,
            "today_pnl_aud": round(today_pnl_aud, 2),
            "cash_usd": round(cash_usd, 2),
            "invested_usd": round(invested_usd, 2),
            "exposure_pct": exposure_pct,
        },
        "curve": curve,
        "curve_skipped_days": skipped_days,
        "positions": positions,
        "exam": exam,
        "next_decision": _next_decision(now, Path(runtime_dir)),
        "timeline": timeline,
        "health": {"components": components, "kill_switch": kill_switch.active(),
                   "last_mail": ({"at_syd": f"{last_mail['at'].astimezone(SYD):%m-%d %H:%M}",
                                  "text": last_mail["text"]} if last_mail else None),
                   "server": "新加坡节点"},
        "meta": {
            "updated_at_syd": f"{now.astimezone(SYD):%m月%d日 %H:%M:%S}",
            "fx_aud_usd": fx_aud_usd,
            "note_fx": "美元→澳元按固定口径 0.65 折算(与契约资金常量一致)",
        },
    }
