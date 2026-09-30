"""盘前自检(每交易日开盘前跑一次;只读,永不下单)。

一次性回答"系统现在到底能不能正常做单",按模式检查:
  1) 交易进程还在跑(心跳 180 秒内)、上报模式与配置一致且没退化成 BLOCKED_* 空转;三组件齐全;
  2) 券商模式:OpenD 会话还活着(能查账户购买力);影子盘:Yahoo 行情能取到(盘前时间戳旧不算错);
  3) 只在微实盘时:预签授权对当前风控仍有效、距到期 ≥3 天;
  4) 漏评估(与守护同一判据 health.evaluate_health)、紧急刹车状态。
每一项经告警状态簿去重:转红发一封、转绿发一封「已恢复」,重复运行不重发;不再发每日绿灯信
(死人开关改由每日在岗摘要承担)。结果写 facts/preflight_status.json 供看盘运维页展示。
入队成功即返回 0;只有脚本自身崩溃才返回非 0(交给 alpha-alert@ 告警)。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HEARTBEAT_MAX_AGE_SECONDS = 180


def _opend_power(acc_id: str, trd_env: str) -> tuple[bool, float | None, str]:
    """OpenD 会话探针:能查到账户购买力就算会话活着。"""
    try:
        from moomoo import (RET_OK, Currency, OpenSecTradeContext, SecurityFirm,
                            TrdEnv, TrdMarket)
        tc = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host="127.0.0.1",
                                 port=11111, security_firm=SecurityFirm.FUTUAU)
        try:
            ret, df = tc.accinfo_query(trd_env=getattr(TrdEnv, trd_env), acc_id=int(acc_id),
                                       refresh_cache=True, currency=Currency.USD)
            if ret == RET_OK and df is not None and len(df):
                return True, float(df.iloc[0]["power"]), ""
            return False, None, f"accinfo_query 非 OK:{df}"
        finally:
            tc.close()
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"[:160]


def main(*, quotes=None, now: datetime | None = None) -> int:
    from backend.app import health, truth, wiring
    from backend.app.adapters.brokers.base import MODE_TO_TRD_ENV, SystemMode
    from backend.app.notify.outbox import AlertBook
    from backend.app.store.db import create_session_factory, init_engine
    from backend.app.workers.heartbeat import HeartbeatStore
    from backend.app.workers.killswitch import KillSwitch

    now = now or datetime.now(timezone.utc)
    m = truth.mode()
    checks: list[dict] = []

    def add(slug: str, name: str, ok: bool, detail: str) -> None:
        checks.append({"slug": slug, "name": name, "ok": bool(ok), "detail": detail})

    factory = create_session_factory(init_engine())
    heartbeats = HeartbeatStore(factory, now_fn=lambda: now)
    kill = KillSwitch(os.environ.get("ALPHA_KILL_SWITCH_PATH", "runtime/KILL_SWITCH"))

    # 1) 交易进程 + 模式 + 三组件
    try:
        snap = heartbeats.snapshot()
        tw = snap.get("trading-worker", {})
        beat = datetime.fromisoformat(tw["beat_at"]) if tw.get("beat_at") else None
        age = int((now - beat).total_seconds()) if beat else None
        detail = str(tw.get("detail", ""))
        add("heartbeat", "交易进程在跑(心跳新鲜)",
            age is not None and age < HEARTBEAT_MAX_AGE_SECONDS,
            f"{age} 秒前" if age is not None else "从未心跳")
        reported, blocked = health.heartbeat_mode(detail), health.heartbeat_blocked(detail)
        add("mode", f"模式={truth.mode_label(m)}且未空转",
            reported == m.value and blocked is None,
            f"进程报告 {blocked or reported or '未知'},配置 {m.value}")
        add("components", "三组件齐全", {"trading-worker", "notify-worker", "supervisor"} <= set(snap),
            "、".join(sorted(snap)) or "无")
    except Exception as exc:
        add("heartbeat", "交易进程/心跳可读", False, f"{type(exc).__name__}: {exc}"[:120])

    # 2) 行情/券商通路:券商模式探 OpenD,影子盘探 Yahoo(只看取不取得到)
    power = None
    if wiring.resolve(m, "funds") is not None:
        acc = os.environ.get("ALPHA_EXPECTED_ACC_ID", "")
        alive, power, err = (_opend_power(acc, MODE_TO_TRD_ENV[m][0].value) if acc
                             else (False, None, "未配置账户 ALPHA_EXPECTED_ACC_ID"))
        add("opend", "OpenD 券商会话活着", alive, f"购买力 {power:.2f} USD" if alive else err)
    elif m is SystemMode.SHADOW:
        try:
            from backend.app.strategies.s1_momentum import load_s1_config
            cfg = load_s1_config(truth.strategy_config_path())
            symbols = list(dict.fromkeys(list(cfg["universe"]) + [cfg["cash_proxy"]]))
            src = quotes or wiring.resolve(m, "quotes")()
            bad = []
            for sym in symbols:
                try:
                    src.get_quote(sym)
                except Exception as exc:
                    bad.append(f"{sym}({type(exc).__name__})")
            add("quotes", "Yahoo 行情取得到", not bad,
                f"{len(symbols) - len(bad)}/{len(symbols)} 只取到" + (f";失败:{'、'.join(bad)}" if bad else ""))
        except Exception as exc:
            add("quotes", "Yahoo 行情可探测", False, f"{type(exc).__name__}: {exc}"[:120])

    # 3) 预签授权:只在微实盘时查(影子盘/模拟盘不涉及授权)
    days_left = None
    if truth.is_micro_live():
        try:
            from backend.app.execution.gates import validate_authorization
            auth_path = os.environ.get("ALPHA_AUTHORIZATION_PATH",
                                       str(truth.runtime_dir() / "LIVE_AUTHORIZATION.json"))
            ok_auth, reasons = validate_authorization(
                auth_path, policy_path="configs/trading_governor_policy.yaml",
                promotion_config_path="configs/strategy_promotion.yaml", now=now)
            add("auth", "预签授权对当前风控有效", ok_auth, "有效" if ok_auth else f"{reasons[:2]}")
            vu = json.loads(Path(auth_path).read_text()).get("valid_until", "").replace("Z", "+00:00")
            if vu:
                days_left = (datetime.fromisoformat(vu) - now).days
                add("auth_expiry", "授权距到期 ≥3 天", days_left >= 3,
                    f"还剩 {days_left} 天(到 {vu[:10]});续签只有你能授权")
        except Exception as exc:
            add("auth", "预签授权可校验", False, f"{type(exc).__name__}: {exc}"[:120])

    # 4) 漏评估(与守护同一判据)+ 紧急刹车
    try:
        items = health.evaluate_health(session_factory=factory, heartbeats=heartbeats,
                                       kill_switch=kill, now=now)
        missed = next(i for i in items if i.key.startswith("eval_missed:"))
        add("eval_missed", "评估日已按时评估(业务级)", not missed.bad, missed.detail)
    except Exception as exc:
        add("eval_missed", "评估产出可核验", False, f"{type(exc).__name__}: {exc}"[:120])
    add("kill_switch", "紧急刹车未拉下", not kill.active(),
        "待命" if not kill.active() else f"已拉下:{kill.detail()}")

    all_ok = all(c["ok"] for c in checks)
    facts = truth.facts_dir() / "preflight_status.json"
    facts.parent.mkdir(parents=True, exist_ok=True)
    facts.write_text(json.dumps({
        "at": now.isoformat(), "mode": m.value, "all_ok": all_ok, "power_usd": power,
        "auth_days_left": days_left, "checks": checks,
    }, ensure_ascii=False))

    # 每项过状态簿:转红一封、恢复一封;重复运行不重发
    alerts = AlertBook(factory, now_fn=lambda: now)
    for c in checks:
        alerts.observe(f"preflight:{c['slug']}", not c["ok"], payload={
            "title": f"盘前自检:{c['name']} 未通过", "detail": c["detail"],
            "action": "需要代理排查;失败关闭原则下系统不会因此乱下单。"})

    for c in checks:
        print(f"{'✅' if c['ok'] else '❌'} {c['name']} — {c['detail']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
