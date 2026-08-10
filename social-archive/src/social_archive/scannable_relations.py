"""扩展真正会去枚举的关系类型——**这个文件是生成的，不要手改。**

真源是 `apps/browser-extension/content/platform-catalog.js` 的
`SCANNABLE_RELATIONS`。改了那边之后跑：

    python3 scripts/generate_scannable_relations.py --apply

为什么不在运行时读那个 .js：装进镜像之后 `social_archive` 在
site-packages 里，仓的相对路径不存在，import 当场炸、API 起不来
（2026-08-10 实测，那次 1402 条判据全绿）。
"""

from __future__ import annotations


SCANNABLE_RELATIONS: dict[str, tuple[str, ...]] = {
    "bilibili": ("favorite",),
    "douyin": ("favorite",),
    "instagram": ("saved",),
    "kuaishou": ("favorite",),
    "reddit": ("saved",),
    "xiaohongshu": ("favorite",),
}
