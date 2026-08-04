"""B站的「成功」可以是空的（v0.0.0.7 / T08 / INV-NO-SILENT-ZERO）。

实测（2026-08-04，不带任何 Cookie、纯 curl，四个 media_id 全一致）：

    GET https://api.bilibili.com/x/v3/fav/resource/list?media_id=12&pn=1&ps=5&platform=web
    → HTTP 200
    → {"code":0,"message":"OK","ttl":1,"data":null}

**HTTP 200、业务码 0、message "OK"、data 是 null。**

一个照常理写的解析器会 `data.get("medias", [])` 拿到空列表，报告
「同步成功，0 条」。用户看到「你没有收藏」，真相是「你没登录」。
v0.0.0.6 生产上"永远是 0"就是这个形状。

下面这些判据里，`ANONYMOUS_REAL_RESPONSE` 是**当天真实抓下来的字节**，
不是我编的样例。
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from social_archive.platform_payloads import PayloadUnreadable, parse_bilibili_favlist


def _client(tmp_path, monkeypatch) -> TestClient:
    """按 tests/focused/test_library_api.py 里既有的方式起一个 app。"""
    root = tmp_path / "data"
    pwa = tmp_path / "pwa"
    pwa.mkdir()
    (pwa / "index.html").write_text("ok")
    for key, value in {
        "SOCIAL_ARCHIVE_DATA_ROOT": root,
        "SOCIAL_ARCHIVE_RUNTIME_DB": root / "db.sqlite",
        "SOCIAL_ARCHIVE_STAGING_ROOT": root / "staging",
        "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": root / "private",
        "SOCIAL_ARCHIVE_WATCH_ROOT": root / "import",
        "SOCIAL_ARCHIVE_PWA_ROOT": pwa,
    }.items():
        monkeypatch.setenv(key, str(value))
    import social_archive.api as api

    importlib.reload(api)
    return TestClient(api.app)

# 2026-08-04 实测原文，逐字节。
ANONYMOUS_REAL_RESPONSE = '{"code":0,"message":"OK","ttl":1,"data":null}'


def test_the_real_anonymous_response_is_a_failure_not_an_empty_list() -> None:
    with pytest.raises(PayloadUnreadable) as caught:
        parse_bilibili_favlist(ANONYMOUS_REAL_RESPONSE)
    assert caught.value.failure_code == "NOT_LOGGED_IN"
    # 用户读到的必须是"这不代表你没有收藏"，而不是"0 条"
    assert "不代表你没有收藏" in caught.value.message_zh
    assert "登录" in caught.value.message_zh


def test_an_explicitly_empty_page_is_allowed_and_is_not_the_same_thing() -> None:
    """平台**明确说**「这里没有」和平台**什么都没说**，是两件事。

    前者是合法的空（翻到最后一页、收藏夹真的空），后者是失败。
    把两者合并成一个 `[]` 正是这个模块要防的。
    """
    items, has_more = parse_bilibili_favlist(
        '{"code":0,"message":"OK","ttl":1,"data":{"medias":[],"has_more":false}}'
    )
    assert items == []
    assert has_more is False


def test_platform_refusal_carries_the_platforms_own_words() -> None:
    with pytest.raises(PayloadUnreadable) as caught:
        parse_bilibili_favlist('{"code":-101,"message":"账号未登录","data":null}')
    assert caught.value.failure_code == "NOT_LOGGED_IN"
    assert "账号未登录" in caught.value.message_zh, "丢掉了平台自己的原话"


def test_a_non_empty_list_that_maps_to_nothing_raises_instead_of_returning_zero() -> None:
    """**这条是整个模块的理由。**

    字段名来自公开文档、没有被真实响应验证过。哪天 B 站改了字段名，
    「读到 20 条、一条都读不懂」绝不能报成「你有 0 条收藏」。
    """
    body = '{"code":0,"message":"OK","data":{"medias":[{"nope":1},{"nope":2}],"has_more":false}}'
    with pytest.raises(PayloadUnreadable) as caught:
        parse_bilibili_favlist(body)
    assert caught.value.failure_code == "PAYLOAD_SHAPE_CHANGED"
    assert "2 条" in caught.value.message_zh, "没有说清读到了多少条却读不懂"
    assert "不会假装同步成功" in caught.value.message_zh


def test_documented_item_shape_maps_when_it_does_match() -> None:
    """文档说的字段名**如果**对得上，就该正常映射。

    这条判据不证明字段名是对的——它只证明"对上了就能用"。
    真实字段要等 Owner 那边第一次真实抓包（T09「抓到即固化」）。
    """
    body = (
        '{"code":0,"message":"OK","data":{"has_more":true,"medias":['
        '{"id":114514,"bvid":"BV1xx411c7mD","title":"标题",'
        '"cover":"https://i0.hdslb.com/x.jpg","pubtime":1600000000,"fav_time":1700000000,'
        '"upper":{"name":"某UP主"}}]}}'
    )
    items, has_more = parse_bilibili_favlist(body)
    assert has_more is True
    assert len(items) == 1
    only = items[0]
    assert only.external_id == "BV1xx411c7mD"
    assert only.url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert only.title == "标题"
    assert only.author == "某UP主"
    assert only.favorited_at == 1700000000


def test_garbage_is_not_silently_an_empty_page() -> None:
    for body in ("", "not json at all", "[1,2,3]"):
        with pytest.raises(PayloadUnreadable) as caught:
            parse_bilibili_favlist(body)
        assert caught.value.failure_code == "PAYLOAD_NOT_JSON"


def test_the_http_endpoint_never_reports_a_bare_success_with_zero_items(
    tmp_path, monkeypatch
) -> None:
    """端点层：实测那条响应必须变成「失败 + 中文原因」，不是「成功 0 条」。

    这条判据走的是真实 HTTP 栈，不是直调函数——中间隔着 pydantic 校验、
    依赖注入和序列化，每一层都出过「函数写得对、接口回的不是那个」的事。
    """
    response = _client(tmp_path, monkeypatch).post(
        "/v1/extension/captures/parse",
        json={"platform": "bilibili", "url": "https://api.bilibili.com/x/v3/fav/resource/list",
              "body": ANONYMOUS_REAL_RESPONSE},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["failure_code"] == "NOT_LOGGED_IN"
    assert payload["items"] == []
    assert "不代表你没有收藏" in payload["message_zh"]


def test_an_unknown_platform_says_so_instead_of_pretending(tmp_path, monkeypatch) -> None:
    response = _client(tmp_path, monkeypatch).post(
        "/v1/extension/captures/parse",
        json={"platform": "xiaohongshu", "body": '{"anything":1}'},
    )
    payload = response.json()
    assert payload["ok"] is False
    assert payload["failure_code"] == "PLATFORM_PARSER_MISSING"
    assert payload["items"] == []
