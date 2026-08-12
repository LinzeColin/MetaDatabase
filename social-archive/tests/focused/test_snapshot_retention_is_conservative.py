"""按 48 小时清快照，但**最新那份永远不删**（v0.0.0.7 / T16）。

Owner 2026-08-06 定了保留期 48 小时。`backup_runtime_db.py` 一直故意不删，
它的文件头写着「保留策略是运维决定……自动删除历史备份是那种『出事才发现』
的操作」——那句话是对的，而它等的决定现在有了。

删除不可逆，所以这里钉三条底线。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/prune_runtime_db_snapshots.py"


def _make(root: Path, names: list[str]) -> None:
    for name in names:
        (root / name).mkdir(parents=True)
        (root / name / "runtime.sqlite3.gz.age").write_bytes(b"x" * 1024)


def _run(root: Path, *extra: str) -> dict:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--now", "2026-08-06T12:00:00", *extra],
        capture_output=True, text=True)
    return json.loads(result.stdout)


def test_it_only_looks_unless_you_say_apply(tmp_path) -> None:
    """**默认只看不删。** 一个默认就删的脚本，跑错一次没有后悔药。"""
    _make(tmp_path, ["20260801T000000Z", "20260806T110000Z"])
    report = _run(tmp_path)
    assert report["applied"] is False
    assert report["would_remove"] == ["20260801T000000Z"]
    assert (tmp_path / "20260801T000000Z").is_dir(), "没给 --apply 却真删了"


def test_the_newest_is_never_removed_even_when_stale(tmp_path) -> None:
    """**最新那份永远不删**，哪怕它自己也超期了。

    否则一段时间没产出新快照，这个脚本会把最后一份也清掉——
    而那正是最需要它的时候。
    """
    _make(tmp_path, ["20260701T000000Z", "20260702T000000Z"])   # 两份都远超 48 小时
    report = _run(tmp_path, "--apply")
    assert report["removed"] == ["20260701T000000Z"]
    assert (tmp_path / "20260702T000000Z").is_dir(), "**把最后一份也删了**"
    assert report["newest_always_kept"] == "20260702T000000Z"


def test_names_it_cannot_read_are_left_alone(tmp_path) -> None:
    """**认不出就不动**，而且要说出来——不能默默跳过。"""
    _make(tmp_path, ["20260801T000000Z", "20260806T110000Z", "手工备份-别删"])
    report = _run(tmp_path, "--apply")
    assert "手工备份-别删" in report["unrecognised_left_alone"]
    assert (tmp_path / "手工备份-别删").is_dir()


def test_an_empty_or_renamed_directory_is_not_reported_as_clean(tmp_path) -> None:
    """**一份都认不出，不等于「已经清干净了」。**

    少了这条，目录改名之后它会一直报 PASS、什么都不删，而没人知道。
    """
    (tmp_path / "看不懂的名字").mkdir()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--apply"],
        capture_output=True, text=True)
    assert result.returncode != 0, "一份都认不出却报了成功"
    assert json.loads(result.stdout)["error_code"] == "NO_SNAPSHOTS_RECOGNISED"


def test_the_default_retention_is_the_one_the_owner_chose() -> None:
    """48 小时是他定的。改这个数要经过他，不是随手调。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert "DEFAULT_HOURS = 48" in source, "默认保留期被改了——那是 Owner 定的数"


def test_the_prune_runs_only_after_a_fresh_snapshot_succeeded() -> None:
    """**先做出新的，再清旧的。**

    `Type=oneshot` 的多条 `ExecStart` 按顺序执行、前一条失败就不往下走。
    所以清理必须排在产出**后面**——排前面的话，某天备份坏了而清理照跑，
    就会在最需要旧快照的那天把它们清掉。
    """
    unit = (Path(__file__).resolve().parents[2]
            / "deploy/systemd/social-archive-backup.service").read_text(encoding="utf-8")
    lines = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
    assert any("prune_runtime_db_snapshots.py" in l for l in lines), "备份单元里没人调清理脚本"
    produce = max(i for i, l in enumerate(lines) if "backup_runtime_db.py" in l)
    prune = min(i for i, l in enumerate(lines) if "prune_runtime_db_snapshots.py" in l)
    assert prune > produce, "**清理排在了产出前面**——备份失败的那天会连旧的一起没"
    assert any("--apply" in l for l in lines if "prune_runtime_db_snapshots.py" in l), (
        "接上了却没给 --apply——那它只会看不会删，等于没接"
    )
