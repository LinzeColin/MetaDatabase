r"""手工补跑成功，不许把定时那次的失败盖住（2026-08-14）。

## 一次真的漏报

`check_durability_units.sh` 存在的全部理由是回答一句话：
**「没人管它，那件事还在做吗？」** 2026-08-13 生产上它答错了：

    timer   LastTriggerUSec        = 03:33:46   ← 定时触发，200/CHDIR **失败**
    service ExecMainStartTimestamp = 08:51:06   ← 我手工补跑，成功

而那张表印的是 **「✓ 上次成功 08:51:06」**。
journalctl 里白纸黑字躺着 `Failed to start social-archive-backup.service`，
而这道判据说绿的。

**根因**：systemd 只保留「最近一次运行」的结果，**不分是谁叫起来的**。
脚本读 `Result`/`ExecMainStartTimestamp` 拿到的是那次手工运行的结论，
它跟「定时器叫起来的那次」没有任何关系。
「手工能跑通」和「没人管也会跑」是两件事——**后者才是这个产品的卖点**。

## 这道测试怎么测

不需要 systemd：把一个**假的 `systemctl`** 放到 PATH 最前面，
让脚本整条真跑起来，再断言它印了什么。三种情形：

1. 服务最近一次运行 ≈ 定时触发那一刻 → 可以说「✓ 上次成功」
2. 服务最近一次运行**远晚于**定时触发 → 只能说「?」并给出排查命令
3. 时间串解不出来 → 也只能说「?」，**不许掉进"看着像成功"那一支**
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_durability_units.sh"

TIMERS = (
    "social-archive-backup.timer",
    "social-archive-replication.timer",
    "social-archive-private-database-sync.timer",
    "social-archive-status.timer",
)

FAKE = r'''#!/usr/bin/env python3
"""假 systemctl。取值从环境变量来，好让每个用例自己摆状态。"""
import os, sys

argv = sys.argv[1:]
def out(text):
    print(text); raise SystemExit(0)

if argv and argv[0] == "is-enabled":
    out("enabled")
if argv and argv[0] == "is-active":
    out("active")
if argv and argv[0] == "show":
    unit = argv[1]
    prop = ""
    for i, a in enumerate(argv):
        if a == "-p" and i + 1 < len(argv):
            prop = argv[i + 1]
    if prop == "Unit":
        out(unit[:-len(".timer")] + ".service" if unit.endswith(".timer") else "")
    if prop == "LastTriggerUSec":
        out(os.environ.get("FAKE_TRIGGER", ""))
    if prop == "ExecMainStartTimestamp":
        out(os.environ.get("FAKE_STARTED", ""))
    if prop == "Result":
        out(os.environ.get("FAKE_RESULT", "success"))
    if prop == "ExecMainStatus":
        out("0")
    out("")
out("")
'''


def _run(tmp_path: Path, trigger: str, started: str, result: str = "success"):
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir(parents=True, exist_ok=True)
    fake = fake_dir / "systemctl"
    fake.write_text(FAKE, encoding="utf-8")
    fake.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{fake_dir}:{env['PATH']}"
    env["FAKE_TRIGGER"] = trigger
    env["FAKE_STARTED"] = started
    env["FAKE_RESULT"] = result
    return subprocess.run(["bash", str(SCRIPT)], cwd=ROOT, env=env,
                          capture_output=True, text=True, check=False)


def _table(text: str) -> str:
    """只取**表格那几行**（每行以某个 unit 名开头）。

    **为什么必须切出来**：脚本的解释段里逐字引了一句
    「而这张表当时印的是『✓ 上次成功 08:51:06』」——
    整篇 grep 会命中那句**说明文字**，而不是它真的印在哪一格。
    第一版就是这么误红的：产品行为完全正确，红的是我自己的断言扫错了范围。
    （同型：我写来解释修复的那句注释，把判据本身废掉了。）
    """
    return "\n".join(line for line in text.splitlines()
                     if any(line.startswith(u) for u in (*TIMERS, "social-archive.service")))


def test_定时那次和手工那次隔了几小时时不许说成功(tmp_path: Path) -> None:
    """**2026-08-13 生产上的真实取值。**"""
    done = _run(tmp_path,
                trigger="Thu 2026-08-13 03:33:46 UTC",
                started="Thu 2026-08-13 08:51:06 UTC")
    text = done.stdout + done.stderr

    assert "✓ 上次成功" not in _table(text), (
        "手工补跑的成功被印在了「上次成功」那一格——定时那次失败就这样被盖住了。\n" + text)
    assert "手工" in _table(text), "表格里没说清那次成功是手工触发的：\n" + text
    # 必须给出去哪儿看的确切命令，而且时间窗要是**定时触发那一刻**
    assert "journalctl" in text and "2026-08-13 03:33:46" in text, (
        "没给出查那次定时到底成没成的命令（时间窗必须是触发那一刻）：\n" + text)
    assert "每个定时器上次真的跑成了" not in text, (
        "结尾还在宣称「每个定时器上次真的跑成了」——这正是那句错话。\n" + text)


def test_定时那次就是最近一次时可以说成功(tmp_path: Path) -> None:
    """反方向。没有它，实现可以靠「永远说 ?」把上面那条骗过去，
    而一个永远不变绿的灯和坏掉的灯长得一样。"""
    done = _run(tmp_path,
                trigger="Thu 2026-08-13 18:20:29 UTC",
                started="Thu 2026-08-13 18:20:30 UTC")
    text = done.stdout + done.stderr
    assert "✓ 上次成功" in _table(text), "定时那次就是最近一次，却不肯说成功：\n" + text
    assert "手工" not in _table(text), "没人手工跑过，却报成手工：\n" + text
    assert "每个定时器上次真的跑成了" in text, "该给的那句结论没给：\n" + text


def test_时间串解不出来时也不许说成功(tmp_path: Path) -> None:
    """**解析失败必须落到「不知道」，不能落到「看着像成功」。**

    这个仓最常踩的就是空默认值：转不出来回空，而空被当成 0、
    0 被当成「差值很小」、于是印出 ✓。这条钉死那条路。
    """
    done = _run(tmp_path, trigger="这不是时间", started="也不是时间")
    text = done.stdout + done.stderr
    assert "✓ 上次成功" not in _table(text), "时间串解不出来，却印了「上次成功」：\n" + text
    assert "比不出" in _table(text), "没说清是「比不出来」：\n" + text


def test_定时器一个都没少扫(tmp_path: Path) -> None:
    """**扫描集不许悄悄缩水。** 脚本里那张 REQUIRED 表少一个定时器，
    对应那条链就再也没人问过——而它会静悄悄地不跑。
    """
    done = _run(tmp_path,
                trigger="Thu 2026-08-13 18:20:29 UTC",
                started="Thu 2026-08-13 18:20:30 UTC")
    text = done.stdout + done.stderr
    missing = [t for t in TIMERS if t not in text]
    assert not missing, f"这几个保命的定时器没有出现在表里：{missing}\n{text}"
