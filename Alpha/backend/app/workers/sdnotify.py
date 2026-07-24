"""systemd 看门狗通知(零依赖实现)。

进程每拍发 WATCHDOG=1,systemd 在 WatchdogSec 内收不到就杀掉重启——
专治"进程活着但卡死"(2026-07-23 事故形态:网关闪断后重启的进程卡死在
初始化 7 小时,心跳全无而 systemd 认为它健康)。无 NOTIFY_SOCKET(本地/
测试环境)时静默无操作,绝不影响业务路径。
"""

from __future__ import annotations

import os
import socket


def sd_notify(state: str) -> bool:
    addr = os.environ.get("NOTIFY_SOCKET")
    if not addr:
        return False
    try:
        if addr.startswith("@"):
            addr = "\0" + addr[1:]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            s.connect(addr)
            s.send(state.encode())
        finally:
            s.close()
        return True
    except Exception:
        return False
