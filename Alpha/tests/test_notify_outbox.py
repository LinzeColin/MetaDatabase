"""ALPHA-LIVE-040:事务发件箱——投递重试、退避、不重投、永久失败升级。"""

from datetime import datetime, timedelta, timezone

from backend.app.notify.outbox import MAX_ATTEMPTS, Outbox
from backend.app.store.db import create_session_factory, init_engine

NOW = datetime(2026, 7, 17, 16, 0, tzinfo=timezone.utc)


class FlakySender:
    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.sent: list[str] = []

    def send(self, *, subject: str, body: str) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("SMTP 暂时不可达")
        self.sent.append(subject)


def make_outbox(tmp_path):
    clock = {"t": NOW}
    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'outbox.sqlite'}"))
    ob = Outbox(f, now_fn=lambda: clock["t"])
    return ob, clock


def test_delivery_success_marks_delivered_once(tmp_path):
    ob, _ = make_outbox(tmp_path)
    ob.enqueue(event_type="ORDER_FILLED", payload={"order": "x"})
    sender = FlakySender()
    r1 = ob.process_once(sender)
    assert (r1.delivered, ob.pending_count()) == (1, 0)
    r2 = ob.process_once(sender)          # 已投递不重投
    assert r2.delivered == 0
    assert sender.sent == ["[Alpha] ORDER_FILLED"]


def test_retry_with_backoff_until_success(tmp_path):
    ob, clock = make_outbox(tmp_path)
    ob.enqueue(event_type="RISK_BLOCKED", payload={})
    sender = FlakySender(fail_times=2)

    assert ob.process_once(sender).retried == 1     # 失败 1:退避 1s
    assert ob.process_once(sender).retried == 0     # 未到期,不重试
    clock["t"] = NOW + timedelta(seconds=2)
    assert ob.process_once(sender).retried == 1     # 失败 2:退避 5s
    clock["t"] = NOW + timedelta(seconds=10)
    assert ob.process_once(sender).delivered == 1   # 第三次成功
    assert ob.pending_count() == 0


def test_permanent_failure_after_max_attempts(tmp_path):
    ob, clock = make_outbox(tmp_path)
    ob.enqueue(event_type="DAILY_SUMMARY", payload={})
    sender = FlakySender(fail_times=99)
    for i in range(MAX_ATTEMPTS):
        clock["t"] = NOW + timedelta(hours=i)       # 跳过全部退避窗
        ob.process_once(sender)
    assert ob.pending_count() == 0                  # 不再 PENDING
    from sqlalchemy import select
    from backend.app.domain.models import OutboxEvent

    with ob._sessions() as session:  # noqa: SLF001
        row = session.scalars(select(OutboxEvent)).one()
        assert row.delivery_status == "FAILED"
        assert row.attempts == MAX_ATTEMPTS
        assert "SMTP" in row.last_error


def test_enqueue_is_transactional_with_business_write(tmp_path):
    """业务事务回滚时,发件箱事件必须一并消失(不丢不重的『不重』面)。"""
    from backend.app.notify.outbox import enqueue_in_session

    f = create_session_factory(init_engine(f"sqlite:///{tmp_path / 'tx.sqlite'}"))
    try:
        with f() as session, session.begin():
            enqueue_in_session(session, event_type="WILL_ROLLBACK", payload={})
            raise RuntimeError("业务失败")
    except RuntimeError:
        pass
    ob = Outbox(f)
    assert ob.pending_count() == 0
