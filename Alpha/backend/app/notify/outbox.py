"""事务发件箱(ALPHA-LIVE-040,configs/notify.yaml)。

不丢:业务事务内 enqueue,与业务写同生共死。
不重:投递成功即置 DELIVERED;Worker 单实例(与执行网关同租约纪律可选)。
重试:指数退避 1s/5s/25s/125s/625s,超过 max_attempts 置 FAILED 并升级告警。
限流:每小时最多送出 hourly_cap 封(每日在岗摘要不计),超出置 FOLDED,有额度时合成一封汇总。
去重:AlertBook 按 key 记告警状态(持久化),只在「转坏」「恢复」两个状态变化时各发一封。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.domain.models import AlertState, OutboxEvent

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
    folded: int = 0


#: 不受每小时上限约束的事件(每日在岗摘要:死人开关,每天必发)
CAP_EXEMPT_EVENTS = frozenset({"DAILY_DIGEST"})


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
        "同一故障只提醒这一次;恢复后你会收到一封『已恢复』。")),
    "WORKER_RECOVERED": ("系统组件已恢复", lambda p: (
        "刚才失联的组件已全部恢复心跳。\n"
        "若紧急刹车仍处于拉下状态,恢复交易前会先完成对账核验,无需你操作。")),
    "DAILY_SUMMARY": ("每日小结", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "PAPER_3DAY_REPORT": ("三日模拟盘考核报告", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "DASHBOARD_UPGRADED": ("看盘页升级上线", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "FUNDING_NOTICE": ("实盘启动前需要你入金", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "STRATEGY_DECISION": ("策略证据与你的三个选项", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "LIVE_ACTIVATED": ("已自动切换微实盘", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "ACTIVATION_BLOCKED": ("实盘切换暂缓(失败关闭)", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "PRESIGN_RECORDED": ("预签授权已记录", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "WORKER_RESTARTED": ("组件失联超时,守护已自动重启", lambda p: (
        f"失联组件:{'、'.join(p.get('lost', [])) or '未知'};已按序自动重启对应服务。\n"
        "若重启后恢复健康,刹车会在连续健康确认后自动解除,无需你操作;"
        "若持续失联,会按冷却间隔再试并继续提醒你。")),
    "KILL_SWITCH_CLEARED": ("刹车已自动解除,交易恢复", lambda p: (
        "刚才由守护程序自己拍下的紧急刹车,已在连续健康确认后自动解除,系统恢复正常节拍。\n"
        "说明:只有守护自己拍的闸会自动解;你手动拍的闸永远只有你能解。")),
    "INCIDENT_REPORT": ("事故报告与修复", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "UNIT_FAILED": ("定时任务运行失败", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "PRESIGN_SUSPENDED": ("预签授权已按你指令挂起", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "PREFLIGHT_OK": ("盘前自检通过(系统在岗)", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "PREFLIGHT_ALERT": ("⚠️ 盘前自检发现问题,需要处理", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "AUTH_EXPIRING": ("预签授权即将到期,不续签实盘会停", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "LEDGER_BACKUP": ("交易账本备份", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
    "ALERT_RAISED": ("⚠️ {title}", lambda p: (
        f"{p.get('detail', '')}\n\n要不要你动手:{p.get('action', '不用,系统会自动处理。')}\n"
        "同一问题只提醒这一次;恢复后你会收到一封『已恢复』。")),
    "ALERT_RECOVERED": ("✅ 已恢复:{title}", lambda p: (
        f"「{p.get('title', '')}」已恢复正常。\n"
        f"从 {p.get('since', '未知')} 起异常,期间又复查到 {p.get('repeat_count', 0)} 次异常(未重复发信)。")),
    "ALERTS_FOLDED": ("最近一小时另有 {count} 条提醒被合并", lambda p: (
        "为防止告警刷屏,每小时最多发 6 封;超出的提醒已合并如下(主题 × 次数):\n\n"
        + "\n".join(f"· {t} × {n}" for t, n in p.get("by_title", {}).items())
        + "\n\n最新状况以每日在岗摘要与看盘页为准。")),
    "DAILY_DIGEST": ("每日在岗摘要", lambda p: p.get("text", json.dumps(p, ensure_ascii=False))),
}

#: 关键事件:除邮件外,若配置了 ALPHA_ALERT_WEBHOOK 也推一份到第二通道(防 Gmail 单点失效)。
CRITICAL_EVENTS = frozenset({
    "WORKER_HEARTBEAT_LOST", "ACTIVATION_BLOCKED", "UNIT_FAILED", "INCIDENT_REPORT",
    "PREFLIGHT_ALERT", "AUTH_EXPIRING", "ALERT_RAISED",
})


def post_alert_webhook(subject: str, body: str) -> bool:
    """把关键告警推到第二通道(owner 自配的 webhook URL,如 Telegram/Discord/Slack)。

    默认休眠:未设 ALPHA_ALERT_WEBHOOK 时直接返回 False,不做任何事。best-effort,失败不抛。
    """
    import os
    url = os.environ.get("ALPHA_ALERT_WEBHOOK", "").strip()
    if not url:
        return False
    try:
        import urllib.request
        data = json.dumps({"text": f"{subject}\n\n{body}"[:3500]}).encode()
        req = urllib.request.Request(url, data=data,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=8):
            return True
    except Exception:
        return False


def render_email(event_type: str, payload: dict) -> tuple[str, str]:
    """事件 -> (主题, 正文),一律说人话;未知类型退化为『字段:值』行,绝不发裸 JSON。"""
    tpl = _EMAIL_TEMPLATES.get(event_type)
    if tpl is not None:
        title, body_fn = tpl
        return f"【Alpha】{title.format_map(_Blank(payload))}", body_fn(payload)
    lines = []
    for k, v in payload.items():
        if isinstance(v, (str, int, float, bool)):
            lines.append(f"{k}:{v}")
        else:
            lines.append(f"{k}:{json.dumps(v, ensure_ascii=False)}")
    return f"【Alpha】{event_type}", "\n".join(lines) or "(无内容)"


class _Blank(dict):
    """主题占位符取值:载荷里没有的键渲染为空,绝不因缺字段抛错丢信。"""

    def __missing__(self, key: str) -> str:
        return ""


def enqueue_in_session(session: Session, *, event_type: str, payload: dict,
                       created_at: Optional[datetime] = None) -> str:
    """业务事务内入队(事务发件箱核心:与业务写原子)。"""
    row = OutboxEvent(event_type=event_type, payload=json.dumps(payload, ensure_ascii=False, default=str))
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    session.flush()
    return row.event_id


class Outbox:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        hourly_cap: Optional[int] = None,
    ) -> None:
        self._sessions = session_factory
        self._now = now_fn
        if hourly_cap is None:
            from backend.app.health import load_thresholds
            hourly_cap = int(load_thresholds()["hourly_cap"])
        self._hourly_cap = hourly_cap

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._sessions

    def enqueue(self, *, event_type: str, payload: dict) -> str:
        with self._sessions() as session, session.begin():
            return enqueue_in_session(session, event_type=event_type, payload=payload,
                                      created_at=self._now())

    def pending_count(self) -> int:
        with self._sessions() as session:
            return len(session.scalars(
                select(OutboxEvent).where(OutboxEvent.delivery_status == "PENDING")
            ).all())

    def process_once(self, sender: EmailSender) -> DeliveryReport:
        """投递一轮到期的 PENDING 事件。失败退避重试;超限置 FAILED;超出每小时上限置 FOLDED。

        **发信绝不在持写锁的事务里**:SMTP 最长 15 秒,占着 SQLite 写锁会让交易进程的心跳/网关写入
        超过 busy_timeout 抛错崩溃。分三步,每步都是短事务:①领取(折叠汇总入队、挑出到期行)
        并提交;②事务外逐封发信;③每封发完立刻用短事务回写结果。
        """
        report = DeliveryReport()
        now = self._now()
        with self._sessions() as session, session.begin():
            sent = session.scalars(
                select(OutboxEvent.event_type)
                .where(OutboxEvent.delivery_status == "DELIVERED",
                       OutboxEvent.delivered_at >= now - timedelta(hours=1))
            ).all()
            budget = self._hourly_cap - sum(1 for t in sent if t not in CAP_EXEMPT_EVENTS)
            due_ids: list[str] = []
            summary_id = ""
            folded = session.scalars(
                select(OutboxEvent).where(OutboxEvent.delivery_status == "FOLDED")
                .order_by(OutboxEvent.created_at)
            ).all()
            if folded and budget > 0:
                # 有额度了:被折叠的提醒按主题计数合成一封,原行标记已汇报(不再单发)
                by_title: dict[str, int] = {}
                for row in folded:
                    subject = render_email(row.event_type, json.loads(row.payload))[0]
                    title = subject.removeprefix("【Alpha】")
                    by_title[title] = by_title.get(title, 0) + 1
                    row.delivery_status = "FOLDED_REPORTED"
                summary_id = enqueue_in_session(
                    session, event_type="ALERTS_FOLDED",
                    payload={"count": len(folded), "by_title": by_title}, created_at=now)
                due_ids.append(summary_id)
            due_ids += session.scalars(
                select(OutboxEvent.event_id)
                .where(OutboxEvent.delivery_status == "PENDING",
                       OutboxEvent.event_id != summary_id)
                .order_by(OutboxEvent.created_at)
            ).all()

        delivered_any = False
        for event_id in due_ids:
            with self._sessions() as session:
                row = session.get(OutboxEvent, event_id)
                if row is None or row.delivery_status != "PENDING":
                    continue
                next_at, attempts = row.next_attempt_at, row.attempts
                event_type, raw_payload = row.event_type, row.payload
            if next_at is not None:
                if next_at.tzinfo is None:
                    next_at = next_at.replace(tzinfo=timezone.utc)
                if next_at > now:
                    continue
            capped = event_type not in CAP_EXEMPT_EVENTS
            if capped and budget <= 0:
                self._mark(event_id, delivery_status="FOLDED")
                report.folded += 1
                continue
            subject, body = render_email(event_type, json.loads(raw_payload))
            if event_type in CRITICAL_EVENTS and attempts == 0:
                # 第二通道:与邮件并行、互不依赖;只推首发,重试不再重复推
                post_alert_webhook(subject, body)
            try:
                sender.send(subject=subject, body=body)
            except Exception as exc:  # 任何发送失败都进入退避,不吞事件
                attempts += 1
                fields: dict = {"attempts": attempts, "last_error": str(exc)[:500]}
                if attempts >= MAX_ATTEMPTS:
                    fields["delivery_status"] = "FAILED"
                    report.failed_permanently += 1
                else:
                    delay = BACKOFF_BASE_SECONDS * (BACKOFF_FACTOR ** (attempts - 1))
                    fields["next_attempt_at"] = now + timedelta(seconds=delay)
                    report.retried += 1
                self._mark(event_id, **fields)
                continue
            self._mark(event_id, delivery_status="DELIVERED", delivered_at=now,
                       attempts=attempts + 1)
            report.delivered += 1
            delivered_any = True
            if capped:
                budget -= 1
        if delivered_any:
            self._revive_failed(now)
        return report

    def _mark(self, event_id: str, **fields) -> None:
        """短事务回写一行的投递结果。"""
        with self._sessions() as session, session.begin():
            row = session.get(OutboxEvent, event_id)
            for k, v in fields.items():
                setattr(row, k, v)

    def _revive_failed(self, now: datetime) -> None:
        """邮件中继恢复(刚有一封送达)后,把近 24 小时内永久失败的告警重新排队:
        中继重启超过退避总长(约 13 分钟)不该让告警永久丢失。重投仍受每小时上限约束。"""
        with self._sessions() as session, session.begin():
            for row in session.scalars(select(OutboxEvent).where(
                    OutboxEvent.delivery_status == "FAILED",
                    OutboxEvent.created_at >= now - timedelta(hours=24))):
                row.delivery_status, row.attempts, row.next_attempt_at = "PENDING", 0, None

    def prune(self, days: int = 30) -> int:
        """删掉 days 天前已送达/已汇报的行,库不臃肿;PENDING/FAILED/FOLDED 一律保留。"""
        cutoff = self._now() - timedelta(days=days)
        with self._sessions() as session, session.begin():
            result = session.execute(
                delete(OutboxEvent).where(
                    OutboxEvent.delivery_status.in_(("DELIVERED", "FOLDED_REPORTED")),
                    OutboxEvent.created_at < cutoff))
            return int(result.rowcount or 0)


class AlertBook:
    """告警状态簿:同一 key 只在状态变化时入队(转坏一封、恢复一封),状态持久化。

    状态迁移与入队在同一事务:要么都成,要么都不成,重启后不重发、不漏发。
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._sessions = session_factory
        self._now = now_fn

    def observe(self, key: str, bad: bool, *, event_type: str = "ALERT_RAISED",
                payload: Optional[dict] = None, raise_after: int = 1, clear_after: int = 1,
                hold_seconds: float = 0.0) -> str:
        """记一次检查结果。返回 "RAISED"(本次转坏并入队)、"RECOVERED"(本次恢复并入队)或 ""。

        转坏:OK 状态下连续 raise_after 次坏、且这轮坏已持续 hold_seconds 秒。
        恢复:FIRING 状态下连续 clear_after 次好。FIRING 期间再坏只累加 repeat_count,不发信。
        """
        payload = dict(payload or {})
        now = self._now()
        with self._sessions() as session, session.begin():
            row = session.get(AlertState, key)
            if row is None:
                row = AlertState(key=key, status="OK", bad_streak=0, good_streak=0,
                                 repeat_count=0, last_text="")
                session.add(row)
            if bad:
                row.good_streak = 0
                if row.since is None:
                    row.since = now
                row.bad_streak += 1
                if row.status == "FIRING":
                    row.repeat_count += 1
                    return ""
                held = (now - _aware(row.since)).total_seconds()
                if row.bad_streak >= raise_after and held >= hold_seconds:
                    row.status = "FIRING"
                    row.last_notified = now
                    row.repeat_count = 0
                    row.last_text = str(payload.get("title", key))
                    payload.setdefault("key", key)
                    enqueue_in_session(session, event_type=event_type, payload=payload,
                                       created_at=now)
                    return "RAISED"
                return ""
            row.bad_streak = 0
            if row.status != "FIRING":
                row.since = None
                return ""
            row.good_streak += 1
            if row.good_streak < clear_after:
                return ""
            enqueue_in_session(session, event_type="ALERT_RECOVERED", payload={
                "key": key, "title": row.last_text or key,
                "since": _aware(row.since).isoformat() if row.since else "",
                "repeat_count": row.repeat_count}, created_at=now)
            row.status, row.good_streak, row.since = "OK", 0, None
            row.last_notified = now
            return "RECOVERED"

    def bad_since(self, key: str) -> Optional[datetime]:
        """这一轮「坏」从何时开始(未在坏 = None)。只读。"""
        with self._sessions() as session:
            row = session.get(AlertState, key)
            return _aware(row.since) if row is not None and row.since is not None else None

    def retire_stale(self, prefix: str, keep: set[str]) -> int:
        """把带日期的旧 key(同前缀、不在 keep 里)静默收回 OK:新一期的 key 已接手叙事,不发信。"""
        with self._sessions() as session, session.begin():
            rows = session.scalars(select(AlertState).where(
                AlertState.key.startswith(prefix), AlertState.status == "FIRING")).all()
            n = 0
            for row in rows:
                if row.key in keep:
                    continue
                row.status, row.bad_streak, row.good_streak, row.since = "OK", 0, 0, None
                n += 1
            return n

    def open_alerts(self) -> list[dict]:
        """尚未恢复的告警(体检与摘要用)。"""
        with self._sessions() as session:
            rows = session.scalars(select(AlertState).where(AlertState.status == "FIRING")
                                   .order_by(AlertState.key)).all()
            return [{"key": r.key, "title": r.last_text or r.key,
                     "since": _aware(r.since).isoformat() if r.since else "",
                     "repeat_count": r.repeat_count} for r in rows]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class SmtpEmailSender:
    """SMTP 出口:可接主机邮件中继(无认证、明文回环)或 Gmail(STARTTLS + 应用专用密码)。

    凭据只从环境读,永不进 Git。用户名为空时不登录;starttls 由配置决定;发件人独立配置。
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        recipient: str,
        sender: str,
        username: str = "",
        password: str = "",
        starttls: bool = False,
    ) -> None:
        self._host, self._port = host, port
        self._recipient, self._sender = recipient, sender
        self._username, self._password = username, password
        self._starttls = starttls

    def send(self, *, subject: str, body: str) -> None:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = self._sender
        msg["To"] = self._recipient
        with smtplib.SMTP(self._host, self._port, timeout=15) as smtp:
            if self._starttls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.sendmail(self._sender, [self._recipient], msg.as_string())
