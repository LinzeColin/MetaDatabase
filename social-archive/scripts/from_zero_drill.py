#!/usr/bin/env python3
r"""从零到能用，在**刚部署的那个真镜像**上走一遍（2026-08-11）。

Owner：「账号内存删除，增加删除按钮，从零测试能不能用，你自己先测试一下」。

## 为什么要有这个脚本

这条链我在真镜像上手跑通过一次，而**证据只留在终端里**——
换一台机器、换一个人、下一个版本，都没法再跑一遍。
（`evidence-must-live-in-the-repo-not-the-terminal`：采集要做成可重跑命令。）

`tests/focused/test_from_zero_to_working_over_http.py` 打的是路由，但跑在
本机 `TestClient` 上。它证明不了**生产上那个镜像**里的那一份代码也是这样。
这个脚本补的就是那一格。

## 它怎么跑，以及为什么碰不到他的数据

在生产主机上起一个**一次性容器**，用的是刚部署的那个镜像 tag，
数据根指向容器内的临时目录（`--tmpfs`），端口只绑回环的一个高位口。
跑完 `docker rm -f`。

    他的库    /opt/social-archive/runtime/data   ← 一个字节都不碰
    这一轮    容器内 tmpfs，容器一删就没了

## 走的这条链（17 步；数字由报告现算，别手写——我上一版写成了 18）

    GET    /health                              这个容器起来了吗、报的哪一版
    GET    /v1/library                          空库（从零）
    POST   /v1/accounts/connect/start           连一个抖音
    POST   /v1/accounts/connect/douyin/complete
    POST   /v1/sync-runs/{id}/batches           送一条终批 → run 要到 completed
    GET    /v1/library                          看得见它，且标题/作者都是清干净的
    GET    /v1/accounts                         连上之后 auto_sync 得是开着的
    DELETE /v1/accounts/{id}                    断开——**内容一条不许少**
    POST   …/connect/douyin/complete            重连 → auto_sync 跟着恢复
    POST   /v1/accounts/{id}/forget             删除并清空
    GET    /v1/library、/v1/accounts            都空了
    （再连一次、再同步一次，确认删完还能从头来，内容回得来）

中间那三步（连上会自己跑 / 断开不删东西 / 重连恢复自动同步）是**他今天真正
卡着的那一段**：生产实况是三个账号全 disconnected、auto_sync 关，
最后一次同步 2026-08-04 报 PLATFORM_PERMISSION_MISSING。
使用说明写着「连上之后自动同步会跟着恢复」——那句话得在真镜像上验过。

★ 第一版我把完成连接的地址写成 `/v1/accounts/douyin/complete`（少了 `connect/`），
整段静默走空还报成功——所以每一步的断言都盯**它该产生的那个变化**，不盯 200。
"""

from __future__ import annotations

import argparse
import json
import secrets
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTAINER = "sa-from-zero-drill"
PORT = 18099
# **每轮现生成，不写死。**
#
# 第一版这里是一个写死的字符串常量，被 scripts/scan_plaintext_credentials.py
# 判成明文凭据（S2 必须停）——而它是对的：仓里不该有令牌形状的常量，
# 哪怕它只喂给一个跑完就删的容器。
#
# ★ 改成现生成之后它**又红了一次**，这回红在我上面那行解释里：
#   我把那个被删掉的常量原样写进了注释。判据不看你是不是在讲道理，
#   只看仓里有没有那个形状的串——它同样是对的。
TOKEN = secrets.token_urlsafe(24)


def _host() -> str:
    return (ROOT / "deploy/PRODUCTION_HOST").read_text(encoding="utf-8").strip()


def _version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def ssh(host: str, command: str, *, check: bool = True) -> str:
    """在生产主机上跑一条命令。

    **不接管道。** `pipe-to-tail-hides-the-exit-code`：管道会把成败吃掉，
    而这个脚本的每一步都要靠退出码判断。
    """
    done = subprocess.run(["ssh", host, command], capture_output=True, text=True, check=False)
    if check and done.returncode != 0:
        raise RuntimeError(f"远端命令失败（exit {done.returncode}）：{command}\n"
                           f"{done.stdout[-600:]}{done.stderr[-600:]}")
    return done.stdout


def curl(host: str, method: str, path: str, body: dict | None = None,
         *, check: bool = True) -> dict:
    """从生产主机上打那个一次性容器的回环端口。

    `check=False` 给起容器时的等待循环用——那几秒里 curl 必然先报 exit 7
    （连不上），那是**预期**，不是失败。
    """
    parts = ["curl", "-sS", "-X", method, f"http://127.0.0.1:{PORT}{path}",
             "-H", f"Authorization: Bearer {TOKEN}"]
    if body is not None:
        parts += ["-H", "Content-Type: application/json", "-d", json.dumps(body, ensure_ascii=False)]
    raw = ssh(host, " ".join(shlex.quote(p) for p in parts), check=check)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:400]}


def run(host: str, version: str) -> int:
    image = f"social-archive/core:{version}"
    steps: list[dict] = []
    problems: list[str] = []

    def note(name: str, measured, expectation: str, ok: bool) -> None:
        steps.append({"step": name, "measured": measured, "expected": expectation,
                      "ok": bool(ok)})
        if not ok:
            problems.append(f"{name}：期望{expectation}，实际 {measured!r}")

    ssh(host, f"docker rm -f {CONTAINER} >/dev/null 2>&1 || true", check=False)
    container_id = ssh(host, " ".join([
        "docker", "run", "-d", "--name", CONTAINER,   # 不加 --rm：崩了要能读日志
        # **mode=1777**：docker 的 --tmpfs 默认挂成 root 拥有、0755，
        # 而镜像里进程是 uid 10001——实测容器起来就死在
        # `PermissionError: /var/lib/social-archive/staging`，`--rm` 还把日志一起带走了。
        "--tmpfs", "/var/lib/social-archive:rw,size=64m,mode=1777",
        "-e", f"SOCIAL_ARCHIVE_API_TOKEN={TOKEN}",
        "-e", "SOCIAL_ARCHIVE_DATA_ROOT=/var/lib/social-archive",
        "-e", "SOCIAL_ARCHIVE_RUNTIME_DB=/var/lib/social-archive/db.sqlite3",
        "-e", "SOCIAL_ARCHIVE_STAGING_ROOT=/var/lib/social-archive/staging",
        "-e", "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT=/var/lib/social-archive/private",
        "-e", "SOCIAL_ARCHIVE_WATCH_ROOT=/var/lib/social-archive/import",
        "-p", f"127.0.0.1:{PORT}:8765", image, "social-archive-api",
    ])).strip()
    try:
        health: dict = {}
        for _ in range(30):
            health = curl(host, "GET", "/health", check=False)
            if health.get("status") or health.get("version"):
                break
            ssh(host, "sleep 1", check=False)
        if not (health.get("status") or health.get("version")):
            # **「起不来」和「起来了但答得不对」长得一样。** 把容器日志带出来，
            # 否则报出去的只有一句「连不上」，下一个人得从头查起。
            logs = ssh(host, f"docker logs {CONTAINER} 2>&1 | tail -25", check=False)
            note("容器起来了、报的是刚部署那一版",
                 {"health": health, "container_logs": logs[-1200:]}, f"= {version}", False)
        else:
            note("容器起来了、报的是刚部署那一版", health.get("version"), f"= {version}",
                 health.get("version") == version)

        empty = curl(host, "GET", "/v1/library")
        note("从零：库是空的", empty.get("total"), "0 条", empty.get("total") == 0)

        started = curl(host, "POST", "/v1/accounts/connect/start",
                       {"platform": "douyin", "auth_method": "browser_session"})
        connection_ref = started.get("connection_ref")
        note("能开始连一个抖音", connection_ref or started, "一个 connection_ref",
             bool(connection_ref))

        connected = curl(host, "POST", "/v1/accounts/connect/douyin/complete", {
            "connection_ref": connection_ref, "external_account_id": "owner",
            "display_name": "抖音", "verified": True,
            "metadata": {"auth_method": "browser_session"}})
        account_id = connected.get("account_id")
        run_id = (connected.get("first_sync") or {}).get("sync_run_id")
        note("连接完成，拿到账号和一次首同步", {"account_id": account_id, "sync_run_id": run_id},
             "两个都非空", bool(account_id) and bool(run_id))

        batch = curl(host, "POST", f"/v1/sync-runs/{run_id}/batches", {
            "relation_type": "favorite", "scope_type": "relation",
            "completeness": "complete", "has_more": False,
            "items": [{"platform": "douyin",
                       "url": "https://www.douyin.com/video/769",
                       "external_content_id": "769", "relation_type": "favorite",
                       "title": "2.0万真正的一次性她来了真正的一次性她来了",
                       "author_name": "26.6万"}]})
        note("送完终批，那次同步跑到 completed", batch.get("status"), "completed",
             batch.get("status") == "completed")

        filled = curl(host, "GET", "/v1/library")
        items = filled.get("items", [])
        note("库里看得见它", filled.get("total"), "1 条", filled.get("total") == 1)
        # **标题和作者是他真会看到的两个字段**——生产上这两处都出过事
        # （标题「2.0万文案文案」、作者装着点赞数「26.6万」）。
        note("标题清干净了", items[0].get("title") if items else None,
             "真正的一次性她来了",
             bool(items) and items[0].get("title") == "真正的一次性她来了")
        note("点赞数没被当成作者", items[0].get("author_name") if items else "（没有条目）",
             "空", bool(items) and not items[0].get("author_name"))

        # ── 他今天真正卡在的那一段：断开之后能不能连回来、连回来会不会自己跑 ──
        #
        # 生产实况（2026-08-11 读的）：三个账号全是 disconnected、auto_sync=关，
        # 最后一次同步 2026-08-04 报 PLATFORM_PERMISSION_MISSING。
        # 所以「重连之后自动同步会跟着恢复」这句话（使用说明里写着）
        # **必须在真镜像上验过**，不能只在源码里看到默认值是 True。
        listed = curl(host, "GET", "/v1/accounts")
        mine = [a for a in listed.get("items", []) if a.get("id") == account_id]
        note("连上之后它自己会跑（auto_sync 开着）",
             {"state": mine[0].get("connection_state") if mine else None,
              "auto_sync": mine[0].get("auto_sync_enabled") if mine else None},
             "connected 且 auto_sync=True",
             bool(mine) and mine[0].get("connection_state") == "connected"
             and mine[0].get("auto_sync_enabled") is True)

        curl(host, "DELETE", f"/v1/accounts/{account_id}")
        after_disconnect = curl(host, "GET", "/v1/accounts")
        dropped = [a for a in after_disconnect.get("items", []) if a.get("id") == account_id]
        kept = curl(host, "GET", "/v1/library")
        note("断开只是不再自己跑，**内容一条不少**",
             {"state": dropped[0].get("connection_state") if dropped else None,
              "auto_sync": dropped[0].get("auto_sync_enabled") if dropped else None,
              "库里还有": kept.get("total")},
             "disconnected + auto_sync 关 + 内容还在",
             bool(dropped) and dropped[0].get("connection_state") == "disconnected"
             and dropped[0].get("auto_sync_enabled") is False and kept.get("total") == 1)

        back = curl(host, "POST", "/v1/accounts/connect/start",
                    {"platform": "douyin", "auth_method": "browser_session"})
        curl(host, "POST", "/v1/accounts/connect/douyin/complete", {
            "connection_ref": back.get("connection_ref"), "external_account_id": "owner",
            "display_name": "抖音", "verified": True,
            "metadata": {"auth_method": "browser_session"}})
        revived = [a for a in curl(host, "GET", "/v1/accounts").get("items", [])
                   if a.get("id") == account_id]
        note("重连之后自动同步真的恢复了（说明书就是这么写的）",
             {"state": revived[0].get("connection_state") if revived else None,
              "auto_sync": revived[0].get("auto_sync_enabled") if revived else None},
             "connected 且 auto_sync=True",
             bool(revived) and revived[0].get("connection_state") == "connected"
             and revived[0].get("auto_sync_enabled") is True)

        forgotten = curl(host, "POST", f"/v1/accounts/{account_id}/forget")
        note("删除并清空真的删了", forgotten.get("removed_content"), "1 条",
             forgotten.get("removed_content") == 1)

        # ★ **这两步是空默认值最容易骗人的地方。**（empty-default-swallows-unknown）
        # 上面那一段要是整段静默走空，这里读到的也是「0 条 / 没有账号」——
        # 于是「删干净了」在**什么都没建过**的情况下也是绿的。
        # 所以它们的前提写成「刚才真的建出来过」，建不出来就不许算通过。
        created_for_real = bool(account_id) and filled.get("total") == 1
        after = curl(host, "GET", "/v1/library")
        note("删完库空了", {"total": after.get("total"), "刚才真建出来过": created_for_real},
             "0 条，且这一步有前提", created_for_real and after.get("total") == 0)
        accounts = curl(host, "GET", "/v1/accounts")
        ids = [a.get("id") for a in accounts.get("items", [])]
        note("删完账号也不在了", {"账号": ids, "刚才真建出来过": created_for_real},
             "不含刚才那个账号", created_for_real and account_id not in ids)

        again = curl(host, "POST", "/v1/accounts/connect/start",
                     {"platform": "douyin", "auth_method": "browser_session"})
        again_done = curl(host, "POST", "/v1/accounts/connect/douyin/complete", {
            "connection_ref": again.get("connection_ref"), "external_account_id": "owner",
            "display_name": "抖音", "verified": True,
            "metadata": {"auth_method": "browser_session"}})
        again_run = (again_done.get("first_sync") or {}).get("sync_run_id")
        note("删完还能从头再连一次", again_run, "一个非空 sync_run id", bool(again_run))
        again_batch = curl(host, "POST", f"/v1/sync-runs/{again_run}/batches", {
            "relation_type": "favorite", "scope_type": "relation",
            "completeness": "complete", "has_more": False,
            "items": [{"platform": "douyin",
                       "url": "https://www.douyin.com/video/769",
                       "external_content_id": "769", "relation_type": "favorite",
                       "title": "2.0万真正的一次性她来了真正的一次性她来了",
                       "author_name": "26.6万"}]})
        note("重连之后同步还是跑得完", again_batch.get("status"), "completed",
             again_batch.get("status") == "completed")
        back = curl(host, "GET", "/v1/library")
        note("重新同步把内容带回来了", back.get("total"), "1 条", back.get("total") == 1)
    finally:
        ssh(host, f"docker rm -f {CONTAINER} >/dev/null 2>&1 || true", check=False)

    result = {
        "status": "FAIL" if problems else "PASS",
        "host": host, "image": image, "container_id": container_id[:12],
        "what_this_proves": "刚部署的那个镜像里，从空库到连接、同步、看得见、"
                            "删除并清空、再从头来一遍，整条链在 HTTP 上真的走得通",
        "what_this_does_not_prove": "不碰他自己的库（这一轮跑在容器内 tmpfs 上），"
                                    "所以不证明他那份数据的状态",
        "steps": steps,
        "problems": problems,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="在真镜像上从零走一遍")
    parser.add_argument("--host", default=None)
    parser.add_argument("--version", default=None)
    args = parser.parse_args()
    try:
        return run(args.host or _host(), args.version or _version())
    except RuntimeError as error:
        print(json.dumps({"status": "FAIL", "error_code": "REMOTE_STEP_FAILED",
                          "detail": str(error)[:800]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
