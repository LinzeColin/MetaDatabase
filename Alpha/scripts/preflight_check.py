"""盘前自检 / 死人开关(每交易日开盘前跑一次;只读,永不下单)。

一次性回答"系统现在到底能不能正常做单",把过去只能靠 owner 盯页面才发现的静默故障
变成主动告警。检查五件事:
  1) 交易进程还在跑、且模式=MICRO_LIVE、没退化成 BLOCKED_ON_OPEND 空转;
  2) OpenD 券商会话还活着(能查账户购买力)——会话过期是首单静默落空的头号原因;
  3) 预签授权对当前风控政策仍有效,且距到期还有几天(<3 天单独告警);
  4) 紧急刹车状态、三组件心跳是否新鲜;
  5) 汇总成一封邮件:全绿=『盘前自检通过(系统在岗)』——这封每日绿灯本身就是死人开关,
     哪天你没收到,就说明这台机器整个黑了。任何一项红=『盘前自检发现问题』并推第二通道。

写 machine/facts/preflight_status.json 供看盘运维页展示。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FACTS = Path("machine/facts/preflight_status.json")


def _opend_power(acc_id: str) -> tuple[bool, float | None, str]:
    """OpenD 会话探针:能查到真实账户购买力就算会话活着。"""
    try:
        from moomoo import (RET_OK, Currency, OpenSecTradeContext, SecurityFirm,
                            TrdEnv, TrdMarket)
        tc = OpenSecTradeContext(filter_trdmarket=TrdMarket.US, host="127.0.0.1",
                                 port=11111, security_firm=SecurityFirm.FUTUAU)
        try:
            ret, df = tc.accinfo_query(trd_env=TrdEnv.REAL, acc_id=int(acc_id),
                                       refresh_cache=True, currency=Currency.USD)
            if ret == RET_OK and df is not None and len(df):
                return True, float(df.iloc[0]["power"]), ""
            return False, None, f"accinfo_query 非 OK:{df}"
        finally:
            tc.close()
    except Exception as exc:
        return False, None, f"{type(exc).__name__}: {exc}"[:160]


def main() -> int:
    checks: list[dict] = []
    now = datetime.now(timezone.utc)

    def add(name: str, ok: bool, detail: str):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    from backend.app.store.db import create_session_factory, init_engine
    factory = create_session_factory(init_engine())

    # 1) 交易进程 + 模式
    try:
        from backend.app.workers.heartbeat import HeartbeatStore
        snap = HeartbeatStore(factory).snapshot()
        tw = snap.get("trading-worker", {})
        beat = datetime.fromisoformat(tw["beat_at"]) if tw.get("beat_at") else None
        age = int((now - beat).total_seconds()) if beat else 99999
        detail = str(tw.get("detail", ""))
        add("交易进程在跑(心跳新鲜)", age < 180, f"{age}s 前")
        add("模式=微实盘且未空转", "MICRO_LIVE" in detail and "BLOCKED_ON_OPEND" not in detail,
            detail[:80] or "无 detail")
        add("三组件齐全", {"trading-worker", "notify-worker", "supervisor"} <= set(snap),
            "、".join(sorted(snap)))
    except Exception as exc:
        add("交易进程/心跳可读", False, f"{type(exc).__name__}: {exc}"[:120])

    # 2) OpenD 会话
    acc = os.environ.get("ALPHA_REAL_ACC_ID", "")
    alive, power, err = _opend_power(acc) if acc else (False, None, "未配置账户")
    add("OpenD 券商会话活着", alive, (f"购买力 {power:.2f} USD" if alive else err))

    # 3) 预签授权有效性 + 到期天数
    days_left = None
    try:
        from backend.app.execution.gates import validate_authorization
        ok_auth, reasons = validate_authorization(
            os.environ.get("ALPHA_AUTHORIZATION_PATH", "runtime/LIVE_AUTHORIZATION.json"),
            policy_path="configs/trading_governor_policy.yaml",
            promotion_config_path="configs/strategy_promotion.yaml", now=now)
        add("预签授权对当前风控有效", ok_auth, "有效" if ok_auth else f"{reasons[:2]}")
        auth = json.loads(Path(os.environ.get(
            "ALPHA_AUTHORIZATION_PATH", "runtime/LIVE_AUTHORIZATION.json")).read_text())
        vu = auth.get("valid_until", "").replace("Z", "+00:00")
        if vu:
            days_left = (datetime.fromisoformat(vu) - now).days
            add("授权距到期 ≥3 天", days_left >= 3, f"还剩 {days_left} 天(到 {vu[:10]})")
    except Exception as exc:
        add("预签授权可校验", False, f"{type(exc).__name__}: {exc}"[:120])

    # 3.5) 业务级健康:该评估的日子过了窗口却没评估(2026-07-28 事故根因 R3)
    #      心跳只证明进程在转,不证明业务在做事——必须绑业务产出才能发现"空转"。
    try:
        from zoneinfo import ZoneInfo

        from backend.app.workers.live_cycle import missed_evaluation
        marker = Path(os.environ.get("ALPHA_RUNTIME_DIR", "runtime")) / "last_s1_eval.txt"
        last_tag = marker.read_text().strip() if marker.exists() else ""
        is_live = (os.environ.get("ALPHA_MODE", "").upper() == "MICRO_LIVE"
                   and os.environ.get("LIVE_TRADING_ENABLED", "0") == "1")
        missed, why = missed_evaluation(now.astimezone(ZoneInfo("America/New_York")),
                                        last_eval_tag=last_tag, is_live=is_live)
        add("评估日已按时评估(业务级)", not missed,
            why if missed else f"最近评估:{last_tag or '尚未开始'}")
    except Exception as exc:
        add("评估产出可核验", False, f"{type(exc).__name__}: {exc}"[:120])

    # 4) 紧急刹车
    try:
        from backend.app.workers.killswitch import KillSwitch
        ks = KillSwitch(os.environ.get("ALPHA_KILL_SWITCH_PATH", "runtime/KILL_SWITCH"))
        add("紧急刹车未拉下", not ks.active(), "待命" if not ks.active() else f"已拉下:{ks.detail()}")
    except Exception as exc:
        add("刹车状态可读", False, str(exc)[:80])

    all_ok = all(c["ok"] for c in checks)
    reds = [c for c in checks if not c["ok"]]

    # 落盘供看盘页
    FACTS.parent.mkdir(parents=True, exist_ok=True)
    FACTS.write_text(json.dumps({
        "at": now.isoformat(), "all_ok": all_ok, "power_usd": power,
        "auth_days_left": days_left, "checks": checks,
    }, ensure_ascii=False))

    # 组邮件
    lines = [("✅ 系统在岗,盘前自检全绿。" if all_ok
              else f"⚠️ 盘前自检发现 {len(reds)} 项问题,需要处理:"), ""]
    for c in checks:
        lines.append(f"{'✅' if c['ok'] else '❌'} {c['name']} — {c['detail']}")
    if all_ok:
        lines += ["", "(这封每日绿灯本身就是『死人开关』:哪天你没收到它,就说明这台机器可能整个黑了,"
                  "请立刻找我或检查。)"]
    text = "\n".join(lines)

    try:
        from backend.app.notify.outbox import Outbox, post_alert_webhook
        Outbox(factory).enqueue(
            event_type="PREFLIGHT_OK" if all_ok else "PREFLIGHT_ALERT",
            payload={"text": text})
        # 授权临期单独再吼一封(更醒目)
        if days_left is not None and 0 <= days_left < 3:
            Outbox(factory).enqueue(event_type="AUTH_EXPIRING", payload={"text":
                f"预签授权只剩 {days_left} 天到期。不续签的话,到期后实盘会自动停止下单。\n"
                "续签动作只有你能授权(需要你的原话),到点我会提醒你重签。"})
        if not all_ok:
            post_alert_webhook("【Alpha】盘前自检发现问题", text)  # 第二通道兜底
    except Exception as exc:
        print("邮件入队失败(自检结果仍已落盘):", exc)

    print(text)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
