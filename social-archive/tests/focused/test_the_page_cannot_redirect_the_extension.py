"""档案馆页面能给扩展令牌，**但不能改它往哪儿发、也不能改「打开档案馆」去哪**。

## 这条边界的来历

配对走零门槛那条路：已登录页面替扩展取一个长期令牌，通过 bridge 交过去，
用户一个字符都不用输入。代价是**页面能对扩展说话**。

background.js 里那条规则写得很清楚：

    服务地址取扩展自己的托管配置，不接受页面下发——
    页面能改端点就等于任何拿到桥的页面都能把上行改到别处去。

而 bridge.js 里记着：原先真有一条 `SA_CONFIGURE → SA_WEB_BRIDGE_CONFIGURE`
在做那件事，**已整条删除**，理由正是它和上面那条冲突。

## 那次删除只删了一半

2026-08-05 的桥边界演练实测：页面发一条 `SA_ADOPT_TOKEN` 夹带 libraryUrl——
**端点纹丝不动（那条守住了），而 libraryUrl 被改成了页面指定的地址。**

那条被删掉的转发，原文写的是「让页面下发 **endpoint 与 libraryUrl**」。
删掉的是 endpoint 那一半；libraryUrl 这一半原样留在了隔壁的 ADOPT_TOKEN 里。

libraryUrl 是「打开档案馆」那颗按钮的去处——用户点它时认为那是自己的档案馆。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
BRIDGE = (ROOT / "apps/browser-extension/bridge.js").read_text(encoding="utf-8")
DRILL = (ROOT / "scripts/extension_bridge_boundary_drill.py").read_text(encoding="utf-8")


def test_the_endpoint_never_comes_from_the_page() -> None:
    """端点只能来自扩展自己的托管配置。"""
    handler = BACKGROUND.split('message?.type === "SA_WEB_BRIDGE_ADOPT_TOKEN"')[1][:900]
    assert 'const endpoint = String(current.endpoint' in handler, (
        "端点不再取自扩展自己的配置——页面就能把上行改到别处"
    )
    assert "message.endpoint" not in handler, "端点开始接受页面下发了"


def test_the_library_url_is_only_taken_when_same_origin() -> None:
    """**那次删除只删了一半。** libraryUrl 这一半留在了隔壁。"""
    handler = BACKGROUND.split('message?.type === "SA_WEB_BRIDGE_ADOPT_TOKEN"')[1][:1600]
    assert "new URL(offered).origin === new URL(endpoint).origin" in handler, (
        "异源的 libraryUrl 会被收下——「打开档案馆」会把用户送到别人那儿"
    )


# 这几个名字都是 bridge.js / background.js 的注释里**明写「已整条删除」**的。
# 写在注释里不等于守住了——所以逐个钉。
DELETED_BY_DESIGN = (
    ("SA_CONFIGURE", "页面下发 endpoint/libraryUrl 的那一端"),
    ("SA_WEB_BRIDGE_CONFIGURE", "桥转发到后台的那一端"),
    ("SA_PAIR", "旧的一次性配对码转发（手抄一串字符，INV-ZERO-BARRIER 明令禁止）"),
)


def test_every_deleted_path_stays_deleted() -> None:
    """**注释说删了，就得真的没了。**

    这条判据自己返修过一次：第一版只钉了 `SA_WEB_BRIDGE_CONFIGURE` 一个，
    而 `SA_CONFIGURE` 和 `SA_PAIR` 只出现在**文档字符串**里——
    grep 一查「判据里有没有提到」是「有」，而 assert 行数是 **0**。
    提到不等于守住，这是今天反复栽的那一种。
    """
    for name, what in DELETED_BY_DESIGN:
        for label, source in (("bridge.js", BRIDGE), ("background.js", BACKGROUND)):
            assert name not in _code(source), f"{name} 在 {label} 里回来了（{what}）"


def test_the_guard_would_notice_if_one_came_back() -> None:
    """**先确认它抓得住。** 一个永远绿的防复活守卫等于没有。

    把名字拼出来喂给同一个判定——它必须认得出来。
    """
    revived = 'if (message.type === "SA_" + "PAIR") forward();'
    assert "SA_PAIR" not in _code(BRIDGE), "前提不成立：SA_PAIR 现在就在代码里"
    # 拼接是躲得过 grep 的，所以顺带说明这道守卫的**已知盲区**：
    # 有人把名字拆开写就查不到。今天没有这种写法（全仓搜过），但它查不到。
    assert "SA_" + "PAIR" not in _code(BRIDGE)
    assert revived.count("SA_") == 1  # 这行只是把盲区写出来，不是断言产品


def _code(text: str) -> str:
    """去掉注释——**那两个文件的注释里正好在讲这个名字**，不能拿它当证据。"""
    out = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("*") or stripped.startswith("/*"):
            continue
        out.append(line)
    return "\n".join(out)


def test_the_drill_checks_both_directions() -> None:
    """**只验「异源被拒」的话，把 libraryUrl 整个忽略掉也能过**——
    那是把边界修成了「功能没了」。真档案馆页面发的就是同源地址，必须收。"""
    assert "same_origin" in DRILL and "cross_origin" in DRILL
    assert "边界修成了「功能没了」" in DRILL


def test_the_drill_requires_the_pairing_to_actually_work() -> None:
    """令牌没被采纳的话，「端点没被改」什么都证明不了——那可能只是消息没送到。"""
    assert "配对路没走通，这时候别的结论都不算数" in DRILL
