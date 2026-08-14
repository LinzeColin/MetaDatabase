"""托管的平台会话必须真的交到工具手里（v0.0.0.7 / T06）。

## 为什么需要这组判据

T06 的验收原文是：**服务端收到的 cookies.txt 能让 gallery-dl 取到只有
登录用户才看得到的内容**。

而在这组判据存在之前，链路是断的：

    CredentialStore.materialize()  全仓只有 tests/ 在调，**零个生产调用方**
    capture_url 的 argv            **根本没有 --cookies**

也就是说 Owner 就算上传了 X 的会话，服务端仍然按未登录去抓，只拿得到
公开内容。那条验收**无论谁登录都不可能通过**——它卡的不是「等 Owner
登录」，是这段代码没写。

这是本会话第四次遇到同一形态：
  · failure_copy.py 建好了没有生产调用方
  · unexplained_zero_runs 建好了没有调用方
  · SYNC_QUEUE_LAST_RESULT_KEY 写了四处、没有任何界面读
  · 现在是凭据托管

**「做完了」和「接上了」是两件事。**
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_capture_url_accepts_and_forwards_a_cookies_path(tmp_path) -> None:
    """给了 cookies 路径，argv 里就必须出现 --cookies。"""
    from social_archive.connectors.command import CommandArtifactConnector

    seen: dict[str, list[str]] = {}

    def fake_run(self, argv, run_dir):
        seen["argv"] = list(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    connector = CommandArtifactConnector("x", tmp_path / "staging")

    for tool in ("gallery-dl", "yt-dlp"):
        seen.clear()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(CommandArtifactConnector, "_run", fake_run)
            connector.capture_url("https://x.com/i/bookmarks", tool=tool, cookies_path=str(cookies))
        argv = seen["argv"]
        assert "--cookies" in argv, f"{tool} 的 argv 里没有 --cookies：{argv}"
        assert argv[argv.index("--cookies") + 1] == str(cookies)
        # URL 必须仍然是最后一个位置参数
        assert argv[-1].startswith("https://"), f"{tool} 的 URL 不在末尾：{argv}"


def test_no_cookies_path_means_no_flag(tmp_path) -> None:
    """不给就不加——未登录抓公开内容是合法路径，不能凭空塞个空参数。"""
    from social_archive.connectors.command import CommandArtifactConnector

    seen: dict[str, list[str]] = {}

    def fake_run(self, argv, run_dir):
        seen["argv"] = list(argv)
        return subprocess.CompletedProcess(args=argv, returncode=0, stdout="", stderr="")

    connector = CommandArtifactConnector("x", tmp_path / "staging")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(CommandArtifactConnector, "_run", fake_run)
        connector.capture_url("https://x.com/status/1", tool="gallery-dl")
    assert "--cookies" not in seen["argv"]


def test_the_worker_actually_looks_up_and_materializes_a_credential() -> None:
    """光有参数不算接上——**下载路径必须真的去取凭据**。

    这条盯的是「有没有调用方」，不是「函数写得对不对」。
    """
    worker = (ROOT / "src/social_archive/worker.py").read_text(encoding="utf-8")
    assert "materialize(" in worker, (
        "worker 里没有 materialize 调用——凭据存了但没人用，"
        "T06 的验收无论谁登录都不可能通过"
    )
    assert "cookies_path=" in worker, "worker 没有把 cookies 路径传给 capture_url"
    assert "CUSTODIAL_PLATFORMS" in worker, "没有按平台判断该不该取凭据"
    assert "owner_user_for_content" in worker, "没有解析这条内容属于谁"


def test_materialize_has_a_production_caller_not_only_tests() -> None:
    """这条是上一条的推广：只在 tests/ 里被调用等于没接上。

    本会话已经四次栽在这上面（failure_copy / unexplained_zero_runs /
    SYNC_QUEUE_LAST_RESULT_KEY / 凭据托管）。
    """
    import subprocess as sp

    out = sp.run(
        ["grep", "-rn", "materialize(", "--include=*.py", "src/"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    ).stdout
    callers = [
        line for line in out.splitlines()
        if "def materialize" not in line and line.strip()
    ]
    assert callers, "src/ 下没有任何 materialize 调用方——它只活在测试里"


def test_a_missing_credential_degrades_but_records_why(tmp_path) -> None:
    """没托管过会话时不能崩，但**必须把原因记下来**。

    静默降级成「未登录抓一遍、0 条」正是这一版要消灭的形状。
    """
    worker = (ROOT / "src/social_archive/worker.py").read_text(encoding="utf-8")
    assert "CredentialUnavailable" in worker, "没有接住「没托管/解不开」这两种情况"
    assert "cookie_note" in worker, "降级了却没有把原因带进 errors"
    # 原因要进 errors，最终会出现在 RuntimeError 的消息里
    assert "errors.append(cookie_note)" in worker
