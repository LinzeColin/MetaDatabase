#!/usr/bin/env python3
r"""一个**真平台**的收藏，真的进到档案馆里（2026-08-12）。

## 这条链此前从来没有被一次走完过

Owner 那句话的第一条是「**多平台聚合真的发生**：至少一个真实平台的收藏
能自动读进档案馆」。仓里有两个演练各证一半，而**没有一个把两半接起来**：

    bilibili_acquisition_drill   打 B 站真接口，证明「读得到」——
                                 全文 0 次 POST，读到的东西哪儿也没去
    from_zero_drill              整条链走通，证明「进得去」——
                                 而它连的是仓里自己写的假站

两个都绿，合起来仍然答不了那句话。**这个演练就是那一步**：

    真 B 站公开收藏夹 → 插件自己的 readFolder → 真的 POST 进档案馆 → 从库里读回来

## 边界（这几条是这个演练能不能被信的全部理由）

· **不碰他的库。** 档案馆起在生产机上的一次性容器里，数据根是容器内 tmpfs，
  跑完就删；他那份 `/opt/social-archive/runtime/data` 一个字节都不动。
· **不带登录态。** 读的是**公开**收藏夹，不粘 Cookie、不用令牌——
  正是 Owner 要求的「零费用、不要他粘任何东西」那一条。
· 取数用的是**插件里那一份** `bilibili-reader.js`，不是这里另抄一遍；
  入库用的是 `/v1/captures/batch`，和 background.js 送条目走的是同一条路。
· 它只证明 bilibili 这一个平台。别的平台要登录态才看得见收藏夹，
  那只能发生在 Owner 自己的浏览器里——**这条边界写在结论里，不许含糊**。
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 部署占着工作树时，这个演练可以先从 scratchpad 里跑：--root 指回仓即可。
# 落进仓之后这个参数仍然有用（换一个检出跑同一条链）。
CONTAINER = "social-archive-real-platform-drill"
PORT = 8791
TOKEN = secrets.token_urlsafe(24)
# 一个**公开**收藏夹（不需要登录）。和 bilibili_acquisition_drill 用的是同一个——
# 第一版我随手编了一个 id，读回来是 BILIBILI_FOLDER_NOT_VISIBLE，
# 差点被我读成「B 站这条路今天不通」。常量要从已有真源抄，别现编。
PUBLIC_FOLDER = "4026748432"

READ_LIVE = """
const R = require("./apps/browser-extension/content/bilibili-reader.js");
(async () => {
  const read = await R.readFolder("%(folder)s", { pageSize: 10 });
  const items = (read.items || []).slice(0, %(limit)s);
  process.stdout.write(JSON.stringify({
    ok: read.ok, failureCode: read.failureCode || null,
    declared: read.expected, folder_title: read.folderTitle || "",
    items: items.map(i => ({
      url: i.url, title: i.title || null, author_name: i.author_name || null,
      published_at: i.published_at || null,
    })),
  }));
})().catch(e => process.stdout.write(JSON.stringify({ _error: String(e && e.message || e) })));
"""


def ssh(host: str, command: str, check: bool = True) -> str:
    done = subprocess.run(["ssh", "-o", "ConnectTimeout=25", host, command],
                          capture_output=True, text=True, check=False)
    if check and done.returncode != 0:
        raise RuntimeError(f"ssh 失败：{(done.stderr or done.stdout)[-300:]}")
    return done.stdout


def curl(host: str, method: str, path: str, body: dict | None = None) -> dict:
    """打那个一次性容器。**令牌只在生产机内部出现**，不进日志。"""
    parts = ["curl", "-sS", "-X", method, f"http://127.0.0.1:{PORT}{path}",
             "-H", f"'Authorization: Bearer {TOKEN}'"]
    if body is not None:
        parts += ["-H", "'Content-Type: application/json'", "--data-binary", "@-"]
        raw = ssh(host, f"{' '.join(parts)} <<'JSON'\n{json.dumps(body, ensure_ascii=False)}\nJSON")
    else:
        raw = ssh(host, " ".join(parts))
    for line in reversed((raw or "").strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"_raw": (raw or "")[-300:]}


def read_real_folder(limit: int) -> dict:
    """在**本机**跑插件那份 reader，打 B 站真接口。"""
    script = READ_LIVE % {"folder": PUBLIC_FOLDER, "limit": limit}
    done = subprocess.run(["node", "-e", script], cwd=ROOT,
                          capture_output=True, text=True, check=False)
    try:
        return json.loads((done.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"_error": f"读不懂 node 的输出：{(done.stdout + done.stderr)[-300:]}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="真平台的收藏真的进档案馆")
    parser.add_argument("--host", default=None)
    parser.add_argument("--root", default=None, help="仓的位置（默认按脚本所在处推）")
    parser.add_argument("--version", default=None, help="期望容器自报的版本")
    parser.add_argument("--limit", type=int, default=5, help="真取几条（够证明就行）")
    args = parser.parse_args()
    global ROOT
    if args.root:
        ROOT = Path(args.root).resolve()
    host = args.host or (ROOT / "deploy/PRODUCTION_HOST").read_text(encoding="utf-8").strip()
    version = args.version or (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    image = f"social-archive/core:{version}"

    steps: list[dict] = []
    problems: list[str] = []

    def note(name: str, measured, expectation: str, ok: bool) -> None:
        steps.append({"step": name, "measured": measured, "expected": expectation, "ok": bool(ok)})
        if not ok:
            problems.append(f"{name}：期望{expectation}，实际 {measured!r}")

    # ① 真平台那一头
    live = read_real_folder(args.limit)
    items = live.get("items") or []
    note("从 B 站**真接口**读到公开收藏夹",
         {"ok": live.get("ok"), "declared": live.get("declared"),
          "read": len(items), "folder_title": live.get("folder_title"),
          "error": live.get("_error") or live.get("failureCode")},
         f"读到 ≥1 条（不带登录态）", bool(live.get("ok")) and bool(items))
    if not items:
        print(json.dumps({"status": "FAIL", "error_code": "NO_LIVE_ITEMS",
                          "steps": steps, "problems": problems,
                          "message_zh": "B 站那头没读到东西——**这不是产品缺陷也不算通过**，"
                                        "先看是不是这台机器到不了 api.bilibili.com"},
                         ensure_ascii=False, indent=2))
        return 4
    openable = [i for i in items if re.match(r"^https://www\.bilibili\.com/video/BV", i.get("url") or "")]
    note("每条都是能在浏览器里打开的网址", f"{len(openable)}/{len(items)}",
         "全部是 https://www.bilibili.com/video/BV…", len(openable) == len(items))

    # ② 档案馆那一头：一次性容器，碰不到他的库
    ssh(host, f"docker rm -f {CONTAINER} >/dev/null 2>&1 || true", check=False)
    ssh(host, " ".join([
        "docker", "run", "-d", "--name", CONTAINER,
        "--tmpfs", "/var/lib/social-archive:rw,size=64m,mode=1777",
        "-e", f"SOCIAL_ARCHIVE_API_TOKEN={TOKEN}",
        "-e", "SOCIAL_ARCHIVE_DATA_ROOT=/var/lib/social-archive",
        "-e", "SOCIAL_ARCHIVE_RUNTIME_DB=/var/lib/social-archive/db.sqlite3",
        "-e", "SOCIAL_ARCHIVE_STAGING_ROOT=/var/lib/social-archive/staging",
        "-e", "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT=/var/lib/social-archive/private",
        "-e", "SOCIAL_ARCHIVE_WATCH_ROOT=/var/lib/social-archive/import",
        "-p", f"127.0.0.1:{PORT}:8765", image, "social-archive-api",
    ]))
    try:
        health: dict = {}
        for _ in range(30):
            health = curl(host, "GET", "/health")
            if health.get("version"):
                break
            ssh(host, "sleep 1", check=False)
        note("一次性档案馆起来了，报的是刚部署那一版", health.get("version"),
             f"= {version}", health.get("version") == version)

        empty = curl(host, "GET", "/v1/library")
        note("它一开始是空的", empty.get("total"), "0 条", empty.get("total") == 0)

        # ③ 送进去——走 background.js 送条目的同一条路
        body = {"items": [{
            "platform": "bilibili",
            "url": item["url"],
            "relation_type": "saved",
            "collection_key": live.get("folder_title") or "",
            "title": item.get("title"),
            "author_name": item.get("author_name"),
            "published_at": item.get("published_at"),
            "media_urls": [],
            "raw_metadata": {"capture_source": "real_platform_drill"},
            "requested_levels": ["L0"],
            "destination_ids": [],
        } for item in items]}
        batch = curl(host, "POST", "/v1/captures/batch", body)
        saved = batch.get("items") or []
        note("真条目送进档案馆", {"saved": len(saved), "errors": batch.get("errors") or []},
             f"{len(items)} 条全进去", len(saved) == len(items))

        # ④ 从库里读回来——**比标题，不只比条数**
        library = curl(host, "GET", "/v1/library")
        rows = library.get("items") or []
        in_library = {str(row.get("title") or "").strip() for row in rows}
        wanted = {str(i.get("title") or "").strip() for i in items if i.get("title")}
        missing = sorted(wanted - in_library)
        note("库里读得回来，且标题就是 B 站上那几条",
             {"total": library.get("total"), "missing_titles": missing[:3]},
             f"{len(items)} 条、标题一条不缺", library.get("total") == len(items) and not missing)

        with_author = [row for row in rows if str(row.get("author_name") or "").strip()]
        note("作者也跟着进来了", f"{len(with_author)}/{len(rows)}",
             "每条都有作者（B 站那头给得出）", len(with_author) == len(rows))
    finally:
        ssh(host, f"docker rm -f {CONTAINER} >/dev/null 2>&1 || true", check=False)

    print(json.dumps({
        "status": "FAIL" if problems else "PASS",
        "platform": "bilibili",
        "folder_title": live.get("folder_title"),
        "items_read_from_the_real_platform": len(items),
        "steps": steps,
        "problems": problems,
        "boundary_zh":
            "档案馆起在生产机上的一次性容器里（容器内 tmpfs，跑完就删）——**他的库一个字节没动**；"
            "读的是 B 站**公开**收藏夹，不带登录态、不粘 Cookie。",
        "what_this_does_not_prove":
            "只证明 bilibili 这一个平台。其余平台的收藏夹要登录态才看得见，"
            "那只能发生在 Owner 自己的浏览器里——这个演练答不了那一维。",
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 4


if __name__ == "__main__":
    sys.exit(main())
