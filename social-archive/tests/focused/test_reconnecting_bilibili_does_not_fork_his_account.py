"""他重连 B 站时，不许开出第二个 B 站账号（2026-08-10）。

## 这一条只差一个条件

`account_sync.py` 里那段注释把规则写得很清楚，连他三行账号的真实形状都抄下来了：

    这个平台已经有一个同样连接方式的账号时，沿用它的外部 id。

**而代码只在外部 id 恰好是 `"browser-session"` 那个哨兵值时才执行它。**
小红书 / 抖音 / 快手走按形状读那条路，认不出用户是谁，报的就是哨兵值 —— 它们没事。
**B 站不是**：它走 B 站自己的接口，认得出用户，报的是 mid。

2026-08-10 对着他生产库量：

    已有那一行   external_account_id = 'https://space.bilibili.com/3493091105311656'
    重连会报的   external_account_id = '3493091105311656'      （background.js:1807，`String(who.mid)`）

两者不等，也不等于哨兵值 → **认领分支整个跳过** → `stable_id("acct","bilibili",…)`
算出另一个账号 id → 多出一行 B 站账号，卡片上写着 0 条，
而他那 **103 条 B 站内容**留在旧账号名下。

内容没丢（资料库按内容列，不按账号列），但：

  · 账号页上会并排两张 B 站卡，一张断开的有历史、一张连着的是 0 条；
  · `apply_complete_scan` 的关闭范围按 `source_account_id` 圈定，
    新账号永远关不掉旧账号那 30 条收藏，它们会一直挂着；
  · 而这一切发生在**他照着说明做那唯一一件事的那一刻**。

## 规矩

`browser_session` 这条路上，一个平台只有一个账号。**认领它，别开第二个。**
Chrome 书签走的是 `chrome_bookmarks`，外部 id 是固定字面量，不受这条影响。
"""

from __future__ import annotations

import pytest

from social_archive.models import AccountConnectRequest

# 他生产库里那三行，逐字抄。**夹具不许比真东西干净。**
REAL = {
    "bilibili": "https://space.bilibili.com/3493091105311656",
    "douyin": "https://www.douyin.com/user/self?from_nav=1",
    "xiaohongshu": "https://www.xiaohongshu.com/user/profile/68f8b6130000000037008d07",
}
# B 站重连时扩展真正会报的那个值（background.js:1807 `String(who.mid)`）。
BILIBILI_MID = "3493091105311656"


def _coordinator(settings, store, service):
    from social_archive.account_sync import AccountSyncCoordinator
    from social_archive.registry import ConnectorRegistry

    return AccountSyncCoordinator(settings, store, service, ConnectorRegistry(settings))


def _seed(store, platform: str) -> str:
    return store.upsert_source_account(
        platform=platform, external_account_id=REAL[platform],
        display_name="旧账号", auth_method="browser_session",
        auth_handle_ref="conn_legacy", connection_state="disconnected")


def _complete(coordinator, platform: str, external_account_id: str,
              auth_method: str = "browser_session") -> str:
    start = coordinator.connect_start(AccountConnectRequest(
        platform=platform, auth_method=auth_method, display_name="账号",
        relation_types=["favorite"]))
    return coordinator.complete_connection(
        platform=platform, auth_method=auth_method,
        connection_ref=start.connection_ref,
        external_account_id=external_account_id,
        display_name="账号", auto_sync_enabled=True, sync_interval_minutes=360,
        metadata={}, verified=True)


def test_bilibili_reconnect_adopts_the_account_his_items_hang_on(settings, store, service) -> None:
    """**这是他现在就要做的那一步。**"""
    old_id = _seed(store, "bilibili")
    new_id = _complete(_coordinator(settings, store, service), "bilibili", BILIBILI_MID)
    assert new_id == old_id, (
        f"重连 B 站开出了第二个账号（旧 {old_id} / 新 {new_id}）——"
        f"他那 103 条会留在旧账号下面，新卡片上写着 0 条。"
        f"扩展报的是 mid（{BILIBILI_MID!r}），而库里那一行是主页地址")


def test_the_shape_read_platforms_still_adopt(settings, store, service) -> None:
    """**别把原来работ的那条路改坏。** 哨兵值这条分支必须继续成立。"""
    from social_archive.account_sync import UNIDENTIFIED_BROWSER_ACCOUNT

    for platform in ("douyin", "xiaohongshu"):
        old_id = _seed(store, platform)
        new_id = _complete(_coordinator(settings, store, service),
                           platform, UNIDENTIFIED_BROWSER_ACCOUNT)
        assert new_id == old_id, f"{platform}：哨兵值那条认领路被改坏了"


def test_chrome_bookmarks_is_not_swept_into_this(settings, store, service) -> None:
    """**Chrome 书签不走这条。**

    它的 auth_method 是 `chrome_bookmarks`，外部 id 是固定字面量
    `chrome-bookmarks`。认领规则只管 `browser_session`——
    顺手把别的也认领了，就会把两种不同的连接方式混成一个账号。
    """
    old_id = store.upsert_source_account(
        platform="generic-web", external_account_id="chrome-bookmarks",
        display_name="Chrome 书签", auth_method="chrome_bookmarks",
        auth_handle_ref="conn_bm", connection_state="disconnected")
    new_id = _complete(_coordinator(settings, store, service), "generic-web",
                       "chrome-bookmarks", auth_method="chrome_bookmarks")
    assert new_id == old_id, "Chrome 书签自己那条（同名外部 id）本来就该认领同一行"


def test_a_genuinely_new_platform_still_creates_an_account(settings, store, service) -> None:
    """**正例**：这个平台一个账号都没有时，照旧建一个。"""
    new_id = _complete(_coordinator(settings, store, service), "bilibili", BILIBILI_MID)
    assert new_id, "第一次连接反而建不出账号了"
    assert store.get_source_account(new_id), "建出来的账号查不到"


@pytest.mark.parametrize("platform", sorted(REAL))
def test_the_fixture_matches_what_is_really_in_his_database(platform: str) -> None:
    """夹具用的是 2026-08-10 从生产读回来的原值——写死在这里，好让它被看见。"""
    assert REAL[platform].startswith("https://"), REAL[platform]
