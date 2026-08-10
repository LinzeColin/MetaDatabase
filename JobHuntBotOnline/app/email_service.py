from __future__ import annotations

import json
import smtplib
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import EmailDelivery, EmailToken, User, utcnow
from .security import CryptoBox, mask_email, random_token, token_hash


class Mailer:
    def __init__(self, settings: Settings, crypto: CryptoBox):
        self.settings = settings
        self.crypto = crypto
        self.outbox_path = settings.upload_root.parent / "test-outbox.json"

    def create_token(self, db: Session, user: User, purpose: str, hours: int) -> str:
        now = utcnow()
        existing = db.scalars(
            select(EmailToken).where(
                EmailToken.user_id == user.id,
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
            )
        ).all()
        for item in existing:
            item.used_at = now
        raw = random_token()
        db.add(
            EmailToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=token_hash(raw),
                expires_at=now + timedelta(hours=hours),
            )
        )
        db.commit()
        return raw

    def consume_token(self, db: Session, raw: str, purpose: str) -> User | None:
        row = db.scalar(
            select(EmailToken).where(
                EmailToken.token_hash == token_hash(raw),
                EmailToken.purpose == purpose,
                EmailToken.used_at.is_(None),
                EmailToken.expires_at > utcnow(),
            )
        )
        if not row:
            return None
        user = db.get(User, row.user_id)
        if not user:
            return None
        row.used_at = utcnow()
        db.commit()
        return user

    def send_verification(self, db: Session, user: User) -> None:
        raw = self.create_token(db, user, "verify", 24)
        link = f"{self.settings.base_url}/verify-email?token={raw}"
        self._send(db, user, "verify", "验证你的 JobHuntBot 邮箱", f"点击下面链接验证邮箱：\n{link}\n\n链接 24 小时有效。")

    def send_reset(self, db: Session, user: User) -> None:
        raw = self.create_token(db, user, "reset", 1)
        link = f"{self.settings.base_url}/reset-password?token={raw}"
        self._send(db, user, "reset", "重置你的 JobHuntBot 密码", f"点击下面链接重置密码：\n{link}\n\n链接 1 小时有效且只能使用一次。")

    def _send(self, db: Session, user: User, kind: str, subject: str, body: str) -> None:
        recipient = self.crypto.decrypt_text(user.email_encrypted)
        delivery = EmailDelivery(
            user_id=user.id,
            kind=kind,
            recipient_masked=mask_email(recipient),
            status="pending",
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        try:
            if self.settings.testing or (self.settings.app_env != "production" and not self.settings.smtp_host):
                self.outbox_path.parent.mkdir(parents=True, exist_ok=True)
                rows = []
                if self.outbox_path.exists():
                    rows = json.loads(self.outbox_path.read_text(encoding="utf-8"))
                rows.append({
                    "to": recipient,
                    "kind": kind,
                    "subject": subject,
                    "body": body,
                })
                self.outbox_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
            elif not self.settings.smtp_host:
                raise RuntimeError("邮件发送尚未配置；请先接入任意标准 SMTP，再开放注册或密码找回。")
            else:
                msg = EmailMessage()
                msg["From"] = self.settings.smtp_from
                msg["To"] = recipient
                msg["Subject"] = subject
                msg.set_content(body)
                with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=20) as server:
                    if self.settings.smtp_starttls:
                        server.starttls()
                    if self.settings.smtp_username:
                        server.login(self.settings.smtp_username, self.settings.smtp_password)
                    server.send_message(msg)
            delivery.status = "sent"
            db.commit()
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = str(exc)[:1000]
            db.commit()
            raise
