"""事务发件箱(ALPHA-LIVE-040,configs/notify.yaml)。

不丢:业务事务内 enqueue,与业务写同生共死。
不重:投递成功即置 DELIVERED;Worker 单实例(与执行网关同租约纪律可选)。
重试:指数退避 1s/5s/25s/125s/625s,超过 max_attempts 置 FAILED 并升级告警。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import OutboxEvent

MAX_ATTEMPTS = 6
BACKOFF_BASE_SECONDS = 1
BACKOFF_FACTOR = 5


class EmailSender(Protocol):
    def send(self, *, subject: str, body: str) -> None: ...


@dataclass
class DeliveryReport:
    delivered: int = 0
    retried: int = 0
    failed_permanently: int = 0


def enqueue_in_session(session: Session, *, event_type: str, payload: dict) -> str:
    """业务事务内入队(事务发件箱核心:与业务写原子)。"""
    row = OutboxEvent(event_type=event_type, payload=json.dumps(payload, ensure_ascii=False, default=str))
    session.add(row)
    session.flush()
    return row.event_id


class Outbox:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._sessions = session_factory
        self._now = now_fn

    def enqueue(self, *, event_type: str, payload: dict) -> str:
        with self._sessions() as session, session.begin():
            return enqueue_in_session(session, event_type=event_type, payload=payload)

    def pending_count(self) -> int:
        with self._sessions() as session:
            return len(session.scalars(
                select(OutboxEvent).where(OutboxEvent.delivery_status == "PENDING")
            ).all())

    def process_once(self, sender: EmailSender) -> DeliveryReport:
        """投递一轮到期的 PENDING 事件。失败退避重试;超限置 FAILED。"""
        report = DeliveryReport()
        now = self._now()
        with self._sessions() as session, session.begin():
            due = session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.delivery_status == "PENDING")
                .order_by(OutboxEvent.created_at)
            ).all()
            for row in due:
                next_at = row.next_attempt_at
                if next_at is not None:
                    if next_at.tzinfo is None:
                        next_at = next_at.replace(tzinfo=timezone.utc)
                    if next_at > now:
                        continue
                payload = json.loads(row.payload)
                subject = f"[Alpha] {row.event_type}"
                body = json.dumps(payload, ensure_ascii=False, indent=2)
                try:
                    sender.send(subject=subject, body=body)
                except Exception as exc:  # 任何发送失败都进入退避,不吞事件
                    row.attempts += 1
                    row.last_error = str(exc)[:500]
                    if row.attempts >= MAX_ATTEMPTS:
                        row.delivery_status = "FAILED"
                        report.failed_permanently += 1
                    else:
                        delay = BACKOFF_BASE_SECONDS * (BACKOFF_FACTOR ** (row.attempts - 1))
                        row.next_attempt_at = now + timedelta(seconds=delay)
                        report.retried += 1
                    continue
                row.delivery_status = "DELIVERED"
                row.delivered_at = now
                row.attempts += 1
                report.delivered += 1
        return report


class SmtpEmailSender:
    """Gmail SMTP(应用专用密码;凭据只从环境读,永不进 Git)。真机验证在部署日。"""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        app_password: str,
        recipient: str,
    ) -> None:
        self._host, self._port = host, port
        self._username, self._password = username, app_password
        self._recipient = recipient

    def send(self, *, subject: str, body: str) -> None:  # pragma: no cover - 真机路径
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._username
        msg["To"] = self._recipient
        with smtplib.SMTP(self._host, self._port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(self._username, self._password)
            smtp.sendmail(self._username, [self._recipient], msg.as_string())
