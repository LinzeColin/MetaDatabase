#!/usr/bin/env python3
"""adp-cloud 唯一认可的生产部署入口。

    CLOUDFLARE_API_TOKEN=… python3 deploy/cloudflare/deploy.py

不要直接跑 `npx wrangler deploy`。它不做任何回读：发出去之后没人知道线上跑的
是不是刚构建的这份代码，也没人知道线上的变量还在不在。
2026-08-12 在 WeReadPort 上，裸跑一次就把 8 个仓外变量清空、站点断了 3 分钟。

本脚本：
  1 脏树 / 缺 token -> 拒绝
  2 把 BUILD 戳成与当前源码一致（内容派生，改了必变）
  3 线上有而 wrangler 配置里没有的 plain_text 变量 -> 原样带回去；为空则拒绝部署
  4 部署，然后回读 /build.json：线上 build_id 必须等于刚构建的这份
  5 回读不过 -> 自动 rollback 回上一版，非零退出
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]                      # arxiv-daily-push/
sys.path.insert(0, str(PROJECT / "src"))
from adp.cloudflare_deploy import (            # noqa: E402
    assert_no_empty_carry, check_live_build, collect_plain_text_vars,
    pick_current_deployment, redact, stamp_build, vars_to_carry,
)

WORKER = "adp-cloud"
CONFIG = HERE / "wrangler_cloud.jsonc"
WORKER_SOURCE = HERE / "worker_cloud.js"
SITE = os.environ.get("ADP_DEPLOY_SITE", "https://adp.linzezhang.com")
ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
API_BASE = os.environ.get("ADP_CF_API_BASE", "https://api.cloudflare.com/client/v4")
VERIFY_TRIES, VERIFY_SLEEP = 10, 3             # 有上限的等待（合同 §2.4）

carried: list[tuple[str, str]] = []


def say(message: str) -> None:
    print(redact(f"[deploy] {message}", carried), flush=True)


def fail(message: str) -> "NoReturn":          # noqa: F821
    print(redact(f"[deploy] {message}", carried), file=sys.stderr, flush=True)
    raise SystemExit(1)


TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
if not TOKEN:
    fail("缺少 CLOUDFLARE_API_TOKEN。凭据取用方式见 Governance/cloud-deployment/README.md。")


def cf(path: str):
    request = urllib.request.Request(f"{API_BASE}{path}", headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if not payload.get("success"):
        detail = "；".join(e.get("message", "") for e in payload.get("errors") or [])
        raise RuntimeError(f"Cloudflare API 失败（{path}）：{detail or '未知'}")
    return payload["result"]


def account_id() -> str:
    if ACCOUNT_ID:
        return ACCOUNT_ID
    # 不在脚本里写死账号 id：仓是公开的，能少一份就少一份。
    cache = PROJECT.parent / ".wrangler/cache/wrangler-account.json"
    if cache.exists():
        value = json.loads(cache.read_text("utf-8")).get("account", {}).get("id")
        if value:
            return value
    fail("拿不到 Cloudflare 账号 id：设 CLOUDFLARE_ACCOUNT_ID 环境变量再跑。")


def current_version() -> str:
    result = cf(f"/accounts/{ACCOUNT}/workers/scripts/{WORKER}/deployments")
    return pick_current_deployment(result.get("deployments") or [])


def version_vars(version_id: str) -> dict[str, str]:
    result = cf(f"/accounts/{ACCOUNT}/workers/scripts/{WORKER}/versions/{version_id}")
    return collect_plain_text_vars((result.get("resources") or {}).get("bindings") or result.get("bindings") or [])


def declared_vars() -> set[str]:
    text = "\n".join(line for line in CONFIG.read_text("utf-8").splitlines()
                     if not line.strip().startswith("//"))
    return set((json.loads(text).get("vars") or {}).keys())


def run(argv: list[str], **kwargs):
    return subprocess.run(argv, cwd=PROJECT, check=True, capture_output=True, text=True, **kwargs)


def fetch_json(url: str):
    # 必须显式带 User-Agent：Cloudflare 的 bot 规则会把 urllib 的默认
    # "Python-urllib/3.x" 直接 403 掉（curl 同一个地址是 200）。第一版没带，
    # 于是回读连挂 10 次、把一个**完全正常**的部署自动回滚了 ——
    # 夹具的限制长得和产品坏了一模一样。
    request = urllib.request.Request(url, headers={
        "User-Agent": "ADP-Deploy/1.0 (+https://adp.linzezhang.com)",
        "Accept": "application/json",
        "cache-control": "no-cache",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


# ── 1. 部署前 ──────────────────────────────────────────────────────────────
# 顺序有意为之：最便宜、最能说明问题的检查排最前。
# 第一版把账号 id 解析放在了脏树检查之前，于是脏树时报的是「拿不到账号 id」——
# 用户会去查凭据，而真正的问题是他有没提交的改动。跑反例才看见。
dirty = subprocess.run(["git", "status", "--porcelain", "--", str(PROJECT)],
                       cwd=PROJECT, capture_output=True, text=True).stdout.strip()
if dirty:
    fail(f"工作树不干净，拒绝部署：\n{dirty}")

ACCOUNT = account_id()

try:
    previous_version = current_version()
    live_vars = version_vars(previous_version)
    carried = vars_to_carry(live_vars, declared_vars())
    assert_no_empty_carry(carried)
except Exception as error:                                     # noqa: BLE001
    fail(f"{error}（读的是线上版本 {locals().get('previous_version', '未知')[:8]}）")

say(f"当前线上版本 {previous_version[:8]}；线上 plain_text {len(live_vars)} 个，"
    f"其中配置里没有、需要原样带回去的 {len(carried)} 个"
    + (f"：{'、'.join(name for name, _ in carried)}" if carried else "（无）"))

# ── 2. 戳 BUILD（内容派生，改了必变）────────────────────────────────────────
source = WORKER_SOURCE.read_text("utf-8")
stamped, expected_build_id = stamp_build(source, date.today().isoformat())
if stamped != source:
    WORKER_SOURCE.write_text(stamped, "utf-8")
    fail(f"BUILD 与源码不一致，已就地更新为 {expected_build_id}。"
         f"请 commit 这一处改动后重跑 —— 部署要发的必须是提交过的东西。")
say(f"BUILD 与源码一致：{expected_build_id}")

# ── 3. 部署 ────────────────────────────────────────────────────────────────
say("wrangler deploy（secret 由 Cloudflare 自动保留，不重传）")
argv = ["npx", "wrangler", "deploy", "--config", str(CONFIG)]
for name, value in carried:
    argv += ["--var", f"{name}:{value}"]
try:
    stdout = run(argv).stdout
    say("\n".join(line for line in stdout.splitlines() if "Uploaded" in line or "Current Version" in line))
except subprocess.CalledProcessError as error:
    fail(f"wrangler deploy 失败：{error.stderr or error}")

deployed_version = current_version()
if deployed_version == previous_version:
    fail("部署后版本 id 没变，wrangler 可能没真发出去。")


# ── 4. 回读 ────────────────────────────────────────────────────────────────
def verify_once() -> list[str]:
    problems: list[str] = []
    deployed_vars = version_vars(deployed_version)
    problems += [f"{name} 丢失" for name, _ in carried if name not in deployed_vars]
    problems += [f"{name} 与部署前不一致" for name, value in carried
                 if name in deployed_vars and deployed_vars[name] != value]
    try:
        problems += check_live_build(fetch_json(f"{SITE}/build.json"), expected_build_id)
    except Exception as error:                                 # noqa: BLE001
        problems.append(f"回读 /build.json 失败：{error}")
    return problems


problems: list[str] = []
for attempt in range(1, VERIFY_TRIES + 1):
    problems = verify_once()
    if not problems:
        say(f"第 {attempt}/{VERIFY_TRIES} 次回读通过：线上 build_id = {expected_build_id}")
        break
    if attempt == VERIFY_TRIES:
        break
    say(f"第 {attempt}/{VERIFY_TRIES} 次回读未过（{'；'.join(problems)}），{VERIFY_SLEEP}s 后重试")
    time.sleep(VERIFY_SLEEP)

# ── 5. 不过就回滚 ──────────────────────────────────────────────────────────
if problems:
    say(f"回读失败，自动回滚到 {previous_version[:8]}：{'；'.join(problems)}")
    try:
        run(["npx", "wrangler", "rollback", "--config", str(CONFIG),
             "--version-id", previous_version, "--message", "自动回滚：部署后回读未通过", "-y"])
        fail("已回滚到上一版。站点应已恢复，请查上面的失败原因。")
    except subprocess.CalledProcessError as error:
        fail(f"回滚也失败了，站点可能仍处于坏状态，立刻人工介入：{error.stderr or error}")

say(f"完成：{deployed_version[:8]} 已上线，/build.json 回读确认为 {expected_build_id}。")
