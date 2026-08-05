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

import json
from pathlib import Path

from social_archive.account_sync import (
    NOT_SYNCABLE_YET,
    PLATFORM_LABELS,
    PLATFORM_RELATIONS,
    SYNCABLE_NOW,
)

ROOT = Path(__file__).resolve().parents[2]

# 「有实测底」不再是一个写死的名单，而是**仓里真有一份跑出来的实测记录**。
#
# 写死名单的毛病是加名字太便宜：改一行就多一个平台，而没有任何东西去查
# 它凭什么在里面。改成读证据之后，「进 SYNCABLE_NOW」必须先「跑出一份
# status=PASS 且真打过接口的记录」——判据和事实之间有了一条实线。
PROVEN_EVIDENCE = {
    # T04 实测 62 条 Chrome 书签全量入库。这条早于本机制，仍按老规矩认。
    "generic-web": None,
    # v0.0.0.7 / G1：scripts/bilibili_acquisition_drill.py 生成。
    "bilibili": "evidence/G1/BILIBILI_ACQUISITION.json",
}


def _proven() -> set[str]:
    proven: set[str] = set()
    for platform, relative in PROVEN_EVIDENCE.items():
        if relative is None:
            proven.add(platform)
            continue
        report = ROOT / relative
        if not report.is_file():
            continue
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except ValueError:
            continue
        # **两个条件缺一不可**：跑出来是 PASS，而且真的打过接口。
        # 只看 status 的话，一次 --no-live（离线降级）跑出来的 PASS
        # 也会被当成「量过了」——那正是"降级当通过"的老毛病。
        if data.get("status") == "PASS" and data.get("live_probe_ran") is True:
            proven.add(platform)
    return proven


def test_nothing_claims_to_be_syncable_without_a_measured_basis() -> None:
    unproven = sorted(SYNCABLE_NOW - _proven())
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


def test_the_onboarding_sentence_is_not_a_second_capability_list() -> None:
    """第 3 步那句「本版本能自动同步的是…」原来是硬编码的。

    2026-08-05 实测它写着「Chrome 书签，以及连接后的 X / Instagram」——
    而 X 与 Instagram **都同步不了**（X 被零费用门关着，Instagram 的授权
    那一步没有 Owner 点得到的界面），两个都已经在 NOT_SYNCABLE_YET 里。
    **那句文案比能力声明晚了整整一轮。**

    这是同一种病的第五处，也是**第一处靠搜索找出来的**——搜「乐观措辞 +
    中文」的用户可见串，47 处里就这一处在撒谎。
    """
    from pathlib import Path

    app = (Path(__file__).resolve().parents[2] / "apps/pwa/app.js").read_text(encoding="utf-8")
    code = "\n".join(l for l in app.splitlines() if not l.lstrip().startswith("//"))
    step = code.split("第 3 步：连接一个能同步的来源", 1)[1][:900]
    assert "state.platformSupport" in step, "那句话不是从能力声明现算的——它会再漂一次"
    for hardcoded in ("X / Instagram", "小红书、抖音、B站、快手"):
        assert hardcoded not in step, f"那句话里又硬编码了平台名单：{hardcoded}"
