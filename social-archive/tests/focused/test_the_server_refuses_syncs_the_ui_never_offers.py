r"""界面不发的同步请求，服务端也不许接受（2026-08-10）。

## 它补的是一个只差一步的洞

Owner 要的是**全平台**。逐平台量下来，修完同步范围之后：

    抖音/B站/小红书/快手 → 收藏      会跑完
    Reddit / Instagram   → 已保存    会跑完
    Chrome 书签          → 书签      会跑完
    X                    → 走服务端授权那条路，不是扩展
    YouTube              → ['watch_later','playlist']   ← 扩展一条都不会扫

**扩展里没有 YouTube 的取数路**（`INTERCEPT_PREFIXES` 只有
bilibili / xiaohongshu / douyin）。要是真起了这么一次 run，
那两档永远等不到终批 —— 和他抖音那二十次「点了同步，圈一直转」一模一样。

## ★ 界面这一侧本来就是对的，我一开始判错了

我读了 `options.js` 的 `platformOrder` 和写死的 `relationCopy`，
就断言「YouTube 是一个按了会转到死的按钮」。**不对**：
服务端早把它排在 `SYNCABLE_NOW` 之外、`NOT_SYNCABLE_YET` 里写着原因，
界面据此收起同步按钮、并把那句原因显示出来。**卡片是诚实的。**

真正缺的是**服务端这一侧**：它仍然会按 `PLATFORM_RELATIONS`
下发一个扫不动的范围。界面替服务端守住了不变量 ——
而**不变量不能靠界面守**（换个客户端、或者直接打 API 就绕过去了）。

修法：把 YouTube 在 `SCANNABLE_RELATIONS` 里登记成**空**，
`start_sync` 走现成的拒绝路径当场报出来，
话直接取 `NOT_SYNCABLE_YET` 里那一句 —— 同一件事不写两遍。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from social_archive.account_sync import (  # noqa: E402
    NOT_SYNCABLE_YET,
    SCANNABLE_RELATIONS,
    SYNCABLE_NOW,
    AccountSyncCoordinator,
)
from social_archive.models import AccountSyncRequest  # noqa: E402


def _connect(store, platform: str) -> str:
    return store.upsert_source_account(
        platform=platform, external_account_id="owner", display_name=platform,
        auth_method="browser_session", auth_handle_ref=f"ext_{platform}",
        connection_state="connected")


def test_there_is_something_to_check() -> None:
    """反空扫：一个「不能同步」的平台都没有的话，下面那条会白过。"""
    assert NOT_SYNCABLE_YET, "NOT_SYNCABLE_YET 空了——这条判据在空扫"


@pytest.mark.parametrize("platform", sorted(NOT_SYNCABLE_YET))
def test_a_platform_the_ui_will_not_sync_is_refused_by_the_server_too(
        platform: str, settings, store, service) -> None:
    """**不变量不能靠界面守。**

    界面收起了按钮，不代表服务端可以接受这个请求：换个客户端、
    或者直接打 `/v1/accounts/{id}/sync`，就绕过去了。
    """
    assert platform not in SYNCABLE_NOW, f"{platform} 同时在两张表里，先把表理清"
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    scope = AccountSyncCoordinator._scannable_relations(platform)
    if scope:
        # 走服务端连接器那条路的（x）：不经扩展，范围由连接器自己收敛，
        # 这条判据不管它——但要说清楚，别让它悄悄落进「反正没红」。
        assert platform == "x", (
            f"{platform} 界面上不给同步，服务端却仍会下发范围 {scope}——"
            "扩展不会去扫，那次 run 永远等不到终批（圈一直转）。\n"
            "在 platform-catalog.js 的 SCANNABLE_RELATIONS 里把它登记成 "
            "Object.freeze([])，start_sync 就会当场拒绝。")
        return
    with pytest.raises(ValueError) as caught:
        coordinator.start_sync(_connect(store, platform),
                               AccountSyncRequest(mode="first_full", trigger_type="first_connect"))
    assert str(caught.value) == NOT_SYNCABLE_YET[platform], (
        "拒绝了，但说的话和界面上那句不一样——同一件事两处措辞必然漂开：\n"
        f"  服务端：{caught.value}\n  界面：{NOT_SYNCABLE_YET[platform]}")


def test_youtube_is_registered_as_scanning_nothing() -> None:
    """**空不是占位符，是一句准话：这一版读不到。**

    没登记（`None`）和登记成空（`()`）在服务端是两种行为：
    前者退回「把允许的全列进去」，正是那个不收敛的老写法。
    """
    assert SCANNABLE_RELATIONS.get("youtube") == (), (
        "youtube 没有在 SCANNABLE_RELATIONS 里登记成空——"
        f"现在是 {SCANNABLE_RELATIONS.get('youtube')!r}，"
        "服务端会退回「把允许的关系全列进去」，那次 run 就永远不收敛")


def test_the_platforms_he_can_sync_all_still_work(settings, store, service) -> None:
    """**反向也要绿。** 只堵住一个平台却把别的一起堵了，判据不会告诉你。"""
    coordinator = AccountSyncCoordinator(settings, store, service, registry=None)  # type: ignore[arg-type]
    for platform in sorted(SYNCABLE_NOW):
        scope = AccountSyncCoordinator._scannable_relations(platform)
        assert scope, f"{platform} 在「现在就能同步」表里，范围却是空的"
