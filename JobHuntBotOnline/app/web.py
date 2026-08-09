from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.auth import get_csrf_token
from app.config import get_settings


settings = get_settings()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _format_datetime(value: Any, fmt: str = "%Y-%m-%d %H:%M") -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo(settings.timezone_name)).strftime(fmt)
    return str(value)


def _status_class(value: str) -> str:
    mapping = {
        "Apply": "success",
        "Applied": "success",
        "Offer": "success",
        "High": "success",
        "Eligible": "success",
        "Fresh": "success",
        "Review": "warning",
        "Needs review": "warning",
        "Needs user": "warning",
        "Needs confirmation": "warning",
        "Medium": "warning",
        "Stretch": "warning",
        "Aging": "warning",
        "Skip": "danger",
        "Rejected": "danger",
        "Ineligible": "danger",
        "Low": "danger",
        "Old": "danger",
        "Blocked": "danger",
        "Interview": "info",
        "Recent": "info",
        "Unknown": "muted",
        "not_configured": "muted",
        "pending_sync": "warning",
        "exported": "warning",
        "synced": "success",
        "failed": "danger",
        "stale": "warning",
        "success": "success",
    }
    return mapping.get(value, "muted")


templates.env.filters["datetime"] = _format_datetime
templates.env.filters["status_class"] = _status_class


def flash(request: Request, message: str, category: str = "info") -> None:
    items = request.session.setdefault("flashes", [])
    items.append({"message": message, "category": category})
    request.session["flashes"] = items[-5:]


def render(
    request: Request,
    name: str,
    *,
    status_code: int = 200,
    user: Any = None,
    **context: Any,
):
    flashes = request.session.pop("flashes", [])
    base_context = {
        "request": request,
        "user": user,
        "csrf_token": get_csrf_token(request),
        "flashes": flashes,
        "app_name": settings.app_name,
        "app_version": settings.app_version,
    }
    base_context.update(context)
    return templates.TemplateResponse(
        request=request,
        name=name,
        context=base_context,
        status_code=status_code,
    )
