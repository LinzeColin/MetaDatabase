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
