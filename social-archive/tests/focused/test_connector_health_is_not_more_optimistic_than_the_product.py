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


def test_a_browser_side_platform_is_not_reported_as_unavailable():
    """**服务端探不到 ≠ 他那边同步不了。**

    2026-08-07 打生产读 /v1/status：小红书 `HEALTH_PROBE_FAILED`（detail 是
    ConnectError）、抖音和快手 `WORKER_PROBE_OR_CALL_FAILED`，三条文案都是

        状态代码：HEALTH_PROBE_FAILED。这个来源暂时不可用；先用"保存当前页面"。

    **两处不对：** 把内部码摆给他看（registry.py 自己的注释里就记着 x 那次
    同样的事故）；以及**「这个来源暂时不可用」对这三家是错的**——它们靠的是
    他浏览器里的登录状态，服务端按 INV-DOMESTIC-COOKIE-STAYS 永远不该有他的
    Cookie，**探不通是预期不是故障**。而同一时刻连接面板正给它们画着能用的
    「连接账号」：两处对同一件事说反话。
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "src/social_archive/registry.py").read_text(encoding="utf-8")
    assert 'message = f"状态代码：{error_code}。{next_action}"' not in source, (
        "又把内部码拼进给用户看的句子里了")
    assert "SERVER_ACCOUNT_CONNECTORS" in source, (
        "没有区分「走服务端」和「走他浏览器」——服务端探针对后者说什么都不作数")
    assert "服务器这边探不到它很正常" in source, (
        "浏览器侧平台探测失败时，没有给出那句解释")


def test_a_syncable_browser_platform_is_never_marked_structurally_blocked() -> None:
    """**`blocked_environment` 是留给"本版本根本做不了"的。**

    2026-08-07 生产上 reddit 是 `blocked_environment` + 「最近一次读取未完成；
    请按下一步处理或使用保存当前页面。」——那是一句**旧的 OAuth 探测结果**
    留在库里的，而 reddit 今天走的是浏览器那条路（演练每次发布都在跑，
    面板上那颗按钮按下去会停在「正在连接…」）。

    用 tiktok / youtube 同一档去标它，他会以为这个平台不支持。
    浏览器侧平台的服务端探测失败最多只能降到 `degraded`，
    而且那句消息必须被换掉——**任何来自服务端探针的话都是在说另一条路**。
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2]
              / "src/social_archive/registry.py").read_text(encoding="utf-8")
    assert 'if browser_side and state != "healthy":' in source, (
        "浏览器侧平台的探测结果没有被单独处理")
    assert 'state = "degraded"' in source.split("if browser_side")[1][:400], (
        "浏览器侧平台还会被标成 blocked_environment——那一档是「本版本做不了」的意思")
    assert 'message = ""' in source.split("if browser_side")[1][:400], (
        "库里存着的那句服务端探测结果没被换掉——reddit 就是这么漏的")
