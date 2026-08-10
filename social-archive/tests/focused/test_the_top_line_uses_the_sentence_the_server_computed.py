"""顶部那一条要说服务端算好的那句，也只许说最近一次同步的事（2026-08-10）。

## 他一连上账号就会撞到

顶部那一条只在**有账号连着**时才出现（`!connected` 那一支提前 return）。
而它挑的是 `state.syncRuns` 里**历史上任何一次失败**——
`/v1/sync-runs?limit=200` 是全量返回的。

Owner 生产库里躺着 8 月 3–4 号那三次 `status=failed`。也就是说：
**他重新连上账号的那一刻**，顶部立刻拿六天前那批 run 说话。

说出来的还是错的。`SYNC_RUN_ABANDONED` 不在 PWA 本地词典里
（`failureCopy` 11 条、`failureAliases` 45 条，两张表都没有），于是落到兜底那句：

    这次没有取到任何内容，而且我们没能记录下原因。这是产品的问题…

**两句都假。** 那批 run 入过库；原因白纸黑字记在 `last_error_code` 里，
而且服务端 `api.py:_explain_sync_run` **已经算好了正确的一句发过来**：
「这次同步卡住了，没有正常结束。你已经取到的内容都还在。」

同一页的账号表反而是对的——它走 `runSentence()`，服务端那句优先。
**一页之内两个答案**，而这个仓在「同一道门在两处布局给出相反结论」上栽过。

生产实测（2026-08-10，逐个码问 `describe_sync_outcome`）：

    RELATION_SCOPE_UNCONFIRMED  →「这次同步卡住了…都还在。」   ← 本地词典没有
    SYNC_RUN_ABANDONED          →「这次同步卡住了…都还在。」   ← 本地词典没有
    STABLE_END_WITHOUT_PROOF    →「新增 35 条。」               ← 本地词典没有
    BROWSER_SCAN_FAILED         →（本地也有，一致）
    PLATFORM_PERMISSION_MISSING →（本地也有，一致）

**他撞到过的五个码里三个走的是那句假话**，而这三个占了他 20 次同步里的 13 次。

## 为什么不是"把三条补进本地词典"

补了这次，下次服务端再加一个码又要漏。词典的真源在服务端
（`failure_copy.py` 的注释自己写着：「在这里算一次，两边都拿得到，
且词典只有一处真源」）。要守的是**别再自己查一遍**。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/pwa/app.js"

pytestmark = pytest.mark.skipif(not APP.is_file(), reason="app.js 不存在")


def _code() -> str:
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    from js_source import code_only

    return code_only(APP)


def test_only_run_sentence_may_consult_the_local_dictionary() -> None:
    """**本地词典只许 `runSentence` 碰。**

    它自己第一行就是 `if (run.message_zh) return run.message_zh;`——
    服务端那句优先、本地只做兜底。绕过它直接查词典，就是绕过了真源。
    """
    code = _code()
    definition = code.find("function failureSentence(")
    assert definition >= 0, "failureSentence 没了——这条判据在空扫"
    body = code.find("function runSentence(")
    assert body >= 0, "runSentence 没了；顶部那一条就没有正确的出口了"
    run_body = code[body:code.find("\n  }", body)]

    callers = [m.start() for m in re.finditer(r"failureSentence\(", code)
               if m.start() != definition + len("function ")]
    outside = [pos for pos in callers
               if not (body <= pos < body + len(run_body))
               and pos != definition + len("function ")]
    # 定义那一行本身会被 `failureSentence\(` 匹配到，排掉它
    outside = [pos for pos in outside if not code.startswith("function failureSentence(", pos - len("function "))]
    assert not outside, (
        "有人绕过 runSentence 直接查本地词典："
        + "；".join(code[max(0, p - 90):p + 60].replace("\n", " ") for p in outside)
        + "——服务端已经把这句话算好发过来了，本地那张表少三个他真撞到过的码")


def test_the_top_line_speaks_about_the_latest_run_not_any_run_ever() -> None:
    """**「需要处理」说的必须是最近一次，不是历史上任何一次。**

    这一页本来就有正确的口径：`latestRunFor(accountId)`（按 updated_at 倒序取第一条），
    账号表用的就是它。顶部那一条却直接 `state.syncRuns.filter(...)` 扫全量。
    """
    code = _code()
    index = code.find("const failures = ")
    assert index >= 0, "找不到 failures 那一行——它是不是改名了？"
    line = code[index:code.find("\n", index)]
    assert "latestRunFor" in line or "latestRuns" in line, (
        f"顶部那一条还在从全部历史里挑失败：{line.strip()}——"
        "Owner 库里躺着 8 月 3–4 号那三次 failed，他一重连就会被它们说话")


def test_the_strip_renders_the_server_sentence() -> None:
    code = _code()
    index = code.find("const failures = ")
    window = code[index:index + 2600]
    assert "runSentence(" in window, (
        "顶部那一条没走 runSentence——服务端算好的 message_zh 会被丢掉")
