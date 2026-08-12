"""回滚必须说清它会抹掉什么（v0.0.0.7）。

`scripts/rollback_0007.sh` 用整库 `.restore` 恢复——**快照里没有的表，
恢复之后就不存在了**。它原本的行数比对只覆盖 7 张业务表，
而 v0.0.0.7 新增的 users / oauth_identity / session / extension_token /
platform_credential 一张都不在其中。

于是拿一个 v0.0.0.7 之前的快照去 --verify，会得到一句干干净净的
「✓ 校验通过」，而实际上一执行就会连登录身份、扩展令牌和**已托管的平台凭据**
一起抹掉。对 Owner 的表现是「我明明连过，怎么全没了」。

这是 INV-REVERSIBLE 与 INV-NO-SILENT-ZERO 的交叉地带：回滚本身是对的，
**不说清代价才是问题**。
"""

from __future__ import annotations

import shutil
import sqlite3

from social_archive.git_env import clean_git_env
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rollback_0007.sh"


# v0.0.0.7 **并进 main 之前**那个 main 的提交。
#
# 这里原来写的是 `origin/main`——在 v0.0.0.7 还没合进去的时候，那确实就是
# 「v0.0.0.7 之前」。2026-08-12 把 PR #178 合进 main 之后，`origin/main`
# 变成了**这条线自己**，schema 里当然有 `platform_credential` 了，
# 于是这条判据的前提当场不成立。
#
# **是它自己那条防空转的断言把这件事喊出来的**（「快照里不该有 v0.0.0.7 的表——
# 否则这条判据在空转」）。没有那一句，它会安安静静地拿一个「已经有那些表」的
# 快照去测「回滚会丢哪些表」，然后一路绿着什么也没测。
#
# 所以钉死这个 SHA：「v0.0.0.7 之前长什么样」是一件**历史事实**，不会再变，
# 而 `origin/main` 会一直往前走。
PRE_V0007_MAIN = "9bb82da350c474a149f521c6b0dd96dd6bb31b4d"


def _pre_v0007_snapshot(path: Path) -> None:
    """用 v0.0.0.7 合进 main **之前**那个 main 的 schema 造快照。"""
    schema = subprocess.run(
        ["git", "show",
         f"{PRE_V0007_MAIN}:social-archive/src/social_archive/sql/runtime_schema.sql"],
        cwd=ROOT, env=clean_git_env(), capture_output=True, text=True, check=True,
    ).stdout
    con = sqlite3.connect(path)
    con.executescript(schema)
    con.close()


@pytest.mark.skipif(not shutil.which("sqlite3"), reason="本机没有 sqlite3 命令行")
def test_verify_names_every_table_the_rollback_would_drop(tmp_path: Path) -> None:
    from social_archive.db import RuntimeStore

    snapshot = tmp_path / "snapshot.sqlite3"
    _pre_v0007_snapshot(snapshot)
    assert sqlite3.connect(snapshot).execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name='platform_credential'"
    ).fetchone()[0] == 0, "快照里不该有 v0.0.0.7 的表——否则这条判据在空转"

    current = tmp_path / "current.sqlite3"
    store = RuntimeStore(current)
    store.initialize()
    with store.connection() as con:
        con.execute("INSERT INTO users(id,display_name,created_at,is_owner) VALUES('u','Owner','t',1)")
        con.execute(
            "INSERT INTO platform_credential(id,user_id,platform,recipient_fingerprint,"
            "cipher,cipher_sha256,cipher_byte_size,created_at,updated_at) "
            "VALUES('c','u','x','fp',X'00','h',1,'t','t')"
        )

    result = subprocess.run(
        ["bash", str(SCRIPT), "--verify", str(current), str(snapshot)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    for table in ("users", "oauth_identity", "session", "extension_token", "platform_credential"):
        assert table in out, f"--verify 没有提到 {table} 会被抹掉"
    assert "回滚后会整表消失" in out
    # 光列出表名不够——要说清对 Owner 意味着什么
    assert "重新用 Google/GitHub 登录一次" in out
    assert "已托管的平台登录信息全部消失" in out
    # 有凭据在库里时必须报出行数，不能只说"这张表没了"
    assert "当前有 1 行" in out


@pytest.mark.skipif(not shutil.which("sqlite3"), reason="本机没有 sqlite3 命令行")
def test_verify_stays_quiet_when_the_snapshot_already_has_the_new_tables(tmp_path: Path) -> None:
    """同版本快照之间回滚不该报「会抹掉」——否则告警会被当成噪音忽略。"""
    from social_archive.db import RuntimeStore

    for name in ("snapshot.sqlite3", "current.sqlite3"):
        RuntimeStore(tmp_path / name).initialize()
    result = subprocess.run(
        ["bash", str(SCRIPT), "--verify",
         str(tmp_path / "current.sqlite3"), str(tmp_path / "snapshot.sqlite3")],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "回滚后会整表消失" not in result.stdout


def test_the_dropped_table_list_is_computed_not_hand_written(tmp_path: Path) -> None:
    """会被抹掉的表必须**现算**，不能是脚本里手写的一串名字。

    ## 原来这条判据在守什么

    脚本里原有一行 `V0007_TABLES="users oauth_identity session …"`，
    这条判据比对它与 `RuntimeStore.IDENTITY_TABLES`，防止两边漂开。
    它守住的是「今天这五个名字对不对」。

    ## 为什么改成现在这样

    手写清单的问题不是今天不对，是**将来加一张表时没有任何东西提醒你回来改它**
    ——而这一节的全部意义就是"必须说出来"。漏一张，它安静地不说，且看起来正常。
    比对判据也只能证明"这五个还在"，证明不了"没漏第六个"。

    所以清单改成从两个库的 sqlite_master 现算，判据也跟着改成：
    **给当前库塞一张脚本从没听说过的表，看它说不说得出来。**
    这比比对清单强——它不依赖任何人维护任何名单。
    """
    from social_archive.db import RuntimeStore

    text = SCRIPT.read_text(encoding="utf-8")
    assert 'V0007_TABLES="users' not in text, "又退回手写清单了"
    assert "sqlite_master" in text.split("V0007_TABLES=", 1)[1][:600], "清单不是从库里算出来的"

    snapshot = tmp_path / "snapshot.sqlite3"
    current = tmp_path / "runtime.sqlite3"
    RuntimeStore(snapshot).initialize()
    with sqlite3.connect(snapshot) as con:
        for table in RuntimeStore.IDENTITY_TABLES:
            con.execute(f"DROP TABLE IF EXISTS {table}")
    RuntimeStore(current).initialize()
    # 脚本从没听说过这张表。现算的清单必须照样把它说出来。
    with sqlite3.connect(current) as con:
        con.execute("CREATE TABLE a_table_the_script_never_heard_of(id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO a_table_the_script_never_heard_of VALUES('x')")

    result = subprocess.run(
        ["bash", str(SCRIPT), "--verify", str(current), str(snapshot)],
        capture_output=True, text=True, check=False,
    )
    out = result.stdout
    assert "a_table_the_script_never_heard_of" in out, (
        "将来新加的表被静默抹掉——这正是手写清单会犯的错"
    )
    for table in RuntimeStore.IDENTITY_TABLES:
        assert table in out, f"--verify 没有提到 {table} 会被抹掉"
