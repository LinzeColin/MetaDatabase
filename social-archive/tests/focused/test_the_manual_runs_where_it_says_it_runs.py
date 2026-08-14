r"""运维手册标着「在生产上」的命令，得在生产上真的跑得动（2026-08-13）。

## 它修的是什么

手册开头就写着「**先分清你在哪台机器上——两套命令不能混用**」，而它自己
在生产那一侧给了**五条**跑不通的命令。2026-08-13 逐条在生产上实测——
其中 `journalctl` 与 `systemctl enable` 两条是**后来才发现的**：
前者不报错只给个空，后者挂在一个标题里没有「生产」二字的小节下、
被这条判据第一版的切法整个漏掉（射程因此改成按命令本身判）：

    systemctl restart social-archive.service
      → Failed to restart …: Interactive authentication required.
        （以 ubuntu 跑；在 /run 里放一个无害探针 unit 试出来的，没动他真正的服务。
          同一个探针以 root 跑，退出码 0。）

    bash scripts/backup.sh
      → PermissionError: /var/lib/social-archive
        ubuntu 不在 socialarchive 组，而那个目录是 2770。
      → 换成 sudo -u socialarchive 跑，得到
        {"error_code": "AGE_RECIPIENT_MISSING", "message": "缺少 …；禁止明文备份"}
        那个变量来自 systemd unit 的 EnvironmentFile，不在 shell 里。
        （脚本**拒绝**而不是退化成明文备份，这一点是对的。）

    bash scripts/update.sh
      → 第 2/3 步 systemctl restart 被拒，**而它排在重建镜像之后**：
        留下「新镜像已建好、容器还跑着旧的」这种没人描述过的中间态。

**三条都不是"少个 sudo"那么简单**：备份那条根本不该走脚本，
它的正确入口是那个 systemd unit 本身（和每天自动跑的是同一条路）。

## 这条判据只管一件事

**手册里标着「在生产上」的那些块**，不许再出现已知跑不通的写法。
它不检查开发机那一节——那些命令本来就不是给生产用的，
在生产上跑出来的红是跑的人造的，不是手册的错（我自己先造了一次）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANUAL = ROOT / "docs/06_运维手册.md"


# 只可能在生产机上跑的东西：systemd 是生产的，`/opt/social-archive` 也是。
# 开发机那一节两样都不含（start/stop/doctor/backup/restore/export 全是相对路径），
# 所以按这个判不会误伤它。
_PRODUCTION_ONLY = ("systemctl", "journalctl", "/opt/social-archive")


def _production_commands() -> list[str]:
    """哪些命令是「在生产上跑」的。

    两条信号，满足其一即算：

      A. **块被标成生产**——在 `### 生产…` 小节里，或块里写着 `# 在生产上`；
      B. **命令本身只可能在生产上跑**——含 `systemctl` / `journalctl` /
         `/opt/social-archive`。

    **第一版只有 A，于是漏了一处**：`systemctl enable --now …` 那个块挂在
    「### 保命的三个 timer」小节下，标题里没有「生产」两个字，
    而它同样需要 root。加上 B 之后立刻就抓住了。

    口径写出来，免得被当成扫了全文——开发机那一节不在射程内，
    那些命令本来就不是给生产用的。
    """
    text = MANUAL.read_text(encoding="utf-8")

    # 每个代码块连同它最近的上级标题一起取出来
    blocks: list[tuple[str, str]] = []
    for match in re.finditer(r"```bash\n(.*?)```", text, re.S):
        heading = ""
        for head in re.finditer(r"^#{2,4} .*$", text[: match.start()], re.M):
            heading = head.group(0)
        blocks.append((heading, match.group(1)))

    cmds: list[str] = []
    for heading, block in blocks:
        marked = heading.startswith("### 生产") or "在生产上" in block
        for line in block.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line or line.startswith(("```", ">")):
                continue
            if marked or any(token in line for token in _PRODUCTION_ONLY):
                cmds.append(line)
    return cmds


def test_切得出生产那一侧的命令() -> None:
    """**先证明这条判据看得见东西。** 切不出来的话，下面几条会安静全绿。"""
    cmds = _production_commands()
    assert len(cmds) >= 4, f"只切出 {len(cmds)} 条，八成是小节标题变了：{cmds}"
    assert any("systemctl" in c for c in cmds), f"没切到 systemctl 那几条：{cmds}"


def test_重启服务要带_sudo() -> None:
    """以 ubuntu 跑会得到 Interactive authentication required（实测）。"""
    for cmd in _production_commands():
        if "systemctl restart" in cmd or "systemctl enable" in cmd:
            assert cmd.startswith("sudo "), (
                f"这条在生产上会被拒（要 root）：{cmd!r}\n"
                "以 ubuntu 跑得到 Interactive authentication required；同一条以 root 跑退出码 0。")


def test_生产上取快照不许走那个脚本() -> None:
    """`bash scripts/backup.sh` 在生产上两层都过不去（权限 + 缺 AGE_RECIPIENT）。
    正确入口是 systemd unit 本身——它和每天自动跑的是同一条路。"""
    for cmd in _production_commands():
        assert "scripts/backup.sh" not in cmd, (
            f"生产上这条跑不通：{cmd!r}\n"
            "改用：sudo systemctl start social-archive-backup.service")


def test_看日志要带_sudo() -> None:
    """**这条是最坏的一种：它不报错，它给你一个空。**

    以 ubuntu 跑 `journalctl -u social-archive-replication`（实测）：

        Hint: You are currently not seeing messages from other users and the system.
        -- No entries --

    退出码 0，看起来像「这个服务从来没跑过」。而手册给这条命令的注释正是
    「复制真的在跑吗」——它专门用来回答的那个问题，被它自己静默答错。
    加 sudo 之后真日志就出来了。
    """
    for cmd in _production_commands():
        if cmd.startswith("journalctl") or " journalctl" in cmd:
            assert cmd.startswith("sudo "), (
                f"这条不带 sudo 会打「-- No entries --」并退出 0：{cmd!r}\n"
                "他会据此以为服务从来没跑过。")


def test_就地更新要带_sudo() -> None:
    """`update.sh` 第 2/3 步要 `systemctl restart`，非 root 会被拒——
    **而那一步排在重建镜像之后**，倒下时机器已经处于中间态。"""
    for cmd in _production_commands():
        if "scripts/update.sh" in cmd:
            assert cmd.startswith("sudo "), (
                f"这条会在重建完镜像之后倒在第 2/3 步：{cmd!r}")


def test_只读那两条不要平白加_sudo() -> None:
    """**别把「都加上 sudo」当成修法。** 实测 `systemctl status` 与
    `check_durability_units.sh` 都不需要 root（status 会显示 Loaded/Active/PID，
    也没有 journalctl 那种隐藏提示）；无谓的提权会让人以为每条都要，
    下次就懒得分了。"""
    for cmd in _production_commands():
        if "systemctl status" in cmd or "check_durability_units.sh" in cmd:
            assert not cmd.startswith("sudo "), (
                f"这条实测不需要 root，别加 sudo：{cmd!r}")
