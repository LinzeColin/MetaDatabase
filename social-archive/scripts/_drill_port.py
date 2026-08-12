"""演练要用的那个本机端口被占着时，说人话（2026-08-11）。

## 为什么值得单开一个文件

**十一个演练共用 `127.0.0.1:8765`**，因为扩展的 `host_permissions` 里本机源
只有这一个——换个口，内容脚本就注不进去，那些以「插件装着」为前提的屏一个都走不到。

它们在部署里是顺序跑的，本不该撞。但只要有一个的 Chrome / HTTP 服务端
关得慢一点（或者有人手动跑过一次没收干净），下一个就会撞上：

    OSError: [Errno 48] Address already in use

而 run_all_drills 只看得到「没有回 JSON（exit 1）」，部署于是中止，
提示是「真 Chrome 演练没全过」——**一句和真因毫无关系的话**。
实测代价：连着两次部署被这个撞停，第一次报的还是「下一步那张卡没指出他真正的下一步」
（旧插件没被认出来），我照着那个假象查了一轮。

## 它做两件事

1. **等一小会儿**：上一个演练的端口通常一两秒就放开了；
2. 等不到就打印一段**说得出下一步**的 JSON，而不是抛一个 traceback。

> 只等、不抢。绝不去杀占着口的进程——那可能是 Owner 自己在跑的东西。
"""

from __future__ import annotations

import json
import socket
import sys
import time


def wait_until_free(port: int, *, seconds: float = 25.0, host: str = "127.0.0.1") -> bool:
    """等这个端口空出来。空出来返回 True，等不到返回 False。"""
    deadline = time.monotonic() + seconds
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, port))
                return True
            except OSError:
                pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def require_free(port: int, *, drill: str, seconds: float = 25.0) -> None:
    """端口不空就带着**能照着做的下一步**退出，不留一个 traceback 给上游。"""
    if wait_until_free(port, seconds=seconds):
        return
    print(json.dumps({
        "status": "FAIL",
        "error_code": "DRILL_PORT_BUSY",
        "port": port,
        "drill": drill,
        "message_zh": (
            f"本机 {port} 端口被占着，等了 {seconds:.0f} 秒还没放开。"
            "**这不是产品缺陷，是演练之间没让开**——十一个演练共用这个口"
            "（扩展的 host_permissions 里本机源只有它）。"),
        "next_step_zh": (
            f"看谁占着：lsof -nP -iTCP:{port} -sTCP:LISTEN；"
            "多半是上一个演练的 Chrome 或它的假档案馆还没退干净。"
            "等几秒重跑即可；**别去杀不认识的进程**。"),
    }, ensure_ascii=False, indent=2))
    sys.exit(3)
