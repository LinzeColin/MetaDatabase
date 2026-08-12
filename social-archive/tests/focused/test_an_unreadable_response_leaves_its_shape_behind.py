r"""读不懂一条响应时，留下它的字段骨架——只留名字，不留值（2026-08-12）。

## 为什么

Owner 按那颗诊断按钮，是为了让我知道**该盯哪个地址**。地址只解决一半：
拿到之后服务端还得读得懂那个响应，而 `PAYLOAD_PARSERS` 里现在**只有 B 站**。

也就是说他按完那一下，我拿到抖音的地址，然后发现自己还是写不出解析器——
因为不知道抖音的响应长什么样。诊断上报**故意不送响应体**。
于是我得回头请他再做一件事。**让他按第二次，正是这个项目一直在拔的那种东西。**

响应体本来就到了他自己的服务器（`/v1/extension/captures/parse` 收的就是它，
读完就丢）。读不懂时把**结构**留下，我照着写解析器，他那一下就够了。

## 这个测试钉两件事

1. **骨架真的留下来了**——不然他按完，我还是两手空空；
2. **骨架里一个值都没有**——字段名是平台的接口约定，而标题、作者、链接是他的内容。
   这一条比第一条更要紧：为了省他一次操作而把他的内容落盘，是把事情做反了。
"""

from __future__ import annotations

import json
import re

from social_archive.payload_shape import sketch

# 照抖音收藏响应可能的样子编的——**这里必须是编的**：真实的抖音响应我没有，
# 而这个测试要验的是「骨架不带值」，用编的反而更好检查（我知道每个值是什么）。
FAKE_BODY = json.dumps({
    "status_code": 0,
    "has_more": True,
    "aweme_list": [{
        "aweme_id": "7669577378074578239",
        "desc": "初中单词不用背，这样学快N倍",
        "author": {"uid": "112233", "nickname": "英语老张", "signature": "每天一个知识点"},
        "statistics": {"digg_count": 226000, "comment_count": 812},
        "share_url": "https://www.douyin.com/video/7669577378074578239",
    }],
}, ensure_ascii=False)

# 上面那些**值**，一个都不许出现在骨架里。
VALUES_THAT_MUST_NOT_LEAK = [
    "初中单词不用背", "英语老张", "每天一个知识点",
    "7669577378074578239", "112233", "226000",
    "https://www.douyin.com/video/7669577378074578239",
]


def test_the_shape_says_enough_to_write_a_parser() -> None:
    got = sketch(FAKE_BODY)
    assert got["readable_as_json"] is True
    blob = json.dumps(got, ensure_ascii=False)
    # 写解析器要的就是这些名字
    for name in ("aweme_list", "aweme_id", "desc", "author", "nickname",
                 "statistics", "has_more"):
        assert name in blob, f"骨架里没有 {name}——照着它写不出解析器"
    # 数组要说清是数组，否则分不出「一条」和「一串」
    assert "array(" in blob, f"没说清哪个是数组：{blob[:200]}"


def test_not_one_value_leaks_into_the_shape() -> None:
    """**这一条比上面那条更要紧。**"""
    blob = json.dumps(sketch(FAKE_BODY), ensure_ascii=False)
    leaked = [value for value in VALUES_THAT_MUST_NOT_LEAK if value in blob]
    assert not leaked, f"骨架里漏出了值：{leaked}"
    # 兜底：任何两个以上连着的中文字都不该出现（字段名这一层是英文的）
    chinese = re.findall(r"[一-鿿]{2,}", blob)
    assert not chinese, f"骨架里出现了中文，多半是值漏出来了：{chinese[:5]}"


def test_a_response_that_is_not_json_says_so_instead_of_guessing() -> None:
    got = sketch("<!doctype html><html>登录后才能看</html>")
    assert got["readable_as_json"] is False
    assert got.get("first_bytes_are_html") is True
    blob = json.dumps(got, ensure_ascii=False)
    assert "登录后才能看" not in blob, f"不是 JSON 也不许把正文带出来：{blob}"


def test_an_empty_body_is_not_mistaken_for_a_shape() -> None:
    got = sketch("")
    assert got["readable_as_json"] is False
    assert "shape" not in got, "空响应不该编出一个骨架"


def test_the_sketch_does_not_grow_with_the_response() -> None:
    """一条很大的响应，骨架不该跟着大——不然台账会被一次诊断撑爆。"""
    big = json.dumps({"list": [{"k": "x" * 5000, "n": i} for i in range(500)]})
    blob = json.dumps(sketch(big), ensure_ascii=False)
    assert len(blob) < 1200, f"骨架太大了（{len(blob)} 字符）"
    assert "array(500)" in blob, "该说清有 500 项"
