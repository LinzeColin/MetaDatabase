"""武装/解除「立即评估」开关(owner 2026-07-26:"不能用真实时间等待浪费")。

用法:
  python scripts/arm_force_eval.py --arm     # 武装:下一个开市时刻立即评估并按纪律下单
  python scripts/arm_force_eval.py --disarm  # 解除
  python scripts/arm_force_eval.py           # 只看状态

边界(不可越界):只改变"什么时候评估",**不放宽任何风控**——总敞口 3000 澳元、单笔≤90%、
每小时≤5 笔、行情新鲜度、辖区、失败关闭一律照旧;休市时不会触发;用后即焚只生效一次。
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ET = ZoneInfo("America/New_York")
SYD = ZoneInfo("Australia/Sydney")
MARKER = Path(os.environ.get("ALPHA_RUNTIME_DIR", "runtime")) / "FORCE_EVAL.txt"


def _next_open_hint(now_et: datetime) -> str:
    from datetime import timedelta

    from backend.app.workers.live_cycle import market_open_now
    if market_open_now(now_et):
        return "美股现在就开着 → 下一拍(≤30 秒)即评估"
    cand = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    while cand <= now_et or cand.weekday() >= 5:
        cand = (cand + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
    syd = cand.astimezone(SYD)
    return f"下一个开市:{cand:%m-%d %H:%M} 纽约 = {syd:%m月%d日 %H:%M} 悉尼"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="store_true")
    ap.add_argument("--disarm", action="store_true")
    a = ap.parse_args()
    now_et = datetime.now(timezone.utc).astimezone(ET)

    if a.arm:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(datetime.now(timezone.utc).isoformat())
        print(f"✅ 已武装立即评估。{_next_open_hint(now_et)}")
        print("   风控一律照旧(敞口/单笔/频控/行情新鲜度/失败关闭);用后即焚,只生效一次。")
        try:
            from backend.app.notify.outbox import Outbox
            from backend.app.store.db import create_session_factory, init_engine
            Outbox(create_session_factory(init_engine())).enqueue(
                event_type="INCIDENT_REPORT", payload={"text":
                    "【立即评估已武装】按你的指令,系统不再枯等周二:下一个开市时刻会立刻做一次"
                    "策略评估,并按纪律下单(全部硬风控照旧)。下单前后你都会收到邮件。\n"
                    f"{_next_open_hint(now_et)}"})
        except Exception as exc:
            print("   (提醒邮件入队失败,不影响触发本身:", exc, ")")
    elif a.disarm:
        existed = MARKER.exists()
        MARKER.unlink(missing_ok=True)
        print("✅ 已解除立即评估。" if existed else "本来就没武装。")
    else:
        print(("状态:已武装(等下一个开市时刻)" if MARKER.exists() else "状态:未武装(按周二例行节拍)"))
        print("  ", _next_open_hint(now_et))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
