#!/usr/bin/env python3
"""系统体检(给 owner 与代理的一页人话;除 --digest 写一行发件箱外,全部只读,永不下单)。

用法:
    python scripts/alpha_doctor.py                # 人话体检:首行结论,逐项 ✅/❌ 附含义与要不要你动手
    python scripts/alpha_doctor.py --json         # 机器格式(install.sh 自检用)
    python scripts/alpha_doctor.py --check-env    # 只查影子盘环境(install.sh 启用前调用)
    python scripts/alpha_doctor.py --probe-quotes # 实测 Yahoo 行情时间戳年龄(新鲜度 5 秒阈值的依据)
    python scripts/alpha_doctor.py --digest       # 生成每日在岗摘要入队(死人开关),顺带清理旧发件箱行
退出码:全绿 0,有红 1。业务判据与守护同一出处(health.evaluate_health),这里只加基础设施项。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_WORKERS = ("trading-worker", "notify-worker", "supervisor")
UNITS = ("alpha-trading-worker.service", "alpha-notify-worker.service",
         "alpha-supervisor.service", "alpha-control-page.service",
         "alpha-equity-snapshot.timer", "alpha-preflight.timer",
         "alpha-backup.timer", "alpha-digest.timer")
MIN_FREE_BYTES = 1 << 30          # 数据盘至少留 1 GiB
MAX_DB_BYTES = 512 << 20          # 账本库超过 512 MiB 视为臃肿
DAILY_MAX_AGE = timedelta(hours=26)   # 每日任务(备份/摘要)允许的最长间隔
#: 业务判据键前缀 -> 体检里的中性名称(绿灯时显示;红灯时显示判据自己的告警标题)
HEALTH_NAMES = {
    "eval_missed": "周二评估按时完成", "eval_blocked": "最近一次评估的单子都成交了",
    "blocked": "交易循环没有卡在空转", "equity_stale": "净值快照在更新",
    "quote_feed": "行情源取得到", "outbox_broken": "邮件发得出去",
    "mode_drift": "运行模式与配置一致", "ledger_mismatch": "影子账对得上",
}
WORKER_CN = {"trading-worker": "交易主循环", "notify-worker": "邮件投递", "supervisor": "守护监督"}


@dataclass(frozen=True)
class Check:
    key: str
    ok: bool
    title: str      # 这一项查的是什么
    detail: str     # 这是什么意思
    action: str     # 要不要你动手


def _systemctl_state(unit: str) -> Optional[str]:
    """systemctl is-active;非 Linux 或没有 systemctl 返回 None(跳过并注明)。"""
    if not sys.platform.startswith("linux") or shutil.which("systemctl") is None:
        return None
    r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10)
    return (r.stdout or r.stderr).strip() or "unknown"


def collect(*, now: Optional[datetime] = None,
            systemctl: Callable[[str], Optional[str]] = _systemctl_state) -> list[Check]:
    from sqlalchemy import func, select

    from backend.app import health, truth
    from backend.app.adapters.brokers.base import SystemMode
    from backend.app.domain.models import OutboxEvent
    from backend.app.notify.outbox import AlertBook
    from backend.app.store.db import create_session_factory, init_engine
    from backend.app.workers.heartbeat import HeartbeatStore
    from backend.app.workers.killswitch import KillSwitch
    from backend.app.workers.supervisor import DEFAULT_STALE_SECONDS

    now = now or datetime.now(timezone.utc)
    m = truth.mode()
    rt = truth.runtime_dir()
    engine = init_engine()
    factory = create_session_factory(engine)
    heartbeats = HeartbeatStore(factory, now_fn=lambda: now)
    kill = KillSwitch(os.environ.get("ALPHA_KILL_SWITCH_PATH", "runtime/KILL_SWITCH"))
    alerts = AlertBook(factory, now_fn=lambda: now)
    checks: list[Check] = []

    # ---- 业务判据(与守护同一出处) ----
    for item in health.evaluate_health(session_factory=factory, heartbeats=heartbeats,
                                       kill_switch=kill, now=now, alerts=alerts):
        name = HEALTH_NAMES.get(item.key.split(":", 1)[0], item.title)
        checks.append(Check(item.key, not item.red, name,
                            item.detail if not item.red else f"{item.title}。{item.detail}",
                            item.action))

    # ---- 组件心跳 ----
    for w in EXPECTED_WORKERS:
        age = heartbeats.age_seconds(w)
        checks.append(Check(
            f"hb:{w}", age is not None and age <= DEFAULT_STALE_SECONDS,
            f"{WORKER_CN[w]}在报平安",
            f"最近心跳 {age:.0f} 秒前" if age is not None else "从未心跳",
            "先不用:守护会拉闸保护并等待自动拉起;持续失联需要代理排查。"))

    # ---- 服务单元 ----
    for unit in UNITS:
        state = systemctl(unit)
        checks.append(Check(
            f"unit:{unit}", state is None or state == "active", f"服务 {unit} 在运行",
            "非 Linux 主机,跳过" if state is None else f"状态 {state}",
            "需要代理检查该服务(systemctl status 与 journalctl)。"))

    # ---- 磁盘与账本库 ----
    disk_path = rt if rt.exists() else Path.cwd()
    free = shutil.disk_usage(disk_path).free
    checks.append(Check("disk", free >= MIN_FREE_BYTES, "数据盘有余量",
                        f"{disk_path} 剩余 {free / (1 << 30):.1f} GiB(下限 {MIN_FREE_BYTES >> 30} GiB)",
                        "需要代理清理;本系统数据只在运行目录,其他项目的文件不许动。"))
    db_file = engine.url.database if engine.url.get_backend_name() == "sqlite" else None
    if db_file:
        import sqlite3

        size = Path(db_file).stat().st_size if Path(db_file).exists() else 0
        checks.append(Check("db_size", size <= MAX_DB_BYTES, "账本库不臃肿",
                            f"{size / (1 << 20):.1f} MiB(上限 {MAX_DB_BYTES >> 20} MiB)",
                            "需要代理核查是哪张表在长;发件箱旧行每天由摘要任务清理。"))
        try:
            with sqlite3.connect(f"file:{db_file}?mode=ro", uri=True) as conn:
                verdict = conn.execute("PRAGMA quick_check").fetchone()[0]
        except Exception as exc:
            verdict = f"{type(exc).__name__}: {exc}"
        checks.append(Check("db_quick_check", verdict == "ok", "账本库完整",
                            f"PRAGMA quick_check = {verdict}",
                            "需要代理立刻处理:先停交易进程,用最近一次备份核对恢复。"))

    # ---- 模式与授权边界 ----
    if m is SystemMode.SHADOW:
        from backend.app.workers.shadow_cycle import check_shadow_env
        problems = check_shadow_env()
        checks.append(Check("shadow_env", not problems, "影子盘环境干净(无券商账户/凭据/实盘开关)",
                            "、".join(problems) or "干净",
                            "需要你或代理从 /opt/alpha/env 删掉这些键;影子盘在此之前拒绝启动。"))
    if not truth.is_micro_live():
        auth = rt / "LIVE_AUTHORIZATION.json"
        checks.append(Check("no_live_auth", not auth.exists(), "没有实盘授权文件",
                            f"{auth} {'存在' if auth.exists() else '不存在'}",
                            "需要代理查明来源并删除:非微实盘模式下不应出现实盘授权。"))

    # ---- 每日任务:备份与在岗摘要(部署未满 26 小时不算缺席) ----
    deployed = health.frozen_at(rt)
    young = deployed is not None and now - deployed < DAILY_MAX_AGE
    try:
        bk = json.loads((truth.facts_dir() / "backup_status.json").read_text())
        bk_at = datetime.fromisoformat(bk["at"])
        bk_ok = bool(bk.get("ok")) and now - bk_at <= DAILY_MAX_AGE
        bk_txt = f"{bk_at.isoformat()[:16]} {'成功' if bk.get('ok') else '失败'}"
    except Exception:
        bk_ok, bk_txt = False, "尚无备份记录"
    checks.append(Check("backup_recent", bk_ok or young, "账本 26 小时内备份过",
                        bk_txt + ("(部署未满 26 小时)" if young and not bk_ok else ""),
                        "需要代理检查 alpha-backup 定时任务。"))
    with factory() as s:
        digest_n = int(s.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.event_type == "DAILY_DIGEST", OutboxEvent.delivery_status == "DELIVERED",
            OutboxEvent.delivered_at >= now - DAILY_MAX_AGE)) or 0)
        folded = int(s.scalar(select(func.count()).select_from(OutboxEvent).where(
            OutboxEvent.delivery_status.in_(("FOLDED", "FOLDED_REPORTED")),
            OutboxEvent.created_at >= now - timedelta(hours=24))) or 0)
    checks.append(Check("digest_recent", digest_n > 0 or young, "26 小时内送出过每日在岗摘要",
                        f"送出 {digest_n} 封" + ("(部署未满 26 小时)" if young and not digest_n else ""),
                        "需要代理检查 alpha-digest 定时任务与邮件出口;你没收到摘要就说明这台机器可能黑了。"))

    # ---- 告警簿:只靠告警才知道的故障(定时任务失败、盘前自检等)不能藏 ----
    covered = {c.key for c in checks}
    hidden = [a for a in alerts.open_alerts() if a["key"] not in covered]
    checks.append(Check("open_alerts", not hidden, "没有未恢复的其他告警",
                        "、".join(a["title"] for a in hidden) or "无",
                        "需要代理逐条查明;恢复后会自动发『已恢复』。"))
    checks.append(Check("folded", True, "近 24 小时被合并的提醒",
                        f"{folded} 条(每小时最多发 6 封,超出合并成一封汇总)", "不用。"))
    return checks


def conclusion(checks: list[Check]) -> str:
    reds = [c for c in checks if not c.ok]
    return "系统在岗,今天该做的都做了" if not reds else f"有 {len(reds)} 件事需要处理"


def render(checks: list[Check]) -> str:
    lines = [conclusion(checks), ""]
    for c in checks:
        lines.append(f"{'✅' if c.ok else '❌'} {c.title} — {c.detail}"
                     f"|要不要你动手:{'不用' if c.ok else c.action}")
    return "\n".join(lines)


def probe_quotes() -> int:
    """实测:universe + 现金替身逐只取报价,打印价格、美东时间戳、年龄、是否常规时段、是否 ≤ 阈值。"""
    from backend.app import truth
    from backend.app.marketdata.guard import DEFAULT_FRESHNESS_THRESHOLD_SECONDS
    from backend.app.marketdata.yahoo_live import YahooQuoteSource
    from backend.app.strategies.s1_momentum import load_s1_config
    from backend.app.workers.live_cycle import ET, market_open_now

    cfg = load_s1_config(truth.strategy_config_path())
    src = YahooQuoteSource()
    failed = 0
    for sym in dict.fromkeys(list(cfg["universe"]) + [cfg["cash_proxy"]]):
        try:
            q = src.get_quote(sym)
        except Exception as exc:
            failed += 1
            print(f"{sym:5s} 取不到:{exc}")
            continue
        now = datetime.now(timezone.utc)
        age = (now - q.ts_utc).total_seconds()
        ts_et = q.ts_utc.astimezone(ET)
        print(f"{sym:5s} {q.price:>10.2f}  {ts_et:%Y-%m-%d %H:%M:%S} ET  年龄 {age:>8.1f} 秒  "
              f"{'常规时段' if market_open_now(ts_et) else '非常规时段'}  "
              f"{'≤' if age <= DEFAULT_FRESHNESS_THRESHOLD_SECONDS else '>'}"
              f"{DEFAULT_FRESHNESS_THRESHOLD_SECONDS:g} 秒")
    return 1 if failed else 0


def digest(checks: list[Check], *, now: Optional[datetime] = None) -> str:
    """每日在岗摘要入队(不受每小时上限约束),随后清理 30 天前已送达的发件箱行。返回正文。"""
    from backend.app import truth
    from backend.app.adapters.brokers.base import SystemMode
    from backend.app.control_page.dashboard_data import _next_decision, last_eval_summary
    from backend.app.notify.outbox import AlertBook, Outbox
    from backend.app.store.db import create_session_factory, init_engine

    now = now or datetime.now(timezone.utc)
    rt = truth.runtime_dir()
    factory = create_session_factory(init_engine())
    capital = truth.capital_aud()
    try:
        last = json.loads((rt / "equity_history.json").read_text())[-1]
        eq = float(last["equity_aud"])
        eq_txt = f"{eq:,.2f} 澳元(期初基线 {capital:,.0f} 澳元,{eq - capital:+,.2f})"
    except Exception:
        eq_txt = f"尚无净值点(期初基线 {capital:,.0f} 澳元)"
    nd = _next_decision(now, rt)
    opened = AlertBook(factory, now_fn=lambda: now).open_alerts()
    by_key = {c.key: c for c in checks}
    lines = [
        f"模式:{truth.mode_label()}",
        f"{'影子' if truth.mode() is SystemMode.SHADOW else '策略'}净值:{eq_txt}",
        f"最近一次评估:{last_eval_summary(rt, factory)['text']}",
        f"下一次评估:{nd['at_syd']}(悉尼,周{nd['weekday_syd']})",
        f"未恢复的故障:{len(opened)} 件" + (f"({'、'.join(a['title'] for a in opened)})" if opened else ""),
        f"近 24 小时被合并的提醒:{by_key['folded'].detail if 'folded' in by_key else '未知'}",
        f"最近一次账本备份:{by_key['backup_recent'].detail if 'backup_recent' in by_key else '未知'}",
        "",
        f"体检结论:{conclusion(checks)}",
        "(这封摘要每天必发;哪天没收到,说明这台机器可能整个黑了,请找我。)",
    ]
    text = "\n".join(lines)
    outbox = Outbox(factory, now_fn=lambda: now)
    outbox.enqueue(event_type="DAILY_DIGEST", payload={"text": text})
    outbox.prune(30)
    return text


def main(argv: Optional[list[str]] = None, *,
         systemctl: Callable[[str], Optional[str]] = _systemctl_state) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--check-env" in args:
        from backend.app.workers.shadow_cycle import check_shadow_env
        problems = check_shadow_env()
        print("影子盘环境干净" if not problems else "影子盘环境有问题:\n" + "\n".join(problems))
        return 1 if problems else 0
    if "--probe-quotes" in args:
        return probe_quotes()
    checks = collect(systemctl=systemctl)
    if "--digest" in args:
        print(digest(checks))
        return 0
    if "--json" in args:
        print(json.dumps({"conclusion": conclusion(checks),
                          "checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=1))
    else:
        print(render(checks))
    return 0 if all(c.ok for c in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
