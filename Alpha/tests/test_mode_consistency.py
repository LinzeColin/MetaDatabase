"""模式一致性回归门(2026-07-25 外部复审抓到):页头写微实盘,门禁却写"保持 Paper"。

铁律:进入 MICRO_LIVE 后,纸面阶段的晋级门禁/结论一律不得作为"当前状态"展示。
"""

import json

import pytest

from backend.app.control_page.dashboard_data import build_overview
from backend.app.control_page.render import render_dashboard_html


class _KS:
    def active(self): return False
    def detail(self): return ""


@pytest.fixture()
def stale_paper_report(tmp_path):
    """换帅前那份纸面报告:两红一结论『保持 Paper』。"""
    rep = tmp_path / "rep" / "2026-07-23"
    rep.mkdir(parents=True)
    (rep / "report.json").write_text(json.dumps({"promotion": {
        "days_qualified": 4, "days_required": 3,
        "decision": "未全绿:保持 Paper,进入调参循环并邮件报告差距",
        "auto_promote": False,
        "PROMO-2": {"passed": True, "reason": "行为样本齐备"},
        "PROMO-3": {"passed": False, "pace_month_pct": -11.116, "target_pct": 0.36},
        "PROMO-4": {"passed": False, "uptime_pct": 66.58, "notify_p95_seconds": 2.99},
    }}, ensure_ascii=False))
    return tmp_path / "rep"


def _overview(tmp_path, reports_dir, tag):
    return build_overview(session_factory=None, heartbeats=None, kill_switch=_KS(),
                          runtime_dir=tmp_path / f"rt{tag}", reports_dir=reports_dir,
                          real_power_usd=1587.09)


def test_live_mode_hides_stale_paper_gates(tmp_path, stale_paper_report, monkeypatch):
    """实盘模式:不得出现纸面门禁、未达标灯、以及被推翻的『保持 Paper』结论。"""
    monkeypatch.setenv("ALPHA_MODE", "MICRO_LIVE")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "1")
    o = _overview(tmp_path, stale_paper_report, "live")
    html = render_dashboard_html(o)

    assert o["mode_cn"] == "微实盘(真实资金)"
    assert o["exam"] is None, "实盘下不得把纸面晋级门禁当作当前状态"
    assert o["live_stage"] is not None
    # 旧结论可以被"引用并声明已作废",但绝不能作为当前状态孤零零地摆出来:
    # 凡出现『保持 Paper』处,必须紧跟"已被…取代/历史存档"的作废说明。
    assert "未达标" not in html, "页面仍显示纸面阶段的未达标灯"
    if "保持 Paper" in html:
        idx = html.find("保持 Paper")
        tail = html[idx:idx + 120]
        assert ("取代" in tail or "历史存档" in tail), "旧结论未声明作废,会被误读为当前状态"
    assert "实盘运行阶段" in html and "真实资金、真实订单" in html
    # 旧报告仍可追溯(作为历史存档提及),但明确标注不代表当前
    assert "2026-07-23" in html and "历史存档" in html


def test_paper_mode_still_shows_gates(tmp_path, stale_paper_report, monkeypatch):
    """纸面模式:行为完全不变,门禁照常展示(不能因修复而丢功能)。"""
    monkeypatch.setenv("ALPHA_MODE", "PAPER")
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "0")
    o = _overview(tmp_path, stale_paper_report, "paper")
    html = render_dashboard_html(o)

    assert o["exam"] is not None and o["live_stage"] is None
    assert "保持 Paper" in html and "三日模拟盘考核" in html


def test_mode_badge_and_gate_never_disagree(tmp_path, stale_paper_report, monkeypatch):
    """核心不变量:页头徽章说实盘 ⟺ 页面不含纸面门禁结论。"""
    for mode, flag in (("MICRO_LIVE", "1"), ("PAPER", "0")):
        monkeypatch.setenv("ALPHA_MODE", mode)
        monkeypatch.setenv("LIVE_TRADING_ENABLED", flag)
        o = _overview(tmp_path, stale_paper_report, f"x{mode}")
        html = render_dashboard_html(o)
        live_badge = "微实盘" in o["mode_cn"]
        # 不变量:徽章说实盘 ⟺ 不把纸面门禁当作当前状态(exam 为空)
        assert live_badge == (o["exam"] is None), f"{mode}: 页头与门禁自相矛盾"
        if live_badge:
            assert "未达标" not in html, f"{mode}: 实盘却显示纸面未达标灯"
