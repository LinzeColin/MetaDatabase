"""覆盖有缺口时，「下一步」不许说一切正常（v0.0.0.7 / T11）。

## 抓到它的那次实测

2026-08-05 在生产上把八个目的地的视图逐个打出来看，Owner 会读到的是：

    Obsidian     已送到 1 / 193 条     下一步：最近一次自动导入成功。
    ArchiveBox   已送到 0 / 193 条     下一步：连接检查通过，可以自动导入。

**两句下一步单独看都是真的**——最近那一次确实成功、连接确实通过。
而它们合起来把「192 条从来没到过这里」说成了「一切正常」。

2026-08-04 已经修过一次这个地方：那次让 `coverage_zh` 照实说
「已送到 1 / 193 条」。**数字诚实了，下一步没动。**
他没有技术背景，读到「导入成功」就不会再往下想那个 1。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.destinations import DestinationRegistry, DestinationView  # noqa: E402

SOURCE = (ROOT / "src/social_archive/destinations.py").read_text(encoding="utf-8")


def _view(**kwargs) -> dict:
    base = dict(
        destination_id="obsidian", display_name="Obsidian", state="connected",
        enabled=True, configured=True, authorized=True, automatic=True,
        next_action_zh="最近一次自动导入成功。", privacy_note_zh="",
        exported_count=1, content_total=193,
    )
    base.update(kwargs)
    return DestinationView(**base).as_dict()


def test_the_number_itself_is_still_told_straight() -> None:
    """2026-08-04 修好的那一半不许退回去。"""
    assert "已送到这里 1 / 193 条" in _view()["coverage_zh"]


def test_a_gap_is_named_in_the_next_step(settings, store, service) -> None:
    """**下一步必须提到那个差额**，而不是只说最近一次成功。

    真跑 views()，不 grep 源码：造 3 条内容、只给 markdown 记 1 条成功回执，
    于是 markdown 是 1/3——正是生产上 obsidian 的形状。
    """
    from social_archive.models import CaptureRequest

    for index in range(3):
        service.capture(CaptureRequest(
            platform="generic-web", url=f"https://example.com/gap{index}",
            relation_type="manual_save", requested_levels=["L0"],
            destination_ids=["social_archive"],
        ))
    with store.connection() as con:
        content_id = con.execute("SELECT id FROM content LIMIT 1").fetchone()["id"]
    store.record_destination_receipt(
        destination_id="markdown", content_id=content_id, status="done",
        projection_sha256="0" * 64, attempted_at="2026-08-05T00:00:00Z",
        message_zh="导入完成。",
    )

    # **必须先让它「已授权」。** 没授权的目的地要先说「怎么连上」，
    # 那时提覆盖差额是把顺序说反了——这一条正是这个判据第一次跑出来教我的：
    # 它红在「markdown 还没授权」，而不是红在差额没报。
    registry = DestinationRegistry(settings, store)
    assert registry.probe("markdown")["authorized"] is True, "探针没把 markdown 标成已授权"

    views = {v["destination_id"]: v for v in registry.views()}
    markdown = views["markdown"]
    assert markdown["exported_count"] == 1 and markdown["content_total"] == 3
    assert "还有 2 条从来没送到这里" in markdown["next_action_zh"], (
        "覆盖 1/3，而下一步只字不提那 2 条：" + markdown["next_action_zh"]
    )
    # 主保存链路是满的，不该被这条提示打扰。
    assert "从来没送到这里" not in views["social_archive"]["next_action_zh"]


def test_it_says_why_the_gap_exists_not_just_that_it_does() -> None:
    """**差额不是错误，是投递只在新内容进来时发生。**

    只报「少了 192 条」会让人以为坏了，然后去查一个没坏的东西。
    """
    assert "自动投递只在新内容进来时发生" in SOURCE
    assert "先前入库的不会自己追上去" in SOURCE


def test_it_gives_the_command_that_actually_fixes_it() -> None:
    """说了差额还得说怎么补——**而且是那条真能跑的命令**。

    在主机上跑会报 RUN_ME_INSIDE_THE_CONTAINER（密钥路径是容器里的挂载点），
    所以这里给的必须是 `docker compose exec` 那一条。
    """
    assert "backfill_destination.py" in SOURCE
    assert "docker compose exec core-api" in SOURCE, (
        "给的命令在主机上跑不通——那等于没给"
    )
    assert (ROOT / "scripts/backfill_destination.py").exists(), "那个脚本不在"


def test_a_full_destination_keeps_its_ordinary_next_step() -> None:
    """**满覆盖的不许被打扰。** 否则这条提示会变成人人都有的噪音。"""
    assert "authorized and total and exported < total" in SOURCE, (
        "条件不对：可能对满覆盖的目的地也报差额"
    )


def test_the_main_path_is_excluded() -> None:
    """主保存链路（social_archive）按定义就是全量，不该出现这条提示。"""
    assert 'destination_id != "social_archive"' in SOURCE


def test_an_unauthorized_destination_is_not_nagged_about_coverage() -> None:
    """还没授权的（Notion / Karakeep / Linkwarden）要先说「怎么连上」。

    对一个还没连上的目的地说「还有 193 条没送到」，是把顺序说反了。
    """
    assert "authorized and total" in SOURCE, "没授权的也会被报差额"
