"""把报告发到 Owner 邮箱：经 VPS-3 上的本机邮件中继（linze-smtp-bridge），不需要密码。

只在基金净值日期前进时发一封（每个工作日最多一封），净值没更新就不重复发。
没配置 SERENITY_SMTP_HOST / SERENITY_MAIL_TO 时整步跳过（本地测试、公开仓都不带收件人）。
"""

from __future__ import annotations

import json
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Callable


def mail_config(env: dict[str, str] | None = None) -> dict[str, str] | None:
    env = dict(os.environ) if env is None else env
    host, to = env.get("SERENITY_SMTP_HOST", "").strip(), env.get("SERENITY_MAIL_TO", "").strip()
    if not host or not to:
        return None
    return {
        "host": host,
        "port": env.get("SERENITY_SMTP_PORT", "25").strip() or "25",
        "from": env.get("SERENITY_MAIL_FROM", "").strip() or to,
        "to": to,
    }


def _state_path(data_dir: Path) -> Path:
    return data_dir / "mail_state.json"


def last_mailed_nav_date(data_dir: Path) -> str:
    try:
        return str(json.loads(_state_path(data_dir).read_text(encoding="utf-8")).get("nav_date") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def subject_for(result: dict[str, object], nav_date: str) -> str:
    recs = [r for r in (result.get("recommendations") or []) if isinstance(r, dict)]
    recs.sort(key=lambda r: r.get("rank") or 999)
    if recs:
        name = f"{recs[0].get('asset_name') or ''}（{recs[0].get('asset_code') or ''}）"
    else:
        top = result.get("top5") or []
        name = str(top[0]) if top else "无候选"
    return f"Serenity 基金日报 · 净值 {nav_date} · 第一名 {name}"


def maybe_send(
    data_dir: Path,
    result: dict[str, object],
    health: dict[str, object],
    report_html: str,
    report_md: str,
    *,
    config: dict[str, str] | None = None,
    smtp_factory: Callable[[str, int], smtplib.SMTP] = lambda h, p: smtplib.SMTP(h, p, timeout=30),
) -> dict[str, object]:
    config = mail_config() if config is None else config
    if not config:
        return {"mail": "not_configured"}
    nav_date = str(health.get("latest_nav_date") or "")
    if not nav_date or health.get("status") != "ok":
        return {"mail": "skipped_data_not_ok"}
    if nav_date <= last_mailed_nav_date(data_dir):
        return {"mail": "skipped_same_nav_date", "nav_date": nav_date}
    msg = EmailMessage()
    msg["Subject"] = subject_for(result, nav_date)
    msg["From"] = config["from"]
    msg["To"] = config["to"]
    msg.set_content(report_md)
    msg.add_alternative(report_html, subtype="html")
    with smtp_factory(config["host"], int(config["port"])) as smtp:
        smtp.send_message(msg)
    _state_path(data_dir).write_text(json.dumps({"nav_date": nav_date, "run_id": result.get("run_id")}, ensure_ascii=False), encoding="utf-8")
    return {"mail": "sent", "nav_date": nav_date}
