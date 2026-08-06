"""按形状认收藏列表，不靠预先知道那个地址（v0.0.0.21）。

## 它解开的是哪一个死结

小红书 / 抖音 / 快手的主路径是「扩展读取页面和列表」：在 Owner 自己已登录的
收藏页上**拦截平台自己发出的那个列表请求**——不是我们去调，所以不需要破解签名。

挡住这条路的一直是「要先知道那个请求的 URL 前缀」。`INTERCEPT_PREFIXES` 里
三个平台都是 null，而它们的正当来源被定义成「Owner 去收藏页按一次诊断按钮」。
**他的原话是「不要让我和你重复地反攻」——那一步不该由他做。**

而观察器本来就支持不带前缀（net-observer.js:97 `urlPrefixes.length === 0`）：
全都收下。于是问题从「先知道地址」变成「收下之后认出哪个是列表」，
后者不需要他做任何事。

这个文件验的就是那个识别器。**它不认识任何平台名**——只认形状，
所以平台改接口不用改它，加平台也不用改它。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "apps/browser-extension/content/list-shape.js"


def _run(body: str) -> dict:
    script = f'const S = require("{MODULE}");\n{body}'
    done = subprocess.run(["node", "-e", script], cwd=ROOT, capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-500:]
    return json.loads(done.stdout.strip().splitlines()[-1])


def _capture(url: str, payload) -> dict:
    return {"url": url, "text": json.dumps(payload, ensure_ascii=False)}


NOISE = [
    _capture("https://p.example.com/api/log", {"ok": 1}),
    _capture("https://p.example.com/api/config", {"flags": {"a": 1, "b": 2, "c": 3}}),
    _capture("https://p.example.com/api/user", {"user": {"id": 1, "nickname": "我"}}),
    # 推荐流：**有数组、长度也够**，但元素带不出 id——正是最容易误认的那种
    _capture("https://p.example.com/api/feed",
             {"data": [{"banner": "a"}, {"banner": "b"}, {"banner": "c"}]}),
]
COLLECTION = _capture("https://p.example.com/api/collect/page", {"data": {"notes": [
    {"note_id": f"n{i}", "display_title": f"第{i}条",
     "user": {"nickname": f"作者{i}"}, "create_time": 1700000000 + i}
    for i in range(1, 6)]}})


def test_it_picks_the_collection_out_of_a_noisy_page() -> None:
    """收藏页会同时发出十几个请求，**只有一个是列表**。"""
    out = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(NOISE + [COLLECTION])})));")
    assert out["ok"] is True, out
    assert out["best"]["url"].endswith("/collect/page"), out["best"]["url"]
    assert out["best"]["path"] == "data.notes"
    assert out["best"]["stats"]["count"] == 5


def test_a_recommendation_feed_is_not_mistaken_for_a_collection() -> None:
    """**最容易误认的那一种**：有数组、长度够，但元素带不出 id。

    认错的后果不是少读，是把首页推荐当成他的收藏存进档案馆。
    """
    out = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(NOISE)})));")
    assert out["ok"] is False, f"把推荐流当成收藏列表了：{out.get('best')}"
    assert out["failureCode"] == "LIST_SHAPE_NOT_RECOGNISED"


def test_it_says_why_each_response_was_rejected() -> None:
    """落选的每一个都要说得出为什么——只说「找到了」的识别器，出错时没人查得动。"""
    out = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(NOISE + [COLLECTION])})));")
    reasons = {item["url"].rsplit("/", 1)[-1]: item["why"] for item in out["rejected"]}
    assert len(reasons) == len(NOISE), f"有响应被悄悄丢掉了：{reasons}"
    assert "id" in reasons["feed"], f"推荐流的落选理由没说到点上：{reasons['feed']}"


def test_recognising_nothing_is_a_failure_not_an_empty_list() -> None:
    """**认不出 ≠ 他没有收藏。** 返回空列表会变成静默的零。"""
    out = _run("console.log(JSON.stringify(S.recogniseList([])));")
    assert out["ok"] is False
    assert out["failureCode"] == "LIST_SHAPE_NOT_RECOGNISED"
    assert "收藏夹页面" in out["error"], "没告诉他下一步该做什么"


def test_items_without_an_openable_url_are_skipped_and_counted() -> None:
    """读不出网址的要跳过并记下——默默丢等于静默的少读。"""
    payload = {"data": {"notes": [
        {"note_id": "a", "display_title": "有链接", "url": "https://example.com/a"},
        {"note_id": "b", "display_title": "没链接"},
        {"note_id": "c", "display_title": "深链", "url": "app://x/c"},
        {"note_id": "d", "display_title": "也有", "url": "https://example.com/d"}]}}
    out = _run(
        f"const r = S.recogniseList([{json.dumps(_capture('https://p/x', payload))}]);\n"
        "console.log(JSON.stringify(S.normaliseItems(r.best, { platform: 'x' })));")
    assert len(out["items"]) == 2, out
    assert len(out["skipped"]) == 2, "被跳过的没有记下来"
    assert all(item["url"].startswith("https://") for item in out["items"])


def test_it_does_not_know_any_platform_names() -> None:
    """**这个文件里不许出现平台名。**

    出现了就意味着换个平台要改它、平台改接口也要改它——
    而它存在的全部意义就是不用为每个平台各写一份。
    """
    text = MODULE.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith(("*", "/*", "//")))
    for name in ("xiaohongshu", "douyin", "kuaishou", "bilibili", "小红书", "抖音", "快手"):
        assert name not in code, f"识别器里写死了平台名 {name}——它就该只认形状"


def test_no_signature_or_token_ever_leaves_the_browser() -> None:
    """**平台的签名/token 在查询串里，一个都不许跟出去。**

    抖音的 a_bogus、小红书的 xsec_token 都在查询串上。而这条路会把
    「看到过哪些响应」写进三个地方，每一个都会离开浏览器：

      1. 认不出时的诊断  → 跟着同步回执落到服务端
      2. 条目的 raw_metadata → **入库**，还会出现在导出里
      3. 同步游标 matched_url → 落到服务端回执

    只留路径不影响用处（要的是"哪个端点"，不是那串签名），
    而漏掉任何一处都等于把他的凭据写进了我们的日志。
    **这个仓在「修一处就当修完了」上栽过四次**，所以三处一起验。
    """
    secret = "SIGNATURE_MUST_NOT_LEAK"
    payload = {"data": {"notes": [
        {"note_id": f"n{i}", "title": f"t{i}", "url": f"https://e/{i}"} for i in range(4)]}}
    noisy = {"junk": 1}
    out = _run(
        f"const caps = [{{url: 'https://p/api/list?a_bogus={secret}', "
        f"text: JSON.stringify({json.dumps(payload)})}},"
        f" {{url: 'https://p/api/log?token={secret}', "
        f"text: JSON.stringify({json.dumps(noisy)})}}];\n"
        "const r = S.recogniseList(caps);\n"
        "const n = S.normaliseItems(r.best, { platform: 'x' });\n"
        "console.log(JSON.stringify({ rejected: r.rejected, items: n.items, "
        "matched: r.best.url }));")
    # ① 诊断（淘汰记录）
    assert secret not in json.dumps(out["rejected"]), (
        f"淘汰记录里带出了签名：{out['rejected']}"
    )
    # ② 入库的元数据
    assert secret not in json.dumps(out["items"]), (
        f"条目的 raw_metadata 里带出了签名：{out['items'][0]['raw_metadata']}"
    )
    assert out["items"][0]["raw_metadata"]["matched_url"] == "https://p/api/list"
    # ③ 路径本身要留着——剥太狠就没用了
    assert "/api/log" in json.dumps(out["rejected"]), "把路径也剥掉了，诊断就没用了"


def test_the_background_strips_it_before_the_cursor_too() -> None:
    """第三处在 background：同步游标里的 matched_url 也会落到服务端。"""
    from pathlib import Path

    background = (Path(__file__).resolve().parents[2]
                  / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    code = "\n".join(line for line in background.splitlines()
                     if not line.lstrip().startswith("//"))
    assert "matched_url: globalThis.SAListShape.safePath(" in code, (
        "游标里的 matched_url 没剥查询串——签名会跟着回执落到服务端"
    )


def test_a_feed_that_looks_identical_never_wins_by_chance() -> None:
    """**收藏页上推荐流和收藏列表可以长得一模一样。**

    都带 id、标题、作者、时间——纯按形状打分会打平，谁赢是碰运气。
    实测（真 Chrome + 假站）：随机挑中推荐流，于是 **6 条首页推荐被当成
    他的收藏导进档案馆**，而界面还说「已在你的小红书收藏页上认出 6 条」。

    破平局用地址里的词。**注意这只是提示、不是前提**：
    没有这些词照样认得出（这条路的全部意义就是不需要预先知道地址），
    只有分数打平时才拿它当参考。
    """
    same = lambda prefix, n: [                                   # noqa: E731
        {"note_id": f"{prefix}{i}", "display_title": f"t{i}",
         "user": {"nickname": "u"}, "create_time": 1700000000 + i} for i in range(n)]
    caps = [
        _capture("https://p.example.com/api/homefeed", {"data": {"items": same("rec", 6)}}),
        _capture("https://p.example.com/api/collect/page", {"data": {"notes": same("fav", 6)}}),
    ]
    out = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(caps)})));")
    assert out["ok"] is True
    assert "collect" in out["best"]["url"], (
        f"打平时挑中了推荐流：{out['best']['url']}——那会把首页推荐存进他的档案馆"
    )
    # 反过来：顺序调换也要挑对（不能只是碰巧靠排序赢的）
    out2 = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(caps[::-1])})));")
    assert "collect" in out2["best"]["url"], "换个顺序就挑错了——那说明它靠的是顺序不是规则"


def test_the_hint_is_only_a_tiebreaker_not_a_requirement() -> None:
    """**地址里没有那些词，照样要认得出。**

    否则就退回了「必须先知道地址」——那正是这条路要解开的结。
    """
    caps = [_capture("https://p.example.com/xyz/abc", {"d": [
        {"item_id": f"x{i}", "title": f"t{i}", "author": "a", "time": i} for i in range(5)]})]
    out = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(caps)})));")
    assert out["ok"] is True, "地址里没有提示词就认不出了——那等于又要先知道地址"
    assert out["best"]["stats"]["count"] == 5


# ---------------------------------------------------------------------------
# 元素外面套一层壳（2026-08-06）
#
# 第一版只看元素**自己身上**的字段。拿三家真实的响应形状去试认，三家全灭，
# 理由一模一样：「只有 0% 的元素带得出 id」——因为 id 不在元素身上：
#
#     Reddit     children[].data.id
#     Instagram  items[].media.pk
#     X          entries[].content.itemContent.tweet_results.result.rest_id
#
# **而这不只是「少认几个平台」。** 小红书自己的条目就是这个形状：
# `id` 摊在外面，`display_title` / `user.nickname` 在 `note_card` 里。
# 照第一版：id 找得到 → 照样入库；标题作者取不到 → 全是 null。
# **真站上会存进一批没标题没作者的条目，而判据全绿。**
# 上面那些判据一条都没抓到，因为夹具里的条目全是我摊平了写的。
# ---------------------------------------------------------------------------

def _wrapped(prefix: str, n: int, wrapper: str) -> list:
    return [{"id": f"{prefix}{i}", wrapper: {
        "display_title": f"第{i}条", "user": {"nickname": f"作者{i}"},
        "create_time": 1700000000 + i}} for i in range(1, n + 1)]


def test_the_title_and_author_are_not_lost_when_the_item_has_a_wrapper() -> None:
    """这条盯的是**已经上线的小红书**，不是将来某个平台。"""
    caps = [_capture("https://p.example.com/api/collect/page",
                     {"data": {"items": _wrapped("n", 5, "note_card")}})]
    out = _run(f"console.log(JSON.stringify(S.recogniseList({json.dumps(caps)})));")
    assert out["ok"] is True, f"套一层壳就认不出了：{out.get('rejected')}"
    # 这个形状里 **id 摊在外面、内容在壳里**，所以「正身」还是元素本身
    # （core_path 为空），救回标题作者的是那个限深搜索。
    assert out["best"]["stats"]["core_path"] == "", out["best"]["stats"]
    assert out["best"]["stats"]["title_rate"] == 1.0, "标题在壳里，取不到就会全存成 null"
    assert out["best"]["stats"]["author_rate"] == 1.0, "作者在壳里，取不到就会全存成 null"

    body = (f"const f = S.recogniseList({json.dumps(caps)});"
            "console.log(JSON.stringify(S.normaliseItems(f.best, "
            "{platform:'p', urlBuilder:(raw,id)=>`https://p.example.com/x/${id}`})));")
    got = _run(body)
    assert len(got["items"]) == 5
    assert got["items"][0]["title"] == "第1条", got["items"][0]
    assert got["items"][0]["author_name"] == "作者1", got["items"][0]
    assert got["items"][0]["url"].endswith("/x/n1"), "id 在壳外，拼网址要用外面那个"


def test_digging_into_a_wrapper_needs_corroboration() -> None:
    """**挖得越深越要旁证。**

    `id` 是最常见的字段名之一——挖五层几乎能在任何数组里挖出一个来
    （埋点事件、实验分组、配置项都带 id）。所以放宽深度的同时必须收紧判据：
    挖到壳里去的，必须另有一致的标题或作者，光有 id 不算。
    否则这个改动会把一堆埋点数组认成他的收藏。
    """
    events = [{"seq": i, "payload": {"id": f"evt{i}", "ms": i}} for i in range(8)]
    out = _run("console.log(JSON.stringify(S.recogniseList("
               f"{json.dumps([_capture('https://p.example.com/api/track', {'e': events})])})));")
    assert out["ok"] is False, f"埋点数组被认成收藏列表了：{out.get('best', {}).get('path')}"
    assert "旁证" in out["rejected"][0]["why"], out["rejected"]


def test_the_url_is_taken_from_the_data_before_it_is_ever_built() -> None:
    """**拼错的网址比没有更糟。**

    它会安安静静进档案馆，半年后点开才发现全是 404，那时已无从追溯。
    所以顺序是：条目自带的绝对网址 → 相对路径拼本站域 → 短码套模板 →
    id 套模板 → **都不成立就跳过并报数**。每条还要记下它是怎么来的。
    """
    items = [{"data": {"id": f"a{i}", "title": f"t{i}", "author": f"u{i}",
                       "permalink": f"/r/s/comments/a{i}/t/"}} for i in range(4)]
    body = (f"const f = S.recogniseList({json.dumps([_capture('https://p.example.com/l', {'children': items})])});"
            "console.log(JSON.stringify(S.normaliseItems(f.best, "
            "{platform:'p', origin:'https://www.example.com',"
            " urlBuilder:(raw,id)=>`https://WRONG.example.com/${id}`})));")
    got = _run(body)
    assert len(got["items"]) == 4, got
    assert got["items"][0]["url"] == "https://www.example.com/r/s/comments/a0/t/", got["items"][0]
    assert got["items"][0]["raw_metadata"]["derived_by"] == "relative_link"
    assert "WRONG" not in json.dumps(got), "数据里明明带着网址，却去拼了一个"


def test_an_item_with_no_derivable_url_is_skipped_and_counted() -> None:
    """没法说出网址的，跳过并报数——**不许硬拼一个**。"""
    items = [{"data": {"id": "", "title": f"t{i}", "author": "u"}} for i in range(4)]
    body = (f"const f = S.recogniseList({json.dumps([_capture('https://p.example.com/l', {'children': items})])});"
            "console.log(JSON.stringify(f.ok ? S.normaliseItems(f.best, "
            "{platform:'p', urlBuilder:(raw,id)=>(id?`https://p.example.com/${id}`:'')}) "
            ": {items:[],skipped:[]}));")
    got = _run(body)
    assert not got["items"], "没有 id 也没有链接，却拼出了网址"
    if got["skipped"]:
        assert got["skipped"][0]["reason"] == "没有能在浏览器里打开的网址"


def test_the_cover_image_comes_along() -> None:
    """**按形状读进来的条目此前一个媒体地址都不带。**

    他打开资料库看到的是一排纯文字。而 `CaptureRequest` 一直支持 `media_urls`、
    批次协议（items 就是 CaptureRequest）也一直原样透传——
    **缺的只是取数这一步没取**。

    取法只有一条规则：这个值是 http(s) 字符串，而它所在的**键路径里有媒体词**
    （cover / image / thumb / video / candidates …）。不看域名（各家 CDN
    穷举不完），不看后缀（很多平台的图片地址不带 .jpg）。
    """
    items = [{"id": f"n{i}", "note_card": {
        "display_title": f"笔记{i}", "user": {"nickname": "作者"},
        "cover": {"url_default": f"https://img.example/{i}.webp"}}} for i in range(4)]
    body = (f"const f = S.recogniseList({json.dumps([_capture('https://p.example.com/l', {'notes': items})])});"
            "console.log(JSON.stringify(S.normaliseItems(f.best, "
            "{platform:'p', urlBuilder:(raw,id)=>`https://p.example.com/x/${id}`})));")
    got = _run(body)
    assert len(got["items"]) == 4
    assert got["items"][0]["media_urls"] == ["https://img.example/0.webp"], got["items"][0]


def test_a_head_shot_next_to_the_content_is_not_mistaken_for_a_cover() -> None:
    """**取不到就空着，不许拿别的顶。**

    条目里没有任何媒体字段时必须是空数组——那是诚实的"没有"。
    随手抓一个 http 串（比如作者主页链接）顶上去，他会看到一排错的缩略图，
    而且**看起来像是对的**。
    """
    items = [{"id": f"n{i}", "title": f"t{i}",
              "author": {"name": "作者", "home": "https://p.example.com/user/1"}}
             for i in range(4)]
    body = (f"const f = S.recogniseList({json.dumps([_capture('https://p.example.com/l', {'notes': items})])});"
            "console.log(JSON.stringify(S.normaliseItems(f.best, "
            "{platform:'p', urlBuilder:(raw,id)=>`https://p.example.com/x/${id}`})));")
    got = _run(body)
    assert got["items"][0]["media_urls"] == [], got["items"][0]
