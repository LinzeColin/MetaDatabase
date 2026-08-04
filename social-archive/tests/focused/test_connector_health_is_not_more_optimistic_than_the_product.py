"""连接器的健康度不许比产品自己的能力声明更乐观（v0.0.0.7 / INV-REAL-USABLE）。

2026-08-05 生产实测，那份连接器视图说：

    instagram  healthy  「可直接点击"读取/保存"。」
    bilibili   healthy  「可直接点击"读取/保存"。」
    tiktok     healthy  「可直接点击"读取/保存"。」

而真跑一次：instagram → INSTAGRAM_SIDECAR_BLOCKED（session 是空的）、
bilibili → BILI_SIDECAR_BLOCKED。**tiktok 甚至不在 PLATFORM_RELATIONS 里**，
界面上根本没有这个平台。

根因：这三个的探针是 `self.command.health()`——它测的是
**「CLI sidecar 活着吗」**，不是「这个连接器干得成活吗」。sidecar 活着，
于是三个都报 healthy。

**这是同一种病的第四处**：前三处是「立即同步」按钮、连接入口、
目的地「自动导入」。
"""

from social_archive.account_sync import NOT_SYNCABLE_YET, SYNCABLE_NOW
from social_archive.registry import ConnectorRegistry


def _views(settings, store):
    # ConnectorRegistry 只收 settings；已持久化的连接器状态从 store 单独传进去。
    return ConnectorRegistry(settings).health_views(store.connector_states())


def test_no_connector_claims_healthy_for_a_platform_that_cannot_sync(settings, store) -> None:
    liars = [
        view for view in _views(settings, store)
        if view["state"] == "healthy" and view["connector_id"] not in SYNCABLE_NOW
    ]
    assert not liars, (
        f"这些连接器自称 healthy，而产品声明它们同步不了："
        f"{[v['connector_id'] for v in liars]}——界面会写「可直接点击读取/保存」"
    )


def test_the_clamped_ones_say_why_in_the_platforms_own_words(settings, store) -> None:
    """钳下来之后要说人话，而且是**那个平台自己那句**（含「现在可以：…」）。"""
    for view in _views(settings, store):
        if view["connector_id"] in SYNCABLE_NOW or view["connector_id"] not in NOT_SYNCABLE_YET:
            continue
        message = str(view.get("last_message_zh") or "")
        assert message == NOT_SYNCABLE_YET[view["connector_id"]], (
            f"{view['connector_id']} 被钳下来了却没有用它自己那句理由：{message[:40]}"
        )
        assert "现在可以" in message, "只说了做不到，没说现在能做什么"


def test_generic_web_stays_healthy(settings, store) -> None:
    """唯一有实测底的那个不能被误伤。"""
    view = next(v for v in _views(settings, store) if v["connector_id"] == "generic-web")
    assert view["state"] == "healthy"


def test_the_clamp_reads_the_single_source_of_truth() -> None:
    """能力只有一处真源。连接器视图里不许再维护一份平台名单。"""
    import inspect

    source = inspect.getsource(ConnectorRegistry.health_views)
    code = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
    assert "SYNCABLE_NOW" in code and "NOT_SYNCABLE_YET" in code
    for hardcoded in ("instagram", "bilibili", "tiktok", "xiaohongshu"):
        assert f'"{hardcoded}"' not in code, f"这里硬编码了 {hardcoded}——第二份名单必然漂开"


def test_the_same_situation_gets_the_same_state(settings, store) -> None:
    """同样是「本版本读不了」，不能一部分 degraded、一部分 blocked_environment。

    `degraded` 读起来像「暂时不行、待会儿再试」，而这件事重试多少次都一样。
    第一版修完后生产上正是这个样子：bilibili/instagram 是 blocked_environment，
    小红书/抖音/快手 是 degraded。
    """
    states = {
        view["connector_id"]: view["state"]
        for view in _views(settings, store)
        if view["connector_id"] in NOT_SYNCABLE_YET
    }
    assert states, "一个不可同步的平台都没有？判据失去依附"
    assert set(states.values()) == {"blocked_environment"}, (
        f"同一处境却有多种状态：{states}"
    )
