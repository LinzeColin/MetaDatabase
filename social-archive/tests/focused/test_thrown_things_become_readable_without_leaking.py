r"""抛出物写进回执之前，必须**能读**，而且**不带值**（2026-08-12）。

## 撞见它的经过

`background.js` 里那一行原来是：

    error: String(error?.message || error).slice(0, 300),

node 实测四种抛出物：

    new Error("网络超时")         → "网络超时"          ✓
    "纯字符串错误"                 → "纯字符串错误"       ✓
    {code:502, detail:"上游拒绝"}  → "[object Object]"   ✗
    ["a","b"]                     → "a,b"              ✓

第三种把 `[object Object]` 写进 cursor 的 error 字段，而**那个字段跟着这次同步
落进服务端回执、是我从生产直接读的那一个**。读到 `[object Object]` 等于什么都没读到。

## 为什么不能直接 JSON.stringify

那一行**自己上面的注释**写着：「只留 URL 和淘汰理由，**不留响应内容**
（那可能是他的私人数据）」。把错误对象整个序列化进去正好违反这一条——
一个 502 的错误对象往往就带着响应体。

所以 `describeThrown` 只取**形状**：构造器名 + 键名，绝不取值。
这两条要一起钉：只钉「可读」会诱使人去 stringify，只钉「不泄漏」
会诱使人回到那个恒定的兜底串。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKGROUND = ROOT / "apps/browser-extension/background.js"


def _call(payload_js: str) -> str:
    """在真 node 里跑**产品那一份** describeThrown，不在这里另抄一遍。"""
    source = BACKGROUND.read_text(encoding="utf-8")
    start = source.index("function describeThrown")
    end = source.index("\nfunction ", start + 1)
    script = (source[start:end]
              + f"\nprocess.stdout.write(JSON.stringify(describeThrown({payload_js})));")
    done = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(done.stdout)


@pytest.mark.parametrize("payload_js,expected", [
    ('new Error("网络超时")', "网络超时"),
    ('"纯字符串错误"', "纯字符串错误"),
])
def test_the_readable_cases_stay_readable(payload_js: str, expected: str) -> None:
    assert _call(payload_js) == expected


def test_a_plain_object_does_not_become_object_Object() -> None:
    """这是原来那个缺陷本身。"""
    out = _call('{code: 502, detail: "上游拒绝"}')
    assert not out.startswith("[object"), f"又写回 [object Object] 了：{out!r}"
    # 形状要说得出是什么，否则「可读」只是换了一个没信息的串
    assert "code" in out and "detail" in out, f"连键名都没有，读了也不知道是什么：{out!r}"


def test_it_never_puts_the_values_into_the_receipt() -> None:
    """**这一条比上一条重要。**

    回执是要落到服务端、被我从生产读出来的东西。值可能是他的私人数据，
    一旦写进去就跟着备份走了三份，删不干净。
    """
    out = _call('{code: 502, detail: "上游拒绝", body: "他收藏的那条视频标题"}')
    for secret in ("502", "上游拒绝", "他收藏的那条视频标题"):
        assert secret not in out, f"把值写进回执了：{out!r} 里出现了 {secret!r}"


def _code_only(source: str) -> str:
    """把整行的 `//` 注释去掉再断言。

    **第一版栽在这里**：我在那处修复旁边写了一段注释，原文引用了旧写法
    `String(error?.message || error)`，于是「旧写法不许再出现」这条断言
    被**我自己的说明文字**打红——干净状态下就是红的，
    再跑反例自然也是红的，**红得毫无意义**（红之前必须先看见它绿）。
    同一天在凭据扫描器上也栽过一次：注释里摆出那个形状，扫描器把说明它的
    文字也报成一处泄漏。
    """
    return "\n".join(line for line in source.splitlines()
                     if not line.lstrip().startswith("//"))


def test_the_product_actually_uses_it() -> None:
    """函数没有调用方就不算修好。

    只断言「文件里定义了 describeThrown」是不够的：调用点如果还留着旧的
    `String(error?.message || error)`，缺陷原样还在，而定义在旁边干看着。
    """
    code = _code_only(BACKGROUND.read_text(encoding="utf-8"))
    assert "error: describeThrown(error).slice(0, 300)," in code
    assert "String(error?.message || error)" not in code, "旧写法还在，说明没换干净"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
