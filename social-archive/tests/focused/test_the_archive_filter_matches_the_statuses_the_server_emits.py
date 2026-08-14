"""归档状态筛选里的选项，必须就是服务端会产出的那几个（v0.0.0.7 / T15）。

## 实测出来的

`db.py` 里那个 CASE 只会出三种：

    完整 / 处理中 / **仅元数据**

而界面上写死的是：

    完整 / 处理中 / **需处理**

两头都错：`需处理` 服务端**从来不产出**（选了永远 0 条），
而真会出现的 `仅元数据` **筛不出来**。

今天 193 条全是「完整」，所以没人撞见过。**它是等真出现那一天才露的那种。**

## 判据

从 db.py 那个 CASE 里把中文常量抠出来，和 index.html 里那几个 option 比。
两边**必须一样**——多一个是死选项，少一个是筛不出来。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _statuses_the_server_emits() -> set[str]:
    db = (ROOT / "src/social_archive/db.py").read_text(encoding="utf-8")
    block = re.search(r"CASE\s*\n(.*?)END AS archive_status", db, re.S)
    assert block, "db.py 里那个 archive_status 的 CASE 找不到了——判据的射程失效"
    return set(re.findall(r"'([^']*[一-鿿][^']*)'", block.group(1)))


def _statuses_the_page_offers() -> set[str]:
    html = (ROOT / "apps/pwa/index.html").read_text(encoding="utf-8")
    block = re.search(r'<select id="archiveFilter">(.*?)</select>', html, re.S)
    assert block, "归档状态筛选找不到了——判据的射程失效"
    return {value for value in re.findall(r'value="([^"]*)"', block.group(1)) if value != "all"}


def test_the_two_lists_are_the_same() -> None:
    emitted = _statuses_the_server_emits()
    offered = _statuses_the_page_offers()
    assert len(emitted) >= 3, f"只抠出 {emitted}——**抠不全和「都对上了」长得一样**"
    assert offered == emitted, (
        f"**归档状态两边对不上**：界面多了 {sorted(offered - emitted) or '—'}"
        f"（选了永远 0 条）／少了 {sorted(emitted - offered) or '—'}（真出现时筛不出来）"
    )
