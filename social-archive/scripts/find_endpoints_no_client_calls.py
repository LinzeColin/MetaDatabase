#!/usr/bin/env python3
"""服务端开了接口，却没有任何客户端在调（v0.0.0.7）。

## 为什么单开一个

`find_unwired_code.py` 把带装饰器的函数当作「框架注册，本来就没有显式
调用方」放过——对 FastAPI 路由函数来说那是对的：`@app.get(...)` 就是它的
调用方。但它因此看不见另一半问题：

    路由注册了 ✓   服务端能响应 ✓   **而没有任何界面去请求它** ✗

这是「建好了没接上」的第 6 次，前五次是：
failure_copy 词典、unexplained_zero_runs 审计、扩展的 lastResult、
凭据托管 materialize、多租户审计 tenancy_audit。

本次实例：`/v1/storage/status` 与 `/v1/extension/bootstrap` 在 api.py 里
都在，PWA 的 app.js **一次都没调过**。前者意味着存储/配额状态
永远不会出现在界面上——而失败文案词典里明明有 DISK_QUOTA 那一条。

## 判据

对 api.py 里每一个 `@app.<method>("/v1/…")`，在 apps/ 下找有没有人请求它。
路径含 `{参数}` 的按前缀匹配（客户端会拼字符串）。

## 它不保证什么

- 只看 `apps/`（PWA 与扩展）。外部脚本、curl、第三方集成不算客户端。
- 拼接得太碎的调用（`"/v1/" + kind + "/status"`）扫不到。
- **「有人调」不等于「调对了」**，只等于「不是死接口」。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "src/social_archive/api.py"
# **客户端不只有界面。** scripts/ 下的运维脚本（status_server、备份、复制）
# 同样是这些接口的真实调用方。第一版只扫 apps/，把 /v1/jobs、
# /v1/status-projection、/v1/storage/status 等一批全报成死接口——
# **又一次射程写错**，本会话第三次。
CLIENT_DIRS = ("apps", "scripts")

ROUTE = re.compile(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*"(/v1/[^"]*)"')

# 有意不给界面调的接口。每条写清为什么。
NOT_FOR_CLIENTS: dict[str, str] = {
    "/v1/status": "运维/诊断用（sync_health、tenancy、provenance 三个审计挂在这里），不是界面数据源",
    "/v1/health": "探活",
    "/v1/connectors": "连接器目录，目前只有判据在用；界面走 /v1/accounts 那条路",
    "/v1/destinations/obsidian-local/receipts": "扩展的本机 Obsidian 桥回执入口，由桥自己 POST，不在仓内客户端里",
    # —— 下面两条是**真的没人调**，登记在此是为了让「知道」可查，不是让检查器闭嘴 ——
    "/v1/import/markdown": "**没有任何调用方**。界面走的是 /v1/import/social-archiver（ZIP 导入）。这条是早期的单文件导入，未接界面。",
    "/v1/search": "**没有任何调用方**。资料库自己带全文与多维筛选（/v1/library?q=…），这条是它之前的独立搜索接口，已被取代但没删。",
}


def _strip_comments(text: str, suffix: str) -> str:
    """把注释去掉再找调用。

    **注释里提到一个接口不等于有人在调它。** 实测踩到过：
    我在 app.js 里写了一段注释解释「/v1/storage/status 此前没人调」，
    然后把真正的调用改掉，这道门**照样通过**——因为那段注释满足了它。
    判据把自己的说明文字当成了证据。
    """
    lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if suffix in {".js"} and (stripped.startswith("//") or stripped.startswith("*")):
            continue
        if suffix in {".py", ".sh"} and stripped.startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def client_text() -> str:
    chunks: list[str] = []
    for folder in CLIENT_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.suffix in {".js", ".html", ".py", ".sh"} and path.is_file():
                if path.name == Path(__file__).name:
                    continue  # 别把自己的正则和说明当成调用
                try:
                    chunks.append(_strip_comments(path.read_text(encoding="utf-8"), path.suffix))
                except (OSError, UnicodeDecodeError):
                    continue
    return "\n".join(chunks)


def main() -> int:
    api_text = API.read_text(encoding="utf-8")
    blob = client_text()

    routes: dict[str, set[str]] = {}
    for method, path in ROUTE.findall(api_text):
        routes.setdefault(path, set()).add(method.upper())

    dead: list[str] = []
    for path in sorted(routes):
        # 允许按前缀豁免：/v1/connectors 一条即覆盖 /v1/connectors/{id}/run
        if any(path == k or path.startswith(k.rstrip("/") + "/") for k in NOT_FOR_CLIENTS):
            continue
        # 带路径参数的按前缀找：客户端是拼出来的
        probe = path.split("{")[0].rstrip("/")
        if not probe:
            continue
        if probe not in blob:
            dead.append(f"  {','.join(sorted(routes[path])):18s} {path}")

    print(f"api.py 里的 /v1 路由 {len(routes)} 个；客户端目录 {', '.join(CLIENT_DIRS)}")
    if dead:
        print(f"**没有任何界面调用的 {len(dead)} 个**（服务端开着，界面从不请求）：")
        for line in dead:
            print(line)
        print("\n接上它，或写进 NOT_FOR_CLIENTS 并说明为什么界面不该调。")
        return 1
    print("每个接口都至少有一处界面调用。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
