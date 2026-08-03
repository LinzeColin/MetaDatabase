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
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rollback_0007.sh"


def _pre_v0007_snapshot(path: Path) -> None:
    """用 origin/main 的 schema 造一个 v0.0.0.7 之前的快照。"""
    schema = subprocess.run(
        ["git", "show", "origin/main:social-archive/src/social_archive/sql/runtime_schema.sql"],
        cwd=ROOT, capture_output=True, text=True, check=True,
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


def test_the_new_table_list_matches_what_the_schema_actually_adds() -> None:
    """脚本里那份 V0007_TABLES 不能和 schema 漂开。

    漂开的方式很隐蔽：以后再加一张带 user_id 的表，忘了加进这里，
    回滚就又会静默抹掉它——和这次 platform_credential 一模一样。
    """
    from social_archive.db import RuntimeStore

    listed = set(
        SCRIPT.read_text(encoding="utf-8")
        .split('V0007_TABLES="', 1)[1].split('"', 1)[0].split()
    )
    # 审计面里的身份类表必须全部被回滚脚本认识
    assert set(RuntimeStore.IDENTITY_TABLES) <= listed, (
        f"这些表回滚脚本不认识，会被静默抹掉：{set(RuntimeStore.IDENTITY_TABLES) - listed}"
    )
    assert "users" in listed, "users 表也是 v0.0.0.7 新增的"
