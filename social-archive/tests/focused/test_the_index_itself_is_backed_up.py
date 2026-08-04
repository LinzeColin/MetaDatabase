"""给制品赋予意义的那张索引，不能只有一份（v0.0.0.7 / T16 / INV-REVERSIBLE）。

2026-08-04 实测生产：

    制品（内容字节）  552 个，每个三份已验证副本（R2 + OCI + GitHub）
    运行库 sqlite3    **4.59 MB，全世界只有一份**——就在那块盘上

对象仓里只有 `primary-objects/sha256/…` 和 GitHub 的 release 包，全是制品字节。
`social-archive-backup.service` 备份的是「私有库事实」，最近一次
`fact_count: 1`、1217 字节——**不是这个库**。

那块盘没了：三个云上躺着 552 个加密块，**而没有任何东西说得出它们分别是什么**。
标题、链接、关系、收藏时间、artifact→content 的对应、导出回执，全在这个 sqlite 里。
**制品还在，档案馆没了。**

T16 的标题一直是「549/549 制品三副本齐全」。那句话是真的，
而它从没提过：给这些制品赋予意义的那张索引，只有一份。
"""

import gzip
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module():
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location(
        "_backup_runtime_db", ROOT / "scripts/backup_runtime_db.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_backup_runtime_db"] = module
    spec.loader.exec_module(module)
    return module


def test_the_snapshot_is_consistent_and_readable(tmp_path: Path) -> None:
    """**不能用 cp。** 库跑在 WAL 模式，直接拷文件会拿到撕裂的中间态，
    而且 -wal 里尚未合并的事务不在那个文件里。"""
    source = tmp_path / "live.sqlite3"
    con = sqlite3.connect(source)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE content(id TEXT PRIMARY KEY, title TEXT)")
    con.executemany("INSERT INTO content VALUES(?,?)", [(f"cnt_{i}", f"标题{i}") for i in range(50)])
    con.commit()
    # 故意不 checkpoint：让数据留在 -wal 里，这正是 cp 会漏掉的部分
    target = _module().snapshot_database(source, tmp_path / "snap.sqlite3")
    con.close()

    restored = sqlite3.connect(f"file:{target}?mode=ro", uri=True)
    assert restored.execute("SELECT COUNT(*) FROM content").fetchone()[0] == 50, (
        "快照漏掉了还在 WAL 里的事务——这正是直接 cp 的毛病"
    )


def test_a_plain_copy_would_have_missed_it(tmp_path: Path) -> None:
    """把上一条的反面也钉住：证明「不能 cp」不是空话。"""
    import shutil

    source = tmp_path / "live.sqlite3"
    con = sqlite3.connect(source)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE content(id TEXT PRIMARY KEY)")
    con.executemany("INSERT INTO content VALUES(?)", [(f"cnt_{i}",) for i in range(50)])
    con.commit()
    copied = tmp_path / "copied.sqlite3"
    shutil.copyfile(source, copied)   # 只拷主文件，不拷 -wal
    con.close()

    naive = sqlite3.connect(f"file:{copied}?mode=ro", uri=True)
    try:
        rows = naive.execute("SELECT COUNT(*) FROM content").fetchone()[0]
    except sqlite3.DatabaseError:
        rows = -1
    assert rows != 50, "这一版 SQLite 下 cp 恰好也拿到了全部数据——判据失去意义，需要换构造"


def test_it_refuses_to_report_success_without_two_verified_copies() -> None:
    """「传上去了」不算数，「读回来一致」才算。"""
    source = (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
    assert "REQUIRED_VERIFIED_COPIES = 2" in code
    assert 'receipt.get("status") == "verified"' in code, "统计的不是已验证副本"
    assert "return 0 if verified >= REQUIRED_VERIFIED_COPIES else 4" in code, (
        "副本不够却仍然退 0——定时器会以为备份成功了"
    )


def test_the_second_store_is_not_attempted_when_the_first_failed() -> None:
    """第一份没验成就不往下走，免得两边都是坏的还各自报成功。"""
    source = (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8")
    assert "R2_BACKUP_NOT_VERIFIED" in source


def test_it_does_not_delete_old_snapshots() -> None:
    """保留策略是运维决定。自动删历史备份是那种「出事才发现」的操作。"""
    source = (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8")
    for destructive in ("shutil.rmtree", "unlink(", "os.remove"):
        # readback 的临时下载文件由 _upload_and_verify 自己清理，这个脚本里不该有删除
        assert destructive not in source.split('"""', 2)[2], f"脚本里出现了删除操作：{destructive}"


def test_the_backup_timer_actually_runs_it() -> None:
    """写了脚本没人跑，等于没写——本会话反复撞到的那种形状。"""
    unit = (ROOT / "deploy/systemd/social-archive-backup.service").read_text(encoding="utf-8")
    lines = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
    assert any("backup_runtime_db.py" in l for l in lines), (
        "备份单元不跑运行库快照——索引仍然只有一份"
    )
    assert any(l.endswith("backup.py --once") for l in lines), "原来那条私有库备份被挤掉了"


# ——— 取回演练：证明那份快照不只是「传上去了」，而是真的打得开 ———

DRILL = ROOT / "scripts/restore_runtime_db_drill.py"


def test_the_drill_goes_all_the_way_to_opening_the_database() -> None:
    """密文哈希一致只说明字节没坏，**不说明解密之后是一个能用的 SQLite**。

    这一天里已经吃过两次同形状的亏：三份副本全登记 verified 而 GitHub
    那条取回路根本跑不通；恢复报 target_written: true 而目标目录是空的。
    """
    code = "\n".join(
        l for l in DRILL.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")
    )
    for step in ("download_file", "age", "--decrypt", "gzip.open", "sqlite3.connect"):
        assert step in code, f"演练没走到这一步：{step}"
    assert "COMPARED_TABLES" in code, "打开了却不数表，等于只验了它是个文件"


def test_the_drill_refuses_to_write_into_the_live_data_plane() -> None:
    code = DRILL.read_text(encoding="utf-8")
    assert "RECOVERY_TARGET_INVALID" in code, "没有拦住落进运行数据面的目标"
    assert "settings.runtime_db.parent" in code, "没有把运行库所在目录算进保护范围"


def test_it_checks_both_the_ciphertext_and_the_plaintext_hash() -> None:
    """只比密文哈希不够：解密出来的东西也得对得上 manifest。"""
    code = DRILL.read_text(encoding="utf-8")
    assert "CIPHER_SHA256_MISMATCH" in code
    assert "PLAINTEXT_SHA256_MISMATCH" in code


def test_decrypt_failure_does_not_echo_stderr() -> None:
    """解密失败的输出里可能带密钥材料的片段。"""
    code = DRILL.read_text(encoding="utf-8")
    block = code.split("AGE_DECRYPT_FAILED", 1)[0][-400:]
    assert "completed.stderr" not in code.split("AGE_DECRYPT_FAILED", 1)[1][:200], (
        "把 age 的 stderr 回显出去了"
    )
    assert "不回显 stderr" in block, "没有写清为什么不回显——下一个人会顺手加回去"
