#!/usr/bin/env python3
"""界面在调一条服务端没有的接口（v0.0.0.7）。

## 为什么单开一个

`find_endpoints_no_client_calls.py` 查的是**另一个方向**：服务端开了接口、
没人调。反过来这一边一直没人管——而它更贵：

    界面上有一颗按钮 → 它打一个不存在的地址 → 用户点了得到一句英文报错

2026-08-06 实测抓到的：`apps/pwa/app.js` 的「批量修改分类」表单打的是
`POST /v1/library/classify`，而 api.py 里 `/v1/library` 下只有四条路由，
**没有 classify**。实测回 **405 Method Not Allowed**。
那颗按钮从产品有它那天起就没成功过一次，而 1000 多条判据、23 道门
没有一个看得见——**因为没有任何一条判据去点它**。

## 判据

把服务端所有路由收齐（`@app.<method>(...)` 与 `APIRouter(prefix=...)` 下的
`@router.<method>(...)` 都要，**少收一类就会把好路由报成坏的**），
再把 `apps/` 与 `scripts/` 里出现的 `/v1/...` 字面量收齐，逐个对。

对法要宽一点，因为客户端是拼出来的：

  · 路由里的 `{参数}` 当成「一段任意字符」；
  · 客户端字面量若是某条路由的**前缀**（`"/v1/library/" + id`），算命中。

**宽是有代价的**：一个拼错成 `/v1/librari/...` 的地址不会被前缀规则救回来
（它不是任何路由的前缀），所以还是抓得到；但 `/v1/library/` 后面接什么
它都不看——那一段得靠别的判据。

## 它不保证什么

- 只看字面量。完全动态拼出来的（`"/v1/" + kind`）扫不到。
- 方法是**猜**出来的：取地址前后各 220 字符里的 `method: "POST"` 或 `.post(`，
  都没有就按 GET 算（fetch 与 SA.api 的默认）。拼得太散的写法会猜错。
- 不保证调用参数对。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_FILES = ("src/social_archive/api.py", "src/social_archive/auth.py")
CLIENT_DIRS = ("apps", "scripts")

APP_ROUTE = re.compile(r'@app\.(get|post|put|delete|patch)\(\s*"(/[^"]*)"')
ROUTER_PREFIX = re.compile(r'APIRouter\(\s*prefix="([^"]*)"')
ROUTER_ROUTE = re.compile(r'@router\.(get|post|put|delete|patch)\(\s*"([^"]*)"')
CLIENT_PATH = re.compile(r'"(/v1/[A-Za-z0-9/_\-]*)')


def _routes() -> list[tuple[str, str]]:
    """(方法, 路径) 一对一对地收。**只收路径是不够的**——见文件头。"""
    found: list[tuple[str, str]] = []
    for name in API_FILES:
        path = ROOT / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        found += [(method.upper(), route) for method, route in APP_ROUTE.findall(text)]
        # **带前缀的 router 一定要算上。**
        # 第一版漏了它，于是 /v1/auth/me 这类好端端的地址被报成「不存在」——
        # 5 条误报，而它们在生产上明明是通的。
        prefixes = ROUTER_PREFIX.findall(text)
        prefix = prefixes[0] if prefixes else ""
        found += [(method.upper(), prefix + route)
                  for method, route in ROUTER_ROUTE.findall(text)]
    return sorted(set(found))


def _client_paths() -> list[tuple[str, int, str, str]]:
    out: list[tuple[str, int, str, str]] = []
    for folder in CLIENT_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in (".js", ".html", ".py", ".sh"):
                continue
            # **别的检查器把路由名当数据存着**（豁免表、清单），那不是「在调它」。
            # 第一版把 `find_endpoints_no_client_calls.py` 里的 `/v1/health`
            # 报成了「调了一个不存在的地址」——那是它的豁免字典的键，
            # 而真实路由是 `/health`（没有 /v1 前缀）。
            # **演练与验收脚本里那些地址是「收到的」，不是「发出的」。**
            # 它们起假服务端、然后断言收到了什么：
            #     if path == "/v1/captures" and request.method == "POST":   ← 在收
            #     posted = [r for r in received if "/v1/captures" in r["path"]]
            # 按客户端算的话会被读成 GET /v1/captures，报成「调了不存在的地址」。
            if (path.name == Path(__file__).name or "__pycache__" in str(path)
                    or path.name.startswith(("find_", "check_", "list_", "probe_"))
                    or path.name.endswith("_drill.py")
                    or path.name == "browser_acceptance.py"):
                continue
            # **窗口要开在整份文件上，不能只看当前这一行。**
            # 第一版把 `line` 当成搜索范围，于是
            #     await SA.api("/v1/captures/batch", {
            #       method: "POST",
            # 这种写法一律被读成 GET —— 9 处 POST 全被报成「调了不存在的地址」。
            blob = path.read_text(encoding="utf-8", errors="ignore")
            for match in CLIENT_PATH.finditer(blob):
                line_start = blob.rfind("\n", 0, match.start()) + 1
                line_end = blob.find("\n", match.start())
                line = blob[line_start: line_end if line_end > 0 else len(blob)]
                if line.lstrip().startswith(("//", "*", "#")):
                    continue
                out.append((str(path.relative_to(ROOT)),
                            blob.count("\n", 0, match.start()) + 1,
                            match.group(1), _method_near(blob, match.start())))
    return out


# 客户端那一侧的方法：`{ method: "POST" }` 或 `.post(`，取地址前后各 220 字符。
METHOD_IN_OPTIONS = re.compile(r'method\s*:\s*"(get|post|put|delete|patch)"', re.I)
METHOD_AS_CALL = re.compile(r"\.(get|post|put|delete|patch)\(", re.I)


def _method_near(blob: str, index: int) -> str:
    window = blob[max(0, index - 220): index + 220]
    hits = {m.upper() for m in METHOD_IN_OPTIONS.findall(window)}
    hits |= {m.upper() for m in METHOD_AS_CALL.findall(window)}
    # fetch 与 SA.api 的默认都是 GET
    return sorted(hits)[0] if hits else "GET"


def _matches(method: str, path: str, routes: list[tuple[str, str]]) -> bool:
    """**方法也要对上。**

    第一版只比路径，于是它抓不到自己要抓的那个缺陷：
    `POST /v1/library/classify` 的**路径**能被 `GET /v1/library/{content_id}`
    的形状匹配上（`{参数}` 当成任意一段），而真实失败是 405——方法不对。
    一道抓不到自己要抓的那件事的门，比没有更坏。
    """
    for route_method, route in routes:
        if route_method != method:
            continue
        if re.match("^" + re.sub(r"\{[^}]+\}", "[^/]+", route) + "$", path):
            return True
        if path.rstrip("/") and route.startswith(path.rstrip("/")):
            return True
    return False


def main() -> int:
    routes = _routes()
    calls = _client_paths()
    # **收不齐就直接失败。** 路由收成 0 条的话，每一个调用都会被报成「不存在」；
    # 调用收成 0 条的话，这道门会报「全都对得上」——两种都不是通过。
    if len(routes) < 20 or not calls:
        print(json.dumps({"status": "FAIL", "error_code": "SCOPE_LOOKS_WRONG",
                          "routes_found": len(routes), "client_paths_found": len(calls),
                          "message_zh": "路由或调用收得太少——**这不是通过**，是这道门的射程失效了。"},
                         ensure_ascii=False, indent=2))
        return 4

    missing = [
        {"where": f"{where}:{line}", "call": f"{method} {path}"}
        for where, line, path, method in calls if not _matches(method, path, routes)
    ]
    print(json.dumps({
        "status": "PASS" if not missing else "FAIL",
        "routes_found": len(routes),
        "distinct_client_calls": len({(m, p) for _, _, p, m in calls}),
        "calls_to_nothing": missing,
        "message_zh": ("界面调的每一个地址，服务端都有。"
                       if not missing else
                       "**界面在调服务端没有的地址**——那颗按钮点下去只会得到一句报错。"),
        "what_this_does_not_prove": "只看字面量、不查方法；POST 打一条只有 GET 的路由，这道门看不出来。",
    }, ensure_ascii=False, indent=2))
    return 0 if not missing else 4


if __name__ == "__main__":
    sys.exit(main())
