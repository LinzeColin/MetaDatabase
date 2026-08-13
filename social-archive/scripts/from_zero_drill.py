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
import re
import secrets
import shlex
import subprocess
import time
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


class TransportError(RuntimeError):
    """ssh 那一层断了——**和「产品坏了」是两件事**，报出去要分得清。"""


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
    # **exit 255 是 ssh 自己断了，不是那条命令失败。**（2026-08-11 实测）
    #
    # 一次部署里这个演练报「从零到能用这条链走不通」而中止，日志里是
    # `exit 255 · Connection closed by … port 22`——**连接掉了**，
    # 单独重跑立刻 PASS。把它报成产品缺陷，是又一张假脸
    # （同 `_drill_port` 那次端口撞车）。
    #
    # 掉线就重连一次；还不行就带着**说清是连接问题**的错误码退出。
    if done.returncode == 255:
        time.sleep(3)
        done = subprocess.run(["ssh", host, command],
                              capture_output=True, text=True, check=False)
        if done.returncode == 255:
            raise TransportError(
                f"ssh 连不上或中途断了（exit 255）：{host}\n"
                f"{(done.stderr or '')[-300:]}")
    if check and done.returncode != 0:
        # **报错时不许把令牌带出来。**（2026-08-11，被 secret_scan.py 抓到）
        # 失败的命令里含 `Authorization: Bearer <令牌>`，原样写进 evidence/ 和
        # 部署日志之后，仓里就躺着一个令牌形状的串——哪怕它只是这一轮临时容器的。
        # 打印之前一律抹掉：这个习惯迟早会印到一个真的上。
        safe = re.sub(r"Bearer [A-Za-z0-9_\-]+", "Bearer <已抹去>", command)
        raise RuntimeError(f"远端命令失败（exit {done.returncode}）：{safe}\n"
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

        # **这一批刻意带上两样他库里出过问题的东西**（2026-08-13）：
        #
        #   · `collection_name` + `external_collection_id` —— 他库里那 3 行
        #     `platform_collection` 的 external id 是 NULL，联表永远匹配不上，
        #     于是「收藏夹」那一列 194 条全是「未分组」。客户端那一侧
        #     8f32ef76 已经改成"发名字必带 id"，**而这条链从没被端到端走过**。
        #   · 地址上的埋点 —— 他库里 127 条带着 `source=` / `spm_id_from`。
        #     今天改了规范化，**同样没有端到端证据**。
        #
        # 两样都验在「他重连之后会怎样」这个问题上，而这个演练正好走的就是那条路。
        batch = curl(host, "POST", f"/v1/sync-runs/{run_id}/batches", {
            "relation_type": "favorite", "scope_type": "relation",
            "completeness": "complete", "has_more": False,
            "collection_name": "我的收藏夹",
            "external_collection_id": "dy:favlist:1",
            "items": [{"platform": "douyin",
                       "url": "https://www.douyin.com/video/769?source=Baiduspider-sdc",
                       "external_content_id": "769", "relation_type": "favorite",
                       "collection_key": "dy:favlist:1",
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

        # **收藏夹那一列要显示得出名字。**（2026-08-13）
        # 他库里 194 条全是「未分组」——因为 platform_collection 的
        # external id 是 NULL，联表匹配不上。这一条走的是修好之后的那条链。
        note("收藏夹显示得出名字（不是「未分组」）",
             items[0].get("primary_collection") if items else "（没有条目）",
             "我的收藏夹",
             bool(items) and items[0].get("primary_collection") == "我的收藏夹")

        # **存下来的地址不许带埋点。**（2026-08-13）
        # 送进去的是 `...?source=Baiduspider-sdc`，存下来该是干净的。
        stored_url = items[0].get("canonical_url") if items else ""
        note("地址上的埋点被洗掉了", stored_url, "不含 source=",
             bool(items) and "source=" not in str(stored_url))

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
    except TransportError as error:
        print(json.dumps({
            "status": "FAIL", "error_code": "SSH_TRANSPORT_FAILED",
            "detail": str(error)[:600],
            "message_zh": "**这不是产品缺陷，是 ssh 断了**（已自动重连过一次）。"
                          "重跑一次这个演练即可；老是这样再去查网络或那台机器的 sshd。",
        }, ensure_ascii=False, indent=2))
        return 3
    except RuntimeError as error:
        print(json.dumps({"status": "FAIL", "error_code": "REMOTE_STEP_FAILED",
                          "detail": str(error)[:800]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
