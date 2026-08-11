"""他生产库里那 20 次同步，逐条渲染成句子，逐条看对不对（2026-08-07）。

## 为什么用他的真数据当夹具

失败文案一直是照着「我能想到的码」写的。而 2026-08-04 那次教训写在
`failure_copy.py` 里：**生产库里有代码里已经不存在的码**（v0.0.0.6 留下的
RELATION_SCOPE_UNCONFIRMED / STABLE_END_WITHOUT_PROOF / SYNC_RUN_ABANDONED），
光读代码列不全。

这条判据反过来做：把 `evidence/G1/PRODUCTION_AGGREGATION_REALLY_HAPPENED.json`
里**真实发生过的每一次运行**（平台/状态/错误码/导入条数原样）喂进去，
看它说出来的那句话成不成立。

## 它抓到了什么

一条 `cancelled`（没有 failure_code、0 条）说的是

    这次没有取到任何内容，而且我们没能记录下原因。**这是产品的问题**，请重试一次

而 `cancelled` 的来路是 db.py 断开账号那一步：「把还在跑的 sync_run 落到
cancelled（否则界面上永远转圈）」。**那是有人主动断开，不是产品出错。**
和 `failure_copy.py` 里已经修过的「刚排上队就被告知产品坏了」是同一种错。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from social_archive.failure_copy import describe_sync_outcome

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "evidence/G1/PRODUCTION_AGGREGATION_REALLY_HAPPENED.json"
LABELS = {"xiaohongshu": "小红书", "douyin": "抖音", "bilibili": "B站"}


def _runs() -> list[dict]:
    assert EVIDENCE.is_file(), (
        f"{EVIDENCE.relative_to(ROOT)} 不在——**这条判据没有夹具就等于没有**。"
        "跑一次 scripts/read_production_sync_history.py")
    runs = json.loads(EVIDENCE.read_text(encoding="utf-8"))["all_runs"]
    assert len(runs) >= 10, f"只有 {len(runs)} 次运行，这份夹具太薄，说明不了什么"
    return runs


def _sentence(run: dict) -> dict:
    return describe_sync_outcome(
        imported=run.get("imported_count") or 0,
        failure_code=run.get("last_error_code"),
        platform_label=LABELS.get(run["platform"], run["platform"]),
        status=run["status"])


def test_every_real_run_gets_a_sentence() -> None:
    for run in _runs():
        text = str(_sentence(run).get("message_zh") or "")
        assert text.strip(), f"{run['platform']}/{run['status']}/{run.get('last_error_code')} 没有句子"


def test_no_internal_code_reaches_the_sentence() -> None:
    """**他不该在界面上读到 `RELATION_SCOPE_UNCONFIRMED` 这种词。**"""
    for run in _runs():
        text = str(_sentence(run).get("message_zh") or "")
        leaked = re.findall(r"[A-Z][A-Z_]{4,}", text)
        assert not leaked, (
            f"{run['platform']}/{run.get('last_error_code')} 的句子里有内部码：{leaked}\n  {text}")


def test_a_cancelled_run_is_not_called_a_product_fault() -> None:
    """**被中断不是失败，更不是产品坏了。**

    `cancelled` 的来路是断开账号时把在跑的运行落下来——有人主动断开。
    给它扣一顶「这是产品的问题」的帽子，会让他以为软件坏了而去重试，
    而真正要做的是重新连接。
    """
    cancelled = [run for run in _runs() if run["status"] == "cancelled"]
    assert cancelled, "他库里那条 cancelled 不见了——这条判据失去了它的样本"
    for run in cancelled:
        out = _sentence(run)
        text = str(out.get("message_zh") or "")
        assert "产品的问题" not in text, f"把一次主动中断说成产品出错：{text}"
        assert "没能记录下原因" not in text, f"原因是知道的（被中断），别说不知道：{text}"
        assert "都还在" in text, f"没说清已取到的内容还在：{text}"


def test_the_runs_that_imported_things_report_the_count() -> None:
    """**进了东西就先报数**——他要先知道拿到了多少，再听别的。"""
    for run in _runs():
        imported = run.get("imported_count") or 0
        if imported <= 0:
            continue
        text = str(_sentence(run).get("message_zh") or "")
        assert str(imported) in text, f"进了 {imported} 条却没在句子里报数：{text}"


def test_a_blocked_download_is_not_called_a_lost_content() -> None:
    """**「视频被平台挡了」不等于「这次没有取到内容」。**

    2026-08-07 他生产库里有 33 个 download_l3 是
    `MEDIA_BLOCKED_BY_PLATFORM`（B 站 412 风控、抖音返回的东西 yt-dlp 解不了）。
    那一条原来落进 PRODUCT_FAULT_CODES，于是对他说

        这次没有取到内容，问题在我们这边，已经记下来了。不用反复重试。

    **两处都不对**：内容取到了（正文、标题、链接全在，33 条一条不缺），
    而「问题在我们这边、已经记下来了」听起来像会修——它是**有意的边界**
    （不绕平台风控、国内 Cookie 不出浏览器），不会变。说得像会变就是骗他等。
    """
    from social_archive.failure_copy import describe_sync_outcome

    out = describe_sync_outcome(imported=0, failure_code="MEDIA_BLOCKED_BY_PLATFORM",
                                platform_label="B站", status="partial")
    text = str(out["message_zh"])
    assert "没有取到内容" not in text, f"内容其实取到了，只是没有视频：{text}"
    assert "问题在我们这边" not in text, (
        f"这是有意的边界，不是待修的缺陷；说成「我们的问题」会让他等一个不会来的修复：{text}")
    assert "已经存下来了" in text and "不受影响" in text, (
        f"没说清他手上还有什么：{text}")


def test_the_last_sync_line_says_how_long_ago() -> None:
    """**一个日期读不出「多久没动了」。**（2026-08-12）

    2026-08-11 查生产：20 次同步全落在 8/3–8/4 之间，此后一条没再进来——
    而 8.7 那一行只写着 "2026-08-04"。天数要读的人自己去减，**而没人会去减**。
    他的档案馆冻了一周这件事，就这样躺在每一次部署日志里没人看见。
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "sync_history", ROOT / "scripts/read_production_sync_history.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    say = module._days_since_sentence
    assert "距今" in say("2026-08-04T05:23:45.358136Z"), "不再报距今多少天了"
    # **坏输入不许把这一步炸掉**——8.7 是播报不是门，它抛异常等于让一次
    # 每项都通过的部署死在最后一句话上（同一天在 8.69 那段已经踩过一次）。
    assert say(None) == ""
    assert say("看起来不像时间") == ""
