"""体检脚本:全绿退出 0 且首行「系统在岗」;红项点名并说明要不要动手;--digest 入队每日摘要;--check-env 拦禁用键。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

import scripts.alpha_doctor as doctor
from backend.app import truth
from backend.app.domain.models import OutboxEvent
from backend.app.notify.outbox import enqueue_in_session
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.live_cycle import ET, missed_evaluation

active = lambda unit: "active"


@pytest.fixture
def green(shadow_env):
    """全部业务与基础设施项都健康的影子盘现场(时间用真实现在,判据里的周二从同一函数推出)。"""
    rt = shadow_env
    now = datetime.now(timezone.utc)
    factory = create_session_factory(init_engine())
    hb = HeartbeatStore(factory)
    for w in doctor.EXPECTED_WORKERS:
        hb.beat(w, status="RUNNING", detail="{'mode': 'SHADOW'}")
    _, _, due = missed_evaluation(now.astimezone(ET), last_completed_tag="", expects=True, since=None)
    (rt / "last_eval_result.json").write_text(json.dumps(
        {"date": due, "completed_at": (now - timedelta(days=1)).isoformat(), "plan": [],
         "submitted": 0, "rejected": 0, "skipped": 0}))
    (rt / "equity_history.json").write_text(json.dumps(
        [{"at": now.isoformat(), "equity_aud": 3012.5}]))
    (rt / "facts").mkdir()
    (rt / "facts" / "backup_status.json").write_text(json.dumps({"at": now.isoformat(), "ok": True}))
    with factory() as s, s.begin():
        eid = enqueue_in_session(s, event_type="DAILY_DIGEST", payload={"text": "在岗"})
        row = s.get(OutboxEvent, eid)
        row.delivery_status, row.delivered_at = "DELIVERED", now - timedelta(hours=2)
    return rt, factory


def test_all_green_exit0_and_red_exit1_names_item(green, capsys):
    rt, _ = green
    assert doctor.main([], systemctl=active) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "系统在岗,今天该做的都做了"
    assert "❌" not in out
    (rt / "equity_history.json").unlink()                       # 净值快照停更
    assert doctor.main([], systemctl=active) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "有 1 件事需要处理"
    red = next(line for line in out.splitlines() if line.startswith("❌"))
    assert "净值快照在更新" in red and "要不要你动手" in red
    assert doctor.main(["--json"], systemctl=active) == 1
    data = json.loads(capsys.readouterr().out)
    assert [c["key"] for c in data["checks"] if not c["ok"]] == ["equity_stale"]


def test_digest_enqueues_daily_digest_with_mode_and_next_eval(green):
    rt, factory = green
    now = datetime.now(timezone.utc)
    text = doctor.digest(doctor.collect(now=now, systemctl=active), now=now)
    with factory() as s:
        rows = [r for r in s.scalars(select(OutboxEvent).where(
            OutboxEvent.event_type == "DAILY_DIGEST", OutboxEvent.delivery_status == "PENDING"))]
    assert len(rows) == 1 and json.loads(rows[0].payload)["text"] == text
    from backend.app.control_page.dashboard_data import _next_decision
    nd = _next_decision(now, rt)
    assert truth.mode_label() in text and "影子盘" in text
    assert nd["at_syd"] in text and "悉尼" in text
    assert "最近一次评估:" in text and "无需调仓" in text
    assert "3,012.50" in text and "基线 3,000" in text
    assert "体检结论:系统在岗" in text


def test_check_env_flags_forbidden_keys(shadow_env, monkeypatch, capsys):
    assert doctor.main(["--check-env"]) == 0
    monkeypatch.setenv("ALPHA_EXPECTED_ACC_ID", "123")
    assert doctor.main(["--check-env"]) == 1
    assert "ALPHA_EXPECTED_ACC_ID" in capsys.readouterr().out
