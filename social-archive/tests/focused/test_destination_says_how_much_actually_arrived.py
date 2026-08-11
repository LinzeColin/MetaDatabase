"""「连上了」不等于「收到了」（v0.0.0.7 / INV-NO-SILENT-ZERO）。

2026-08-04 生产实测：

    destination_state:  github    connected  「最近一次自动导入成功。」
                        obsidian  connected  「最近一次自动导入成功。」
    destination_receipt: github done 1 / obsidian done 1
    content:            193 条

默认导出集是 `["social_archive", "markdown"]`——扩展的 DEFAULT_CONFIG
与 account_sync 两处都是。所以那两个目的地从来就没有自动收到过东西。

界面说「连接成功、自动导入」，实际是 1/193。**这不是谎，是没说全。**
把「收到了多少条」摆出来，比任何措辞都直接。
"""

from social_archive.destinations import DestinationRegistry


def test_every_destination_reports_how_much_arrived(settings, store) -> None:
    views = DestinationRegistry(settings, store).views()
    assert views, "一个目的地都没有"
    for view in views:
        assert "exported_count" in view, f"{view['destination_id']} 不报「收到了多少条」"
        assert "content_total" in view, f"{view['destination_id']} 不报「一共多少条」"
        assert view["coverage_zh"], f"{view['destination_id']} 没有一句中文说明覆盖情况"


def test_the_canonical_store_is_not_counted_by_receipts(settings, store) -> None:
    """主保存链路没有导出回执——它就是库本身。按回执数报会永远是 0。"""
    view = next(v for v in DestinationRegistry(settings, store).views()
                if v["destination_id"] == "social_archive")
    assert view["exported_count"] == view["content_total"]
    assert "主保存链路" in view["coverage_zh"]


def test_a_connected_destination_with_nothing_in_it_says_so(settings, store, service) -> None:
    """这条正是生产上 github / obsidian 的形状：连着，却几乎什么都没收到。

    **必须先往库里放真东西。** 第一版在空库上测，total 和 exported 都是 0，
    于是把 `exported = coverage.get(...)` 改成 `exported = total` 也照样绿——
    判据没有区分能力。反证跑不红的判据等于没有。
    """
    from social_archive.models import CaptureRequest

    for index in range(3):
        service.capture(CaptureRequest(
            platform="generic-web",
            url=f"https://example.com/a{index}",
            relation_type="manual_save",
            requested_levels=["L0"],
            destination_ids=["social_archive"],
        ))
    # 只给 markdown 记一条成功回执，github 一条都不给
    with store.connection() as con:
        content_id = con.execute("SELECT id FROM content LIMIT 1").fetchone()["id"]
    store.record_destination_receipt(
        destination_id="markdown", content_id=content_id, status="done",
        projection_sha256="0" * 64, attempted_at="2026-08-04T00:00:00Z",
        message_zh="导入完成。",
    )

    views = {v["destination_id"]: v for v in DestinationRegistry(settings, store).views()}
    assert views["markdown"]["content_total"] == 3
    assert views["markdown"]["exported_count"] == 1, "收到了 1 条却没这么报"
    assert views["github"]["exported_count"] == 0, (
        "github 一条回执都没有，却报了收到过内容——覆盖率不是从回执数来的"
    )
    assert "1 / 3" in views["markdown"]["coverage_zh"]
    assert "0 / 3" in views["github"]["coverage_zh"]


def test_both_uis_actually_show_the_coverage() -> None:
    """**加了字段没人读，等于没加。**

    2026-08-05：我给目的地视图加了 exported_count / coverage_zh，
    一小时后去查——**两个界面一个都没读它**。这正是这一整天在清的
    「建好了没接上」，而这一次是我自己刚犯的。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    for rel in ("apps/pwa/app.js", "apps/browser-extension/options.js"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "coverage_zh" in text, f"{rel} 不显示「已送到这里 N / M 条」"


def test_the_coverage_line_sits_with_the_destination_card() -> None:
    """显示在那张卡片里，不是塞在别处——否则用户看不到它挨着哪个目的地。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    pwa = (root / "apps/pwa/app.js").read_text(encoding="utf-8")
    card = pwa.split("destination-live-card", 1)[1][:1200]
    assert "coverage_zh" in card, "覆盖率那一行不在目的地卡片里"
