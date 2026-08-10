#!/usr/bin/env python3
"""生产是哪台机器——**唯一真源在 `deploy/PRODUCTION_HOST`**。

## 为什么要有这个文件

2026-08-10：`social-archive-api.linzezhang.com` 背后其实是两台机器
（他打到的那台 95.82G / 跑 0.0.0.25，我部署的那台 38G / 跑 0.0.0.27），
而 `linze-ovh` 这个名字被写死在 **16 个文件、21 处**，其中只有 9 处能用
环境变量覆盖。也就是说「换一台机器」不是改一个配置，是改十几处——
**而漏掉的那几处会静默地继续指向旧机器**，没有任何东西会报错。

所以：默认值只准从这里来。改机器＝改 `deploy/PRODUCTION_HOST` 一行。
临时覆盖用 `SOCIAL_ARCHIVE_DEPLOY_HOST`（演练、并行环境）。

判据 `tests/focused/test_the_production_host_has_one_source.py` 钉住
「scripts/ 里不许再出现写死的主机名（注释除外）」。
"""

from __future__ import annotations

import os
from pathlib import Path

_SOURCE = Path(__file__).resolve().parents[1] / "deploy/PRODUCTION_HOST"


def deploy_host() -> str:
    """部署/运维要连的那台机器。环境变量优先，其次唯一真源。"""
    override = os.environ.get("SOCIAL_ARCHIVE_DEPLOY_HOST") or os.environ.get("SOCIAL_ARCHIVE_HOST")
    if override:
        return override.strip()
    if not _SOURCE.is_file():
        raise RuntimeError(
            f"找不到 {_SOURCE}——生产是哪台机器没有真源了。"
            "**不许在这里回落到某个名字**：静默指向旧机器正是 2026-08-10 那次事故。")
    name = _SOURCE.read_text(encoding="utf-8").strip()
    if not name:
        raise RuntimeError(f"{_SOURCE} 是空的——同上，不许猜。")
    return name


if __name__ == "__main__":
    print(deploy_host())
