"""守住抓取演练本身（v0.0.0.7 / T08）。

演练脚本自己也会腐坏，而它腐坏的方式最阴：**永远 PASS**。
那比没有演练更坏——没有演练时人知道自己没验过。

这些判据守四件事：它必须能失败、它必须照抄诊断的顺序、
它必须真去读抓到的字节、它必须什么都不留下。
"""

from pathlib import Path

DRILL = (Path(__file__).resolve().parents[2] / "scripts/extension_capture_drill.py").read_text(
    encoding="utf-8"
)


def test_the_drill_can_fail() -> None:
    """反例：换一个绝不会出现的前缀，必须抓到 0 条。

    没有这一步的话，「抓到 2 条」既可能是前缀匹配对了，
    也可能是观察器把所有请求都抓了——两者看起来一模一样。

    反例的做法：让它以为这个标签页在另一个域名上，于是**推出来的前缀绝对匹配不上**。
    """
    assert "bogusHost" in DRILL, "反例不见了——这个演练从此只会 PASS"
    assert "不存在.invalid" in DRILL, "反例用的不是一个必定匹配不上的域名"
    assert 'counter.get("captures")' in DRILL, "反例抓到的条数没有被判据用上"


def test_the_drill_calls_the_real_function_not_a_copy_of_it() -> None:
    """演练必须调**正本**，不能照抄一遍处理器的顺序。

    抄件和正本一分叉，演练就会在正本坏掉的时候继续绿。
    2026-08-05 差点就是这样：正本的注入时机改了两处，而抄件没改。
    """
    assert "installNetObserverForTab(" in DRILL, "演练又在自己重写一遍安装流程"
    for reimplemented in ("chrome.scripting.executeScript", "SA_OBSERVER_CONFIGURE"):
        assert reimplemented not in DRILL, (
            f"演练里出现了 {reimplemented}——它在重写正本，而不是调用正本"
        )


def test_the_observer_lands_before_the_page_runs_its_own_js() -> None:
    """**这条判据钉的是这一天里最贵的那个发现。**

    原来是「刷新 → 等 1500ms → executeScript」。实测（2026-08-05，真 Chrome +
    回环假站，页面像真收藏夹页那样只在加载时发一次请求）：观察器自报
    installed/ready 全为 true，抓到 **0 条**——收藏列表那个请求在观察器
    落地之前就打完了。而 Owner 只需要动一次手，那一下如果是这样就白费了。

    改法是注册成 document_start 的内容脚本再刷新。回到 executeScript 就等于
    把那个 0 条重新装回去，所以这里把它钉死。
    """
    background = (BACKGROUND := (Path(__file__).resolve().parents[2]
                                 / "apps/browser-extension/background.js").read_text(encoding="utf-8"))
    install = background.split("async function installNetObserverForTab", 1)[1].split("\nasync function", 1)[0]
    assert "registerContentScripts" in install, "观察器又改回了后注入——页面加载时那个请求会抓不到"
    assert '"document_start"' in install or "'document_start'" in install, "注册的不是 document_start"
    assert "waitForTabComplete" in install, "又在硬等固定毫秒——那把「等够了」和「等到了」混成一件事"
    assert BACKGROUND.count("setTimeout(resolve, 1500)") == 0, "1500ms 硬等又回来了"


def test_the_drill_actually_reads_the_captured_bytes() -> None:
    """「拦到了」和「读得懂」是两件事。

    并且必须**解包**解析器的返回值——它返回 `(条目, 还有下一页)`，
    `len(整个返回值)` 永远等于 2，而 2 正是期望的条目数：条目为空也会绿。
    这个坑在写演练的当天就踩了一次。
    """
    assert "parse_bilibili_favlist" in DRILL, "演练没有去读抓到的字节，只数了条数"
    assert "len(parse_bilibili_favlist(" not in DRILL, (
        "又数成了两元组的长度——那永远是 2，抓到空条目也会绿"
    )
    assert "items, _has_more = parse_bilibili_favlist" in DRILL, "解析器的返回值没有解包"


def test_the_drill_leaves_nothing_behind() -> None:
    for cleanup, why in (
        ("shutil.rmtree(profile", "一次性 profile 没删"),
        ("process.terminate()", "测试用 Chrome 没关"),
        ("server.shutdown()", "本地假站没关，端口会一直被占着"),
    ):
        assert cleanup in DRILL, why


def test_the_drill_never_reaches_a_real_platform() -> None:
    """回环演练一旦真去连平台，它就不再是演练了。"""
    for forbidden in ("bilibili.com", "xiaohongshu.com", "douyin.com", "x.com"):
        assert forbidden not in DRILL, f"演练里出现了真实平台域名：{forbidden}"
    assert "127.0.0.1" in DRILL


def test_a_full_buffer_drops_the_newest_not_the_oldest() -> None:
    """缓冲区满了要丢**新的**，不是丢最早的。

    收藏列表那个请求是页面加载时打的，**它永远是最早的那几条之一**；
    后面涌进来的是心跳、埋点之类的噪声。丢最早的等于专门丢掉唯一有用的那条，
    而且丢得悄无声息——用户看到的是「拦到 200 条，0 条读得懂」。
    """
    background = (Path(__file__).resolve().parents[2]
                  / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    overflow = background.split("netCaptureBuffer.length > NET_CAPTURE_LIMIT", 1)[1][:200]
    assert "netCaptureBuffer.pop()" in overflow, "又改回丢最早的那条了"
    assert "netCaptureBuffer.shift()" not in overflow
    assert "netCapturesDropped" in overflow, "丢掉的条数没记，触顶会变成静默的零"
    assert "dropped" in background.split("SA_PARSE_NET_CAPTURES", 1)[1][:3000], \
        "丢掉的条数没报给用户——静默触顶和「平台没发这个请求」看起来一模一样"


def test_each_diagnostic_starts_from_a_clean_buffer() -> None:
    """一次诊断 = 一次新的测量，不能带着上一次的残留。

    缓冲区原来从头到尾没人清过，只靠 service worker 睡着（约 30 秒）自然消失。
    连按两次诊断，第二次会把第一次的响应一起数进去；换个平台再按更糟——
    拿这个平台去解析上一轮那个平台的字节，全判读不懂，报回来的第一条问题指错方向。

    **这个缺口是演练替产品做了它该做的事才露出来的**：探针里得手写
    netCaptureBuffer.length = 0 才量得准——要手动清，说明产品自己没清。
    """
    background = (Path(__file__).resolve().parents[2]
                  / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    install = background.split("async function installNetObserverForTab", 1)[1].split("\nasync function", 1)[0]
    assert "netCaptureBuffer.length = 0" in install, "诊断开始时不清缓冲区，两次诊断会混在一起"
    assert "netCapturesDropped = 0" in install, "丢弃计数不清零，会把上一次丢掉的算到这一次头上"


def test_the_diagnostic_does_not_upload_two_hundred_bodies_one_at_a_time() -> None:
    """诊断模式的前缀是从域名推的，页面上**每一个**请求都会被抓。

    真实收藏夹页跑满 200 条毫不费力。而解析是「一条一个 HTTP 往返、
    每条 20 秒超时、还要把响应体整个传上去」——200 条就是几分钟的卡死。
    **Owner 只按一次，卡在那里的话他不知道是没坏还是坏了。**

    收敛两步：按去掉查询串的地址去重（页面反复轮询的是同一个接口，
    而收藏列表那个地址是独一份的），再封顶取最早的若干条（收藏列表那个请求
    是加载时打的，永远在最早的那几条里）。

    **两步都不许静默**：没读的条数要说出来——悄悄少读几条，和「平台压根
    没发那个请求」在界面上长得一模一样，而这两件事的下一步完全不同。
    """
    background = (Path(__file__).resolve().parents[2]
                  / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    parse = background.split("SA_PARSE_NET_CAPTURES", 1)[1][:4000]
    assert "PARSE_LIMIT" in parse, "解析没有封顶，200 条会把 Owner 卡在那里"
    assert "seenUrls" in parse, "解析前没有按地址去重"
    assert "for (const capture of toParse)" in parse, "还是在遍历整个缓冲区"
    assert "notParsed" in parse, "没读的条数没算出来"
    assert "没有逐条去读" in parse, "没读的条数没告诉用户——静默少读和「平台没发」长得一样"


def test_the_drill_goes_all_the_way_through_freezing_the_prefix() -> None:
    """演练要走到**固化**为止，不能停在「读得懂」。

    freeze_intercept_prefix.py 的**成功那条路**在此之前一次都没跑过——
    单元判据验的全是它的「拒绝」。而成功那条恰恰是 Owner 按完诊断之后要走的。

    演练里那个地址是**真 Chrome 抓到、生产解析器读得懂**的那一个，
    比手写的报告更有说服力。写进去的是一份**临时**目录副本，真目录不碰。
    """
    assert "freeze_intercept_prefix.py" in DRILL, "演练停在「读得懂」，没走到固化"
    assert "catalog_now_says" in DRILL, "没有回头核对目录里到底写进去了什么"
    assert "tempfile.TemporaryDirectory(prefix=\"sa-freeze-\")" in DRILL, (
        "固化那一步没有写进临时副本——演练绝不能改真的平台目录"
    )
    assert 'FAV_PATH not in freeze["catalog_now_says"]' in DRILL, (
        "写进去了但没核对是不是这次抓到的那个地址"
    )
