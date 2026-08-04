"""SYNCABLE_NOW 是事实清单，不是愿景清单（v0.0.0.7 / INV-REAL-USABLE）。

2026-08-04 生产实测（POST /v1/connectors/{id}/run，打到真服务器）把这张表
砍到只剩一个：

    x          blocked_environment  X_ZERO_COST_NOT_CONFIRMED
    reddit     blocked_environment  REDDIT_AUTH_MISSING
    instagram  HTTP 422「CLI Sidecar 调用失败」
    bilibili   failed               BILI_SIDECAR_BLOCKED

而前三个当时都在 SYNCABLE_NOW 里，界面上都画着「立即同步」。

这些判据守两件事：**表里的每一项都要有实测底**，
以及**不在表里的每一项都要有一句用户读得懂的原因**。
"""

from social_archive.account_sync import (
    NOT_SYNCABLE_YET,
    PLATFORM_LABELS,
    PLATFORM_RELATIONS,
    SYNCABLE_NOW,
)

# 只有这一个平台跑通过真实数据：T04 实测 62 条 Chrome 书签全量入库。
# 往这里加名字之前，先拿出**打到生产上量出来的**证据，不是读代码推的。
PROVEN_BY_REAL_DATA = {"generic-web"}


def test_nothing_claims_to_be_syncable_without_a_measured_basis() -> None:
    unproven = sorted(SYNCABLE_NOW - PROVEN_BY_REAL_DATA)
    assert not unproven, (
        f"这些平台自称「能同步」而没有实测底：{unproven}。"
        "界面会给它们画「立即同步」，点下去是什么，谁也没量过。"
    )


def test_every_platform_is_either_syncable_or_explained() -> None:
    """两张表加起来必须盖满所有平台。

    漏一个的话，界面画的是「立即同步」而 not_syncable_reason 是空串——
    用户点下去，什么也没发生，也没有任何一句话解释。
    """
    orphans = [
        platform
        for platform in PLATFORM_RELATIONS
        if platform not in SYNCABLE_NOW and not NOT_SYNCABLE_YET.get(platform, "").strip()
    ]
    assert not orphans, f"这些平台既不在能同步的表里，也没有一句不能同步的理由：{orphans}"


def test_the_reasons_do_not_make_the_owner_read_our_code() -> None:
    """Owner 的原话：「我没有技术基础」。

    文案里出现 OAuth / token / sidecar / API 这些词，等于让他读我们的代码。
    """
    jargon = ("OAuth", "token", "Token", "sidecar", "Sidecar", "HTTP", "cookie", "Cookie")
    offenders = []
    for platform, reason in NOT_SYNCABLE_YET.items():
        hit = [word for word in jargon if word in reason]
        if hit:
            offenders.append(f"{platform}: {hit}")
    assert not offenders, f"这些不能同步的理由里有技术黑话：{offenders}"


def test_every_reason_says_what_the_owner_can_do_instead() -> None:
    """只说「做不到」是半句话。另外半句是「现在能做什么」。"""
    missing = [
        platform for platform, reason in NOT_SYNCABLE_YET.items()
        if "现在可以" not in reason
    ]
    assert not missing, f"这些理由只说了做不到，没说现在能做什么：{missing}"


def test_reasons_are_written_for_platforms_that_exist() -> None:
    unknown = sorted(set(NOT_SYNCABLE_YET) - set(PLATFORM_RELATIONS))
    assert not unknown, f"给不存在的平台写了理由，永远不会显示：{unknown}"
    for platform in NOT_SYNCABLE_YET:
        assert platform in PLATFORM_LABELS, f"{platform} 没有中文名"
