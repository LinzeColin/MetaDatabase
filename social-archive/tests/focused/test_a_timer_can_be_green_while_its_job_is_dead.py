r"""定时器还亮着，它触发的那件事却已经死了（2026-08-13）。

## 它修的是一道**全程绿着**的检查

`check_durability_units.sh` 只问两件事：`is-enabled`、`is-active`。
这两个问的都是**定时器本身**还在不在，跟它每次叫起来的那个服务跑没跑成
**毫无关系**——定时器越是好好的，失败次数攒得越快。

生产实测，两次，两次这张表都报「✓ 保命的 unit 都已启用」：

    2026-08-11~12  replication 连着失败 108 次、28 小时（200/CHDIR）
    2026-08-12~13  backup     连着两天同一个错

第二次尤其难看：事故当时我只确认了 replication 恢复，**没查 backup**——
它俩共用同一个进不去的 `WorkingDirectory`，所以备份也一起停了两天，
而我把事故报成了已解决。

## 最要命的是第三种情况

systemd 对**从没跑过**的 unit，照样答 `Result=success`、`ExecMainStatus=0`。
（2026-08-13 在生产 `/run` 里放一个没 enable 没 start 的探针 unit 问出来的，
不是查文档猜的。）所以「按 Result 判绿」会把「一次都没跑过」报成「上次成功」
——正是 2026-08-04 那次事故的形状：三个 timer 全 disabled、90 天 No entries。

唯一诚实的字段是 `ExecMainStartTimestamp`：没跑过就是空的。

**下面第三个用例就是那个反例：Result=success，而判据必须判红。**
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_durability_units.sh"

# 这个假 systemctl 只认真脚本真的会发的那几种问法。
# 三种情形的返回值都是 2026-08-13 从生产上照抄的，不是编的。
FAKE_SYSTEMCTL = r"""#!/usr/bin/env bash
cmd="$1"; shift
case "$cmd" in
  is-enabled) echo enabled ;;
  is-active)  echo active ;;
  show)
    unit="$1"; shift
    prop=""
    while [ $# -gt 0 ]; do
      case "$1" in -p) shift; prop="$1" ;; esac
      shift
    done
    case "$prop" in
      Unit)                   echo "${unit%.timer}.service" ;;
      ExecMainStartTimestamp) printf '%s\n' "${FAKE_STARTED}" ;;
      Result)                 printf '%s\n' "${FAKE_RESULT}" ;;
      ExecMainStatus)         printf '%s\n' "${FAKE_CODE}" ;;
    esac ;;
esac
"""


def _run(tmp_path: Path, *, started: str, result: str, code: str):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "systemctl"
    fake.write_text(FAKE_SYSTEMCTL, encoding="utf-8")
    fake.chmod(0o755)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True, text=True, timeout=60,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "FAKE_STARTED": started,
            "FAKE_RESULT": result,
            "FAKE_CODE": code,
        },
    )


GOOD = {"started": "Thu 2026-08-13 08:50:54 UTC", "result": "success", "code": "0"}
# 2026-08-13 生产上 backup.service 的真实值。
FAILED = {"started": "Thu 2026-08-13 03:33:46 UTC", "result": "exit-code", "code": "200"}
# 2026-08-13 生产 /run 探针问出来的真实值：**跑都没跑过，它也说 success。**
NEVER = {"started": "", "result": "success", "code": "0"}


def test_跑成了才算绿(tmp_path: Path) -> None:
    got = _run(tmp_path, **GOOD)
    assert got.returncode == 0, got.stdout + got.stderr
    assert "上次成功" in got.stdout


def test_定时器还活着而服务上次失败必须判红(tmp_path: Path) -> None:
    """**这就是那 28 小时里本该红的地方。**假 systemctl 在这个用例里
    对定时器照答 enabled/active——正是事故当时的真实状态。"""
    got = _run(tmp_path, **FAILED)
    assert got.returncode != 0, "定时器亮着、活儿却死了，判据不能给绿灯"
    assert "上次失败" in got.stdout
    assert "exit-code/200" in got.stdout
    assert "✓ 保命的 unit 都已启用" not in got.stdout, "这句话正是当时在说谎的那句"


def test_从没跑过不许当成上次成功(tmp_path: Path) -> None:
    """**反例**：systemd 在这里回答的是 `Result=success`、`ExecMainStatus=0`，
    而正确答案是红。照 Result 判的写法在这个用例上会给绿灯。"""
    got = _run(tmp_path, **NEVER)
    assert got.returncode != 0, "一次都没跑过被判成绿，就是 2026-08-04 那次事故"
    assert "从没跑过" in got.stdout
    assert "上次成功" not in got.stdout


def test_红的时候要指得出是哪个服务和下一步敲什么(tmp_path: Path) -> None:
    """判据报红不能只说「有问题」——Owner 得知道点哪儿。"""
    got = _run(tmp_path, **FAILED)
    assert "social-archive-backup.service" in got.stdout, "要指名道姓"
    assert "journalctl -u social-archive-backup.service" in got.stdout, "要能查为什么"
    assert "systemctl start social-archive-backup.service" in got.stdout, "要能当场复核"


@pytest.mark.parametrize("scenario", [GOOD, FAILED, NEVER])
def test_四种保命的定时器一个都不能漏(tmp_path: Path, scenario: dict) -> None:
    """三种情形下都要把四个定时器逐个列出来——**漏掉的那个正是上次出事的那个**。"""
    got = _run(tmp_path, **scenario)
    for timer in ("backup", "replication", "private-database-sync", "status"):
        assert f"social-archive-{timer}.timer" in got.stdout
