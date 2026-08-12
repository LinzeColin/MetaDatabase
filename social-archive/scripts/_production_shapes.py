r"""演练夹具要用的那几个「生产形状」——**照服务端现算，不手抄**（2026-08-13）。

## 为什么单开一个文件

`/v1/accounts` 的 `supported_platforms` 决定界面上每个平台画不画按钮、
画哪一颗。夹具里手抄一份，抄完就会漂——而漂的方向恰好最坏：

    bilibili_end_to_end_drill   xiaohongshu/douyin/instagram/reddit 写成不能同步  [PRODUCTION_SHAPES]
    forget_button_render_drill  kuaishou 写成能同步

（下面这段提到好几个平台名，会被 check_every_platform_table_is_complete.py
当成一张平台表。它不是——登记在 DELIBERATE_SUBSETS["PRODUCTION_SHAPES"]：
本文件那个函数是照 PLATFORM_RELATIONS **现算**的，**结构上不可能漏平台**。）

两处都不是「抄漏了」，是**抄反了**。于是那两个演练验的是他看不到的界面：
一个在验「这四家只能手动保存」，而生产上它们能自动同步；另一个在验
「快手能同步」，而生产上它明确不能——**「绝不给一颗结构上不可能成功的按钮」
这条验收，正好是拿一份和生产相反的事实在验的。**

服务端那段就五行（api.py），照着算一遍比抄一遍还短。

    sync_supported      platform in SYNCABLE_NOW
    not_syncable_reason NOT_SYNCABLE_YET.get(platform, "")
    server_handled      platform in SERVER_ACCOUNT_CONNECTORS
    connect_supported   platform in SYNCABLE_NOW or platform in CUSTODIAL_PLATFORMS

漂开由 `tests/focused/test_drill_fixtures_agree_with_the_server_about_syncability.py`
打红：夹具里每一处 `platform` + `sync_supported`，都要和 `SYNCABLE_NOW` 一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from social_archive.account_sync import (  # noqa: E402
    NOT_SYNCABLE_YET,
    PLATFORM_RELATIONS,
    SERVER_ACCOUNT_CONNECTORS,
    SYNCABLE_NOW,
)
from social_archive.credentials import CUSTODIAL_PLATFORMS  # noqa: E402


def supported_platforms_like_production() -> list[dict]:
    """`/v1/accounts` 里那份 `supported_platforms`，逐字段照 api.py 算。"""
    return [
        {
            "platform": platform,
            "relations": list(relations),
            "sync_supported": platform in SYNCABLE_NOW,
            "not_syncable_reason": NOT_SYNCABLE_YET.get(platform, ""),
            "server_handled": platform in SERVER_ACCOUNT_CONNECTORS,
            "connect_supported": (platform in SYNCABLE_NOW
                                  or platform in CUSTODIAL_PLATFORMS),
        }
        for platform, relations in PLATFORM_RELATIONS.items()
    ]
