r"""一条都读不懂 ≠ 这一按白按了（2026-08-12）。

## 为什么钉这一条

说明书把那颗诊断按钮写成了「只有你做得到的那一下」。那一按的**目的是找出该盯
哪个地址**（T09 抓到即固化），不是把收藏收进来——地址进了 `urls`、也送到了他
自己的服务器，那件事就成了。

而原来这条路只会说：

    拦到了响应，但一条都读不懂。

他照着说明书按了唯一的一下，屏幕回他一句听起来像失败的话，**真正要紧的那件事
一个字都没提**。他会以为没成，要么再按一遍，要么干脆不告诉我。

**而「读不懂」是这一按的常态，不是例外。** 实测：B 站收藏页真正请求的四个接口

    x/v3/fav/folder/info      x/v3/fav/folder/whitelist
    x/v3/fav/resource/ids     x/v3/fav/resource/infos

拿真响应喂进服务端解析器，**四个全是 `PAYLOAD_SHAPE_CHANGED` / `PLATFORM_REFUSED`**
——解析器只认 `resource/list`，而网页根本不打那一条。

## 它怎么验

把 `background.js` 里那段 `message_zh` 三分支原样抠出来，在 node 里按三种情形
各跑一次，看他会读到什么。不是读代码，是把那句话真的算出来。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = ROOT / "apps" / "browser-extension" / "background.js"


def _message(readable: int, captured: int, items: int) -> str:
    """按 background.js 里那段三分支，算出他会看到的那句话。

    表达式是从源码里**抠出来的**，不是我在这里重写一份——重写就成了第二把尺子。
    """
    source = BACKGROUND.read_text(encoding="utf-8")
    match = re.search(r"message_zh: readable > 0\s*\n(.*?)\n\s*\};", source, re.S)
    assert match, "background.js 里找不到那段 message_zh 三分支——判据失去依附"
    # 抠出来的那段末尾带着对象属性的逗号，node 会当成语法错误——去掉它。
    expression = "readable > 0\n" + match.group(1).rstrip().rstrip(",")
    node = shutil.which("node")
    if not node:                                             # pragma: no cover
        pytest.skip("这台机器上没有 node")
    script = f"""
      const readable = {readable}, items = {items}, note = "", importedNote = "";
      const firstProblem = null;
      const netCaptureBuffer = {{ length: {captured} }};
      console.log(JSON.stringify({{ said: ({expression}) }}));
    """
    done = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stdout + done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])["said"]


def test_nothing_readable_but_addresses_captured_says_the_address_was_kept() -> None:
    """**这是他最可能看到的那一屏。**"""
    said = _message(readable=0, captured=30, items=0)
    assert "地址" in said, f"没提地址——他会以为白按了：{said!r}"
    assert "30" in said, f"没说拦到了多少条：{said!r}"
    # 不许只剩一句听起来像失败的话
    assert said.strip() != "拦到了响应，但一条都读不懂。", "还是原来那句"


def test_nothing_captured_at_all_still_says_so_plainly() -> None:
    """反面：真的一条都没拦到时，不许说「地址已经记下来了」——那是假话。"""
    said = _message(readable=0, captured=0, items=0)
    assert "地址已经记下来" not in said, f"一条都没拦到却说记下了地址：{said!r}"
    assert "没拦到" in said or "没有" in said, said


def test_the_happy_path_still_reports_what_it_read() -> None:
    said = _message(readable=2, captured=30, items=12)
    assert "2" in said and "12" in said, said
    assert "地址已经记下来" not in said, "读得懂的时候不该拿地址那句话顶上去"
