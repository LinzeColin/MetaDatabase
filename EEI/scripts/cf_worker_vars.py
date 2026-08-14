#!/usr/bin/env python3
"""取回 codex-eei 线上那些「仓外」plain_text 变量，供 deploy_cloud.sh 原样带上。

为什么需要它：`wrangler deploy` 是**用配置文件的内容替换线上 vars，不是合并**。
secret 会自动保留，plain_text 不会。2026-08-12 在 WeReadPort 上，照仓里配置裸发一次
就把线上 8 个仓外变量全清了，站点当场断了 3 分钟。

codex-eei 今天线上的 3 个 plain_text（EEI_BUILD_SHA / EEI_BUILD_TIME / EEI_DEPLOY_ID）
都由 deploy_cloud.sh 每次重传，所以现在是安全的。这个脚本管的是**以后**：
哪天有人在 dashboard 上加一个变量，它会被带回去，而不是被静默清掉。

用法：
    cf_worker_vars.py current-version
    cf_worker_vars.py carry-args --version <id> [--skip NAME ...]

carry-args 每行输出一个 wrangler 参数（`--var` 与 `NAME:VALUE` 交替），
好让 bash 直接 mapfile 成数组。值不会被打印到别处。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

WORKER = os.environ.get("EEI_WORKER_NAME", "codex-eei")
API_BASE = os.environ.get("EEI_CF_API_BASE", "https://api.cloudflare.com/client/v4")


def die(message: str) -> "NoReturn":  # noqa: F821
    print(f"[cf-vars] {message}", file=sys.stderr)
    raise SystemExit(1)


def token() -> str:
    value = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not value:
        die("缺少 CLOUDFLARE_API_TOKEN。凭据取用方式见 Governance/cloud-deployment/README.md。")
    return value


def account_id() -> str:
    value = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    if value:
        return value
    # 不在脚本里写死账号 id：仓是公开的。落到仓里已有的 wrangler 缓存，再没有就明说。
    cache = Path(__file__).resolve().parents[2] / ".wrangler/cache/wrangler-account.json"
    if cache.exists():
        found = json.loads(cache.read_text("utf-8")).get("account", {}).get("id")
        if found:
            return found
    die("拿不到 Cloudflare 账号 id：设 CLOUDFLARE_ACCOUNT_ID 再跑。")


def cf(path: str):
    request = urllib.request.Request(f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token()}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not payload.get("success"):
        detail = "；".join(e.get("message", "") for e in payload.get("errors") or [])
        die(f"Cloudflare API 失败（{path}）：{detail or '未知'}")
    return payload["result"]


def pick_current_deployment(deployments) -> str:
    """按 created_on 排。

    别用 [0] 也别用 [-1]：`wrangler deployments list` 打印是升序（最老在前），
    而 REST API 返回是降序（最新在前）。按时间排就不依赖任一端的顺序约定。
    """
    rows = [
        (item.get("created_on") or "", item["versions"][0]["version_id"])
        for item in deployments or []
        if (item or {}).get("versions") and item["versions"][0].get("version_id")
    ]
    if not rows:
        die("取不到当前线上版本 id。")
    return max(rows)[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("current-version")
    carry = sub.add_parser("carry-args")
    carry.add_argument("--version", required=True)
    carry.add_argument("--skip", action="append", default=[])
    args = parser.parse_args()

    account = account_id()
    if args.command == "current-version":
        result = cf(f"/accounts/{account}/workers/scripts/{WORKER}/deployments")
        print(pick_current_deployment(result.get("deployments") or []))
        return

    result = cf(f"/accounts/{account}/workers/scripts/{WORKER}/versions/{args.version}")
    bindings = (result.get("resources") or {}).get("bindings") or result.get("bindings") or []
    skip = set(args.skip)
    for binding in sorted(bindings, key=lambda b: b.get("name") or ""):
        if binding.get("type") != "plain_text":
            continue
        name = binding.get("name") or ""
        if not name or name in skip:
            continue
        value = binding.get("text") or ""
        if not value.strip():
            die(f"线上变量 {name} 为空。不部署 —— 空值等于没有。")
        print("--var")
        print(f"{name}:{value}")


if __name__ == "__main__":
    main()
