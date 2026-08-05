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
    # **界面渲染的是 last_message_zh || next_action_zh**，前者优先。
    # 只写后一个字段的话，这句话永远轮不到显示——第一版就是那样，写完即隐形。
    assert "还有 2 条从来没送到这里" in (markdown["last_message_zh"] or ""), (
        "界面先读 last_message_zh，而那里没有差额——这句话不会被显示出来："
        + str(markdown["last_message_zh"])
    )
    # 主保存链路是满的，不该被这条提示打扰。
    assert "从来没送到这里" not in views["social_archive"]["next_action_zh"]
    assert "从来没送到这里" not in (views["social_archive"]["last_message_zh"] or "")


def test_both_uis_read_the_field_the_gap_is_written_into() -> None:
    """**两个界面渲染的都是 `last_message_zh || next_action_zh`。**

    这条判据钉的是那个优先级：只要界面还先读 last_message_zh，
    服务端就必须把差额写进那个字段，否则这句话写了也白写。
    界面哪天改成只读 next_action_zh，这条会红——那时该回来重看这段逻辑。
    """
    for name in ("apps/pwa/app.js", "apps/browser-extension/options.js"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "last_message_zh" in source and "next_action_zh" in source, (
            f"{name} 不再同时读这两个字段了——服务端那段「两个字段都写」要重看"
        )


def test_it_says_why_the_gap_exists_not_just_that_it_does() -> None:
    """**差额不是错误，是投递只在新内容进来时发生。**

    只报「少了 192 条」会让人以为坏了，然后去查一个没坏的东西。
    """
    assert "自动投递只在新内容进来时发生" in SOURCE
    assert "先前入库的不会自己追上去" in SOURCE


def test_it_points_at_the_button_before_the_command(settings, store, service) -> None:
    """**他点得到的那颗按钮排在命令前面。**

    第一版只给了 `docker compose exec …`。而档案馆页面上早就有一颗
    「把没送过去的 N 条补上」，出现条件和服务端这段判断**一模一样**
    （missing > 0 且 connected）。对一个说自己没有技术基础的人，
    让他去 ssh 一台服务器、而同一张卡片上就摆着那颗按钮——
    **那不是帮忙，是把他支开。**
    """
    app = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    # 服务端那句话里点名的按钮，界面上必须真有这个词。
    assert "把没送过去的" in app, "档案馆页面上没有这颗按钮了"
    # **顺序要在生成出来的那句话里量，不能在源码里量。**
    # 第一版用 SOURCE.index 比位置，结果量到的是我写在代码上面那段注释里的
    # 「docker compose exec」——**判据钉在注释上**，今天第六次。
    from social_archive.models import CaptureRequest

    for index in range(2):
        service.capture(CaptureRequest(
            platform="generic-web", url=f"https://example.com/order{index}",
            relation_type="manual_save", requested_levels=["L0"],
            destination_ids=["social_archive"]))
    registry = DestinationRegistry(settings, store)
    registry.probe("markdown")
    view = next(v for v in registry.views() if v["destination_id"] == "markdown")
    message = str(view["last_message_zh"] or "")
    assert "把没送过去的" in message, f"那句话没点名他点得到的按钮：{message}"
    assert "docker compose exec core-api" in message, "在主机上跑不通的命令等于没给"
    assert message.index("把没送过去的") < message.index("docker compose exec"), (
        "命令排在按钮前面——他会先看到那条要 ssh 的：" + message
    )
    assert (ROOT / "scripts/backfill_destination.py").exists(), "那个脚本不在"
    assert "backfill" not in (ROOT / "apps/browser-extension/options.js").read_text(
        encoding="utf-8"), (
        "扩展设置页现在也有补送按钮了——那句话该把它也说上"
    )


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


def test_the_privacy_note_is_actually_shown_somewhere() -> None:
    """**写了八条隐私说明，一条都没露过面。**

    2026-08-05 数了一遍服务端产出的中文文案字段：六个里就 privacy_note_zh
    一个没有任何界面读。而这偏偏是他最该看懂的一段——他的东西去了哪儿。

    「建好了没接上」这次落在隐私说明上。
    """
    for name in ("apps/pwa/app.js", "apps/browser-extension/options.js"):
        source = (ROOT / name).read_text(encoding="utf-8")
        assert "privacy_note_zh" in source, f"{name} 不显示隐私说明——那八条写了没人看"


def test_the_privacy_note_is_written_for_him_not_for_us() -> None:
    """**Owner 说过他没有技术基础，让他读这些词等于让他读我们的代码。**

    原来那八条是给工程师看的：「REST 令牌只从 0600 Secret 读取」、
    「Integration Token 不返回扩展」、「L3 对象走加密副本」。
    技术细节没有丢，只是搬到 docs/ 与代码注释里——那才是它们该待的地方。
    """
    import inspect

    from social_archive.destinations import DestinationRegistry

    body = inspect.getsource(DestinationRegistry._privacy_note)
    # 只看 return 的那张表，不看上面的说明（说明里正是在引用这些词）。
    table = body.split("return {", 1)[1]
    for jargon in ("0600", "Secret", "Token", "REST", "L3", "Git 树", "投影"):
        assert jargon not in table, f"隐私说明里还有让他读代码的词：{jargon!r}"
    # 而且每一条都要真说了点什么
    registry_notes = [line for line in table.splitlines() if '":' in line]
    assert len(registry_notes) >= 8, f"隐私说明少了几条：{len(registry_notes)}"


def test_the_privacy_note_class_actually_has_a_style() -> None:
    """引一个不存在的 class，等于给自己留一个「以为它长这样」的错觉。

    第一版给隐私说明加了 `class="muted privacy-note"`，而 styles.css 里
    压根没有 `.privacy-note`——它照样渲染（靠 muted），但那个类名什么都没做。
    **不做事的类名比没有类名更坏**：下次有人以为改它就能改样式。
    """
    app = (ROOT / "apps/pwa/app.js").read_text(encoding="utf-8")
    styles = (ROOT / "apps/pwa/styles.css").read_text(encoding="utf-8")
    if "privacy-note" in app:
        assert ".privacy-note" in styles, "app.js 用了 privacy-note，样式表里没有它"
