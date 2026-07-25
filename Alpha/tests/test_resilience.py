"""运维韧性加固:第二告警通道休眠/触发、盘前自检与备份产物、运维就绪渲染。"""

import json
import os

from backend.app.notify.outbox import CRITICAL_EVENTS, post_alert_webhook


def test_webhook_dormant_without_config(monkeypatch):
    """未配置 ALPHA_ALERT_WEBHOOK 时第二通道完全休眠,不做任何网络动作。"""
    monkeypatch.delenv("ALPHA_ALERT_WEBHOOK", raising=False)
    assert post_alert_webhook("x", "y") is False


def test_webhook_posts_when_configured(monkeypatch):
    """配置了 webhook 时会 POST(用假 urlopen 断言不真连网)。"""
    monkeypatch.setenv("ALPHA_ALERT_WEBHOOK", "https://example.invalid/hook")
    sent = {}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_urlopen(req, timeout=8):
        sent["url"] = req.full_url
        sent["body"] = req.data
        return _Resp()

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    assert post_alert_webhook("主题", "正文") is True
    assert sent["url"] == "https://example.invalid/hook"
    assert "主题" in json.loads(sent["body"])["text"]


def test_critical_events_cover_key_alerts():
    """关键告警必须都在第二通道名单里(失联/切换暂缓/自检红/授权临期)。"""
    for e in ("WORKER_HEARTBEAT_LOST", "ACTIVATION_BLOCKED", "PREFLIGHT_ALERT", "AUTH_EXPIRING"):
        assert e in CRITICAL_EVENTS


def test_backup_skips_non_postgres(monkeypatch, tmp_path):
    """非 PostgreSQL 环境:备份如实跳过并落盘失败状态,绝不假装成功。"""
    monkeypatch.setenv("ALPHA_DATABASE_URL", f"sqlite:///{tmp_path/'x.sqlite'}")
    monkeypatch.chdir(tmp_path)
    import importlib
    import scripts.backup_ledger as bl
    importlib.reload(bl)
    rc = bl.main()
    assert rc == 1
    st = json.loads((tmp_path / "machine/facts/backup_status.json").read_text())
    assert st["ok"] is False and "PostgreSQL" in st["detail"]


def test_readiness_rows_render(tmp_path, monkeypatch):
    """运维就绪:读自检/备份事实文件 → 渲染出对应灯。"""
    from datetime import datetime, timezone

    monkeypatch.chdir(tmp_path)
    facts = tmp_path / "machine/facts"
    facts.mkdir(parents=True)
    (facts / "preflight_status.json").write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "all_ok": True,
        "auth_days_left": 12, "checks": [{"name": "OpenD 会话", "ok": True}]}))
    (facts / "backup_status.json").write_text(json.dumps({
        "at": datetime.now(timezone.utc).isoformat(), "ok": True, "size": 12345, "keep": 14}))
    from backend.app.control_page.dashboard_data import _readiness_rows
    from backend.app.control_page.render import render_ops_html
    rows = _readiness_rows(datetime.now(timezone.utc))
    assert any("盘前自检" in r["name"] and r["ok"] for r in rows)
    assert any("备份" in r["name"] and r["ok"] for r in rows)
    html = render_ops_html({"caps": [], "ledger": [], "events": [], "open_faults": 0,
                            "healthy_now": True, "readiness": rows, "updated_at_syd": "x"})
    assert "运维就绪" in html and "盘前自检" in html
