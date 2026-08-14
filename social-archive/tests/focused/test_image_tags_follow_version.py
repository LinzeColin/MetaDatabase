"""compose 里的镜像标签必须跟着 VERSION 走（v0.0.0.7 / T18）。

## 为什么这条会毁掉回滚

部署时如果用**和上一版相同的标签**构建，新镜像会把旧镜像原地覆盖——
`docker images` 里那个 `:0.0.0.6` 不再是上一版，而是刚构建的这一版。
于是「回滚 = 把标签切回去」这条最简单的退路直接不存在了。

实测：VERSION 已经升到 0.0.0.7，而 compose 三处 image 仍写着 0.0.0.6。
**发现于真正要部署的那一刻**，差一步就把生产的可回滚镜像烧掉。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_every_image_tag_equals_the_version_file() -> None:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    tags = []
    for compose in sorted(ROOT.glob("compose*.yaml")):
        tags += re.findall(r"image:\s*social-archive/[a-z-]+:([0-9.]+)", compose.read_text(encoding="utf-8"))
    assert tags, "一个 social-archive 镜像标签都没解析到——判据在空转"
    wrong = sorted({t for t in tags if t != version})
    assert not wrong, (
        f"镜像标签 {wrong} 与 VERSION（{version}）不一致。"
        "用同一个标签构建会覆盖上一版镜像，回滚就没有可切回去的东西了。"
    )
