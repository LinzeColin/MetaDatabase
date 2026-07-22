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


#: 邮件人话模板:owner 只看中文与关键值;URL 独占一行让邮件客户端自动成链。
_EMAIL_TEMPLATES: dict[str, tuple[str, Callable[[dict], str]]] = {
    "DASHBOARD_URL_CHANGED": ("看盘地址更新", lambda p: (
        "你的看盘地址:\n\n"
        f"{p.get('url', '')}\n\n"
        "打开即看,无需任何密码;此页只读,任何人拿到链接也动不了系统。")),
    "DEPLOY_ACCEPTANCE_TEST": ("部署验收测试", lambda p: (
        f"{p.get('msg', '')}\n\n这封邮件本身就是通知链路打通的证据。")),
    "WORKER_HEARTBEAT_LOST": ("系统组件失联,已自动停车保护", lambda p: (
        f"失联组件:{'、'.join(list(p.get('stale', [])) + list(p.get('missing', []))) or '未知'}\n"
        "系统已自动拉下紧急刹车(不会再下任何单),并由守护程序自动拉起恢复。\n"
        "同一故障最多每 6 小时提醒一次;恢复后你会收到一封『已恢复』。")),
    "WORKER_RECOVERED": ("系统组件已恢复", lambda p: (
        "刚才失联的组件已全部恢复心跳。\n"
        "若紧急刹车仍处于拉下状态,恢复交易前会先完成对账核验,无需你操作。")),
    "DAILY_SUMMARY": ("每日小结", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "PAPER_3DAY_REPORT": ("三日模拟盘考核报告", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "DASHBOARD_UPGRADED": ("看盘页升级上线", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
}


def render_email(event_type: str, payload: dict) -> tuple[str, str]:
    """事件 -> (主题, 正文),一律说人话;未知类型退化为『字段:值』行,绝不发裸 JSON。"""
    tpl = _EMAIL_TEMPLATES.get(event_type)
    if tpl is not None:
        title, body_fn = tpl
        return f"【Alpha】{title}", body_fn(payload)
    lines = []
    for k, v in payload.items():
        if isinstance(v, (str, int, float, bool)):
            lines.append(f"{k}:{v}")
        else:
            lines.append(f"{k}:{json.dumps(v, ensure_ascii=False)}")
    return f"【Alpha】{event_type}", "\n".join(lines) or "(无内容)"


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
                subject, body = render_email(row.event_type, payload)
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
