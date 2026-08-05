"""服务端会回的每一种「关系」，界面都得有中文名（v0.0.0.7 / T15）。

## 为什么钉它

资料库那一列取标签的写法是：

    relationLabels[item.primary_relation] || relationLabels[relations[0]]
        || item.primary_relation || "收藏"

**取不到就退回原值**——用户看到的是一个英文单词。

2026-08-06 数了一遍：服务端 `PLATFORM_RELATIONS` 里一共 9 种关系值，
而界面那张表只有 8 种，**少了 `playlist`**。它是 YouTube 的第二种关系
（`["watch_later", "playlist"]`），而 YouTube 恰恰是交接里让 Owner 去连的那个平台。

今天还没有 playlist 的内容进来，所以没人看见过。**但它是接上就露的那种。**

## 判据

`PLATFORM_RELATIONS` 里出现的每一个关系值，`apps/pwa/app.js` 的
`relationLabels` 里都必须有。反过来不要求——界面多认几个旧值无害。
"""

from __future__ import annotations

import re
from pathlib import Path

from social_archive.account_sync import PLATFORM_RELATIONS

ROOT = Path(__file__).resolve().parents[2]


def _labels() -> dict[str, str]:
    text = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    block = re.search(r"const relationLabels = \{(.*?)\n  \};", text, re.S)
    assert block, "relationLabels 找不到了——判据的射程失效，先修判据"
    body = "\n".join(l for l in block.group(1).splitlines() if not l.lstrip().startswith("//"))
    return dict(re.findall(r'(\w+):\s*"([^"]+)"', body))


def test_no_relation_falls_through_to_its_english_name() -> None:
    labels = _labels()
    assert len(labels) >= 8, f"只解析出 {len(labels)} 个标签——**解析失败和「都齐了」长得一样**"
    wanted = sorted({value for values in PLATFORM_RELATIONS.values() for value in values})
    missing = [value for value in wanted if value not in labels]
    assert not missing, (
        f"**这些关系服务端会回，而界面没有中文名**：{missing}。"
        "取不到标签时会退回原值，用户在「关系」那一列看到的就是英文单词。"
    )


def test_the_labels_are_chinese_not_the_key_repeated() -> None:
    """**别用「把键抄一遍」来糊弄这条判据。**

    少了这条，`playlist: "playlist"` 也能让上面那条绿，而用户看到的还是英文。
    """
    latin_only = [f"{key}: {value}" for key, value in _labels().items()
                  if re.fullmatch(r"[A-Za-z_ ]+", value)]
    assert not latin_only, f"这些标签根本不是中文：{latin_only}"
