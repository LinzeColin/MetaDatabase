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
