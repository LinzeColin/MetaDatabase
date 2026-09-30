"""告警去重与限流(2026-07-28 复盘 R2:同一故障每拍一封、4626 封陈旧告警淹没收件箱)。

规则:同一 key 只在状态变化时发一封(转坏、恢复);状态持久化,进程重启不重发;
每小时最多 6 封,超出折叠成一封汇总;每日在岗摘要不受上限约束;webhook 只推首发。
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from backend.app.domain.models import OutboxEvent
from backend.app.notify.outbox import AlertBook, Outbox, SmtpEmailSender
from backend.app.store.db import create_session_factory, init_engine

NOW = datetime(2026, 9, 30, 0, 0, tzinfo=timezone.utc)


class Sender:
    def __init__(self, fail_times: int = 0):
        self.fail_times, self.sent = fail_times, []

    def send(self, *, subject: str, body: str) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("SMTP 暂时不可达")
        self.sent.append(subject)


def make(tmp_path, name="a"):
    clock = {"t": NOW}
    factory = create_session_factory(init_engine(f"sqlite:///{tmp_path / f'{name}.sqlite'}"))
    now = lambda: clock["t"]
    return factory, Outbox(factory, now_fn=now), AlertBook(factory, now_fn=now), clock


def statuses(factory):
    with factory() as s:
        return [(r.event_type, r.delivery_status) for r in s.scalars(
            select(OutboxEvent).order_by(OutboxEvent.created_at))]


def test_same_key_100_raises_enqueue_once(tmp_path):
    _, ob, book, clock = make(tmp_path)
    for _ in range(100):
        book.observe("quote_feed", True, payload={"title": "行情源连续取不到"})
        clock["t"] += timedelta(seconds=30)
    assert ob.pending_count() == 1
    assert book.open_alerts()[0]["repeat_count"] == 99


def test_state_survives_new_supervisor_instance(tmp_path):
    """新建 AlertBook(等同守护进程重启)后,同一持续故障不重发。"""
    factory, ob, book, clock = make(tmp_path)
    book.observe("outbox_broken", True, payload={"title": "邮件发不出去"})
    for _ in range(3):
        clock["t"] += timedelta(seconds=30)
        again = AlertBook(factory, now_fn=lambda: clock["t"])
        assert again.observe("outbox_broken", True, payload={"title": "邮件发不出去"}) == ""
    assert ob.pending_count() == 1


def test_flap_one_tick_not_alert_two_ticks_alert(tmp_path):
    _, ob, book, _ = make(tmp_path)
    assert book.observe("hb:trading-worker", True, raise_after=2) == ""
    assert book.observe("hb:trading-worker", False, raise_after=2) == ""    # 抖动:好了,计数清零
    assert book.observe("hb:trading-worker", True, raise_after=2) == ""
    assert ob.pending_count() == 0
    assert book.observe("hb:trading-worker", True, raise_after=2) == "RAISED"
    assert ob.pending_count() == 1


def test_recovery_once_after_six_healthy(tmp_path):
    factory, ob, book, _ = make(tmp_path)
    book.observe("hb:notify-worker", True, payload={"title": "邮件投递失联"})
    for i in range(10):
        state = book.observe("hb:notify-worker", False, clear_after=6)
        assert state == ("RECOVERED" if i == 5 else ""), i
    assert [t for t, _ in statuses(factory)] == ["ALERT_RAISED", "ALERT_RECOVERED"]
    assert book.open_alerts() == []


def test_hourly_cap_folds_7th_digest_exempt(tmp_path):
    factory, ob, _, clock = make(tmp_path)
    sender = Sender()
    for i in range(7):
        ob.enqueue(event_type="ALERT_RAISED", payload={"title": f"问题{i}", "detail": "x"})
        clock["t"] += timedelta(seconds=1)
    ob.enqueue(event_type="DAILY_DIGEST", payload={"text": "在岗"})
    report = ob.process_once(sender)
    assert report.delivered == 7 and report.folded == 1           # 6 封提醒 + 摘要;第 7 封提醒折叠
    assert sum(s.startswith("【Alpha】⚠️") for s in sender.sent) == 6
    assert "【Alpha】每日在岗摘要" in sender.sent
    assert ("ALERT_RAISED", "FOLDED") in statuses(factory)
    clock["t"] += timedelta(minutes=61)                              # 下一窗口:额度恢复
    sender.sent.clear()
    ob.process_once(sender)
    assert sender.sent == ["【Alpha】最近一小时另有 1 条提醒被合并"]
    assert ("ALERT_RAISED", "FOLDED_REPORTED") in statuses(factory)
    ob.process_once(sender)                                          # 汇总只发一次
    assert len(sender.sent) == 1


def test_webhook_only_first_attempt(tmp_path, monkeypatch):
    _, ob, _, clock = make(tmp_path)
    calls = []
    monkeypatch.setattr("backend.app.notify.outbox.post_alert_webhook",
                        lambda subject, body: calls.append(subject))
    ob.enqueue(event_type="ALERT_RAISED", payload={"title": "x", "detail": "y"})
    sender = Sender(fail_times=5)
    for _ in range(6):
        ob.process_once(sender)
        clock["t"] += timedelta(hours=3)
    assert len(sender.sent) == 1 and len(calls) == 1


def test_prune_deletes_old_delivered_only(tmp_path):
    factory, ob, _, clock = make(tmp_path)
    old = NOW - timedelta(days=31)
    from backend.app.notify.outbox import enqueue_in_session
    with factory() as s, s.begin():
        for status in ("DELIVERED", "FOLDED_REPORTED", "PENDING", "FAILED", "FOLDED"):
            eid = enqueue_in_session(s, event_type="ORDER_FILLED", payload={}, created_at=old)
            s.get(OutboxEvent, eid).delivery_status = status
        eid = enqueue_in_session(s, event_type="ORDER_FILLED", payload={}, created_at=NOW)
        s.get(OutboxEvent, eid).delivery_status = "DELIVERED"
    assert ob.prune(30) == 2
    assert sorted(st for _, st in statuses(factory)) == ["DELIVERED", "FAILED", "FOLDED", "PENDING"]


def test_smtp_relay_without_auth(monkeypatch):
    """主机邮件中继:用户名为空不登录、starttls=0 不升级、From 取自配置。"""
    log = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): log.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self): log.append(("starttls",))
        def login(self, u, p): log.append(("login", u))
        def sendmail(self, sender, rcpts, msg): log.append(("sendmail", sender, rcpts, msg))

    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    SmtpEmailSender(host="relay", port=25, recipient="me@example.test",
                    sender="alpha@example.test").send(subject="s", body="b")
    assert [x[0] for x in log] == ["connect", "sendmail"]
    assert log[1][1] == "alpha@example.test" and log[1][2] == ["me@example.test"]
    log.clear()
    SmtpEmailSender(host="smtp", port=587, recipient="me@example.test", sender="a@example.test",
                    username="u", password="p", starttls=True).send(subject="s", body="b")
    assert [x[0] for x in log] == ["connect", "starttls", "login", "sendmail"]
