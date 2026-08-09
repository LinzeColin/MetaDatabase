from __future__ import annotations

from datetime import datetime, timezone
import os
import secrets

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.config import get_settings
from app.db import SessionLocal
from app.models import User
from app.services.ai_provider import provider_view
from app.services.canonical import read_sync_status


router = APIRouter()
settings = get_settings()


@router.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok", "product": settings.app_name, "version": settings.app_version}


@router.get("/readyz", include_in_schema=False)
def readyz():
    probe = settings.data_dir / "canonical" / f".ready-{os.getpid()}-{secrets.token_hex(4)}"
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        probe.write_text("ready", encoding="utf-8")
        probe.unlink()
    except Exception:
        probe.unlink(missing_ok=True)
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return {"status": "ready"}


@router.get("/api/status", include_in_schema=False)
def api_status():
    sync = read_sync_status()
    ai_state = {"configured": False, "enabled": False, "ready": False}
    try:
        with SessionLocal() as db:
            owner = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.id))
            if owner:
                view = provider_view(db, owner.id)
                ai_state = {
                    "configured": view.configured,
                    "enabled": view.enabled,
                    "ready": view.ready,
                    "fast_model": view.fast_model,
                    "precision_model": view.precision_model,
                }
    except Exception:
        ai_state = {"configured": False, "enabled": False, "ready": False}
    return {
        "status": "ok",
        "product": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "time": datetime.now(timezone.utc).isoformat(),
        "deepseek": ai_state,
        "long_term_sync": {
            "state": sync.get("state", "unknown"),
            "updated_at": sync.get("updated_at", ""),
        },
    }
