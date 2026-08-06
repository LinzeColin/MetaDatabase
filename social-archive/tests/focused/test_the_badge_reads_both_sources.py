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
    script = f"""
    const PRODUCT_VERSION = "9.9.9.9";
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
    """后台挂了是最要紧的一件事，不许被「插件有新版」盖过去。"""
    out = _paint({"health": {"version": "9.9.9.9", "worker": DEAD},
                  "extension": {"detected": True, "compatible": True, "outdated": True}})
    assert "后台没在跑" in out["text"], out
    assert out["cls"] == "needs"


def test_an_outdated_but_usable_extension_is_mentioned_not_blocked() -> None:
    """**这一支就是那个没人读的字段。** 说一句，但不拦。"""
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True, "outdated": True}})
    assert "插件有新版" in out["text"], f"「有新版本」那半边还是没说：{out}"
    # **两件事都要说，少一件都会误导。**
    # 只说「不影响使用」：v0.0.0.22 起不成立了——Reddit / Instagram 的取数路
    # 在插件里，不更新就是没有，而资料库这边一切正常，他没理由去点更新。
    # 只说「不更新就没有新平台」：他会以为自己又被挡在外面了（那是上一版的伤）。
    assert "现在能用" in out["text"], "没说清它现在就能用，他会以为又被挡住了"
    assert "更新" in out["text"], "没说清不更新会少什么，他不会有理由去更新"
    assert out["cls"] == "connected", "只是有新版本，不该画成告警"


def test_a_current_extension_says_nothing_extra() -> None:
    out = _paint({"health": {"version": "9.9.9.9", "worker": ALIVE},
                  "extension": {"detected": True, "compatible": True, "outdated": False}})
    assert "插件有新版" not in out["text"], f"插件已是最新却还在提示更新：{out}"
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
