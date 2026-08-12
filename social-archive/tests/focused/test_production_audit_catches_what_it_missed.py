"""那条审计，喂它「修之前的样子」必须变红（2026-08-07）。

2026-08-07 在他的生产数据上查出十处缺陷，**没有一处被那 1190 条测试和
31 道发布门抓到**——它们全在问「机制对不对」，而这十处问的是
**「产品对他这份数据说的话对不对」**。

`scripts/audit_production_against_the_product.py` 把那天的查法做成一条命令。
但**一条永远说 PASS 的审计等于没有**：所以这里把当天修之前的真实形状
原样喂给它，逐条证明它会红。

形状全部照抄当天从生产读回来的原文，不是我编的：
  · 小红书 `degraded` + 「状态代码：HEALTH_PROBE_FAILED。这个来源暂时不可用…」
  · reddit `blocked_environment`（而它在 supported_platforms 里可同步）
  · 内容标题为空
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/audit_production_against_the_product.py"

_spec = importlib.util.spec_from_file_location("_production_audit", SCRIPT)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_production_audit"] = _module
_spec.loader.exec_module(_module)
audit = _module.audit


def _accounts(**overrides) -> dict:
    base = {
        "items": [{"platform": "xiaohongshu", "connection_state": "disconnected",
                   "auto_sync_enabled": False, "content_count": 1}],
        "supported_platforms": [
            {"platform": "xiaohongshu", "sync_supported": True, "connect_supported": True},
            {"platform": "reddit", "sync_supported": True, "connect_supported": True},
            {"platform": "x", "sync_supported": False, "connect_supported": True,
             "not_syncable_reason": "本版本还不能自动读取 X 的书签。"},
        ],
    }
    base.update(overrides)
    return base


def _library(items=None) -> dict:
    items = items if items is not None else [
        {"id": "cnt_1", "title": "一条正常内容", "canonical_url": "https://example.com/1",
         "archive_status": "完整", "author_name": "", "published_at": "", "summary": "x"}]
    return {"items": items, "total": len(items)}


def _status(connectors) -> dict:
    return {"connectors": connectors}


HEALTHY = [{"connector_id": "xiaohongshu", "state": "degraded",
            "last_message_zh": "这个来源是在你自己的浏览器里同步的，服务器这边探不到它很正常。",
            "next_action_zh": "在资料库上点「连接账号」即可"},
           {"connector_id": "reddit", "state": "degraded",
            "last_message_zh": "这个来源是在你自己的浏览器里同步的，服务器这边探不到它很正常。",
            "next_action_zh": "在资料库上点「连接账号」即可"}]


def test_the_current_shape_passes() -> None:
    """**正例必须是绿的。** 一条永远喊红的审计和永远说 PASS 的一样没用。"""
    problems, measured = audit(_library(), _accounts(), _status(HEALTHY))
    assert problems == [], problems
    assert measured["items_total"] == 1


def test_it_catches_an_internal_code_in_user_facing_text() -> None:
    """当天原文：「**状态代码：HEALTH_PROBE_FAILED**。这个来源暂时不可用…」"""
    bad = [{"connector_id": "xiaohongshu", "state": "degraded",
            "last_message_zh": "状态代码：HEALTH_PROBE_FAILED。这个来源暂时不可用；先用保存当前页面。",
            "next_action_zh": "这个来源暂时不可用；先用保存当前页面。"}]
    problems, _ = audit(_library(), _accounts(), _status(bad))
    assert any("内部码" in p for p in problems), problems
    assert any("HEALTH_PROBE_FAILED" in p for p in problems), problems


def test_it_catches_a_syncable_platform_marked_structurally_blocked() -> None:
    """当天原文：reddit 是 `blocked_environment`，而它在 supported_platforms 里可同步。"""
    bad = [{"connector_id": "reddit", "state": "blocked_environment",
            "last_message_zh": "最近一次读取未完成；请按下一步处理或使用保存当前页面。",
            "next_action_zh": "本版本还不能自动读取这个来源；先用保存当前页面。"}]
    problems, _ = audit(_library(), _accounts(), _status(bad))
    assert any("blocked_environment" in p for p in problems), problems


def test_it_catches_unavailable_wording_on_a_browser_side_platform() -> None:
    bad = [{"connector_id": "xiaohongshu", "state": "degraded",
            "last_message_zh": "这个来源暂时不可用；先用保存当前页面。",
            "next_action_zh": "这个来源暂时不可用。"}]
    problems, _ = audit(_library(), _accounts(), _status(bad))
    assert any("暂时不可用" in p for p in problems), problems


def test_an_item_with_no_title_but_a_link_is_not_a_problem() -> None:
    """**空标题本身不是缺陷**：资料库用链接的尾巴认人。

    第一版按「标题为空」就报，当场误报 6 条——那 6 条界面上显示的是
    `douyin.com/video/7584…`，他分得清。**判据指错了对象。**
    """
    items = [{"id": "cnt_2", "title": "", "canonical_url": "https://www.douyin.com/video/7584",
              "archive_status": "完整"}]
    problems, measured = audit(_library(items), _accounts(), _status(HEALTHY))
    assert problems == [], problems
    assert measured["items_without_title"] == 1
    assert measured["items_with_nothing_to_identify_them"] == 0


def test_an_item_with_neither_title_nor_link_is_a_problem() -> None:
    items = [{"id": "cnt_3", "title": "", "canonical_url": "", "archive_status": "完整"}]
    problems, _ = audit(_library(items), _accounts(), _status(HEALTHY))
    assert any("认不出是哪一条" in p for p in problems), problems


def test_it_catches_a_failure_code_with_no_human_sentence() -> None:
    """**生产里冒出一个谁都没想到的新码，这里要当场发现。**

    failure_copy.py 里记着 2026-08-04 的教训：生产库里有代码里已经不存在的码
    （v0.0.0.6 留下的三个），**光读代码列不全**。所以反过来——把生产真出现过的
    码逐个渲染，看它说得出话、且不泄漏内部码。
    """
    problems, _ = audit(_library(), _accounts(), _status(HEALTHY),
                        {"A_CODE_NOBODY_WROTE_COPY_FOR"})
    assert problems, "一个没有人话的新码没被发现"
    assert any("A_CODE_NOBODY_WROTE_COPY_FOR" in p for p in problems), problems


def test_the_codes_his_production_really_emitted_all_have_sentences() -> None:
    """他生产里真出现过的那五个码，逐个必须说得出人话。"""
    import json as _json

    history = ROOT / "evidence/G1/PRODUCTION_AGGREGATION_REALLY_HAPPENED.json"
    assert history.is_file(), "取证文件不在——这条判据没有夹具就等于没有"
    codes = {run["last_error_code"] for run
             in _json.loads(history.read_text(encoding="utf-8"))["all_runs"]
             if run.get("last_error_code")}
    assert len(codes) >= 4, f"只有 {len(codes)} 个码，这份夹具太薄"
    problems, _ = audit(_library(), _accounts(), _status(HEALTHY), codes)
    assert problems == [], problems


# ── 2026-08-12：审计一直用 imported=0 渲染，于是「有新增」那一整档从没被看过 ──

# 他生产库里真实那 4 次（照抄，不是编的）：全部「导进了东西 + 没跑完」。
HIS_PARTIAL_IMPORTS = [
    {"platform": "bilibili", "status": "partial", "imported_count": 102,
     "discovered_count": 102, "last_error_code": "RELATION_SCOPE_UNCONFIRMED"},
    {"platform": "douyin", "status": "partial", "imported_count": 35,
     "discovered_count": 35, "last_error_code": "STABLE_END_WITHOUT_PROOF"},
    {"platform": "bilibili", "status": "partial", "imported_count": 67,
     "discovered_count": 67, "last_error_code": "RELATION_SCOPE_UNCONFIRMED"},
    {"platform": "douyin", "status": "partial", "imported_count": 56,
     "discovered_count": 56, "last_error_code": "STABLE_END_WITHOUT_PROOF"},
]


def test_a_partial_import_that_hides_it_is_caught() -> None:
    """**这一档以前审计根本看不见。**

    第 5 条检查固定传 `imported=0`，而 `describe_sync_outcome` 第一条分支就是
    `if imported > 0`——传 0 意味着「有新增」那一整档永远走不到。
    今天的缺陷正落在那里：他 4 次导入全是「有新增 + 没跑完」，
    产品只说「新增 N 条。」，而审计全程绿着。

    这里用**产品当前的真实实现**跑他那 4 个形状：现在必须一条问题都没有。
    反方向由 `test_it_would_have_caught_the_swallowed_incompleteness` 守着。
    """
    codes = {r["last_error_code"] for r in HIS_PARTIAL_IMPORTS}
    problems, _ = audit(_library(), _accounts(), _status(HEALTHY),
                        codes, HIS_PARTIAL_IMPORTS)
    swallowed = [p for p in problems if "没跑完这件事被吞掉了" in p]
    assert not swallowed, swallowed


def test_it_would_have_caught_the_swallowed_incompleteness(monkeypatch) -> None:
    """把产品改回「只报数」，审计必须把 4 次全部报出来。

    **不改产物、只改判据是测不出这个的**——所以这里真的把
    `describe_sync_outcome` 换成修复前那种行为，再看审计红不红。
    """
    from social_archive import failure_copy

    def only_the_count(*, imported, failure_code=None, platform_label="",
                       status="", updated_at=None, **_kw):
        # 修复前的形状：有新增就只报数，别的一概不说。
        if imported > 0:
            return {"outcome": "imported", "imported": imported,
                    "message_zh": f"新增 {imported} 条。",
                    "failure_code": failure_code, "action_zh": None}
        return {"outcome": "stalled", "imported": 0,
                "message_zh": "这次同步卡住了，没有正常结束。你已经取到的内容都还在。",
                "failure_code": failure_code, "action_zh": None}

    monkeypatch.setattr(failure_copy, "describe_sync_outcome", only_the_count)
    codes = {r["last_error_code"] for r in HIS_PARTIAL_IMPORTS}
    problems, _ = audit(_library(), _accounts(), _status(HEALTHY),
                        codes, HIS_PARTIAL_IMPORTS)
    swallowed = [p for p in problems if "没跑完这件事被吞掉了" in p]
    assert len(swallowed) == 4, f"只报出 {len(swallowed)} 条，应为 4：{problems}"
