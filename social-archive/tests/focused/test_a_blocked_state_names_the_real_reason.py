"""指错原因的 BLOCKED 不算 BLOCKED（v0.0.0.7 / T13）。

任务包 T13 的原话是 **「沉默不算 BLOCKED」**（引自
evidence/T02/CREDENTIAL_BLOCKED_RECEIPT.json）。同一条道理再走一步：
**指错原因的 BLOCKED 也不算**——它比沉默更坏，因为它把人送去修一个
不存在的东西。

2026-08-05 生产实测：

    xiaohongshu   blocked_environment   HEALTH_PROBE_FAILED
    douyin        blocked_environment   WORKER_PROBE_OR_CALL_FAILED
    kuaishou      blocked_environment   WORKER_PROBE_OR_CALL_FAILED
    bilibili / reddit / instagram / tiktok   PLATFORM_NOT_SYNCABLE_YET

同样是「本版本读不了」，前三个却报成探针挂了。而它们的探针去连的是
xhs-worker:5556 之类的地址——那三个 worker 早在 T03 就被实测证伪、
连同 compose.workers.yaml 一起删掉了。**失败码指着一个故意移除的组件。**
"""

from pathlib import Path

import pytest

from social_archive.account_sync import NOT_SYNCABLE_YET
from social_archive.registry import INCIDENTAL_PROBE_FAILURES, ConnectorRegistry


@pytest.mark.parametrize("probe_code", sorted(INCIDENTAL_PROBE_FAILURES))
def test_an_incidental_probe_failure_never_becomes_the_stated_reason(
    settings, store, monkeypatch, probe_code: str
) -> None:
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(registry, "_live_probe",
                        lambda _: {"state": "degraded", "error_code": probe_code})
    view = next(item for item in registry.health_views(store.connector_states())
                if item["connector_id"] == "xiaohongshu")
    assert view["last_error_code"] == "PLATFORM_NOT_SYNCABLE_YET", (
        f"{probe_code} 被当成了原因——「探针挂了」读起来像「有东西宕了，重启一下」，"
        "而真相是这条路本版本就没有"
    )
    assert view["state"] == "blocked_environment"


def test_a_real_reason_is_kept_because_it_says_more_than_the_generic_one(
    settings, store, monkeypatch
) -> None:
    """X_ZERO_COST_NOT_CONFIRMED 本身就是真原因（Owner 的零费用门）。

    把它换成通用码是**信息损失**：通用码不会告诉任何人「这道门只有 Owner
    能打开、而且是笔花钱的判断」。
    """
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(registry, "_live_probe",
                        lambda _: {"state": "blocked_environment",
                                   "error_code": "X_ZERO_COST_NOT_CONFIRMED"})
    view = next(item for item in registry.health_views(store.connector_states())
                if item["connector_id"] == "x")
    assert view["last_error_code"] == "X_ZERO_COST_NOT_CONFIRMED", "把真原因换成通用码，是信息损失"


def test_the_probe_code_is_kept_as_a_clue_not_thrown_away(settings, store, monkeypatch) -> None:
    """换掉的那个码不能直接扔——排查时它仍是线索，只是不该当原因。"""
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(registry, "_live_probe",
                        lambda _: {"state": "degraded", "error_code": "HEALTH_PROBE_FAILED"})
    views = {item["connector_id"]: item for item in registry.health_views(store.connector_states())}
    raw = registry.health_views(store.connector_states())
    assert views["xiaohongshu"]["last_error_code"] == "PLATFORM_NOT_SYNCABLE_YET"
    assert any("HEALTH_PROBE_FAILED" in str(item.get("detail") or "") for item in raw), (
        "探针的原码被直接扔了——排查时会少一条线索"
    )


def test_the_message_and_the_code_tell_the_same_story(settings, store, monkeypatch) -> None:
    """**文案说一套、码说另一套**，是这一整天反复出现的那种病。"""
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(registry, "_live_probe",
                        lambda _: {"state": "degraded", "error_code": "HEALTH_PROBE_FAILED"})
    view = next(item for item in registry.health_views(store.connector_states())
                if item["connector_id"] == "xiaohongshu")
    assert view["last_message_zh"] == NOT_SYNCABLE_YET["xiaohongshu"], "文案不是能力声明里那句"
    assert view["last_error_code"] == "PLATFORM_NOT_SYNCABLE_YET", "码和文案讲的不是同一件事"


def test_the_next_step_does_not_point_at_a_wizard_that_cannot_help(settings, store, monkeypatch) -> None:
    """**「下一步」也不许指向一个不存在的东西。**

    通用文案说「尚未配置真实账号或 Worker；……再按向导配置」。生产实测八个
    被挡住的连接器全在显示它。而那三个 Worker 在 T03 就被删了，**也没有任何
    向导能打开这几条路**：bilibili/小红书/抖音/快手是取数路本版本就没建，
    x 是 Owner 的零费用判断，reddit/instagram 的授权那步还没有他点得到的界面。

    叫一个说自己「没有技术基础」的人去按一个不存在的向导，比不给下一步更坏——
    他会去找，找不到，然后以为是自己的问题。
    """
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(registry, "_live_probe",
                        lambda _: {"state": "degraded", "error_code": "HEALTH_PROBE_FAILED"})
    # **凡是被能力声明钳住的都要查，不只是 NOT_SYNCABLE_YET 里那些。**
    #
    # 第一版只查了那张表里的，于是 tiktok 漏网——它不在任何能力表里，
    # 走的是另一条钳制分支。上线之后才在生产上看见只有它还写着「按向导配置」。
    # **一个只修了一半的修复，比没修更难发现**：判据是绿的。
    for view in registry.health_views(store.connector_states()):
        if view["state"] != "blocked_environment":
            continue
        step = view["next_action_zh"]
        assert "向导" not in step, f"{view['connector_id']} 仍被指向一个打不开这条路的向导：{step}"
        assert "Worker" not in step, f"{view['connector_id']} 的下一步还在提已经删掉的 Worker：{step}"


def test_a_platform_in_no_capability_table_also_gets_an_honest_next_step(
    settings, store, monkeypatch
) -> None:
    """tiktok 不在任何一张能力表里，走的是**另一条**钳制分支。

    那条分支只在探针说 healthy 时才触发——所以上面那些用 degraded 探针的判据
    **一条都碰不到它**。2026-08-05 实测：修完上线后其它平台都对了，
    只有 tiktok 还写着「按向导配置」，而判据全绿。

    **一个只修了一半的修复，比没修更难发现。** 这条判据专门走那条分支。
    """
    registry = ConnectorRegistry(settings)
    monkeypatch.setattr(registry, "_live_probe", lambda _: {"state": "healthy"})
    view = next(item for item in registry.health_views(store.connector_states())
                if item["connector_id"] == "tiktok")
    assert view["state"] == "blocked_environment", "探针说 healthy 时它没有被能力声明钳住"
    assert "向导" not in view["next_action_zh"], (
        f"tiktok 仍被指向一个打不开这条路的向导：{view['next_action_zh']}"
    )
    assert "Worker" not in view["next_action_zh"]


def test_no_next_step_anywhere_mentions_the_deleted_workers() -> None:
    """**整张「下一步」表里都不许再提那三个 Worker。**

    它们在 T03 就被实测证伪、连同 compose.workers.yaml 删掉了。
    degraded 那句现在其实到不了（能力钳制把不可同步的都压成 blocked_environment，
    而 generic-web 的探针无条件 healthy）——但**到不了的假话仍然是假话**：
    下一个读代码的人会以为 Worker 还在这套架构里。
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "src/social_archive/registry.py").read_text(encoding="utf-8")
    table = source.split("next_action = {", 1)[1].split("}.get(state", 1)[0]
    # **只看会显示给人的那几句，不看解释它们的注释。**
    # 表里那段注释正是在讲「不该再提那三个已删的 Worker」——把注释也算进去，
    # 判据就会红在一句正确的说明上。今天第三次栽在同一处（doctor 的 PASS、
    # 部署脚本的 system prune，现在是这个）。
    shown = "\n".join(l for l in table.splitlines() if not l.lstrip().startswith("#"))
    assert "Worker" not in shown, f"「下一步」表里还在提已删的 Worker：{shown[:200]}"
    assert "向导" not in shown, "「下一步」表里还在指向一个打不开这些路的向导"
