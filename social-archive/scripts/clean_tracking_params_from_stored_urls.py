#!/usr/bin/env python3
r"""把已经存下来的地址上那截埋点洗掉（2026-08-13）。

## 为什么

他库里 **193 条内容，127 条的 `canonical_url` 拖着埋点**：

    bilibili   `spm_id_from=333.1387.homepage.video_card.click`（你从哪儿点进来的）
    douyin     `source=Baiduspider-sdc`

`canonicalize_url` 已经改成认这些了（白名单：地址的身份只在 path 里），
**但那只管新进来的**——`content` 的 upsert 是 `ON CONFLICT(id) DO UPDATE`，
那段**不更新 canonical_url**，所以旧行永远是脏的。

而这些地址会跟着导出进他的 Obsidian 库。

## 它怎么做

**默认只算不写。** 加 `--apply` 才落盘，并且：

1. **撞车的一律跳过，不合并。** 洗完之后和另一行相同的（他库里正好有一对：
   `BV1oMgZ6EETu` 存了两行，就因为埋点不同），**合并是个真的决定**——
   谁留谁走、两边的关系怎么并——不该由一个洗数据的脚本顺手做掉。
   跳过并报出来，让人去定。
2. **写之前先把每一行的原值记下来**（`--record` 指的那个文件），
   要退回去照着写回即可。
3. **不动 `id`，不动任何关系。** 只改 `canonical_url` 这一列。

## 它不做什么

不重算 `content_id`。那 7 条没有 `external_content_id` 的行，id 是当初按脏地址
推出来的；**洗不洗地址都改不了这一点**，将来再同步时它们可能各自多出一行。
那要改主键并跟着改外键，是另一件事，不在这里顺手做。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# **两种跑法都要能跑**：仓里直接跑，或者被 base64 送进生产容器里 exec。
# 后者没有 `__file__`，第一版就在这儿抛 NameError。
sys.path.insert(0, "/app/src")
try:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
except NameError:
    pass

from social_archive.utils import canonicalize_url  # noqa: E402

RUNTIME_DB = Path("/var/lib/social-archive/runtime/social-archive.sqlite3")


def plan(conn: sqlite3.Connection) -> dict:
    rows = list(conn.execute(
        "SELECT id, platform, canonical_url FROM content ORDER BY id"))
    existing = {(r["platform"], r["canonical_url"]) for r in rows}
    change, collide, failed = [], [], []
    for row in rows:
        try:
            clean = canonicalize_url(row["canonical_url"])
        except Exception as exc:                                  # noqa: BLE001
            failed.append({"id": row["id"], "why": str(exc)[:60]})
            continue
        if clean == row["canonical_url"]:
            continue
        if (row["platform"], clean) in existing:
            collide.append({"id": row["id"], "platform": row["platform"],
                            "was": row["canonical_url"], "would_be": clean})
            continue
        change.append({"id": row["id"], "platform": row["platform"],
                       "was": row["canonical_url"], "now": clean})
    # 两行洗成同一个的情况：也跳过，理由同上。
    seen: dict[tuple[str, str], int] = {}
    for item in change:
        seen[(item["platform"], item["now"])] = seen.get((item["platform"], item["now"]), 0) + 1
    twins = {k for k, n in seen.items() if n > 1}
    if twins:
        collide += [i for i in change if (i["platform"], i["now"]) in twins]
        change = [i for i in change if (i["platform"], i["now"]) not in twins]
    return {"total": len(rows), "change": change, "collide": collide, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser(description="洗掉已存地址上的埋点参数")
    ap.add_argument("--db", default=str(RUNTIME_DB))
    ap.add_argument("--apply", action="store_true", help="真的写（默认只算）")
    ap.add_argument("--record", default="", help="把每一行的原值写到这个文件")
    args = ap.parse_args()

    path = Path(args.db)
    if not path.is_file():
        print(json.dumps({"status": "FAIL", "error": f"库不在这儿：{path}"},
                         ensure_ascii=False)); return 2

    mode = "" if args.apply else "?mode=ro"
    conn = sqlite3.connect(f"file:{path}{mode}", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        report = plan(conn)
        if args.apply and report["change"]:
            # **先留退路，再动数据。**
            if args.record:
                Path(args.record).write_text(
                    json.dumps(report["change"], ensure_ascii=False, indent=1),
                    encoding="utf-8")
            conn.execute("BEGIN IMMEDIATE")
            for item in report["change"]:
                conn.execute("UPDATE content SET canonical_url=? WHERE id=?",
                             (item["now"], item["id"]))
            conn.commit()
            # **回读**：以库里读得到为准，不以"我发过那条 UPDATE"为准。
            still = 0
            for item in report["change"]:
                got = conn.execute("SELECT canonical_url FROM content WHERE id=?",
                                   (item["id"],)).fetchone()
                if got and got["canonical_url"] != item["now"]:
                    still += 1
            report["written_and_read_back"] = len(report["change"]) - still
            report["read_back_mismatch"] = still
    finally:
        conn.close()

    print(json.dumps({
        "status": "PASS" if not report["failed"] else "FAIL",
        "applied": bool(args.apply),
        "total_rows": report["total"],
        "would_change" if not args.apply else "changed": len(report["change"]),
        "skipped_because_it_would_collide": len(report["collide"]),
        "collisions": report["collide"][:4],
        "failed_to_canonicalise": report["failed"],
        "written_and_read_back": report.get("written_and_read_back"),
        "read_back_mismatch": report.get("read_back_mismatch"),
        "message_zh": (
            f"{len(report['change'])} 行的地址上带着埋点"
            + ("（这次只算没写，加 --apply 才落盘）" if not args.apply else "，已洗掉并回读确认")
            + (f"；**另有 {len(report['collide'])} 行跳过了**——洗完会和别的行撞在一起，"
               f"合并是个真的决定，留给人定。" if report["collide"] else "。")),
        "what_this_does_not_prove": (
            "只改 canonical_url 这一列，不动 id、不动任何关系；"
            "也不重算 content_id——没有 external_content_id 的那几行将来再同步时"
            "仍可能各自多出一行，那要动主键，是另一件事。"),
    }, ensure_ascii=False, indent=2))
    return 0 if not report["failed"] else 4


if __name__ == "__main__":
    sys.exit(main())
