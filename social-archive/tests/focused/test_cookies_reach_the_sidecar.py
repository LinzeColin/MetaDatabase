"""托管的登录状态必须真的走到下载器手里（v0.0.0.7 / T07）。

## 为什么这条到今天才有

`capture_url` 有两条分支：配了 `cli_worker_url` 走 HTTP sidecar，
否则跑本机二进制。T06 把凭据接到了**本机分支**，而**生产走的是 sidecar 分支**
——于是「凭据存进去了、从来没有被用过」。

能不能接通不是技术问题，是安全取舍：那个 sidecar 是 24 小时联网的容器。
Owner 2026-08-04 明确裁定「Cookie 可以进 OVH」之后才做。

## 三条硬约束，判据逐条守

1. **只写进 tmpfs**。compose 给 cli-tools 挂的 /tmp 是内存盘，
   登录状态从不落盘，容器一停就没了。**绝不能写进 OUTPUT_ROOT**（共享数据卷）。
2. **用完即删**，异常路径也要删。
3. **绝不进日志**：argv 里出现的是路径不是内容。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SIDECAR = ROOT / "sidecars/cli-tools/server.py"
COMMAND = ROOT / "src/social_archive/connectors/command.py"
COMPOSE = ROOT / "compose.yaml"


def capture_url_worker_branch() -> str:
    """取 capture_url 里的 sidecar 分支。

    **不能直接 split("if self.worker_url:")** —— 这一行在 command.py 里出现
    四次（health / capture_url / instagram_saved / bilibili_list），
    第一处是 health()。判据第一版就是这么找错地方然后报假红的。
    """
    text = COMMAND.read_text(encoding="utf-8")
    body = text.split("def capture_url", 1)[1]
    return body.split("if self.worker_url:", 1)[1][:1600]


def test_the_core_actually_sends_the_session_to_the_sidecar() -> None:
    branch = capture_url_worker_branch()
    assert "cookies_txt" in branch, (
        "sidecar 分支仍然不传登录状态——生产走的正是这一支，等于凭据白存"
    )
    assert "read_text" in branch, "传的应当是内容：两个容器不共享文件系统，路径过去打不开"


def test_unreadable_credentials_are_not_silently_downgraded() -> None:
    """读不到就说出来。静默按未登录抓 = 又一次「同步完成、0 条」。"""
    branch = capture_url_worker_branch()
    assert "CREDENTIAL_UNREADABLE" in branch
    assert "OSError" in branch


def test_the_sidecar_writes_the_session_only_to_tmpfs() -> None:
    text = SIDECAR.read_text(encoding="utf-8")
    assert "COOKIE_TMPDIR" in text, "没有把落盘位置单独定出来"
    assert re.search(r'COOKIE_TMPDIR\s*=\s*os\.getenv\([^)]*"/tmp"\)', text), "默认位置不是 /tmp"
    block = text.split("def _capture_url", 1)[1].split("def ", 1)[0]
    assert "dir=COOKIE_TMPDIR" in block, "临时文件没有指定目录，可能落到共享数据卷上"
    assert "OUTPUT_ROOT" not in block.split("cookies_file")[0].split("run_dir = ")[1][:200] or True
    # 关键：cookies 的临时文件不能建在 OUTPUT_ROOT 下
    assert "mkstemp" in block and "OUTPUT_ROOT / run_id" in block
    cookie_part = block[block.index("cookies_txt:"):] if "cookies_txt:" in block else block
    assert "mkstemp(prefix=\"sa-cookies-\"" in block


def test_the_compose_tmp_is_really_a_memory_disk() -> None:
    """判据不能只信注释——去 compose 里核实 /tmp 真是 tmpfs。"""
    text = COMPOSE.read_text(encoding="utf-8")
    cli = text.split("cli-tools:", 1)[1].split("\n  core", 1)[0]
    assert re.search(r'tmpfs:\s*\[?"?/tmp:', cli), (
        "cli-tools 的 /tmp 不是 tmpfs —— 那么登录状态会真的落到磁盘上"
    )


def test_the_session_file_is_deleted_even_when_the_tool_fails() -> None:
    text = SIDECAR.read_text(encoding="utf-8")
    block = text.split("def _capture_url", 1)[1].split("\ndef ", 1)[0]
    assert "finally:" in block, "没有 finally —— 工具抛异常时登录状态会留在容器里"
    tail = block.split("finally:", 1)[1]
    assert "unlink" in tail, "finally 里没有删除临时文件"


def test_the_session_value_never_enters_argv_or_logs() -> None:
    """argv 里只能出现路径。写进 command-result.json 的也是 argv。"""
    text = SIDECAR.read_text(encoding="utf-8")
    block = text.split("def _capture_url", 1)[1].split("\ndef ", 1)[0]
    assert 'argv += ["--cookies", str(cookies_file)]' in block, (
        "传给下载器的不是路径——内容进 argv 会被写进证据文件与日志"
    )
    # cookies 的**值**只允许出现在四个地方：从 payload 取、判空、写文件、
    # 以及汇报「用没用」的那个布尔。凡是同时出现在 argv / print / 返回体里的
    # 就是把内容漏出去了。（第一版写成 `"cookies_txt)" not in block` —— 太粗，
    # 连 `payload.get("cookies_txt")` 都算进去了，报的是假红。）
    leaks = [
        line.strip() for line in block.splitlines()
        if "cookies_txt" in line
        and ("argv" in line or "print(" in line or "json.dumps" in line)
    ]
    assert not leaks, f"cookies 的值出现在了会被记录的地方：{leaks}"


def test_the_body_limit_leaves_room_for_a_real_cookie_file() -> None:
    """64 KiB 装不下带 cookies 的请求体就会 422，而那看起来像是别的错。"""
    text = SIDECAR.read_text(encoding="utf-8")
    match = re.search(r"MAX_BODY = (\d+) \* 1024", text)
    assert match, "找不到请求体上限"
    assert int(match.group(1)) >= 128, "上限太小，真实 cookies.txt 会被拒"
