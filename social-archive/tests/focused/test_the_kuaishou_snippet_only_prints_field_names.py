r"""我请他粘进控制台的那段代码，**真跑一遍，并证明它不打印内容**（2026-08-11）。

## 为什么要有这条

快手那条取数路是唯一还没验通的——挡住它的不是代码，是一个事实：
**快手收藏列表返回的 JSON 里，编号/标题/作者三个字段各叫什么**，
只有登录状态下看得到。我自己编一份夹具去测，绿或红都不算数
（试过一版，7 条里 3 条丢作者，多半是我把字段名猜错了）。

所以我写了 `scripts/快手字段名怎么给我.md`，请他粘一段进控制台。
**那是我请他在自己浏览器里运行的代码**——它必须满足两件事，
而这两件事都不能靠我说了算：

1. **它真的跑得出东西**（不是一段看起来对的代码）；
2. **它只打印字段名，不打印任何一条内容的值**。

这条判据把文档里那段代码原样抠出来，喂一个「快手形状」的合成响应，
在 node 里真跑，然后逐条核对。

## 边界

合成响应是我按公开可见的结构编的——**这条判据不证明快手真的长这样**，
那正是要问他的问题。它只保证：这段代码本身跑得动、且不外泄内容。
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "scripts/快手字段名怎么给我.md"

SYNTHETIC = """
globalThis.window = globalThis;
const body = JSON.stringify({ data: { visionProfilePhotoList: { feeds:
  Array.from({length: 20}, (_, i) => ({ photoId: "p"+i, caption: "标题"+i,
    userName: "作者"+i, timestamp: 1700000000+i, coverUrl: "https://cover/"+i })) } } });
globalThis.fetch = async () => ({ clone: () => ({ text: async () => body }) });
"""


def _snippet() -> str:
    blocks = re.findall(r"```js\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)
    assert len(blocks) == 2, (
        f"文档里的 js 代码块变成了 {len(blocks)} 段——这条判据按「第一段是安装器、"
        "第二段是取结果」取的，结构变了就取错了")
    return blocks[0]


def _run() -> list[dict]:
    script = (SYNTHETIC + _snippet() +
              '\nawait globalThis.fetch("https://www.kuaishou.com/graphql");'
              '\nawait new Promise(r => setTimeout(r, 50));'
              '\nconsole.log(JSON.stringify(globalThis.__ks));')
    done = subprocess.run(["node", "--input-type=module", "-e", script],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr[-600:]
    line = [l for l in done.stdout.splitlines() if l.startswith("[")]
    assert line, f"那段代码没产出结果：{done.stdout[-300:]}"
    return json.loads(line[-1])


def test_it_finds_the_list_and_reports_the_field_names() -> None:
    """跑得出东西——不是一段看起来对的代码。"""
    found = _run()
    assert found, "喂了一个 20 条的列表进去，它一条都没认出来"
    names = found[0]["第一条的字段名"]
    assert {"photoId", "caption", "userName"} <= set(names), names
    assert found[0]["条数"] == 20
    assert "feeds" in found[0]["数组在"], found[0]["数组在"]


def test_it_never_prints_a_single_value() -> None:
    """**这条是我请他运行这段代码的前提。**

    合成响应里每个值都带着可识别的标记（`标题0`/`作者0`/`https://cover/`），
    任意一个出现在输出里，就说明这段代码会把他的内容带出来。
    """
    dumped = json.dumps(_run(), ensure_ascii=False)
    for leak in ("标题0", "作者0", "https://cover/", "p0"):
        assert leak not in dumped, f"它把内容打出来了：{leak}"


def test_the_doc_says_what_it_does_and_does_not_print() -> None:
    """他要能自己判断该不该运行它——所以文档必须把这件事说在明面上。"""
    text = DOC.read_text(encoding="utf-8")
    assert "只打印字段名" in text
    assert "Object.keys" in text, "没说清「取的是字段名」这件事在代码里是哪一句"
    assert "不想弄也没关系" in text, "没给他一条「不做」的出路"
