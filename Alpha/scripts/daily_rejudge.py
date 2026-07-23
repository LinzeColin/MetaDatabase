#!/usr/bin/env python3
"""每日收盘复判(部署主机 systemd timer 驱动;agent 会话只做监督与归档)。

流程:核可用性(系统日志)→ 取当日日K官方收盘 → 重算日终净值与最大回撤 →
调用 070 取数器出四件套 → 读四灯判定 → 按邮件纪律通知 owner。

红线:
- 只读已发生事实;判定阈值全部由取数器/报告生成器从 strategy_promotion.yaml
  读取,本脚本绝不重定义、绝不放宽;
- 本脚本没有任何激活权限:全绿也只能发喜报,切换 MICRO_LIVE 永远需要
  owner 预签授权 + 实盘总开关,由门禁矩阵在 worker 启动时校验;
- 邮件纪律:全绿必发;灯色与上一次不同才发;首次运行只记档不发(除非全绿)。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIRST_QUALIFIED_DAY = "2026-07-20"      # 模拟盘第 1 个合格交易日(契约窗口起点)
WINDOW_SECONDS_PER_DAY = 23400          # 13:30~20:00 UTC
RESTART_PENALTY_SECONDS = 60            # 每次盘中重启保守扣 60 秒(与人工核算口径一致)


def weekdays_between(start_iso: str, end_iso: str) -> list[str]:
    """[start, end] 闭区间内的工作日(美股节假日若无行情会在估值处如实跳过)。"""
    d = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    out = []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def uptime_pct(days: list[str], restarts_by_day: dict[str, int]) -> float:
    """保守可用性:每个盘中 Started 事件按 60 秒停机计。"""
    total = WINDOW_SECONDS_PER_DAY * len(days)
    if total <= 0:
        return 0.0
    lost = sum(RESTART_PENALTY_SECONDS * restarts_by_day.get(d, 0) for d in days)
    return round(max(0.0, (total - lost) / total * 100.0), 2)


def max_drawdown_pct(equities: list[float]) -> float:
    """日终净值序列最大回撤(峰到谷,百分比,正数)。"""
    peak, dd = float("-inf"), 0.0
    for v in equities:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak * 100.0)
    return round(dd, 2)


def lights_of(report: dict) -> tuple[bool, bool, bool]:
    p = report.get("promotion", {})
    return (bool(p.get("PROMO-2", {}).get("passed")),
            bool(p.get("PROMO-3", {}).get("passed")),
            bool(p.get("PROMO-4", {}).get("passed")))


def should_email(prev: dict | None, lights: tuple, all_green: bool) -> bool:
    if all_green:
        return True
    if prev is None:
        return False              # 首次只记档,不重复打扰
    return tuple(prev.get("lights", ())) != lights


def real_power_usd(acc_id: str) -> float | None:
    """真实账户美元购买力(只读;失败返回 None,调用方按失败关闭处理)。"""
    try:
        from moomoo import RET_OK, Currency, OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket
        tc = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host="127.0.0.1",
                                 port=11111, security_firm=SecurityFirm.FUTUAU)
        try:
            ret, df = tc.accinfo_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id),
                                       refresh_cache=True, currency=Currency.USD)
            if ret != RET_OK or df is None or len(df) == 0:
                return None
            return float(df.iloc[0]["power"])
        finally:
            tc.close()
    except Exception:
        return None


def activation_gate(*, auth_ok: bool, auth_reasons: list, live_flag_on: bool,
                    real_acc: str, power: float | None, min_power: float) -> list[str]:
    """全绿之外的三项切换前提;返回阻塞清单(空=可请求切换)。纯函数可测。"""
    blockers = []
    if live_flag_on:
        blockers.append("已在实盘,无需切换")
    if not auth_ok:
        blockers.append(f"预签授权无效:{auth_reasons[:2]}")
    if not real_acc:
        blockers.append("缺真实账户配置(私密键未设)")
    elif power is None:
        blockers.append("真实账户资金核验暂不可用")
    elif power < min_power:
        blockers.append(f"真实账户购买力 {power:.0f} 美元低于门槛 {min_power:.0f} 美元(等入金到账)")
    return blockers


def journal_restarts(day: str) -> int:
    r = subprocess.run(
        ["journalctl", "-u", "alpha-trading-worker", "--since", f"{day} 13:30",
         "--until", f"{day} 20:00", "--no-pager"],
        capture_output=True, text=True, timeout=60)
    return sum(1 for line in r.stdout.splitlines() if "Started" in line)


def kline_closes(symbol: str, start: str, end: str) -> dict[str, float]:
    from moomoo import KLType, RET_OK, OpenQuoteContext
    qc = OpenQuoteContext(host="127.0.0.1", port=11111)
    try:
        r = qc.request_history_kline(f"US.{symbol}", start=start, end=end,
                                     ktype=KLType.K_DAY)
        ret, df = r[0], r[1]
        if ret != RET_OK:
            return {}
        return {str(row["time_key"])[:10]: float(row["close"]) for _, row in df.iterrows()}
    finally:
        qc.close()


def main() -> int:
    today = datetime.now(timezone.utc).date().isoformat()
    capital_aud = float(os.environ.get("ALPHA_CAPITAL_AUD", "3000"))
    fx = float(os.environ.get("ALPHA_FX_AUD_USD", "0.65"))
    base = Path(os.environ.get("ALPHA_REJUDGE_OUT_BASE", "reports/paper_3day"))
    state_path = Path(os.environ.get("ALPHA_REJUDGE_STATE", "runtime/last_rejudge.json"))

    days = weekdays_between(FIRST_QUALIFIED_DAY, today)
    if today not in days:
        print(f"{today} 非工作日,跳过")
        return 0

    # 成交流水 → 持仓与每日现金(与取数器同源:数据库为唯一事实)
    from sqlalchemy import select

    from backend.app.domain.models import BrokerOrder, Execution, OrderIntent
    from backend.app.store.db import create_session_factory, init_engine
    sf = create_session_factory(init_engine(os.environ["ALPHA_DATABASE_URL"]))
    with sf() as s:
        intents = {i.intent_id: i for i in s.scalars(select(OrderIntent)).all()}
        orders = {o.order_id: o for o in s.scalars(select(BrokerOrder)).all()}
        execs = sorted(s.scalars(select(Execution)).all(), key=lambda e: e.executed_at)
    flows = []      # (日期, symbol, 有向数量, 有向现金流USD)
    for e in execs:
        o = orders.get(e.order_id)
        i = intents.get(o.intent_id) if o else None
        if i is None:
            continue
        sign = 1 if i.side == "BUY" else -1
        d = (e.executed_at if e.executed_at.tzinfo else
             e.executed_at.replace(tzinfo=timezone.utc)).date().isoformat()
        flows.append((d, i.symbol, sign * e.quantity, -sign * e.quantity * float(e.price)))
    held = sorted({sym for _, sym, q, _ in flows})

    closes: dict[str, dict[str, float]] = {
        sym: kline_closes(sym, FIRST_QUALIFIED_DAY, today) for sym in held}
    # 今日估值价:当日官方收盘;持仓却无当日K线 → 视为休市日,如实退出
    marks = {}
    pos_now: dict[str, int] = {}
    for _, sym, q, _ in flows:
        pos_now[sym] = pos_now.get(sym, 0) + q
    for sym, q in pos_now.items():
        if q == 0:
            continue
        px = closes.get(sym, {}).get(today)
        if px is None:
            print(f"{today} 持有 {sym} 但无当日K线(休市/数据缺),今日不复判")
            return 0
        marks[sym] = px

    # 日终净值序列(缺收盘价的历史日如实跳过,与看盘页同口径)
    capital_usd = capital_aud * fx
    equities = []
    for d in days:
        cash = capital_usd
        pos: dict[str, int] = {}
        for fd, sym, q, cf in flows:
            if fd <= d:
                pos[sym] = pos.get(sym, 0) + q
                cash += cf
        ok, mv = True, 0.0
        for sym, q in pos.items():
            if q == 0:
                continue
            px = closes.get(sym, {}).get(d)
            if px is None:
                ok = False
                break
            mv += q * px
        if ok:
            equities.append((cash + mv) / fx)
    dd = max_drawdown_pct(equities)

    restarts = {d: journal_restarts(d) for d in days}
    up = uptime_pct(days, restarts)

    out_dir = base / today
    mark_arg = ",".join(f"{sym}={px}" for sym, px in sorted(marks.items()))
    cmd = [sys.executable, "scripts/export_paper_run.py",
           "--days", ",".join(days), "--uptime", str(up),
           "--max-dd-pct", str(dd), "--fx-aud-usd", str(fx),
           "--capital-aud", str(capital_aud), "--out", str(out_dir)]
    if mark_arg:
        cmd += ["--mark-prices", mark_arg]
    subprocess.run(cmd, check=True, timeout=300)

    report = json.loads((out_dir / "report.json").read_text())
    lights = lights_of(report)
    all_green = bool(report.get("promotion", {}).get("auto_promote"))
    prev = json.loads(state_path.read_text()) if state_path.exists() else None

    # 全绿时核查另外三项切换前提;齐备则写切换请求文件(由根权限切换器接手)
    activation_line = ""
    if all_green:
        from backend.app.execution.gates import validate_authorization
        auth_path = Path(os.environ.get("ALPHA_AUTHORIZATION_PATH",
                                        "runtime/LIVE_AUTHORIZATION.json"))
        auth_ok, auth_reasons = (False, ["授权文件不存在"])
        if auth_path.exists():
            auth_ok, auth_reasons = validate_authorization(
                auth_path, policy_path="configs/trading_governor_policy.yaml",
                promotion_config_path="configs/strategy_promotion.yaml",
                now=datetime.now(timezone.utc))
        real_acc = os.environ.get("ALPHA_REAL_ACC_ID", "").strip()
        min_power = float(os.environ.get("ALPHA_MIN_LIVE_POWER_USD", "1890"))
        power = real_power_usd(real_acc) if real_acc else None
        blockers = activation_gate(
            auth_ok=auth_ok, auth_reasons=list(auth_reasons),
            live_flag_on=os.environ.get("LIVE_TRADING_ENABLED", "0") == "1",
            real_acc=real_acc, power=power, min_power=min_power)
        if not blockers:
            req_path = Path("runtime/ACTIVATE_REQUEST.json")
            req_path.write_text(json.dumps({
                "requested_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "report_dir": str(out_dir), "days": len(days),
                "power_usd": power, "uptime": up, "max_dd_pct": dd,
            }, ensure_ascii=False, indent=2))
            activation_line = ("三项切换前提(预签授权/资金/开关状态)全部齐备,"
                               "已向切换器发出自动切换请求——切换完成会另发一封确认邮件,"
                               "第一笔真实订单在下一个评估窗口。")
        else:
            activation_line = ("但暂不切换实盘:" + ";".join(blockers) +
                               "。条件补齐后的下一次每日复判会自动再试,无需任何人操作。")

    if should_email(prev, lights, all_green):
        from backend.app.notify.outbox import Outbox
        p3 = report["promotion"]["PROMO-3"]
        names = ["行为一致", "收益速度", "工程零违规"]
        light_txt = ";".join(f"{n}{'🟢' if okk else '🔴'}" for n, okk in zip(names, lights))
        if all_green:
            text = (f"今天收盘复判:四项判定全绿!合格交易日 {len(days)} 天,"
                    f"折算月化 {p3['pace_month_pct']}%(容忍线 {p3['target_pct']}%),"
                    f"可用性 {up}%,最大回撤 {dd}%。\n\n{activation_line}\n"
                    "本邮件由服务器每日复判定时任务自动发出。")
        else:
            text = (f"今天收盘复判:灯色有变化 → {light_txt}。"
                    f"合格交易日 {len(days)} 天,折算月化 {p3['pace_month_pct']}%"
                    f"(容忍线 {p3['target_pct']}%),可用性 {up}%,最大回撤 {dd}%。\n"
                    "规则不变,继续模拟盘;详情看 alpha.linzezhang.com。\n"
                    "本邮件由服务器每日复判定时任务自动发出。")
        Outbox(sf).enqueue(event_type="PAPER_3DAY_REPORT", payload={"text": text})
        print("已入队复判邮件")

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(
        {"date": today, "lights": list(lights), "all_green": all_green,
         "uptime": up, "max_dd_pct": dd, "days": len(days)}, ensure_ascii=False))
    print(json.dumps({"date": today, "lights": lights, "all_green": all_green,
                      "uptime": up, "dd": dd, "days": len(days)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
