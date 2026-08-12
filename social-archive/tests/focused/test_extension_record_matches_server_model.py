"""扩展产出的条目形状必须能被服务端 CaptureRequest 收下（v0.0.0.7 / T04）。

## 这个文件是从一个真实缺陷里长出来的

T04 拿 Owner 的真实 Chrome 书签跑脊柱时，第一批就 422 了：

    {"type":"extra_forbidden","loc":["body","items",0,"collection_name"], ...}

`flattenBookmarksTree` 给每条记录都带了 `collection_name`，而 `CaptureRequest`
是 `extra="forbid"`，条目级只收 `collection_key`——`collection_name` 只在**批次**
级别存在（用来给收藏夹起显示名）。于是整批被打回，**一条都进不去**。

这个字段从 v0.0.0.6 就在，也就是说 **Chrome 书签同步从来没有成功过**。
它是「永远是 0」的第二个根因，与 T00 记下的那个 GID 问题各自独立。

## 为什么以前没被发现

两侧各自都有测试：
  · `flattenBookmarksTree` 有单元测试，断言它产出的字段对不对——它确实对
  · `CaptureRequest` 有模型测试，断言它拒绝多余字段——它确实拒绝
**没有一个测试把两者对起来。** 每一边都绿，接缝是红的。

所以这条判据不打在任何一边，打在**接缝**上：用生产代码真的产出记录，
再用生产模型真的去校验它。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from social_archive.models import CaptureRequest

ROOT = Path(__file__).resolve().parents[2]
UTILS = ROOT / "apps/browser-extension/content/extension-utils.js"

# 带嵌套文件夹、无标题项、以及一条 javascript: 坏链——覆盖 walk() 的三条分支
BOOKMARK_TREE = [{
    "id": "0", "title": "", "children": [{
        "id": "1", "title": "书签栏", "children": [
            {"id": "2", "title": "技术", "children": [
                {"id": "3", "parentId": "2", "title": "Anthropic",
                 "url": "https://www.anthropic.com/?utm_source=x#frag", "dateAdded": 1700000000000},
            ]},
            {"id": "4", "parentId": "1", "title": "", "url": "https://example.com/no-title", "dateAdded": 0},
            {"id": "5", "parentId": "1", "title": "坏链", "url": "javascript:alert(1)", "dateAdded": 1700000000000},
        ]
    }]
}]


def _flatten(tree: list) -> list[dict]:
    """跑**生产代码**，不是在 Python 里重写一遍它的逻辑。

    重写一遍的话，这条判据守的就是我的复刻件，而不是真正会被装进浏览器的那份。
    """
    script = (
        "const utils = require(%s);"
        "const tree = JSON.parse(process.argv[1]);"
        "console.log(JSON.stringify(utils.flattenBookmarksTree(tree)));"
    ) % json.dumps(str(UTILS))
    completed = subprocess.run(
        ["node", "-e", script, json.dumps(tree)],
        cwd=ROOT, check=True, text=True, capture_output=True,
    )
    return json.loads(completed.stdout)


def test_flattened_bookmarks_are_accepted_by_capture_request() -> None:
    records = _flatten(BOOKMARK_TREE)
    assert records, "展平出 0 条——判据在空转，这和「没问题」长得一样"
    for record in records:
        # background.js::syncChromeBookmarks 只额外补了 destination_ids
        payload = {**record, "destination_ids": ["social_archive", "markdown"]}
        CaptureRequest.model_validate(payload)


def test_no_field_is_batch_level_only() -> None:
    """逐字段点名，报错信息要能直接指出是哪个字段越界。

    上一条整体校验会在第一个坏字段处抛出；这一条把**全部**越界字段列出来，
    免得修一个跑一次。
    """
    allowed = set(CaptureRequest.model_fields) | {"destination_ids"}
    records = _flatten(BOOKMARK_TREE)
    assert records
    offenders = sorted({key for record in records for key in record if key not in allowed})
    assert not offenders, (
        f"这些字段 CaptureRequest 收不下：{offenders}。"
        "服务端是 extra=forbid，多一个字段就是整批 422、一条都进不去——"
        "v0.0.0.6 的 collection_name 就是这么让 Chrome 书签同步从来没成功过的。"
    )


def test_folder_path_survives_without_collection_name() -> None:
    """删掉 collection_name 之后，文件夹路径不能跟着丢。

    它有两个落点：collection_key（表格「收藏夹」那一列取的就是它）
    和 raw_metadata.folder_path。
    """
    records = _flatten(BOOKMARK_TREE)
    nested = next(r for r in records if r["external_content_id"] == "chrome-bookmark:3")
    assert nested["collection_key"] == "书签栏 / 技术"
    assert nested["raw_metadata"]["folder_path"] == ["书签栏", "技术"]
    assert "collection_name" not in nested


def test_non_http_bookmarks_are_dropped_not_smuggled() -> None:
    """javascript: 之类的链接必须在展平阶段就被丢掉。

    带进去的话服务端会拒（url 校验），而那时它已经混在一批 200 条里，
    整批一起失败——一条坏链拖垮整次同步。
    """
    records = _flatten(BOOKMARK_TREE)
    assert [r["external_content_id"] for r in records] == [
        "chrome-bookmark:3", "chrome-bookmark:4",
    ], "javascript: 那条没有被丢掉"


@pytest.mark.parametrize("relation_field,expected", [("platform", "generic-web"), ("relation_type", "bookmark")])
def test_bookmark_records_are_labelled_consistently(relation_field: str, expected: str) -> None:
    for record in _flatten(BOOKMARK_TREE):
        assert record[relation_field] == expected
