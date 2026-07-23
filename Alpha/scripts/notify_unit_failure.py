#!/usr/bin/env python3
"""定时任务失败自告警(systemd OnFailure 钩子):谁看门人的门,失败也有人知道。

用法(由 alpha-alert@.service 以失败单元名调用):
    python scripts/notify_unit_failure.py <unit-name>
只做一件事:向发件箱入队一封人话告警;绝无其他权限。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNIT_CN = {
    "alpha-rejudge.service": "每日收盘复判",
    "alpha-activate.service": "微实盘自动切换器",
}


def main() -> int:
    unit = sys.argv[1] if len(sys.argv) > 1 else "未知单元"
    from backend.app.notify.outbox import Outbox
    from backend.app.store.db import create_session_factory, init_engine
    ob = Outbox(create_session_factory(init_engine(os.environ["ALPHA_DATABASE_URL"])))
    ob.enqueue(event_type="UNIT_FAILED", payload={"text": (
        f"定时任务「{UNIT_CN.get(unit, unit)}」本次运行失败。\n"
        "影响:当日自动复判/切换可能缺席,交易与风控不受影响(失败关闭原则)。\n"
        "系统日志已留痕,代理会在下次值守时复盘修复;若连续两天收到本邮件,请在会话里提醒一句。")})
    print(f"已入队失败告警: {unit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
