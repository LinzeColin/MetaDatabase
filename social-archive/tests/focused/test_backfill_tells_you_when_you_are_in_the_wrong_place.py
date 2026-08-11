"""补投脚本要分清「没授权」和「跑错地方」（v0.0.0.7 / T11）。

2026-08-05 实测：在**主机上**跑，github 报「这个目的地还没有一次成功的写入
授权」——而在**容器里**跑，同一个判定是 True。原因是 .env 里的
SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE 指着 /run/secrets/github_token，那是容器里
的挂载点，主机上不存在；read_secret 读不到就当成没配。

**这两件事的下一步完全相反**：一个是「去连接向导里完成一次写入」，
另一个是「换个地方跑」。把后者报成前者，会让人去改一个没坏的东西。

这已经是同一个坑今天第四次绊人（恢复脚本、运维手册那条命令、主机上的
判定探针，然后是它）。
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/backfill_destination.py"


def test_it_separates_wrong_place_from_not_authorized() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "RUN_ME_INSIDE_THE_CONTAINER" in source, (
        "主机上跑会被报成「没授权」——那会让人去改一个没坏的东西"
    )
    assert "DESTINATION_NOT_AUTHORIZED" in source, "真没授权那条路不能丢"
    assert source.index("RUN_ME_INSIDE_THE_CONTAINER") < source.index('"status": "REFUSED", "error_code": "DESTINATION_NOT_AUTHORIZED"'), (
        "先判「跑错地方」再判「没授权」——顺序反了就永远报成没授权"
    )
    assert "/run/secrets/" in source, "没有去看那些只在容器里存在的路径"


def test_it_looks_but_does_not_touch_by_default() -> None:
    """补投会往 Owner 的 GitHub / Obsidian 里写 192 条东西。

    **默认必须只看不动**，而且要说清「入队不等于送到」。
    """
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--apply", action="store_true"' in source, "没有 --apply 开关，默认就会写"
    assert "只看了，什么都没动" in source, "只看那条路没说清它什么都没做"
    assert "入队不等于送到" in source, (
        "入队之后就说完了——而作业还要 worker 逐条跑，跑完再看覆盖数才算数"
    )


def test_it_reuses_the_same_job_as_a_single_export() -> None:
    """不另开一条只有补投才走的路——那种路最容易和主路分叉。"""
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"export_destination"' in source, "补投用的不是单条导出那个作业类型"
    service = (ROOT / "src/social_archive/service.py").read_text(encoding="utf-8")
    assert '"export_destination", {"content_id": content_id, "destination_id": destination' in service, (
        "主路的作业形状变了，补投那边要跟着改"
    )
