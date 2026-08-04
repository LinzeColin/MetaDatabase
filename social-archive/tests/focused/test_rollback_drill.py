"""回滚演练把脚本自己的数据丢失缺陷炸出来了（v0.0.0.7 / T18）。

## 演练发现的

T18 记着「发布与回滚演练未做」。真跑一遍，在**撤销回滚**那一步炸了：

    scripts/rollback_0007.sh --restore <db> <db>.pre-rollback-<秒级时间戳>

备份文件名只精确到**秒**。撤销回滚与前一次回滚发生在同一秒时，
这次的备份目标与上次同名 —— 而恢复顺序是

    先 .backup 写 $PRE   ← 覆盖了
    再 .restore 读 $SNAP ← 正是刚被覆盖的那个文件

于是**备份把它正要恢复的快照先毁了**。脚本照样打印「✓ 回滚完成」，
而 users / session / platform_credential 整批数据永久消失，没有任何提示。

实测：撤销之后 `SELECT COUNT(*) FROM users` = **0**（应为 1）。

这是「看起来成功」的最坏形态——**回滚工具自己把数据弄丢了还报成功**。
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/rollback_0007.sh"
TEXT = SCRIPT.read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    subprocess.run(["which", "sqlite3"], capture_output=True).returncode != 0,
    reason="本机没有 sqlite3 命令行",
)


def test_backup_name_is_not_only_second_resolution() -> None:
    """秒级时间戳不足以区分同一秒内的两次恢复。"""
    match = re.search(r'^PRE=.*$', TEXT, re.M)
    assert match, "找不到备份文件名的构造"
    line = match.group(0)
    assert "date -u" in line
    # 判据打在「秒之外还有别的区分位」上，不钉某一种写法（$$ / %N / RANDOM 都行）
    assert any(token in line for token in ("$$", "%N", "RANDOM")), (
        f"备份名只有秒级精度：{line}。同一秒内第二次恢复会覆盖第一次的备份，"
        "而恢复顺序是先备份后读快照——撤销回滚时会把要恢复的那份先毁掉"
    )


def test_it_refuses_when_the_backup_would_clobber_the_snapshot() -> None:
    """$PRE == $SNAP 时必须拒绝——那正是把快照毁掉的那条路径。"""
    assert "备份目标与快照是同一个文件" in TEXT, "没有拦住自毁快照的情况"
    assert "备份目标已存在，拒绝覆盖" in TEXT, "会静默覆盖已存在的备份"


def test_verify_exits_nonzero_when_it_found_a_mismatch(tmp_path: Path) -> None:
    """「没查成」与「查出问题」不能共用一个退出码。

    原来 --verify 无论对不对得上都 exit 0，任何把它当门用的地方都会被骗。
    """
    import sqlite3

    snap = tmp_path / "snap.sqlite3"
    live = tmp_path / "live.sqlite3"
    for path in (snap, live):
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE content(id TEXT PRIMARY KEY)")
        for name in ("user_relation", "source_account", "artifact",
                     "platform_collection", "sync_run", "scan_receipt"):
            con.execute(f"CREATE TABLE {name}(id TEXT PRIMARY KEY)")
        con.commit()
        con.close()
    # 让两边行数对不上
    con = sqlite3.connect(live)
    con.execute("INSERT INTO content(id) VALUES('extra')")
    con.commit()
    con.close()

    result = subprocess.run(
        ["bash", str(SCRIPT), "--verify", str(live), str(snap)],
        capture_output=True, text=True, cwd=ROOT,
    )
    assert result.returncode != 0, (
        "行数对不上，--verify 却报成功。"
        f"输出：{result.stdout[-300:]}"
    )
    assert "校验未通过" in result.stdout


def test_restore_direction_is_stated_not_guessed() -> None:
    """回滚与撤销回滚的期望值相反，自检必须先判方向。

    原来只认「往回滚」一个方向，于是一次**成功的撤销**会打出三行
    「! 可能有问题」，让对的事看着像错的。
    """
    assert "SNAP_HAS_TENANCY" in TEXT, "自检没有判断恢复方向"
    assert "撤销回滚" in TEXT and "回滚到迁移前" in TEXT, "两个方向没有分别说明"


def test_rollback_warns_that_code_must_be_rolled_back_too() -> None:
    """只回滚数据库是不够的——实测 v0.0.0.7 的代码会把迁移静默重做一遍。

    演练结果（回滚后用 v0.0.0.7 代码打开同一个库）：

        initialize() 没报错
        users / session / oauth_identity / platform_credential  **又被建回来了**
        users 行数 0                    ← 表回来了但数据没有
        sync_run.user_id                又加回来了
        业务数据 cnt_old                1 条（完好）

    也就是说：回滚等于白做，而且**你会以为它做成了**。
    这条警告不写出来，回滚工具就是在骗人。
    """
    assert "把代码也回滚" in TEXT, "没有警告「只回滚数据库不够」"
    assert "静默" in TEXT, "没有说清重做迁移是无声无息的"
    assert "先停服务" in TEXT and "回滚代码" in TEXT, "没有给出正确顺序"
