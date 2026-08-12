"""服务徽章要同时读「后台状态」和「插件版本」（v0.0.0.20）。

上一版把兼容判据改成「不低于下限」时我写下这句话：

    界面文案这类改动值得提示「有新版本」，不值得把人挡在外面。

**然后我只做了「不挡」那一半。** `outdated` 算出来了，
而**没有任何地方读它**——「建好了没接上」，在修完同一个毛病的下一轮里自己犯的。

补上之后还有第二个坑：那两个来源是**并行加载**的
（启动时的 `Promise.allSettled([loadHealth(), …, refreshExtensionStatus()])`），
谁先回来不一定。第一版把那句话写在 `loadHealth` 里，于是插件状态如果后回来，
它就永远不出现；而 `refreshEverything` 压根不调 `loadHealth`，
徽章连重画的机会都没有。**靠调用顺序成立的界面，早晚会在某次加载里失灵。**

⚠️ 这里跑的是把 `paintServiceBadge` 抽出来在 Node 里喂三种状态。
**不是浏览器检查**：资料库那个演练加载不了扩展，
`state.extension.detected` 永远是 false，走不到「插件有新版」那一支。
浏览器里验到的是另外两支（后台挂了 / 一切正常），在 pwa_render_drill 里。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_JS = ROOT / "apps/pwa/app.js"


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}")
    opening = source.index("{", source.index("(", start))
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start: index + 1]
    raise AssertionError(f"{name} 的花括号没有闭合")


def _paint(state: dict) -> dict:
    source = APP_JS.read_text(encoding="utf-8")
    body = _function(source, "paintServiceBadge")
    # **它用到的 helper 也从源码里抠，不在这里造一个假的。**（2026-08-10）
    # 造假的话，helper 的行为和真的漂开了这条判据也发现不了——
    # 而 `paintServiceBadge` 现在正是靠 compareVersions 分「连不连得上」那两档。
    helper = _function(source, "compareVersions")
    script = f"""
    const PRODUCT_VERSION = "9.9.9.9";
    {helper}
    let painted = {{ cls: "", text: "" }};
    function setServiceBadge(cls, text) {{ painted = {{ cls, text }}; }}
    const state = {json.dumps(state)};
    {body}
    paintServiceBadge();
    console.log(JSON.stringify(painted));
    """
    done = subprocess.run(["node", "-e", script], cwd=ROOT,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr[-400:]
    return json.loads(done.stdout.strip().splitlines()[-1])


ALIVE = {"ever_seen": True, "alive": True}
DEAD = {"ever_seen": True, "alive": False}


def test_a_dead_worker_wins_over_everything_else() -> None:
    """后台挂了是最要紧的一件事，不许被更新提示盖过去。"""
    out = _paint({"health": {"version": "9.9.9.9", "worker": DEAD},
                  "extension": {"detected": True, "compatible": True, "outdated": True}})
    assert "后台没在跑" in out["text"], out
    assert out["cls"] == "needs"


def test_an_old_extension_that_really_cannot_connect_says_so() -> None:
    """**「旧版连不上账号」是真的——但只对 v0.0.0.22 之前的。**

    权限申请原来写在 service worker 里，那里拿不到用户手势，
    `chrome.permissions.request` 三种写法全抛——他点「连接账号」不会有任何反应。
    修复把它挪进 connect-frame（132d6038d，当时 VERSION = 0.0.0.22）。
    """
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True,
                                "outdated": True, "version": "0.0.0.21"}})
    assert "连不上账号" in out["text"], f"真连不上的那一档没说清：{out}"
    assert "已存的内容不受影响" in out["text"], f"没说清数据还在：{out}"
    assert out["cls"] == "connected", "只是插件旧，不该把整条画成告警"


def test_a_usable_but_outdated_extension_is_not_told_it_cannot_connect() -> None:
    """**他装的就是这一档（0.0.0.25）。**（2026-08-10）

    那句话原来挂在 `outdated` 上：只要不是最新版就说「连不上账号」。
    而他这天要做的正是「重新连一次抖音/B站」——这句话会让他以为必须先换插件，
    不换就以为坏了。**产品在他动手那一刻说了假话。**
    """
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True,
                                "outdated": True, "version": "0.0.0.25"}})
    for lie in ("连不上账号", "连不上", "无法连接"):
        assert lie not in out["text"], (
            f"0.0.0.25 连得上，却告诉他「{lie}」：{out}")
    assert "新版" in out["text"], f"该更新那半边没说：{out}"
    assert "0.0.0.25" in out["text"] and "9.9.9.9" in out["text"], (
        f"两个版本号要都摆出来，他不用猜自己在哪一版：{out}")
    assert "新平台" in out["text"] or "新修复" in out["text"], (
        f"只说有新版、没说不更新会缺什么，他没有理由去更新：{out}")
    assert out["cls"] == "connected"


def test_a_current_extension_says_nothing_extra() -> None:
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True, "outdated": False}})
    assert "更新插件" not in out["text"], f"插件已是最新却还在提示更新：{out}"
    assert "已连接" in out["text"]


def test_it_does_not_depend_on_which_request_finishes_first() -> None:
    """两个来源并行加载，**徽章必须在它们各自落地之后都重画一次**。

    只在 loadHealth 里画的话，插件状态后回来就永远显示不出来。
    """
    code = "\n".join(line for line in APP_JS.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("//"))
    calls = len(re.findall(r"paintServiceBadge\(\)", code))
    assert calls >= 3, (
        f"paintServiceBadge 只被调了 {calls} 次——"
        "它要在 loadHealth、refreshEverything、以及启动那三件并行跑完之后各画一次"
    )
    # refreshEverything 里必须有它：他刚更新完插件，徽章得跟着变
    refresh = _function(code, "refreshEverything")
    assert "paintServiceBadge" in refresh, (
        "refreshEverything 不重画徽章——他刚更新完插件，那句话会一直挂着"
    )


def test_the_badge_shows_which_extension_version_is_installed() -> None:
    """**他随时要能读出插件版本，不用我去查他的库。**

    2026-08-07 去生产库里查「他装的是哪一版」——查不到：账号 metadata、
    同步记录、evidence 里都没有版本号。于是他说「不能用」时我只能猜，
    而猜的第一句往往是"你在旧版上"，那正是他最烦的来回。

    连接时把版本记进服务端只对**连接之后**有用；而他最需要说清版本的时刻
    恰恰是"连不上"的时候。所以徽章上一直显示。
    """
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True,
                                "outdated": False, "version": "0.0.0.22"}})
    assert "插件 v0.0.0.22" in out["text"], f"徽章上读不出插件版本：{out}"
    # 没装插件时不许硬编一个版本号出来
    blank = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                    "extension": {"detected": False, "compatible": False, "version": ""}})
    assert "插件 v" not in blank["text"], f"没装插件却显示了版本：{blank}"


def test_a_modern_but_unpaired_extension_is_not_told_it_cannot_connect() -> None:
    """**别用 `connectFrameUrl` 当「连不连得上」的判据。**（2026-08-10）

    「下一步」卡片判的是 `!state.extension.connectFrameUrl`（有没有连接框），
    那在它那个上下文里是对的。但徽章不能照抄：**新插件在还没配对时
    这个字段同样是空的**，照抄会对连得上的人说「连不上」。

    所以徽章判的是版本（`< 0.0.0.22` 才是真连不上那一档）。
    这条判据钉住那个区别——照抄的话它会红。
    """
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True, "outdated": True,
                                "version": "0.0.0.25", "connectFrameUrl": ""}})
    for lie in ("连不上账号", "连不上", "无法连接"):
        assert lie not in out["text"], (
            f"新插件只是还没配对，却被说成「{lie}」：{out}")
