#!/usr/bin/env python3
r"""给生产库里缺作者的 B 站条目补上作者（2026-08-12）。

## 为什么两边都要修

刚给他 Obsidian 库里 43 篇补上了作者。**生产库是另一份**——资料库页面
读的是它，不修的话他在网页上看到的还是空作者。

上一次修标题就是两边一起改的，这次照办。

## 量到的（生产实测）

    douyin       缺作者 54 条   没有 BV 号 → 公开接口修不了
    bilibili     缺作者 46 条   **有 BV 号 → 可修**
    generic-web  缺作者  2 条   修不了

## 边界

- **只补空作者**；已经有值的一个字不动（包括那些装着点赞数的——
  那一档由 `clean_display_author` 在**显示时**清掉，仓里的原始数据不动，
  这是 2026-08-10 定的规矩：不动存下来的数据）。
- **不碰标题**。
- 原值留在 `metadata_json.author_before_fill`，可回滚。
- `metadata_json` 解析不动就跳过这一条，**绝不用 `{}` 覆盖回去**
  （上一次差点这样抹掉别的元数据）。
- 默认 `--dry-run`。

## 已经跑过了（2026-08-12）

生产库那 46 条**已经补完**：这个脚本补了 7 条，修标题那一趟顺带补了 36 条
（`repair_scraped_titles_in_db.py` 的 update 里带 `coalesce(nullif(author_name,''),?)`），
36 + 7 = 43。剩下 3 条全是 `code=62002`——稿件真的没了，**不是修复失败，是没得可修**。

上面「量到的」是**动手之前**的实测，留着是为了说明当时的分布，不是待办。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.request

DB = "/var/lib/social-archive/runtime/social-archive.sqlite3"
BV = re.compile(r"/video/(BV[0-9A-Za-z]+)")
API = "https://api.bilibili.com/x/web-interface/view?bvid={bv}"
HEAD = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
GONE_FOR_GOOD = {62002, -404, 62004}


def author_of(bv: str, attempts: int = 3) -> str | tuple[str] | None:
    """`(作者,)` = 拿到了；`str` = 确定没了；`None` = 这次没拿到。

    「真没了」和「这次没拿到」必须分开——上次全量跑时有 3 条只是被限流，
    混成一个 None 就会被错记成「没了」，白白少修 3 条。
    """
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(API.format(bv=bv), headers=HEAD), timeout=20) as response:
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
        name = str(((payload.get("data") or {}).get("owner") or {}).get("name") or "").strip()
        if name:
            return (name,)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="补上生产库里缺失的 B 站作者")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()

    con = sqlite3.connect(args.db if args.apply else f"file:{args.db}?mode=ro",
                          uri=not args.apply)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(
        "select id, canonical_url, author_name, metadata_json, title"
        " from content where platform='bilibili'")]

    targets = []
    for row in rows:
        if str(row["author_name"] or "").strip():
            continue
        found = BV.search(str(row["canonical_url"] or ""))
        if found:
            targets.append((row, found.group(1)))
    if args.limit:
        targets = targets[:args.limit]

    filled, unresolved = [], []
    for row, bv in targets:
        got = author_of(bv)
        time.sleep(0.7)
        if isinstance(got, str):
            unresolved.append({"id": row["id"], "bv": bv, "why": got, "kind": "gone_for_good"})
            continue
        if got is None:
            unresolved.append({"id": row["id"], "bv": bv,
                               "why": "重试 3 次仍没拿到（多半是限流）", "kind": "transient"})
            continue
        author = got[0]
        if args.apply:
            try:
                meta = json.loads(row["metadata_json"] or "{}")
                if not isinstance(meta, dict):
                    raise ValueError("metadata_json 不是对象")
            except Exception as error:                       # noqa: BLE001
                unresolved.append({"id": row["id"], "bv": bv,
                                   "why": f"metadata_json 读不动（{error.__class__.__name__}），"
                                          "跳过以免抹掉原有元数据", "kind": "metadata_unreadable"})
                continue
            meta["author_before_fill"] = row["author_name"]
            meta["author_filled_from"] = "bilibili public view api"
            con.execute("update content set author_name=?, metadata_json=? where id=?",
                        (author, json.dumps(meta, ensure_ascii=False), row["id"]))
        filled.append({"id": row["id"], "bv": bv, "author": author,
                       "title": str(row["title"])[:40]})
    if args.apply:
        con.commit()

    print(json.dumps({
        "mode": "APPLIED" if args.apply else "DRY-RUN（没有改任何东西）",
        "bilibili_rows_missing_an_author_with_a_bv": len(targets),
        "filled": len(filled),
        "unresolved": unresolved,
        "reversible": "原值写进 metadata_json.author_before_fill",
        "samples": filled[:4],
        "what_this_does_not_fix":
            "抖音那 54 条和 generic-web 那 2 条没有公开接口，要 Owner 的登录态。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
