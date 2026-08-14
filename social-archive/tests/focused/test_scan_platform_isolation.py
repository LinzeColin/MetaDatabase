import json
import subprocess
from pathlib import Path

import pytest

from social_archive.models import CaptureRequest


ROOT = Path(__file__).resolve().parents[2]
MIRROR_CORE = ROOT / "apps/browser-extension/content/account-mirror-core.js"


def test_complete_scan_only_changes_the_scanned_platform(service, store):
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/100", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))
    reddit_item = service.capture(CaptureRequest(
        platform="reddit", url="https://www.reddit.com/r/example/comments/100/item/", relation_type="saved",
        requested_levels=["L0", "L1"],
    ))
    store.apply_complete_scan("x", set(), relation_type="bookmark")
    store.apply_complete_scan("x", set(), relation_type="bookmark")
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    reddit_relation = store.get_content(reddit_item.content_id)["relations"][0]
    assert x_relation["status"] == "closed"
    assert x_relation["missing_complete_scan_count"] == 2
    assert reddit_relation["status"] == "active"
    assert reddit_relation["missing_complete_scan_count"] == 0


@pytest.mark.parametrize(("platform", "relation_type", "url"), (
    ("xiaohongshu", "favorite", "https://www.xiaohongshu.com/explore/100"),
    ("douyin", "favorite", "https://www.douyin.com/video/100"),
    ("kuaishou", "favorite", "https://www.kuaishou.com/short-video/100"),
    ("bilibili", "favorite", "https://www.bilibili.com/video/BV1fixture"),
))
def test_domestic_complete_scan_never_changes_another_platform(service, store, platform, relation_type, url):
    domestic_item = service.capture(CaptureRequest(
        platform=platform, url=url, relation_type=relation_type, requested_levels=["L0", "L1"],
    ))
    x_item = service.capture(CaptureRequest(
        platform="x", url="https://x.com/example/status/101", relation_type="bookmark",
        requested_levels=["L0", "L1"],
    ))

    store.apply_complete_scan(platform, set(), relation_type=relation_type)
    store.apply_complete_scan(platform, set(), relation_type=relation_type)

    domestic_relation = store.get_content(domestic_item.content_id)["relations"][0]
    x_relation = store.get_content(x_item.content_id)["relations"][0]
    assert domestic_relation["status"] == "closed"
    assert domestic_relation["missing_complete_scan_count"] == 2
    assert x_relation["status"] == "active"
    assert x_relation["missing_complete_scan_count"] == 0



# v0.0.0.7 / T03(a)：本文件原有 3 个"浏览器镜像扫描"测试
# （douyin / kuaishou / bilibili），断言 DOM 抓取器能从构造的页面结构里
# 抠出候选项、并在关系标签未确认时拒绝标注。抓取器已随 T03 删除，
# 这 3 个测试的被测对象不复存在。
#
# **它们不是被静默删掉的**：反转后的守卫在
# tests/focused/test_superseded_paths_stay_removed.py
# （test_no_dom_scraping_symbols_anywhere_in_the_extension 等 6 条）。
#
# 上面这 2 个测试打在**服务端**的平台隔离上——与取数方式无关，原样保留，
# 且 T08 换成 API 拦截之后它们仍然是有效判据。
