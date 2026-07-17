"""Worker 入口公共装配:引擎/心跳/发件箱/杀开关,全部从环境读取,零硬编码秘密。"""

from __future__ import annotations

import os

from backend.app.notify.outbox import Outbox, SmtpEmailSender
from backend.app.store.db import create_session_factory, init_engine
from backend.app.workers.heartbeat import HeartbeatStore
from backend.app.workers.killswitch import KillSwitch


def build_runtime():
    engine = init_engine()  # ALPHA_DATABASE_URL 或本地 SQLite
    factory = create_session_factory(engine)
    return {
        "factory": factory,
        "heartbeats": HeartbeatStore(factory),
        "outbox": Outbox(factory),
        "kill_switch": KillSwitch(os.environ.get("ALPHA_KILL_SWITCH_PATH", "runtime/KILL_SWITCH")),
    }


def build_smtp_sender() -> SmtpEmailSender:
    missing = [k for k in ("ALPHA_SMTP_HOST", "ALPHA_SMTP_USERNAME",
                           "ALPHA_SMTP_APP_PASSWORD", "ALPHA_NOTIFY_RECIPIENT")
               if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"邮件出口缺环境变量(失败关闭,不静默): {missing}")
    return SmtpEmailSender(
        host=os.environ["ALPHA_SMTP_HOST"],
        port=int(os.environ.get("ALPHA_SMTP_PORT", "587")),
        username=os.environ["ALPHA_SMTP_USERNAME"],
        app_password=os.environ["ALPHA_SMTP_APP_PASSWORD"],
        recipient=os.environ["ALPHA_NOTIFY_RECIPIENT"],
    )
