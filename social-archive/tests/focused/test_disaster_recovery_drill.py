"""两个演练各自 PASS，仍然可能拼不成一个档案馆（v0.0.0.7 / T16）。

    restore_object.py            一个制品能不能取回来
    restore_runtime_db_drill.py  索引能不能取回来并打开
    **disaster_recovery_drill.py** 两样合起来对不对得上

索引里记着 552 个制品，而对象仓里少了 3 个——前两个演练都不会发现。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRILL = ROOT / "scripts/disaster_recovery_drill.py"


def _code() -> str:
    return "\n".join(
        l for l in DRILL.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#")
    )


def test_it_reads_the_restored_index_not_the_live_one() -> None:
    """**这是整个演练的要害。** 拿生产库当清单，等于假设生产库还在——
    而这正是灾难恢复要假设它不在。
    """
    code = _code()
    assert '"--runtime-db", str(restored_db)' in code, (
        "逐个取制品时用的不是取回来的那份索引——那就不是灾难恢复演练"
    )
    assert 'SELECT id FROM artifact' in code
    listing = code.split("SELECT id FROM artifact", 1)[0][-400:]
    assert "restored_db" in listing, "制品清单不是从取回来的索引里读的"


def test_it_refuses_to_write_into_the_live_data_plane() -> None:
    assert "RECOVERY_TARGET_INVALID" in _code()


def test_an_index_that_restores_to_nothing_is_a_failure() -> None:
    """本项目栽过这个坑：报成功而文件不在（PrivateTmp 那次）。"""
    code = _code()
    assert "INDEX_RESTORE_EMPTY" in code
    assert "报成功，而文件不在" in DRILL.read_text(encoding="utf-8")


def test_it_fails_when_any_artifact_cannot_be_recovered() -> None:
    """少一个就不算通过——「大部分能恢复」不是恢复。"""
    code = _code()
    assert 'recovered == len(artifact_ids)' in code
    assert "return 0 if recovered == len(artifact_ids) else 4" in code


def test_it_does_not_reimplement_the_two_existing_drills() -> None:
    code = _code()
    assert "restore_runtime_db_drill.py" in code and "restore_object.py" in code, (
        "又写了一套取回逻辑——三份必然漂开"
    )
