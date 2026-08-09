from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User, json_dumps


def record_audit(
    db: Session,
    *,
    user: User | None,
    action: str,
    object_type: str = "",
    object_id: str | int = "",
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            object_type=object_type,
            object_id=str(object_id) if object_id != "" else "",
            details_json=json_dumps(details or {}),
        )
    )
