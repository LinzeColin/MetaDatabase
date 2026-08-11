#!/usr/bin/env python3
r"""把他库里那 56 条「标题是播放进度」的 B 站条目修回真标题（2026-08-12）。

## 坏成什么样

他打开档案馆，B 站那 103 条里有 **56 条**的标题长这样：

    06:26/12:57
    21:52/23:12

那是 B 站播放器上的时间，不是标题。全部来自 history 那条路
（`browser_account_mirror` 镜像他登录后的历史页时，形状读取挑中了每行的
播放进度元素）。**他库里超过一半的 B 站条目认不出是什么。**

## 为什么现在能修（原来以为不能）

原判断是「要修得等他登录后的历史页」。那是对**取数侧**说的——
要知道标题在哪个元素上，确实得看那一页。

但**已经进来的这 56 条不用**：它们每一条的 `canonical_url` 里都带着 BV 号
（实测 56/56），而 B 站的公开接口 `x/web-interface/view?bvid=…`
**不需要登录**就能拿回真标题和作者。实测三条：

    BV111QuBPEo2 → 为什么孩子打游戏能连续6小时不动，写作业8分钟就开始发呆？
    BV13DRiB4Eyw → 吞噬爱马仕：凭空消失的百亿股份与世纪资本恶战【硅谷101】
    BV15r4y1F7jU → 《云上的中国》第1集：云上的数字商业【…】

零费用、不碰他的登录态、不出他的浏览器之外的任何凭据。

## 边界

- **只改标题为播放进度、且 URL 里有 BV 号的那些**。别的一律不碰。
- 改之前把原值写进 `metadata_json.title_before_repair`，**可回滚**。
- 作者为空时顺带补上；作者已有值就不动（不覆盖他已有的东西）。
- 默认 `--dry-run`：先看清楚要改哪 56 条、改成什么，再谈落盘。
- 每条之间 sleep，别把公开接口打急了。

## 这不修取数侧

下一次 history 同步仍然会写进播放进度——那个要等他登录后的页面才能定位。
**这一条如实记着**，别让「库里干净了」被读成「管道修好了」。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"
TIMESTAMP_TITLE = re.compile(r"^\d{1,2}:\d{2}(/\d{1,2}:\d{2})?$")
BV = re.compile(r"/video/(BV[0-9A-Za-z]+)")
API = "https://api.bilibili.com/x/web-interface/view?bvid={bv}"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}


# 这几个码表示稿件真的没了，重试无用；其余失败是暂时的（限流/抖动），必须重试。
GONE_FOR_GOOD = {62002, -404, 62004}


def real_title(bv: str, attempts: int = 3) -> tuple[str, str] | str | None:
    """拿真标题和作者。

    `(标题, 作者)` = 拿到了；字符串 = 确定没了；None = 这次没拿到。

    **必须区分「没了」和「这次没拿到」**：全量跑 56 条时有 4 条失败，
    逐个复查发现只有 1 条是 code=62002「稿件不可见」，另外 3 条单独查一切正常——
    它们只是被限流了。混成一个 None，就会把 3 条能修的白白留着，
    还在报告里写成「查不回来」。
    """
    last = None
    for attempt in range(attempts):
        request = urllib.request.Request(API.format(bv=bv), headers=HEAD)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
        except Exception as error:                           # noqa: BLE001
            last = error.__class__.__name__
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code")
        if code in GONE_FOR_GOOD:
            return f"稿件已不可见（code={code}）"
        if code != 0:
            last = f"code={code}"
            time.sleep(1.5 * (attempt + 1))
            continue
        data = payload.get("data") or {}
        title = str(data.get("title") or "").strip()
        author = str((data.get("owner") or {}).get("name") or "").strip()
        if title:
            return (title, author)
        last = "接口回了 0 但没有标题"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="修回被写成播放进度的标题")
    parser.add_argument("--apply", action="store_true",
                        help="真的落盘（默认只看不改）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条（试跑用）")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()

    con = sqlite3.connect(args.db if args.apply else f"file:{args.db}?mode=ro",
                          uri=not args.apply)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "select id, title, canonical_url, author_name, metadata_json"
        " from content where platform='bilibili'")]

    targets = []
    for row in rows:
        if not TIMESTAMP_TITLE.fullmatch(str(row["title"] or "").strip()):
            continue
        found = BV.search(str(row["canonical_url"] or ""))
        if found:
            targets.append((row, found.group(1)))
    if args.limit:
        targets = targets[:args.limit]

    changed, unresolved = [], []
    for row, bv in targets:
        got = real_title(bv)
        time.sleep(0.7)                      # 别把公开接口打急了
        if isinstance(got, str):
            unresolved.append({"id": row["id"], "bv": bv, "old_title": row["title"],
                               "why": got, "kind": "gone_for_good"})
            continue
        if got is None:
            unresolved.append({"id": row["id"], "bv": bv, "old_title": row["title"],
                               "why": "重试 3 次仍没拿到（多半是限流）", "kind": "transient"})
            continue
        title, author = got
        changed.append({"id": row["id"], "bv": bv, "old_title": row["title"],
                        "new_title": title,
                        "author_before": row["author_name"], "author_after": author})
        if not args.apply:
            continue
        # **解析不了就跳过这一条，不要用 {} 覆盖回去。**
        #
        # 第一版写的是「解析失败 → meta = {}」，然后照样把 {} 写回
        # `metadata_json`——那会把这一行原有的元数据整个抹掉。
        # 修标题修掉别的东西，比不修还糟。
        try:
            meta = json.loads(row["metadata_json"] or "{}")
            if not isinstance(meta, dict):
                raise ValueError("metadata_json 不是对象")
        except Exception as error:                           # noqa: BLE001
            unresolved.append({"id": row["id"], "bv": bv, "old_title": row["title"],
                               "why": f"metadata_json 读不动（{error.__class__.__name__}），"
                                      "跳过以免抹掉原有元数据"})
            changed.pop()
            continue
        # **原值留着**：这一步必须可回滚。
        meta["title_before_repair"] = row["title"]
        meta["title_repaired_from"] = "bilibili public view api"
        con.execute(
            "update content set title=?, author_name=coalesce(nullif(author_name,''),?),"
            " metadata_json=? where id=?",
            (title, author or None, json.dumps(meta, ensure_ascii=False), row["id"]))
    if args.apply:
        con.commit()

    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何东西）",
        "bilibili_rows": len(rows),
        "titles_that_are_playback_timestamps": len(targets),
        "resolved_from_the_public_api": len(changed),
        "could_not_resolve": unresolved,
        "samples": changed[:5],
        "reversible": "原标题写进 metadata_json.title_before_repair",
        "what_this_does_not_fix":
            "**取数侧没修**：下一次 history 同步仍会写进播放进度——"
            "要定位真标题在哪个元素上，得等他登录后的历史页。库里干净了 ≠ 管道修好了。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
