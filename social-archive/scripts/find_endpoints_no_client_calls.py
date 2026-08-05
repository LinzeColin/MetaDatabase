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
- **更要紧的一条：「有调用点」不等于「走得到」。**

  这道门找的是路径字符串在不在客户端代码里，**它看不出那段代码有没有可能执行**。
  2026-08-05 实测到一个现成的例子：`/v1/captures/batch` 在
  `background.js:116` 确确实实被调用，而那一整段在 `mode === "list"` 分支里，
  **四个调用方全都传 `mode: "page"`**——那条分支今天一次都走不到。
  也就是说这道门在这一条上是**绿的，指着一段永远不会执行的代码**。

  没有把它改成可达性分析：那要做数据流，而这道门的价值在于便宜、稳。
  改成钉在别处——`tests/focused/test_the_batch_capture_path_has_no_reachable_caller.py`
  把「今天没有任何调用方传 list」这件事记成判据，**有人接上时它会红**，
  那时再回来更新这里的认知。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# **不能只扫 api.py。** 登录那 7 条路由在 auth.py 里（FastAPI router），
# 这道门从来没看过它——于是「产品里没有登录按钮」这件事一直没被报出来：
# 7 条路由里只有 POST /v1/auth/extension-token 有客户端调用，
# 而 /v1/auth/{provider}/start **零调用**，用户打开页面根本没得点。
# 实测于 Owner 说「我点击也登陆了」而服务端 oauth_identity / session 都是 0 之后。
# 本轮第六次射程写错。
API_FILES = [
    ROOT / "src/social_archive/api.py",
    ROOT / "src/social_archive/auth.py",
]
# **客户端不只有界面。** scripts/ 下的运维脚本（status_server、备份、复制）
# 同样是这些接口的真实调用方。第一版只扫 apps/，把 /v1/jobs、
# /v1/status-projection、/v1/storage/status 等一批全报成死接口——
# **又一次射程写错**，本会话第三次。
CLIENT_DIRS = ("apps", "scripts")

ROUTE = re.compile(r'@(?:app|router)\.(get|post|put|delete|patch)\(\s*"(/[^"]*)"')

# 有意不给界面调的接口。每条写清为什么。
NOT_FOR_CLIENTS: dict[str, str] = {
    "/v1/status": "运维/诊断用（sync_health、tenancy、provenance 三个审计挂在这里），不是界面数据源",
    "/v1/health": "探活",
    "/v1/connectors": "连接器目录，目前只有判据在用；界面走 /v1/accounts 那条路",
    "/v1/destinations/obsidian-local/receipts": "扩展的本机 Obsidian 桥回执入口，由桥自己 POST，不在仓内客户端里",
    # —— 下面两条是**真的没人调**，登记在此是为了让「知道」可查，不是让检查器闭嘴 ——
    "/v1/import/markdown": "**没有任何调用方**。界面走的是 /v1/import/social-archiver（ZIP 导入）。这条是早期的单文件导入，未接界面。",
    "/v1/search": "**没有任何调用方**。资料库自己带全文与多维筛选（/v1/library?q=…），这条是它之前的独立搜索接口，已被取代但没删。",
    "/v1/accounts/{account_id}/sync-runs": (
        "**没有任何调用方。** 界面一律按全局列：`/v1/sync-runs?limit=200`，"
        "再在前端按账号筛。2026-08-05 才发现——此前这道门只比前缀，"
        "客户端某处出现过 `/v1/accounts` 就算它被调过了。"
        "**已知的代价**：全局那条封顶 200 条，某个账号的同步历史一旦被别的账号"
        "挤出前 200，界面就翻不到了；那时候这条按账号列的接口才真正用得上。"
        "登记在此是为了让「知道」可查，不是让检查器闭嘴。"
    ),
    "/v1/jobs": (
        "GET 有真实调用方（status_server）；**POST /v1/jobs/{id}/retry 没有**。"
        "界面上没有任何地方逐条列出下载任务，因此也无从画那颗按钮——"
        "用户目前只能重跑整次同步。这是加了方法维度之后新暴露出来的，"
        "登记在此是为了让「知道」可查，不是让检查器闭嘴。要接的话得先有任务列表界面。"
    ),
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


METHOD_IN_OPTIONS = re.compile(r'method\s*:\s*"(get|post|put|delete|patch)"', re.I)
METHOD_AS_CALL = re.compile(r'\.(get|post|put|delete|patch)\(', re.I)


def methods_near(blob: str, probe: str) -> set[str]:
    """这个路径在客户端里被用哪些 HTTP 方法调过。

    **为什么必须看方法。** 第一版只比对路径字符串，于是
    `GET /v1/credentials`（列出已托管的平台）被判为「有人调」——
    因为同一个前缀出现在别处的 `PUT` 和 `DELETE` 调用里。
    实际上那条 GET 一个调用方都没有，而界面因此永远不知道
    哪些平台存着登录状态，「一键撤销」的按钮也就无从画起。

    窗口取前后各 220 字符：`fetch(url, { method: "DELETE", … })` 这类
    写法里方法名和 URL 通常隔着几十个字符，行内匹配会漏。
    没写方法的按 GET 算——fetch 与 SA.api 的默认值都是 GET。
    """
    found: set[str] = set()
    start = 0
    while True:
        index = blob.find(probe, start)
        if index < 0:
            break
        start = index + len(probe)
        window = blob[max(0, index - 220): index + 220]
        hits = {m.upper() for m in METHOD_IN_OPTIONS.findall(window)}
        hits |= {m.upper() for m in METHOD_AS_CALL.findall(window)}
        found |= hits or {"GET"}
    return found


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
    api_text = "\n".join(p.read_text(encoding="utf-8") for p in API_FILES if p.is_file())
    assert api_text, "一个路由文件都没读到——判据在空转"
    blob = client_text()

    routes: dict[str, set[str]] = {}
    for method, path in ROUTE.findall(api_text):
        routes.setdefault(path, set()).add(method.upper())

    dead: list[str] = []
    for path in sorted(routes):
        # 允许按前缀豁免：/v1/connectors 一条即覆盖 /v1/connectors/{id}/run
        if any(path == k or path.startswith(k.rstrip("/") + "/") for k in NOT_FOR_CLIENTS):
            continue
        # **参数后面还有段的，光比前缀会漏。**
        #
        # 原来一律 `path.split("{")[0]` 取前缀去找。于是
        # `/v1/accounts/{id}/sync-runs` 只要客户端某处出现过 `/v1/accounts`
        # 就算「有人调」——而客户端**从来只按全局列** `/v1/sync-runs`，
        # 那条按账号列的接口一次都没被请求过。2026-08-05 实测捞出来的。
        #
        # 现在按**整条 URL 的形状**找：前缀 + 中间随便什么（客户端是拼出来的）
        # + 参数后面那一段。两头都得对上才算调过。
        prefix = path.split("{")[0].rstrip("/")
        if not prefix:
            continue
        tail = path.rsplit("}", 1)[1] if "}" in path else ""
        if tail:
            shape = re.escape(path.split("{")[0]) + r"[^\s\"'`]*?" + re.escape(tail)
            if not re.search(shape, blob):
                dead.append(f"  {','.join(sorted(routes[path])):18s} {path}"
                            f"（前缀 {prefix} 有人用，但没有一处拼出 …{tail}）")
                continue
        probe = prefix
        if probe not in blob:
            dead.append(f"  {','.join(sorted(routes[path])):18s} {path}")
            continue
        called = methods_near(blob, probe)
        missing = sorted(routes[path] - called)
        if missing:
            dead.append(f"  {','.join(missing):18s} {path}"
                        f"（这个路径有人调，但没人用这个方法：已见 {','.join(sorted(called))}）")

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
