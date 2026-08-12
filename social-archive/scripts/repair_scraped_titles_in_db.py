#!/usr/bin/env python3
r"""把生产库里从页面上抓歪的标题修回真标题（2026-08-12）。

## 两类坏标题，修法完全不同

**一类：正文抓到了，只是抓重了。**

    23.0万极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd极限三选一，你喜欢哪个？ #肉腿微胖 #肉腿ootd

真标题就在这串里，重复本身就是证据。**不联网、不需要他登录**就能修好。
生产实测 11 条，全部是抖音——而抖音恰恰是没有公开接口的那个平台，
所以这 11 条要么这样修，要么永远不修。

**二类：正文根本没抓到，整串都是页面零件。**

    06:26/12:57      播放器上的时间
    已看完            界面标签
    6.6万 / 646       只剩一个数

本地无从修起，只能拿链接去外面查。B 站有公开接口（免登录、零费用）；
抖音没有，所以抖音的这一类**修不了**，如实留着。

## 我上一轮把范围划小了

上一轮这个脚本只认第二类里的 `MM:SS` 一种形状，报「56 → 1」。
那句话对**那一种形状**是真的，而我把它说成了「他的标题修好了」——不是。
同一批页面抓下来的还有另外 37 条，以及上面那 11 条抖音抓重的，一条都没碰。

判据也划错过一次：第一版按「以计数开头就砍前缀」，会把这条正当标题啃掉一个字——

    14万亿巨额放水+50万亿存款到期，微观体感寒冷，钱到底去哪了？   ← 「14万亿」是他要说的话

现在的顺序是**先看正文重不重复，重复了才认定前面那截是页面上的**。判据在
`social_archive.title_repair`，和入口那道校验是**同一份实现**，不许各写一套。

## 边界

- 只改判定得出来的那些，**别的一律不碰**。
- 原标题写进 `metadata_json.title_before_repair`，**可回滚**。
- `metadata_json` 解析不动就跳过这一条，**绝不用 `{}` 覆盖回去**（会抹掉别的元数据）。
- 作者为空时顺带补上；作者已有值就不动。
- 默认干跑，先把要改的每一条打出来看。

## 这修的是存量

抓重那一类**入口已经堵上了**（`CaptureRequest` 上的校验），下次同步不会再写进来。
播放进度那一类入口是**置空**——不会再写进坏的，但也换不回真的，
真标题在历史页哪个元素上仍然要等他登录后的那一页。
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from social_archive.title_repair import is_all_chrome_no_title, undouble_title  # noqa: E402

DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"
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
    for attempt in range(attempts):
        request = urllib.request.Request(API.format(bv=bv), headers=HEAD)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read())
        except Exception:                                    # noqa: BLE001
            time.sleep(1.5 * (attempt + 1))
            continue
        code = payload.get("code")
        if code in GONE_FOR_GOOD:
            return f"稿件已不可见（code={code}）"
        if code != 0:
            time.sleep(1.5 * (attempt + 1))
            continue
        data = payload.get("data") or {}
        title = str(data.get("title") or "").strip()
        author = str((data.get("owner") or {}).get("name") or "").strip()
        if title:
            return (title, author)
    return None


def _write(con: sqlite3.Connection, row: dict, title: str, author: str, source: str) -> str | None:
    """落盘一条，顺带把原值留下。返回 None 表示写成了，否则是跳过的理由。

    **解析不了就跳过，不要用 `{}` 覆盖回去**——第一版那样写会把这一行原有的
    元数据整个抹掉。修标题修掉别的东西，比不修还糟。
    """
    try:
        meta = json.loads(row["metadata_json"] or "{}")
        if not isinstance(meta, dict):
            raise ValueError("metadata_json 不是对象")
    except Exception as error:                               # noqa: BLE001
        return f"metadata_json 读不动（{error.__class__.__name__}），跳过以免抹掉原有元数据"
    meta["title_before_repair"] = row["title"]
    meta["title_repaired_from"] = source
    con.execute(
        "update content set title=?, author_name=coalesce(nullif(author_name,''),?),"
        " metadata_json=? where id=?",
        (title, author or None, json.dumps(meta, ensure_ascii=False), row["id"]))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="把从页面上抓歪的标题修回真标题")
    parser.add_argument("--apply", action="store_true", help="真的落盘（默认只看不改）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条（试跑用）")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()

    con = sqlite3.connect(args.db if args.apply else f"file:{args.db}?mode=ro",
                          uri=not args.apply)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "select id, platform, title, canonical_url, author_name, metadata_json from content")]

    doubled, all_chrome = [], []
    for row in rows:
        title = str(row["title"] or "")
        repaired = undouble_title(title)
        if repaired and repaired.strip() != title.strip():
            doubled.append((row, repaired))
        elif is_all_chrome_no_title(title):
            found = BV.search(str(row["canonical_url"] or ""))
            all_chrome.append((row, found.group(1) if found else None))
    if args.limit:
        doubled, all_chrome = doubled[:args.limit], all_chrome[:args.limit]

    fixed_locally, fixed_from_api, unresolved = [], [], []

    # 第一趟：抓重的。不联网，所有平台都能修。
    for row, repaired in doubled:
        if args.apply:
            skipped = _write(con, row, repaired, "", "去掉页面上多抓的那一遍")
            if skipped:
                unresolved.append({"id": row["id"], "why": skipped, "kind": "metadata_unreadable"})
                continue
        fixed_locally.append({"id": row["id"], "platform": row["platform"],
                              "old": str(row["title"])[:40], "new": repaired[:40]})

    # 第二趟：整串都是页面零件的。只有 B 站查得回来。
    for row, bv in all_chrome:
        if not bv:
            unresolved.append({"id": row["id"], "platform": row["platform"],
                               "old": str(row["title"])[:24],
                               "why": "没有 BV 号（抖音没有公开接口，要他的登录态）",
                               "kind": "no_public_source"})
            continue
        got = real_title(bv)
        time.sleep(0.7)                                      # 别把公开接口打急了
        if isinstance(got, str):
            unresolved.append({"id": row["id"], "bv": bv, "why": got, "kind": "gone_for_good"})
            continue
        if got is None:
            unresolved.append({"id": row["id"], "bv": bv,
                               "why": "重试 3 次仍没拿到（多半是限流）", "kind": "transient"})
            continue
        title, author = got
        if args.apply:
            skipped = _write(con, row, title, author, "bilibili public view api")
            if skipped:
                unresolved.append({"id": row["id"], "bv": bv, "why": skipped,
                                   "kind": "metadata_unreadable"})
                continue
        fixed_from_api.append({"id": row["id"], "old": str(row["title"])[:22], "new": title[:44]})
    if args.apply:
        con.commit()

    kinds: dict[str, int] = {}
    for item in unresolved:
        kinds[item["kind"]] = kinds.get(item["kind"], 0) + 1
    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何东西）",
        "rows": len(rows),
        "scraped_twice_fixed_without_network": len(fixed_locally),
        "all_chrome_looked_up_from_the_public_api": len(fixed_from_api),
        "still_broken_by_kind": kinds,
        "reversible": "原标题写进 metadata_json.title_before_repair",
        "samples_fixed_locally": fixed_locally[:4],
        "samples_fixed_from_api": fixed_from_api[:4],
        "unresolved": unresolved[:8],
        "what_this_does_not_fix":
            "抖音那些「整串只剩一个数」的没有公开接口，要他的登录态才拿得回真标题。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
