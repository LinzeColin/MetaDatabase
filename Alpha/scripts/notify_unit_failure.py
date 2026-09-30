#!/usr/bin/env python3
"""定时任务失败自告警(systemd OnFailure 钩子):谁看门人的门,失败也有人知道。

用法:
    python scripts/notify_unit_failure.py <unit-name>        # alpha-alert@.service 在失败时调用
    python scripts/notify_unit_failure.py --ok <unit-name>   # 各定时任务 ExecStartPost 在成功后调用
经告警状态簿去重:同一单元连续失败只发一封,成功一次发一封「已恢复」,下次失败再发。绝无其他权限。
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

UNIT_CN = {
    "alpha-rejudge.service": "每日收盘复判",
    "alpha-activate.service": "微实盘自动切换器",
    "alpha-equity-snapshot.service": "净值快照",
    "alpha-preflight.service": "盘前自检",
    "alpha-backup.service": "账本备份",
    "alpha-digest.service": "每日摘要",
}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ok = "--ok" in args
    names = [a for a in args if a != "--ok"]
    unit = names[0] if names else "未知单元"
    from backend.app.notify.outbox import AlertBook
    from backend.app.store.db import create_session_factory, init_engine

    cn = UNIT_CN.get(unit, unit)
    state = AlertBook(create_session_factory(init_engine())).observe(
        f"unit:{unit}", not ok, event_type="UNIT_FAILED", payload={
            "title": f"定时任务「{cn}」运行失败",
            "text": (f"定时任务「{cn}」本次运行失败。\n"
                     "影响:这一项定时工作本次缺席;交易与风控不受影响(失败关闭原则)。\n"
                     "同一故障只提醒这一次;下次运行成功你会收到一封『已恢复』。"
                     "系统日志已留痕,代理会在下次值守时复盘修复。")})
    print(f"{unit}: {'成功' if ok else '失败'} {state or '(状态未变,不发信)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
