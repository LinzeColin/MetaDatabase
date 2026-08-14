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


# ——— 「这次和上次一样吗」要判得准，两半都必须确定 ———


def test_vacuum_into_is_deterministic_for_an_unchanged_database(tmp_path: Path) -> None:
    """变更检测的前提。构造里特意留了 freelist（删过几行）。"""
    import hashlib

    source = tmp_path / "live.sqlite3"
    con = sqlite3.connect(source)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE content(id TEXT PRIMARY KEY, title TEXT)")
    con.executemany("INSERT INTO content VALUES(?,?)", [(f"c{i}", f"t{i}") for i in range(500)])
    con.execute("DELETE FROM content WHERE id IN ('c1','c2','c3')")
    con.commit()
    module = _module()
    hashes = {
        hashlib.sha256(module.snapshot_database(source, tmp_path / f"s{n}.sqlite3").read_bytes()).hexdigest()
        for n in range(3)
    }
    con.close()
    assert len(hashes) == 1, "同一个库连做三次 VACUUM INTO 结果不一致，变更检测就没有依据"


def test_the_gzip_header_does_not_leak_time_or_filename(tmp_path: Path) -> None:
    """**只置 mtime=0 还不够。**

    GzipFile 拿到 fileobj 时会从 `fileobj.name` 推出一个文件名写进头部。
    实测：同样的内容写进 a.gz 与 b.gz，哈希 7bddc5ee… vs a5b42f87…，
    **不一致**；显式 filename="" 之后两次都是 fc32ac2f…。
    """
    import hashlib

    module = _module()
    source = tmp_path / "payload"
    source.write_bytes(b"hello" * 10000)
    first = module._gzip(source, tmp_path / "first-name.gz")
    second = module._gzip(source, tmp_path / "a-totally-different-name.gz")
    assert hashlib.sha256(first.read_bytes()).hexdigest() == hashlib.sha256(second.read_bytes()).hexdigest(), (
        "压出来的字节跟着文件名/时间变——「这次和上次一样吗」就判不准了"
    )


def test_unchanged_runs_do_not_upload_again() -> None:
    code = "\n".join(
        l for l in (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8").splitlines()
        if not l.lstrip().startswith("#")
    )
    assert "--skip-if-unchanged" in code, "没法跟着复制定时器跑"
    assert "RUNTIME_DB_UNCHANGED" in code
    skip_at = code.index("RUNTIME_DB_UNCHANGED")
    # **锚在真正的调用上，不是文件顶部的 import。** 第一版钉在 "_upload_and_verify"
    # 上，而那个名字在第 56 行的 import 里就出现了，于是判据永远说「先传后判」。
    upload_at = code.index('receipts["r2"] = _upload_and_verify')
    assert skip_at < upload_at, "先传了再判断，等于没省"


def test_the_index_keeps_up_with_the_artifacts() -> None:
    """制品每 ~15 分钟复制一次，索引原来一天才备一次。

    机器在这两者之间没了，就会留下一批**有制品、没索引行**的孤儿密文
    ——救回来也不知道是什么。
    """
    unit = (ROOT / "deploy/systemd/social-archive-replication.service").read_text(encoding="utf-8")
    lines = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
    matched = [l for l in lines if "backup_runtime_db.py" in l]
    assert matched, "复制单元不带索引快照——索引仍然落后制品一整天"
    assert all("--skip-if-unchanged" in l for l in matched), (
        "每 15 分钟无条件传一次 1MB，一年就是 35GB——必须只在库变了时才传"
    )
    # 每天那一次仍然要留着：它是兜底，且不受 --skip-if-unchanged 影响
    daily = (ROOT / "deploy/systemd/social-archive-backup.service").read_text(encoding="utf-8")
    assert "backup_runtime_db.py" in daily, "每天那一次兜底被拿掉了"


def test_the_index_can_have_the_same_three_copies_as_the_artifacts() -> None:
    """制品有三份副本，索引原来只有两份。**同一件事该有同一个标准。**

    尤其索引比制品更要紧：制品丢一个是丢一条内容，索引丢了是 552 个
    都说不出是什么。
    """
    code = "\n".join(
        l for l in (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8").splitlines()
        if not l.lstrip().startswith("#")
    )
    assert "--github" in code, "索引没有第三份副本的路"
    assert "verify_draft_release" in code, "没有确认那个 release 真的是 Draft"
    assert "GitHub Draft Release 回读哈希不一致" in code, "上传了却不回读比对"
    # 复用，不抄第二遍
    assert "from github_release_backup import" in code, (
        "自己又写了一套 Draft Release 逻辑——两份必然漂开"
    )


def test_the_third_copy_is_not_attempted_before_the_first_is_verified() -> None:
    """和 R2→OCI 同一条规矩：前一份没验成就不往下走。"""
    code = "\n".join(
        l for l in (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8").splitlines()
        if not l.lstrip().startswith("#")
    )
    assert 'if args.github and receipts.get("r2", {}).get("status") == "verified"' in code


def test_the_github_copy_uses_a_draft_release_in_a_private_repo() -> None:
    """草稿 + 私有仓：这两条是备份能放在 GitHub 上的前提。"""
    code = (ROOT / "scripts/backup_runtime_db.py").read_text(encoding="utf-8")
    assert "verify_private_repository" in code, "没有确认那是私有仓"
    assert '"--draft"' in code, "建的不是 Draft Release"


def test_only_the_daily_run_pushes_a_third_copy() -> None:
    """Draft Release 每刻钟建一个会把仓刷爆，而且没必要——
    前两份已经跟上了节奏，第三份每天补一次即可。"""
    daily = (ROOT / "deploy/systemd/social-archive-backup.service").read_text(encoding="utf-8")
    frequent = (ROOT / "deploy/systemd/social-archive-replication.service").read_text(encoding="utf-8")
    daily_lines = [l for l in daily.splitlines() if l.startswith("ExecStart=") and "backup_runtime_db" in l]
    frequent_lines = [l for l in frequent.splitlines() if l.startswith("ExecStart=") and "backup_runtime_db" in l]
    assert daily_lines and all("--github" in l for l in daily_lines), "每天那一次没补第三份"
    assert frequent_lines and not any("--github" in l for l in frequent_lines), (
        "每刻钟都去建 Draft Release——会把私有仓刷爆"
    )


def test_the_drill_can_also_pull_from_github() -> None:
    """**第三份副本不能只验到密文层。**

    「登记成 verified」和「取得回来」是两件事——这一天已经因为这个区别
    撞过两次：GitHub 制品取回路的两个致命缺陷、恢复报 target_written
    而目录是空的。
    """
    code = "\n".join(
        l for l in DRILL.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")
    )
    assert '"r2", "oci", "github"' in code, "drill 取不了 GitHub 那一份"
    assert "verify_draft_release" in code, "没有确认那个 release 真的是 Draft"
    assert "verify_private_repository" in code, "没有确认那是私有仓"
    assert "from github_release_backup import" in code, "又写了一套 gh 调用——两份必然漂开"
    # 取回来之后仍然要走完整链
    for step in ("--decrypt", "gzip.open", "sqlite3.connect", "PLAINTEXT_SHA256_MISMATCH"):
        assert step in code, f"GitHub 那条路没走完整链：缺 {step}"


def test_the_durability_report_shows_the_index_too() -> None:
    """那份对外的耐久性报告，不能只报制品。

    2026-08-04 之前它写着 `all_three_verified: 549 / pending: 0 / PASS`
    ——**每个字都是真的**，而当时运行库索引全世界只有一份：
    552 个加密块躺在三个云上，没有任何东西说得出它们分别是什么。

    「制品都齐了」被当成了「档案馆安全了」。差别不在数字对不对，
    **在于没显示的那一格**。
    """
    code = "\n".join(
        l for l in (ROOT / "scripts/replicate_objects.py").read_text(encoding="utf-8").splitlines()
        if not l.lstrip().startswith("#")
    )
    assert 'report["index_backup"]' in code, "耐久性报告里没有索引这一格"
    assert "_index_backup_status" in code
    # 没备过就必须显式说出来，而不是缺字段
    helper = code.split("def _index_backup_status", 1)[1]
    assert '"MISSING"' in helper, "从未备份过时不报 MISSING——那会变成一格空白，看不出来"
    assert "verified_remote_copies" in helper


def test_the_index_status_is_read_not_recomputed() -> None:
    """这份报告是复制任务顺手带出来的，不该在这里再跑一遍备份。"""
    helper = (ROOT / "scripts/replicate_objects.py").read_text(encoding="utf-8").split(
        "def _index_backup_status", 1)[1].split("\n\n\n", 1)[0]
    for forbidden in ("upload", "boto3", "subprocess", "VACUUM"):
        assert forbidden not in helper, f"这一格里出现了 {forbidden} —— 它只该读 manifest"
