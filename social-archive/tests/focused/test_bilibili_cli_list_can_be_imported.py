"""bilibili-cli 那类工具导出的清单，导得进来吗（v0.0.0.22 / G1）。

Owner 给的项目表里 bilibili-cli 的角色写的是「JSON/YAML 导入」。
在这之前那条路**从入口就是关着的**，两道门各挡一次：

  1. `read_export_archive` 只认压缩包，不是 zip 一律回「这不是一个能打开的压缩包」。
     而这类工具吐的是**一个裸文件**。
  2. 就算读到了 YAML，`_read_yaml` 根本不存在；而且这类清单里
     **一个 url 字段都没有**，只有 `bvid`——按 url 找的那条路会整份漏掉，
     最后落到兜底的正则捡链接，捡到 0 个，回执写「读不出任何链接」。

也就是说：他手上一份完整、干净、自己导出来的收藏清单，
上传上去会被告知「这个包里没有找到任何链接」。
"""

from __future__ import annotations

import json

import pytest

from social_archive.data_export_import import read_export_archive

BVID_LIST = [
    {"bvid": "BV1xx411c7mD", "title": "第一条", "owner": {"name": "作者甲"}, "pubdate": 1700000000},
    {"bvid": "BV1yy411c7mE", "title": "第二条", "owner": {"name": "作者乙"}, "pubdate": 1700000001},
    {"bvid": "BV1zz411c7mF", "title": "第三条", "owner": {"name": "作者丙"}, "pubdate": 1700000002},
]


def test_a_yaml_list_of_bvids_imports() -> None:
    body = "".join(
        f"- bvid: {item['bvid']}\n  title: {item['title']}\n  pubdate: {item['pubdate']}\n"
        for item in BVID_LIST).encode("utf-8")
    read = read_export_archive(body, filename="favorites.yaml")
    assert read["ok"] is True, read.get("error")
    assert read["counted"] == 3
    assert read["items"][0]["url"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert read["items"][0]["title"] == "第一条"
    # 时间也要带上——不然库里那一列全是空的
    assert read["items"][0]["observed_at"] == 1700000000


def test_a_json_list_of_bvids_imports() -> None:
    read = read_export_archive(json.dumps(BVID_LIST, ensure_ascii=False).encode("utf-8"),
                               filename="favorites.json")
    assert read["ok"] is True, read.get("error")
    assert read["counted"] == 3
    assert all(item["url"].startswith("https://www.bilibili.com/video/BV") for item in read["items"])


def test_the_receipt_says_it_read_a_single_file_not_an_archive() -> None:
    """**回执要说清它是按什么读的。**

    「按单个文件读的」和「解开压缩包读的」是两件事；说不清的话，
    上传错东西时他没法判断问题在哪。
    """
    read = read_export_archive(b'[{"bvid": "BV1xx411c7mD"}]', filename="x.json")
    assert read["file_count"] == 1
    note = read["files"][0]["note"]
    assert "单个文件" in note, note
    assert read["files"][0]["name"] == "x.json"


def test_a_config_file_is_refused_with_a_reason_not_a_silent_zero() -> None:
    """**读不出条目不许当成「成功，0 条」**（INV-NO-SILENT-ZERO）。"""
    read = read_export_archive(b"platform: bilibili\nlimit: 10\n", filename="config.yaml")
    assert read["ok"] is False
    assert read["failure_code"] == "FILE_HAS_NO_LINKS"
    assert "没有找到任何条目" in read["error"]


@pytest.mark.parametrize("bad", [b"", b"\x00\x01\x02\x03", b"not: [unclosed"])
def test_rubbish_input_never_raises(bad: bytes) -> None:
    read = read_export_archive(bad, filename="junk.yaml")
    assert read["ok"] is False
    assert read.get("failure_code")


def test_a_zip_still_works_the_old_way() -> None:
    """**别为了加一条路把原来那条弄坏。**"""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bookmarks.html",
                         '<A HREF="https://example.com/a" ADD_DATE="1700000000">甲</A>')
    read = read_export_archive(buffer.getvalue(), filename="export.zip")
    assert read["ok"] is True
    assert read["counted"] == 1
    assert read["items"][0]["url"] == "https://example.com/a"
    assert "单个文件" not in read["files"][0]["note"]


def test_an_item_that_carries_a_real_url_keeps_it() -> None:
    """**取来的优先于拼来的。** 条目自己说得出网址时，不许拿 bvid 去拼。"""
    read = read_export_archive(
        json.dumps([{"bvid": "BV1xx411c7mD", "url": "https://www.bilibili.com/festival/x"}]).encode(),
        filename="a.json")
    assert read["items"][0]["url"] == "https://www.bilibili.com/festival/x"
