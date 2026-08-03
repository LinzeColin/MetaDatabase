"""gallery-dl 三元组契约与失败归类（v0.0.0.7 / T07 + T12）。

判据全部打在**已固化的真实样本**上，不是我构造的理想输入：

  · evidence/fixtures/gallerydl/gallerydl_dumpjson_contract.real.json
  · evidence/fixtures/gallerydl/gallerydl_reddit_unauthenticated_failure.real.json

用真实样本的理由：契约测试如果喂自己编的数据，测的是「我以为上游长什么样」，
而不是上游真的长什么样。上游一改，构造的样本不会变红，真实样本会。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from social_archive.gallerydl_runner import (
    ERROR_MESSAGE_LIMIT,
    GalleryDLResult,
    classify_failure,
    parse_dump_json,
    run,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "evidence/fixtures/gallerydl"
CONTRACT = FIXTURES / "gallerydl_dumpjson_contract.real.json"
REDDIT_FAIL = FIXTURES / "gallerydl_reddit_unauthenticated_failure.real.json"


def test_fixtures_are_present_and_non_trivial() -> None:
    """判据自己的自检：样本不在或是空的，下面所有判据都会变成空转。"""
    for path in (CONTRACT, REDDIT_FAIL):
        assert path.is_file(), f"{path.name} 不在——契约判据会空转"
        assert path.stat().st_size > 1000, f"{path.name} 太小，不像真实样本"


# ── 三元组契约 ──────────────────────────────────────────────────────


def test_real_contract_sample_parses_into_files_and_metadata() -> None:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    result = parse_dump_json(payload, url="https://commons.wikimedia.org/")
    assert result.ok, f"真实契约样本解析出错：{result.errors}"
    assert result.items, "一个文件条目都没解析出来"
    for item in result.items:
        assert item["url"].startswith("http"), "文件条目必须带可用 URL"
    # 类型 2（目录/元数据）不该混进 items
    assert all("imagerepository" not in item or "url" in item for item in result.items)


def test_type_codes_are_handled_exactly_as_the_frozen_contract_says() -> None:
    """2=目录 3=文件 6=队列 -1=错误。逐个码验，不靠真实样本碰巧覆盖到。"""
    payload = [
        [2, {"category": "x", "subcategory": "bookmarks"}],
        [3, "https://example.test/a.jpg", {"id": "a"}],
        [6, "https://example.test/next-page", {}],
    ]
    result = parse_dump_json(payload)
    assert [item["url"] for item in result.items] == ["https://example.test/a.jpg"]
    assert result.queued_urls == ["https://example.test/next-page"]
    assert result.errors == []


def test_unknown_type_code_is_recorded_not_guessed() -> None:
    """T07 的 Stop Condition：上游契约与固化 fixture 不符时先记 conflict，不要猜着改解析器。

    所以认不出的类型码要**记成错误**，不能当成文件混进结果里——
    混进去的话，一个契约变更会表现成"数据变少了"，而不是"契约变了"。
    """
    result = parse_dump_json([[99, "https://example.test/x", {}]])
    assert result.items == []
    assert result.errors, "未知类型码被静默吞掉了"
    assert "CONFLICT_ORDER" in result.errors[0]["message"]


def test_malformed_top_level_does_not_look_like_an_empty_success() -> None:
    """上游吐了非数组时不能表现成「跑通了，0 条」。"""
    result = parse_dump_json({"not": "a list"})
    assert not result.ok
    assert result.failure_code is not None


# ── Reddit 未授权：真实样本 ──────────────────────────────────────────


def test_real_reddit_unauthenticated_sample_is_classified_as_missing_oauth() -> None:
    """任务包的 Stop Condition 原话：**不要把它当网络问题重试**，它就是缺 OAuth。"""
    payload = json.loads(REDDIT_FAIL.read_text(encoding="utf-8"))
    result = parse_dump_json(payload, url="https://www.reddit.com/user/me/saved")
    assert result.failure_code == "REDDIT_NOT_AUTHORIZED", (
        f"未授权样本被归成了 {result.failure_code}——"
        "如果是 SERVER_UNREACHABLE，界面会让用户重试，而重试一万次也一样"
    )
    assert not result.ok


def test_reddit_failure_is_not_retryable_copy() -> None:
    """归类之后落到的文案必须是「去授权」，不是「重试」。"""
    from social_archive.failure_copy import describe_sync_outcome

    outcome = describe_sync_outcome(
        imported=0, failure_code="REDDIT_NOT_AUTHORIZED", platform_label="Reddit"
    )
    assert outcome["message_zh"] == "Reddit 需要单独授权一次。[ 去授权 ]"
    assert outcome["action_zh"] == "去授权"


def test_hundred_kilobytes_of_css_is_truncated_before_it_reaches_the_database() -> None:
    """真实样本里那条 message 有十万字节的 CSS。原样存进 sync_run 会把库撑爆。"""
    payload = json.loads(REDDIT_FAIL.read_text(encoding="utf-8"))
    raw = next(e[1]["message"] for e in payload if e[0] == -1)
    assert len(raw) > 10_000, "样本里的错误信息没那么长——这条判据的前提变了"
    result = parse_dump_json(payload, url="https://www.reddit.com/user/me/saved")
    assert len(result.errors[0]["message"]) == ERROR_MESSAGE_LIMIT
    # 但截断后仍要能辨认出是哪种失败
    assert result.failure_code == "REDDIT_NOT_AUTHORIZED"


def test_markup_detection_keys_on_shape_not_on_a_fixed_string() -> None:
    """Reddit 换个皮肤 CSS 会全变，但「这是一坨样式表」不会变。"""
    from social_archive.gallerydl_runner import _looks_like_markup

    assert _looks_like_markup(":root{--rem360:22.5rem;}@media screen{}")
    assert _looks_like_markup("<!doctype html><html><head></head>")
    assert not _looks_like_markup("HTTP 503 Service Unavailable")
    assert not _looks_like_markup("Connection reset by peer")


# ── 其他失败的归类 ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "error,message,expected",
    [
        ("AuthenticationError", "login required", "CREDENTIAL_EXPIRED"),
        ("HttpError", "429 Too Many Requests", "RATE_LIMITED"),
        ("HttpError", "500 Internal Server Error", "SERVER_UNREACHABLE"),
        ("ConnectionError", "dns failure", "SERVER_UNREACHABLE"),
    ],
)
def test_failure_classification(error: str, message: str, expected: str) -> None:
    assert classify_failure([{"error": error, "message": message}]) == expected


def test_no_errors_means_no_failure_code() -> None:
    assert classify_failure([]) is None


def test_non_reddit_markup_failure_is_expired_session_not_missing_oauth() -> None:
    """拿到网页而不是 API，对 Reddit 是缺 OAuth，对其他平台多半是会话过期被重定向。

    这两者的下一步不一样：一个去授权，一个重新连接。
    """
    code = classify_failure(
        [{"error": "AbortExtraction", "message": ":root{--a:1rem}@media screen{}"}],
        url="https://x.com/i/bookmarks",
    )
    assert code == "CREDENTIAL_EXPIRED"


# ── 子进程边界 ──────────────────────────────────────────────────────


def test_gallerydl_is_never_imported_into_our_process() -> None:
    """任务包 suggested_path：禁止 import 进运行路径（许可证与稳定性）。

    gallery-dl 是 GPL-2.0——import 进来会让许可证问题传导到整个运行路径。
    """
    source = (ROOT / "src/social_archive/gallerydl_runner.py").read_text(encoding="utf-8")
    code = "\n".join(
        line for line in source.splitlines()
        if not line.lstrip().startswith("#") and '"""' not in line
    )
    assert "import gallery_dl" not in code
    assert "from gallery_dl" not in code
    assert "subprocess" in code, "应当以子进程调用"


def test_missing_binary_fails_loudly_instead_of_returning_empty() -> None:
    result = run("https://x.com/i/bookmarks", binary="definitely-not-installed-xyz")
    assert not result.ok
    assert result.failure_code == "SERVER_UNREACHABLE"
    assert result.items == []


def test_range_probe_is_passed_through_for_small_sample_first() -> None:
    """T07 的 probe：先跑 --range 1-3 小样，再全量。"""
    seen: list[list[str]] = []

    class _Fake:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_runner(argv):
        seen.append(argv)
        return _Fake()

    run("https://x.com/i/bookmarks", limit=3, runner=fake_runner, binary="gallery-dl")
    assert "--range" in seen[0] and "1-3" in seen[0]
    assert "-j" in seen[0] and "--no-download" in seen[0]


def test_cookies_path_is_passed_but_never_the_cookie_values(tmp_path: Path) -> None:
    seen: list[list[str]] = []

    class _Fake:
        returncode = 0
        stdout = "[]"
        stderr = ""

    def fake_runner(argv):
        seen.append(argv)
        return _Fake()

    cookie_file = tmp_path / "c.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    run("https://x.com/i/bookmarks", cookies_path=str(cookie_file),
        runner=fake_runner, binary="gallery-dl")
    argv = seen[0]
    assert "--cookies" in argv and str(cookie_file) in argv
    # 传的是路径，不是内容
    assert not any("Netscape" in part for part in argv)


def test_non_json_stdout_is_a_failure_not_an_empty_success() -> None:
    class _Fake:
        returncode = 1
        stdout = "Traceback (most recent call last): ..."
        stderr = "boom"

    result = run("https://x.com/i/bookmarks", runner=lambda argv: _Fake(), binary="gallery-dl")
    assert not result.ok
    assert result.failure_code is not None
    assert result.items == []


# ── 退出码：非 0 却被读成「跑完了、0 条」 ────────────────────────────
#
# 这一组判据的由来：gallery-dl **失败时 stdout 是空的**，错误只写 stderr。
# 实测（生产 cli-tools 容器，gallery-dl 1.32.8）：
#     gallery-dl -j --no-download not-a-url  → exit 64、stdout 0 字节
# 而 run() 里 `json.loads(completed.stdout or "[]")` 把空 stdout 变成 `[]`，
# 于是一次硬失败和「已经是最新的」在数据上完全同形。
#
# 退出码本身是**位掩码**（job.py `status |= exc.code`、__init__.py `retval |= 64`），
# 所以判据必须打在按位与上——写 `rc == 16` 会漏掉 16|4=20。


class _FakeCompleted:
    """假的 subprocess 结果。stdout 空、stderr 有话、退出码非 0——真实失败的形状。"""

    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _run_with(returncode: int, *, url: str, stdout: str = "", stderr: str = ""):
    from social_archive.gallerydl_runner import run

    return run(url, runner=lambda argv: _FakeCompleted(returncode, stdout, stderr))


def test_nonzero_exit_with_empty_stdout_is_not_reported_as_success() -> None:
    """这条判据就是 INV-NO-SILENT-ZERO 本身。

    退出码 64 + 空 stdout 是实测出来的真实形状，不是构造的边界值。
    """
    result = _run_with(64, url="https://www.reddit.com/user/me/saved",
                       stderr="[gallery-dl][error] Unsupported URL 'x'")
    assert not result.ok, "退出码 64 被读成了成功——这正是 v0.0.0.6 的静默的零"
    assert result.failure_code is not None, "非 0 退出却没有失败码"
    assert result.returncode == 64


def test_silent_zero_would_have_shown_up_as_good_news() -> None:
    """把失败码摘掉，界面会说什么——用来证明上一条判据拦住的是什么。"""
    from social_archive.failure_copy import describe_sync_outcome

    # 修复前的行为：failure_code=None、status=completed
    before = describe_sync_outcome(imported=0, failure_code=None, status="completed")
    assert before["message_zh"] == "已经是最新的，没有新增内容。"

    # 修复后：真实退出码进来，说的就不是好消息了
    result = _run_with(64, url="https://www.reddit.com/user/me/saved", stderr="Unsupported URL")
    after = describe_sync_outcome(
        imported=0, failure_code=result.failure_code, status="completed", platform_label="Reddit"
    )
    assert after["message_zh"] != "已经是最新的，没有新增内容。", (
        "一次硬失败仍然显示成「已经是最新的」"
    )
    assert after["outcome"] != "nothing_new"


def test_exit_code_is_a_bitmask_not_a_value() -> None:
    """16|4=20：一次跑里既有鉴权失败又有抽取错误。按值比较会漏掉它。"""
    from social_archive.gallerydl_runner import classify_exit_code

    assert classify_exit_code(16, url="https://reddit.com/u/me/saved") == "REDDIT_NOT_AUTHORIZED"
    assert classify_exit_code(20, url="https://reddit.com/u/me/saved") == "REDDIT_NOT_AUTHORIZED", (
        "20 = 16|4 没被认成鉴权失败——判据写成了按值比较"
    )
    assert classify_exit_code(0, url="x") is None


def test_auth_exit_distinguishes_reddit_from_other_platforms() -> None:
    """同一个退出码，对 Reddit 是「去授权」，对别的平台是「重新连接」。"""
    from social_archive.gallerydl_runner import classify_exit_code

    assert classify_exit_code(16, url="https://www.reddit.com/user/me/saved") == "REDDIT_NOT_AUTHORIZED"
    assert classify_exit_code(16, url="https://www.instagram.com/saved/") == "CREDENTIAL_EXPIRED"


def test_unsupported_url_never_tells_the_user_to_retry() -> None:
    """32/64 是我们传错了 URL。让用户重试是骗他——重试一万次也一样。"""
    from social_archive.failure_copy import DELIBERATELY_UNALIASED, describe_sync_outcome
    from social_archive.gallerydl_runner import classify_exit_code

    code = classify_exit_code(64, url="https://example.com/x")
    assert code == "URL_NOT_SUPPORTED"
    assert code in DELIBERATELY_UNALIASED, "被顺手加了别名，就会退化成一句「重试」"

    outcome = describe_sync_outcome(imported=0, failure_code=code, status="completed")
    assert outcome["message_zh"] != "暂时连不上服务器。你的数据没有丢，[ 重试 ]"
    assert "产品的问题" in outcome["message_zh"]
    assert outcome["outcome"] != "nothing_new"


def test_challenge_exit_does_not_promise_we_will_bypass_it() -> None:
    """退出码 8 = 撞上验证码。L0 边界：我们不绕，只能把人引回浏览器。"""
    from social_archive.failure_copy import describe_sync_outcome
    from social_archive.gallerydl_runner import classify_exit_code

    assert classify_exit_code(8, url="https://www.pixiv.net/x") == "CHALLENGE_REQUIRED"
    outcome = describe_sync_outcome(
        imported=0, failure_code="CHALLENGE_REQUIRED", platform_label="Pixiv", status="completed"
    )
    # 必须落到冻结词典里的句子，不能凭空造一句新的
    assert outcome["message_zh"].startswith("没有在浏览器里找到")
    assert outcome["outcome"] == "failed"


def test_every_exit_bit_produces_some_explanation() -> None:
    """穷举安装源里所有的位：**没有一个能走到「没有原因」**。"""
    from social_archive.gallerydl_runner import classify_exit_code

    for bit in (1, 4, 8, 16, 32, 64, 128):
        assert classify_exit_code(bit, url="https://example.com/x") is not None, (
            f"退出码 {bit} 没有对应的失败码——它会变成一次静默的零"
        )
