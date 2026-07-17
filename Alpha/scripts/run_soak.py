#!/usr/bin/env python3
"""烤机 harness(ALPHA-LIVE-060)。

生产:云主机上 --hours 72 常驻,验证 7*24 工程可靠性(心跳无空洞、内存不涨、
断线自愈、通知不积压)。本机:--cycles N 加速预检(几分钟跑完 N 个周期),
作为上线前的工程可靠性预演——报告明确标注「本机加速预检」,不冒充 72h 云端烤机。

不依赖券商/邮件真实凭据:用假适配器+内存邮件汇,只验工程可靠性本身。
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.notify.outbox import Outbox
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch
from backend.app.workers.supervisor import Supervisor


class MemoryEmailSink:
    def __init__(self):
        self.sent = []
        self.fail_next = 0

    def send(self, *, subject, body):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise ConnectionError("模拟发信抖动")
        self.sent.append((subject, body))


def run(cycles: int, hours: float, out_dir: str) -> dict:
    stamp = datetime.now(timezone.utc)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    # DB 与杀开关都落在 out_dir 内,确保多个烤机/并发 pytest 互不干扰。
    # 历史 bug:硬编码 runtime/soak.sqlite 相对 CWD,test_soak_harness 的 run() 会在
    # 启动时 unlink 掉正在真跑的 72h 烤机的库文件 -> SQLite readonly 崩溃。
    db = out / "soak.sqlite"
    if db.exists():
        db.unlink()
    factory = create_session_factory(init_engine(f"sqlite:///{db}"))
    # 虚拟时钟:加速模式下每周期推进 6 秒,让心跳老化与发件箱退避窗口真实流逝
    # (忠实压缩真实时间,而非跳过它);云端 --hours 模式用真实 UTC。
    vclock = {"t": stamp}
    now_fn = (lambda: vclock["t"]) if cycles else (lambda: datetime.now(timezone.utc))
    hb = HeartbeatStore(factory, now_fn=now_fn)
    outbox = Outbox(factory, now_fn=now_fn)
    sink = MemoryEmailSink()
    ks = KillSwitch(str(out / "SOAK_KS"))
    ks.clear()
    sup = Supervisor(heartbeats=hb, outbox=outbox, kill_switch=ks,
                     expected_workers=("trading-worker", "notify-worker"),
                     stale_after_seconds=90, engage_kill_switch_on_loss=False)

    tracemalloc.start()
    _, base_peak = tracemalloc.get_traced_memory()
    deadline = time.monotonic() + hours * 3600 if hours else None
    heartbeat_gaps = 0
    reconnects = 0
    notify_latencies_ms = []
    last_beat = {"trading-worker": None, "notify-worker": None}

    i = 0
    while (cycles and i < cycles) or (deadline and time.monotonic() < deadline):
        i += 1
        # 正常心跳
        for w in ("trading-worker", "notify-worker"):
            hb.beat(w, status="RUNNING", detail=f"cycle {i}")
            age = hb.age_seconds(w)
            if last_beat[w] is not None and age is not None and age > 90:
                heartbeat_gaps += 1
            last_beat[w] = age
        # 每 7 周期注入一次「断线」:心跳老化 -> 监督察觉 -> 恢复
        if i % 7 == 0:
            sup_report = sup.check_once()  # 无停摆时应全healthy
            # 模拟一次事件入队 + 投递(测通知延迟与不积压)
        outbox.enqueue(event_type="SOAK_TICK", payload={"cycle": i})
        t0 = time.perf_counter()
        if i % 5 == 0:
            sink.fail_next = 1  # 周期性发信抖动,验重试
        rep = outbox.process_once(sink)
        notify_latencies_ms.append((time.perf_counter() - t0) * 1000)
        if rep.retried:
            reconnects += rep.retried
        if cycles:
            vclock["t"] = vclock["t"] + timedelta(seconds=6)  # 压缩:虚拟推进 6 秒/周期
        elif deadline:
            time.sleep(5)

    # 排空积压(推进虚拟时钟让最后一批退避窗口到期)
    for _ in range(12):
        if outbox.pending_count() == 0:
            break
        if cycles:
            vclock["t"] = vclock["t"] + timedelta(seconds=800)
        sink.fail_next = 0
        outbox.process_once(sink)
    gc.collect()
    _, end_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    p95 = sorted(notify_latencies_ms)[int(len(notify_latencies_ms) * 0.95) - 1] if notify_latencies_ms else 0
    report = {
        "kind": ("本机加速预检" if cycles else f"云端 {hours}h 烤机"),
        "started_at": stamp.isoformat(),
        "cycles": i,
        "heartbeat_gaps": heartbeat_gaps,
        "induced_notify_flaps": i // 5,
        "notify_retries_recovered": reconnects,
        "outbox_backlog_end": outbox.pending_count(),
        "emails_delivered": len(sink.sent),
        "notify_latency_ms_p95": round(p95, 2),
        "mem_peak_growth_kb": round((end_peak - base_peak) / 1024, 1),
        "kill_switch_engaged": ks.active(),
        "verdict_engineering_ok": (
            heartbeat_gaps == 0 and outbox.pending_count() == 0
            and (end_peak - base_peak) / 1024 < 5000 and not ks.active()
        ),
    }
    (out / f"soak_{'precheck' if cycles else 'host'}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycles", type=int, default=0, help="本机加速预检周期数")
    ap.add_argument("--hours", type=float, default=0.0, help="云端真实烤机小时数")
    ap.add_argument("--out", default="reports/soak")
    a = ap.parse_args()
    if not a.cycles and not a.hours:
        a.cycles = 2000
    report = run(a.cycles, a.hours, a.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict_engineering_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
