"""零不得沉默（v0.0.0.7 / T14）。

INV-NO-SILENT-ZERO：任何一次同步为 0 条时，界面都说得出为什么。

判据分三组：

  1. 文案与 `01_PRODUCT/ZERO_BARRIER_UX.md` 的冻结词典**逐字**一致
  2. 人为注入四种失败，各自给出对应的中文句子
  3. 库里不允许存在「imported=0 且 failure_code 为空」的同步运行
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from social_archive.failure_copy import (

    COPY_BY_CODE,
    NOTHING_NEW,
    describe_sync_outcome,
    resolve,
)
from tests.focused._source_slices import js_function

ROOT = Path(__file__).resolve().parents[2]

# 逐字照抄任务包 01_PRODUCT/ZERO_BARRIER_UX.md「错误文案词典（冻结）」的右列。
# 这里重抄一遍是**故意**的：词典是产品合同，改代码时如果顺手改了句子，
# 这份独立副本会立刻报红，而不是跟着一起变。
FROZEN = {
    "CREDENTIAL_EXPIRED": "<平台> 的登录状态过期了。[ 重新连接 ]",
    "NOT_LOGGED_IN": "没有在浏览器里找到 <平台> 的登录状态。请先在浏览器里登录 <平台>，然后点 [ 重试 ]",
    "REDDIT_NOT_AUTHORIZED": "Reddit 需要单独授权一次。[ 去授权 ]",
    "TAB_CLOSED": "<平台> 同步中断了，因为标签页被关掉。[ 继续 ]",
    "RATE_LIMITED": "<平台> 请求太频繁，已自动放慢。已经收到的 <N> 条都保住了，稍后会自动继续。",
    "SERVER_UNREACHABLE": "暂时连不上服务器。你的数据没有丢，[ 重试 ]",
    "DISK_QUOTA": "存储空间快满了，已经暂停下载媒体文件，文字和链接还在正常保存。",
    # v0.0.0.22 追加的一行（**上面七句一个字没动**）。理由写在
    # docs/ZERO_BARRIER_UX.md 那张表下面：契约立的时候还没有"主机权限"这条路，
    # 而词典里最接近的一句会把他送回平台页去登录——方向是反的。
    "PLATFORM_PERMISSION_MISSING": "还没有获得读取 <平台> 页面的授权。请点 [ 连接账号 ]，在浏览器弹出的框里选「允许」。",
    # v0.0.0.22 追加的第九行。理由：BROWSER_SCAN_FAILED 一直被别名成
    # SERVER_UNREACHABLE，于是界面说「暂时连不上服务器」——**方向是反的**，
    # 服务器好好的，出问题的是在浏览器里读平台页那一步。
    # 2026-08-07 在 Owner 生产库里量到这个码出现过 5 次。
    "BROWSER_SCAN_FAILED": "在你的浏览器里读 <平台> 的页面时没能完成。请打开该平台的收藏页、确认已登录，然后点 [ 重试 ]。",
}


def test_dictionary_matches_the_frozen_product_copy_verbatim() -> None:
    assert set(COPY_BY_CODE) == set(FROZEN), "词典条目与冻结词典不一致"
    for code, sentence in FROZEN.items():
        assert COPY_BY_CODE[code].template == sentence, f"{code} 的文案被改动了"


def test_frozen_copy_is_still_what_the_task_pack_says() -> None:
    """判据自己的自检：如果产品文档在仓里，就直接对照它，不只对照我抄的副本。

    抄写本身可能抄错——这条把「我抄的」和「文档写的」对起来。
    文档不在仓里时跳过，并说清楚是跳过而不是通过。
    """
    doc = ROOT / "docs" / "ZERO_BARRIER_UX.md"
    if not doc.is_file():
        pytest.skip("仓内没有 ZERO_BARRIER_UX.md（它在任务包里），本条只能对照代码内副本")
    text = doc.read_text(encoding="utf-8")
    for sentence in FROZEN.values():
        assert sentence in text, f"文档里找不到这句：{sentence}"


# ── 任务包点名的四种失败 ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "scenario,code,expected",
    [
        ("凭据过期", "CREDENTIAL_EXPIRED", "X 的登录状态过期了。[ 重新连接 ]"),
        ("未登录", "NOT_LOGGED_IN",
         "没有在浏览器里找到 X 的登录状态。请先在浏览器里登录 X，然后点 [ 重试 ]"),
        ("标签页关闭", "TAB_CLOSED", "X 同步中断了，因为标签页被关掉。[ 继续 ]"),
        ("服务端不可达", "SERVER_UNREACHABLE", "暂时连不上服务器。你的数据没有丢，[ 重试 ]"),
    ],
)
def test_injected_failure_renders_the_dictionary_sentence(
    scenario: str, code: str, expected: str
) -> None:
    outcome = describe_sync_outcome(imported=0, failure_code=code, platform_label="X")
    assert outcome["message_zh"] == expected, f"{scenario} 的文案不对"
    assert outcome["outcome"] == "failed"
    # 界面上不许出现英文错误码
    assert code not in str(outcome["message_zh"])


def test_no_english_error_code_or_stack_leaks_into_any_message() -> None:
    for code in COPY_BY_CODE:
        rendered = describe_sync_outcome(
            imported=0, failure_code=code, platform_label="B站"
        )["message_zh"]
        assert code not in rendered
        for leak in ("Traceback", "Error", "Exception", "None", "null"):
            assert leak not in rendered, f"{code} 的文案里漏出了 {leak}"


# ── 「没有新增」与「失败」是两种显示 ──────────────────────────────────


def test_nothing_new_is_not_shown_as_a_failure() -> None:
    """两者都是 0 条，但一个是好事一个是坏事。混成一句用户永远分不清该不该重试。"""
    nothing = describe_sync_outcome(imported=0, failure_code=None, status="completed")
    assert nothing["outcome"] == "nothing_new"
    assert nothing["message_zh"] == NOTHING_NEW.template
    assert nothing["action_zh"] is None, "「没有新增」不该给重试按钮"

    failed = describe_sync_outcome(imported=0, failure_code="TAB_CLOSED", platform_label="B站")
    assert failed["outcome"] == "failed"
    assert failed["message_zh"] != nothing["message_zh"]


def test_imported_count_is_reported_when_something_came_in() -> None:
    assert describe_sync_outcome(imported=7, failure_code=None)["message_zh"] == "新增 7 条。"


# ── 静默的零本身要被点名 ─────────────────────────────────────────────


def test_zero_without_a_reason_is_called_out_not_dressed_up_as_success() -> None:
    """这是 INV-NO-SILENT-ZERO 的核心判据。

    **收窄过一次，理由记在这里。**

    原来这条用 `status="scanning"` 当例子，断言它必须显示「这是产品的问题」。
    在真实浏览器里跑下来发现那是错的：刚点完连接、run 还在排队的那几十秒，
    用户看到的就是「这次没有取到任何内容…这是产品的问题，请重试一次」——
    刚点完就被告知产品坏了，而它只是还没开始跑。

    真正是 v0.0.0.6 那种形状的，是**已经收尾**却 0 条又说不出原因。
    「永远到不了终态」那一种同样要抓，但它的判据是"多久没动"，
    不是"当前什么状态"，所以归 db.stalled_active_runs()，
    并且和这条一起挂在 /v1/status 的 sync_health 上。
    """
    # 已经收尾、0 条、没有失败码 —— 必须被点名
    for terminal in ("partial", "failed", "blocked_environment"):
        outcome = describe_sync_outcome(imported=0, failure_code=None, status=terminal)
        assert outcome["outcome"] == "unexplained_zero", f"{terminal} 被含糊过去了"
        assert outcome["failure_code"] == "UNEXPLAINED_ZERO"
        assert "我们没能记录下原因" in str(outcome["message_zh"])
        assert "这是产品的问题" in str(outcome["message_zh"])
        assert outcome["action_zh"] == "重试"

    # 未知状态同样不许含糊
    unknown = describe_sync_outcome(imported=0, failure_code=None, status="")
    assert unknown["outcome"] == "unexplained_zero"


def test_the_invariant_has_an_actual_enforcement_point() -> None:
    """两个审计必须真的挂在接口上。

    在此之前 `unexplained_zero_runs` **没有任何调用方**——
    也就是说「不许有说不清的零」这条不变量其实没有任何东西在执行，
    唯一还在响的只是文案。文案一改，信号就没了。
    """
    from pathlib import Path

    api = (Path(__file__).resolve().parents[2] / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert "unexplained_zero_runs(" in api, "终态静默零审计没有挂到接口上"
    assert "stalled_active_runs(" in api, "卡住不动审计没有挂到接口上"
    assert "sync_health" in api


def test_internal_codes_are_aliased_into_dictionary_sentences() -> None:
    """代码里的失败码比词典细，但界面上只许出现词典里的句子。

    **ACQUISITION_PATH_NOT_INSTALLED 从这张表里去掉了。** 它原先别名成
    SERVER_UNREACHABLE，也就是对用户说「暂时连不上服务器，[ 重试 ]」——
    而真实原因是**本版本根本没实现这条取数路**。Owner 因此一遍遍重试一件
    永远不可能成功的事，原话是「不知道应该怎么操作」。

    现在它进 PRODUCT_FAULT_CODES：结论是「我们的问题、别重试」。
    主要修法在界面侧——这些平台根本不画「立即同步」按钮，
    见 test_sync_button_is_not_offered_where_it_cannot_work。
    """
    for internal, expect_code in (
        ("LOGIN_PROOF_UNAVAILABLE", "NOT_LOGGED_IN"),
        ("PERMISSION_DENIED", "NOT_LOGGED_IN"),
        ("MIRROR_TAB_CLOSED", "TAB_CLOSED"),
    ):
        resolved = resolve(internal)
        assert resolved is not None, f"{internal} 没有映射到词典"
        assert resolved.code == expect_code
        rendered = describe_sync_outcome(
            imported=0, failure_code=internal, platform_label="小红书"
        )["message_zh"]
        assert rendered == COPY_BY_CODE[expect_code].render(platform_label="小红书")


def test_unknown_code_does_not_silently_become_success() -> None:
    outcome = describe_sync_outcome(imported=0, failure_code="SOMETHING_NEW_NOBODY_MAPPED")
    assert outcome["outcome"] == "unexplained_zero", (
        "没见过的失败码被当成了成功——那正是静默的零"
    )


def test_rate_limited_keeps_what_was_already_collected() -> None:
    """限速不是失败，且必须把「已经收到的都保住了」说出来。"""
    outcome = describe_sync_outcome(imported=0, failure_code="RATE_LIMITED", platform_label="B站")
    assert outcome["outcome"] == "informational"
    assert "都保住了" in str(outcome["message_zh"])


def test_platform_placeholder_never_leaks_when_label_is_missing() -> None:
    """没传平台名时不能把 `<平台>` 这个占位符直接显示给用户。"""
    for code in COPY_BY_CODE:
        rendered = describe_sync_outcome(imported=0, failure_code=code)["message_zh"]
        assert "<平台>" not in str(rendered), f"{code} 把占位符漏给了界面"
        assert "<N>" not in str(rendered)


# ── 库层审计：不允许存在没有原因的零 ────────────────────────────────


def _store(tmp_path: Path):
    from social_archive.db import RuntimeStore

    store = RuntimeStore(tmp_path / "runtime.sqlite3")
    store.initialize()
    with store.connection() as con:
        con.execute(
            "INSERT OR IGNORE INTO users(id,display_name,created_at,is_owner) "
            "VALUES('usr_owner','Owner','2026-01-01T00:00:00Z',1)"
        )
        con.execute(
            "INSERT INTO source_account(id,user_id,platform,auth_method,display_name,"
            "external_account_id,connection_state,created_at,updated_at) "
            "VALUES('acct','usr_owner','x','browser_session','X','me','connected','t','t')"
        )
    return store


def _insert_run(store, run_id: str, status: str, imported: int, code: str | None) -> None:
    with store.connection() as con:
        con.execute(
            """INSERT INTO sync_run(id,user_id,source_account_id,platform,mode,status,
                                    imported_count,updated_at,last_error_code)
               VALUES(?,'usr_owner','acct','x','first_full',?,?,'2026-01-01T00:00:00Z',?)""",
            (run_id, status, imported, code),
        )


def test_audit_finds_a_terminal_zero_with_no_reason(tmp_path: Path) -> None:
    """先证明审计抓得到，再谈它报绿有没有意义。"""
    store = _store(tmp_path)
    _insert_run(store, "run_bad", "failed", 0, None)
    _insert_run(store, "run_bad2", "partial", 0, "   ")  # 空白字符串也算没有原因
    found = {row["id"] for row in store.unexplained_zero_runs()}
    assert found == {"run_bad", "run_bad2"}, f"审计没抓到静默的零：{found}"


def test_audit_does_not_flag_nothing_new_or_explained_failures(tmp_path: Path) -> None:
    """三种都不该被报：

    · completed + 0 条 —— 「已经是最新的」，是好事
    · failed + 有失败码 —— 说得出原因
    · partial + 有内容进来 —— 不是零
    """
    store = _store(tmp_path)
    _insert_run(store, "run_nothing_new", "completed", 0, None)
    _insert_run(store, "run_explained", "failed", 0, "TAB_CLOSED")
    _insert_run(store, "run_partial_with_items", "partial", 5, None)
    assert store.unexplained_zero_runs() == []


def test_every_audited_row_can_be_turned_into_a_chinese_sentence(tmp_path: Path) -> None:
    """审计抓到之后，界面必须仍然说得出话——不能只在日志里留个 ID。"""
    store = _store(tmp_path)
    _insert_run(store, "run_bad", "failed", 0, None)
    for row in store.unexplained_zero_runs():
        outcome = describe_sync_outcome(
            imported=int(row["imported_count"]),
            failure_code=row["last_error_code"],
            status=str(row["status"]),
            platform_label="X",
        )
        assert outcome["outcome"] == "unexplained_zero"
        assert str(outcome["message_zh"]).strip()
        assert "<" not in str(outcome["message_zh"])


# ── PWA 侧的同一份词典不许和 Python 侧漂开 ──────────────────────────


def test_pwa_dictionary_matches_the_python_one() -> None:
    """同一份冻结词典现在有两处实现：failure_copy.py 与 apps/pwa/app.js。

    两处实现就有两处会漂。这条逐句比对，任一处被改动都会红。
    （PWA 那份是必须的：界面在浏览器里渲染，读不到 Python 模块。）
    """
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert "const failureCopy = {" in app_js, "PWA 里没有失败文案词典——界面会说不出为什么"
    for code, sentence in FROZEN.items():
        assert code in app_js, f"PWA 词典缺少 {code}"
        assert sentence in app_js, f"PWA 里 {code} 的文案与冻结词典不一致：应为 {sentence!r}"


def test_pwa_alias_table_covers_every_internal_code_python_knows() -> None:
    """别名表也会漂，而且比句子更容易漏。

    Python 侧新加一个内部失败码、忘了同步 PWA，界面就会把它当成
    「没见过的码」→ 落到 UNEXPLAINED_ZERO「这是产品的问题」。
    明明知道原因却告诉用户「我们不知道」，比不说更糟。
    """
    from social_archive.failure_copy import _ALIASES

    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    missing = [code for code in _ALIASES if code not in app_js]
    assert not missing, (
        f"这些内部失败码 Python 认识、PWA 不认识：{missing}。"
        "界面会把它们显示成「我们没能记录下原因」，而其实是知道原因的。"
    )


def test_pwa_falls_back_to_the_unexplained_zero_sentence() -> None:
    """没见过的失败码在界面上也不能沉默。"""
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert "我们没能记录下原因" in app_js
    assert "这是产品的问题" in app_js


def test_pwa_reads_the_failure_code_at_all() -> None:
    """v0.0.0.6 的 app.js **一次都没读过** last_error_code——
    所以同步失败时界面只会显示「需要处理」，说不出为什么。这条守着别退回去。"""
    app_js = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    assert "last_error_code" in app_js, "PWA 又不读失败码了——界面将说不出失败原因"
    assert "failureSentence" in app_js


def test_pwa_asset_version_is_not_stale() -> None:
    """缓存版本号必须随界面改动一起升，否则**回访用户拿到的还是旧 app.js**。

    实测踩到过：本地验 T14 时页面一直显示旧文案，就是 index.html 里
    `app.js?v=006-r1` 与 sw.js 的缓存名都还停在 v006。
    发布后老用户会完全看不到 v0.0.0.7 的界面改动。
    """
    for relative in ("apps/pwa/index.html", "apps/pwa/sw.js", "apps/pwa/app.js"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "v=006" not in text, f"{relative} 的资源版本号还停在 v006"
    sw = (ROOT / "apps/pwa/sw.js").read_text(encoding="utf-8")
    assert "social-archive-ui-v007" in sw, "service worker 缓存名还没升到 v007"


# ── 词典必须被生产代码真的用上 ────────────────────────────────────


def test_the_dictionary_is_actually_wired_into_the_api() -> None:
    """写了词典却没有任何生产代码调用它，等于没写。

    实测踩到过：failure_copy.py 落地之后，全仓**没有一个生产模块**调用
    describe_sync_outcome——它只活在判据和 PWA 的一份手抄副本里。
    结果是扩展那一侧根本没有词典，同步失败只显示状态标签「需要处理」。
    T14 的验收是「界面说得出为什么」，那就得**每个**界面都能。
    """
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert "describe_sync_outcome" in api, "API 没有使用失败文案词典"
    assert "_explain_sync_run" in api


def test_every_sync_run_endpoint_returns_a_human_sentence() -> None:
    """三个返回同步运行的端点都要带上 message_zh，漏一个就有界面说不出话。"""
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    for marker in ('def sync_runs(', 'def account_sync_runs(', 'def sync_run_detail('):
        assert marker in api, f"找不到端点 {marker}"
    # 三处都必须过 _explain_sync_run
    assert api.count("_explain_sync_run") >= 4, (
        "有 sync-run 端点没有经过 _explain_sync_run —— 那个界面会拿不到中文说明"
    )


def test_extension_shows_the_reason_not_just_the_status_label() -> None:
    options = (ROOT / "apps/browser-extension/options.js").read_text(encoding="utf-8")
    assert "run.message_zh" in options, (
        "扩展设置页没有显示失败原因，只有状态标签「需要处理」"
    )
    assert "last_error_code" in options


def test_no_surface_renders_raw_upstream_error_text() -> None:
    """T14 硬规矩：界面上不得出现英文错误码或堆栈。

    `last_error_message` 装的是上游原样抛回来的文本——可能是英文，
    也可能是一大坨 CSS（Reddit 未授权时 gallery-dl 塞回来的就是十万字节样式表，
    样本在 evidence/fixtures/gallerydl/）。它可以留在库里供排查，
    但**不许直接渲染到界面上**。

    实测踩到过：sidepanel.js 的任务卡片先前正是 `run.last_error_message || ...`。
    """
    surfaces = {
        "apps/browser-extension/sidepanel.js",
        "apps/browser-extension/options.js",
        "apps/browser-extension/popup.js",
        "apps/pwa/app.js",
    }
    offenders = []
    for relative in sorted(surfaces):
        path = ROOT / relative
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.strip()
            if code.startswith("//") or code.startswith("*"):
                continue
            if "last_error_message" in code:
                offenders.append(f"{relative}: {code[:90]}")
    assert not offenders, (
        f"这些界面直接渲染了上游原始错误文本：{offenders}。"
        "给人看的必须是冻结词典里的中文句子（服务端已在 message_zh 里算好）。"
    )


def test_every_extension_surface_that_shows_runs_uses_message_zh() -> None:
    """哪个界面显示同步运行，哪个界面就得能说出为什么。

    本会话已经因为「只看了一个界面」栽过两次：T14 只验 PWA、
    零输入判据只扫 options.html。这条一次把扩展三个面都覆盖到。
    """
    for relative in ("apps/browser-extension/sidepanel.js",
                     "apps/browser-extension/options.js"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "message_zh" in text, f"{relative} 显示同步状态却说不出失败原因"


def test_no_http_status_code_is_ever_shown_as_a_user_message() -> None:
    """冻结词典的规矩是对**所有**失败说的，不只是同步失败：
    「界面上出现的失败必须用下面这些话，不得出现英文错误码或堆栈」。

    实测踩到过：扩展与 PWA 的 api() 在服务端没给 detail 时，
    兜底成 `HTTP ${status}` / FastAPI 默认的英文 "Internal Server Error"，
    而这个字符串会被八处 toast(error.message) 直接甩给用户。
    """
    for relative in ("apps/browser-extension/shared.js", "apps/pwa/app.js"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        code = "\n".join(
            line for line in text.splitlines()
            if not line.lstrip().startswith(("//", "*", "/*"))
        )
        assert "`HTTP ${response.status}`" not in code, (
            f"{relative} 会把 HTTP 状态码当成给人看的提示语"
        )
        # 必须存在一个统一的中文兜底
        assert ("SA_humanMessage" in code) or ("function humanMessage" in code), (
            f"{relative} 没有统一的中文兜底函数"
        )


def test_the_chinese_fallback_covers_the_status_codes_that_actually_happen() -> None:
    """兜底要真的覆盖会发生的状态码，而不是只写一句 else。"""
    # **切函数，不切「humanMessage 之后的 1200 字」。**
    #
    # 两个文件里 humanMessage 都出现两三次：第一处恰好是定义，后面几处是调用。
    # 也就是说旧写法**现在是对的，但只是因为定义碰巧排在最前**——
    # 哪天有人在定义上面加一处调用，窗口就滑到调用点上，
    # 判据会从「验兜底覆盖了哪些状态码」变成「验调用点附近有没有这些数字」，
    # 而且**不会报错，只会继续绿**。
    for relative, declaration in (
        ("apps/browser-extension/shared.js", "function SA_humanMessage"),
        ("apps/pwa/app.js", "function humanMessage"),
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        block = js_function(text, declaration)
        for code in ("401", "404", "429", "500"):
            assert code in block, f"{relative} 的中文兜底没有覆盖 {code}"


# ── 生产库里真实存在的失败码 ─────────────────────────────────────────
#
# 这一组的由来：我把词典是照着**能读到的代码路径**建的，然后去查了一次
# 生产库，发现 sync_run 里实际存在的四个码里有三个**在当前代码中一个字
# 都搜不到**——它们是 v0.0.0.6 留下的，那部分代码已被 T03 删掉，
# 记录却还在库里。不认它们，这些历史记录在界面上会显示成
# 「我们没能记录下原因」，而原因就明明白白写在 last_error_code 里。


# 2026-08-04 生产 sync_run 表实测（code, 次数, 已入库条数）
PRODUCTION_CODES = [
    ("BROWSER_SCAN_FAILED", 4, 0),
    ("RELATION_SCOPE_UNCONFIRMED", 7, 169),
    ("STABLE_END_WITHOUT_PROOF", 2, 91),
    ("SYNC_RUN_ABANDONED", 3, 0),
]


@pytest.mark.parametrize("code,runs,imported", PRODUCTION_CODES)
def test_every_code_that_actually_exists_in_production_is_explainable(
    code: str, runs: int, imported: int
) -> None:
    """生产库里真有的码，一个都不许落到「我们没能记录下原因」。"""
    outcome = describe_sync_outcome(
        imported=imported, failure_code=code, status="partial", platform_label="B站"
    )
    assert outcome["outcome"] != "unexplained_zero", (
        f"{code} 在生产里出现过 {runs} 次，界面却会说「我们没能记录下原因」——"
        "而原因就写在 last_error_code 里"
    )
    assert "我们没能记录下原因" not in str(outcome["message_zh"])


def test_legacy_incomplete_codes_say_the_data_is_safe() -> None:
    """「没跑完」要同时说清两件事：没正常结束，以及已拿到的没丢。"""
    from social_archive.failure_copy import INCOMPLETE_RUN_CODES

    from social_archive.failure_copy import SCROLL_PARTIAL_CODES

    # **「没读完」和「卡住了」不是一回事**——按形状读那条路每一次成功都报"没读完"，
    # 而它的稳态是"没有新增"（他能看到的那一批已经全在库里）。
    # 那种情况说「同步卡住了」+ 给一颗「重试」是错的：重试读到的还是同一批，
    # 于是他每 6 小时看到一次永远变不绿的红。那几个码单独走一条，见下一条判据。
    for code in sorted(INCOMPLETE_RUN_CODES - SCROLL_PARTIAL_CODES):
        outcome = describe_sync_outcome(imported=0, failure_code=code, status="failed")
        assert outcome["outcome"] == "stalled", f"{code} 落到了 {outcome['outcome']}"
        assert "没有正常结束" in str(outcome["message_zh"])
        assert "都还在" in str(outcome["message_zh"]), f"{code} 没告诉用户数据还在"
        assert outcome["action_zh"] == "重试"


def test_a_scroll_partial_with_nothing_new_is_not_shown_as_stuck() -> None:
    """**这是按形状读那条路的稳态，不是故障。**

    2026-08-07 量到：第一次读到 7 条显示「新增 7 条。」（对），
    而之后每 6 小时那次没有新增，显示的是
    「这次同步卡住了，没有正常结束。」+ 一颗「重试」——
    而重试读到的还是同一批。**一个永远变不绿的红不是信号，是噪音。**

    正确的话是：能看到的那一批已经全在库里了；想要更早的，
    去收藏页往下滚一会儿再同步。
    """
    from social_archive.failure_copy import SCROLL_PARTIAL_CODES

    for code in sorted(SCROLL_PARTIAL_CODES):
        outcome = describe_sync_outcome(imported=0, failure_code=code, status="partial")
        assert outcome["outcome"] != "stalled", f"{code} 被当成卡住了"
        assert "卡住" not in str(outcome["message_zh"]), f"{code} 的文案说它卡住了"
        assert "往下滚" in str(outcome["message_zh"]), (
            f"{code} 没告诉他想要更多该做什么"
        )
        assert outcome["action_zh"] != "重试", (
            "给了一颗「重试」——点了读到的还是同一批，那是一颗骗人的按钮"
        )
        # 读到新的时候仍然先报数
        got = describe_sync_outcome(imported=5, failure_code=code, status="partial")
        assert got["message_zh"] == "新增 5 条。"


def test_partial_runs_that_did_import_still_report_the_count_first() -> None:
    """有新增就先报数——生产里那 169 条和 91 条不能被一句「卡住了」盖掉。"""
    outcome = describe_sync_outcome(
        imported=169, failure_code="RELATION_SCOPE_UNCONFIRMED", status="partial"
    )
    assert outcome["outcome"] == "imported"
    assert outcome["message_zh"] == "新增 169 条。"


def test_failure_codes_are_never_python_class_names() -> None:
    """**不要拿异常类名当失败码。**

    生产 connector_state 里躺着一个 `CONNECTORERROR`——它来自
    `exc.__class__.__name__.upper()`。这类码有三个问题：

      1. 对用户没有意义，且泄漏实现细节
      2. 是**无限集合**，文案词典永远追不上，于是界面只能说
         「我们没能记录下原因」——而原因就在异常对象里
      3. `check_every_failure_code_is_explainable.py` 是扫**字面量**的，
         动态拼出来的码它结构上就看不见

改法是：码用稳定的那个，类名留在 message 里（那一栏是给日志和运维看的）。
    """
    from pathlib import Path

    src = Path(__file__).resolve().parents[2] / "src/social_archive"
    offenders = []
    for path in src.rglob("*.py"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "__class__.__name__" not in line:
                continue
            # 只在它被当作 code/error_code 用的时候才算
            if re.search(r'(error_)?code["\']?\s*[=:]\s*f?["\']?[^"\']*__class__\.__name__', line):
                offenders.append(f"{path.name}:{lineno}  {line.strip()[:80]}")
    # 扩展侧同样不许。当前实测是干净的（码都来自 cookie-export.js 的
    # 显式构造参数，调用点全是字面量），这条判据是防它以后变脏。
    apps = Path(__file__).resolve().parents[2] / "apps"
    for path in apps.rglob("*.js"):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            # 既要抓「直接赋给 code 字段」，也要抓「先赋给局部变量 code
            # 再当失败码用」。第一版只写了前者，我拿后者试了一下——**没红**。
            # 判据写完必须真的用反例试一次，这条本轮已经栽过好几回。
            if re.search(
                r'\b(failureCode|failure_code|code)\s*[=:]\s*[\w?.]*\.(name|constructor)\b', line
            ):
                offenders.append(f"{path.name}:{lineno}  {line.strip()[:80]}")

    assert not offenders, (
        "这些地方把异常类名当成了失败码，界面会显示「我们没能记录下原因」：\n  "
        + "\n  ".join(offenders)
    )


def test_the_unimplemented_path_never_tells_the_user_to_retry() -> None:
    """一个永远不会成功的东西，绝不能配一句「重试」。

    这是本轮最贵的一处教训：Owner 点小红书/抖音/B站 的「立即同步」，
    看到的是「暂时连不上服务器。你的数据没有丢，[ 重试 ]」——
    而那条取数路在本版本压根没实现。
    """
    from social_archive.failure_copy import (
        DELIBERATELY_UNALIASED,
        PRODUCT_FAULT_CODES,
        _ALIASES,
    )

    code = "ACQUISITION_PATH_NOT_INSTALLED"
    assert code not in _ALIASES, "又被别名成某句词典文案了——那必然带上「重试」"
    assert code in DELIBERATELY_UNALIASED
    assert code in PRODUCT_FAULT_CODES, "没有归到「这是我们的问题」那一支"


def test_the_library_prefers_the_servers_sentence_over_its_own_dictionary() -> None:
    """**两张失败码词典，服务端那张说了算。**

    这一侧（apps/pwa/app.js）有一张自己的词典，服务端也有一张。两张各修各的
    就会漂开——这个仓吃过一次：ACQUISITION_PATH_NOT_INSTALLED 在服务端是
    「这是产品的问题」，在界面上是「暂时连不上，重试」，让人反复重试一件
    不可能成功的事。

    2026-08-07 又撞一次：按形状读那条路的**稳态**码 PARTIAL_BY_PAGE_SCROLL
    不在界面那张表里，于是落到兜底句「我们没能记录下原因。这是产品的问题」，
    而服务端刚给它写了一句准确的话。**界面把服务端盖掉了。**

    所以顺序必须是：服务端的 message_zh 优先，没有才回落到本地词典。
    """
    from pathlib import Path

    app = (Path(__file__).resolve().parents[2] / "apps/pwa/app.js").read_text(encoding="utf-8")
    code = "\n".join(l for l in app.splitlines() if not l.lstrip().startswith("//"))
    assert "function runSentence" in code, "找不到那个统一入口——判据射程失效"
    body = code.split("function runSentence", 1)[1].split("function failureSentence", 1)[0]
    assert "run.message_zh" in body, "没有优先用服务端那句话"
    assert body.index("run.message_zh") < body.index("failureSentence"), (
        "本地词典排在服务端前面——它会盖掉服务端刚写对的那句话"
    )
    # 账号表那一行必须走这个入口，不能自己再拼一次
    row = code.split("data-failure-reason", 1)[1][:200]
    assert "runSentence(" in row, f"账号表那一行绕开了统一入口：{row[:120]}"
