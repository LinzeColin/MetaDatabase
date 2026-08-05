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
