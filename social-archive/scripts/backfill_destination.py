#!/usr/bin/env python3
"""把**已经在库里、却还没送到某个目的地**的内容补投一遍（v0.0.0.7 / T11）。

## 为什么需要它

2026-08-05 打生产量出来的：

    markdown   已送到这里 193 / 193 条
    obsidian   已送到这里   1 / 193 条
    github     已送到这里   1 / 193 条

「已连接」是真的，「最近一次自动导入成功」也是真的——**而 192 条从来没去过
那两个地方**。原因不是坏了，是投递只在**新内容进来时**发生：Owner 后来才
连上 GitHub 与 Obsidian，此前入库的那些不会自己追上去。

而在他那一侧，「我连上了 GitHub，我的档案应该都在那儿」是最自然的期待。
在此之前，把 192 条补上去的唯一办法是**在界面上逐条点 192 次导出**。

## 边界

· **默认只看不动。** 不给 `--apply` 就只报数、不入队。
· 只给**已经授权过导出**的目的地补投（沿用 DestinationRegistry 的判定）——
  「用户在界面上选了它」不等于「他授权我们往那里写」。
· 入队的是与单条导出**完全相同**的作业（export_destination），
  不另开一条只有补投才走的路——那种路最容易和主路分叉。
· 作业 id 是 (类型, 目的地, 内容) 的稳定哈希 + INSERT OR IGNORE，
  所以重复跑不会重复投。

## 用法

    python3 scripts/backfill_destination.py --destination github            # 只看
    python3 scripts/backfill_destination.py --destination github --apply    # 真入队
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_archive.config import Settings  # noqa: E402
from social_archive.db import RuntimeStore  # noqa: E402
from social_archive.destinations import DestinationRegistry  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="把还没送到某个目的地的内容补投一遍")
    parser.add_argument("--destination", required=True)
    parser.add_argument("--apply", action="store_true", help="真的入队（默认只看不动）")
    parser.add_argument("--limit", type=int, default=0, help="最多补投这么多条（0 = 全部）")
    args = parser.parse_args()

    settings = Settings.from_env()
    store = RuntimeStore(settings.runtime_db)
    store.initialize()
    destination_id = args.destination.strip().lower()

    registry = DestinationRegistry(settings, store)
    if not registry.is_export_authorized(destination_id):
        # **先分清是「真没授权」还是「你跑错地方了」。**
        #
        # 2026-08-05 实测：在**主机上**跑这个脚本，github 报「没有授权」——
        # 而在容器里跑，同一个判定是 True。原因是 .env 里的
        # SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE 指着 /run/secrets/github_token，
        # 那是**容器里的挂载点**，主机上不存在；read_secret 读不到就当成没配。
        #
        # 这两件事的下一步完全相反：一个是「去连接向导里完成一次写入」，
        # 另一个是「换个地方跑」。**把后者报成前者，会让人去改一个没坏的东西。**
        # 这已经是同一个坑今天第四次绊人（恢复脚本、运维手册那条命令、
        # 主机上的判定探针，现在是它）。
        wrong_place = [
            name for name in ("GITHUB_TOKEN_FILE", "NOTION_TOKEN_FILE", "OBSIDIAN_REST_TOKEN_FILE",
                              "KARAKEEP_TOKEN_FILE", "LINKWARDEN_TOKEN_FILE")
            for value in [os.getenv(f"SOCIAL_ARCHIVE_{name}", "")]
            if value.startswith("/run/secrets/") and not Path(value).exists()
        ]
        if wrong_place:
            print(json.dumps({
                "status": "REFUSED", "error_code": "RUN_ME_INSIDE_THE_CONTAINER",
                "destination_id": destination_id,
                "message_zh": "配置里的密钥路径是**容器里**的挂载点（/run/secrets/…），"
                              "而这台主机上没有那些文件——所以判定成了「没配」。"
                              "**这不是没授权，是跑错了地方。** 换成："
                              "docker compose exec core-api python /app/scripts/backfill_destination.py …",
                "paths_only_visible_inside_the_container": wrong_place,
            }, ensure_ascii=False))
            return 4
        print(json.dumps({
            "status": "REFUSED", "error_code": "DESTINATION_NOT_AUTHORIZED",
            "destination_id": destination_id,
            "message_zh": "这个目的地还没有一次成功的写入授权。"
                          "「在界面上选了它」不等于「授权我们往那里写」——先在连接向导里完成一次真实写入。",
        }, ensure_ascii=False))
        return 4

    connection = sqlite3.connect(f"file:{settings.runtime_db}?mode=ro", uri=True)
    try:
        total = connection.execute("SELECT COUNT(*) FROM content").fetchone()[0]
        missing = [row[0] for row in connection.execute(
            "SELECT c.id FROM content c WHERE NOT EXISTS ("
            "  SELECT 1 FROM destination_binding b"
            "  WHERE b.content_id = c.id AND b.destination_id = ?)"
            " ORDER BY c.first_observed_at", (destination_id,))]
    finally:
        connection.close()

    selected = missing[: args.limit] if args.limit else missing
    result = {
        "status": "READY" if not args.apply else "ENQUEUED",
        "destination_id": destination_id,
        "content_total": total,
        "already_delivered": total - len(missing),
        "missing": len(missing),
        "would_enqueue" if not args.apply else "enqueued": len(selected),
        "applied": bool(args.apply),
    }

    if args.apply:
        job_ids = [
            store.enqueue_job("export_destination",
                              {"content_id": content_id, "destination_id": destination_id},
                              connector_id=destination_id)
            for content_id in selected
        ]
        result["job_ids_sample"] = job_ids[:3]
        result["reminder"] = (
            "**入队不等于送到。** 这些作业要由 worker 逐条跑，"
            "跑完之后再看一次目的地的「已送到这里 N / M 条」才算数。"
        )
    else:
        result["sample"] = selected[:3]
        result["reminder"] = "只看了，什么都没动。确认无误再加 --apply。"

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
