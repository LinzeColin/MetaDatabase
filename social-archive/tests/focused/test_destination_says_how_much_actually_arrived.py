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


def test_a_connected_destination_with_nothing_in_it_says_so(settings, store) -> None:
    """这条正是生产上 github / obsidian 的形状：连着，却几乎什么都没收到。"""
    view = next(v for v in DestinationRegistry(settings, store).views()
                if v["destination_id"] == "github")
    assert view["exported_count"] == 0
    assert "0 /" in view["coverage_zh"] or "库里还没有内容" in view["coverage_zh"]
