from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentUser, hash_password, verify_csrf, verify_password
from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, BackupRecord
from app.services.ai_provider import (
    AIProviderError,
    get_or_create_config,
    provider_view,
    revoke_database_key,
    save_provider_config,
    verify_connection,
)
from app.services.audit import record_audit
from app.services.backup import create_backup
from app.services.canonical import ensure_canonical_export, owner_readable_export, read_sync_status
from app.web import flash, render


router = APIRouter()
settings = get_settings()


@router.get("/settings")
def settings_page(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    backups = list(
        db.scalars(select(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(20))
    )
    audit_rows = list(
        db.scalars(
            select(AuditLog)
            .where((AuditLog.user_id == user.id) | (AuditLog.user_id.is_(None)))
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
    )
    ai_provider = provider_view(db, user.id)
    return render(
        request,
        "settings.html",
        user=user,
        sync_status=read_sync_status(),
        backups=backups,
        audit_rows=audit_rows,
        base_url=settings.base_url,
        environment=settings.environment,
        store_original_files=settings.original_file_retention,
        ai_provider=ai_provider,
    )


@router.post("/settings/deepseek")
async def save_deepseek_settings(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    api_key: Annotated[str, Form()] = "",
    default_mode: Annotated[str, Form()] = "fast",
    daily_request_limit: Annotated[str, Form()] = "60",
    daily_token_limit: Annotated[str, Form()] = "600000",
    enabled: Annotated[str | None, Form()] = None,
    consent: Annotated[str | None, Form()] = None,
):
    verify_csrf(request, csrf_token)
    try:
        request_limit = int(daily_request_limit)
        token_limit = int(daily_token_limit)
        config = save_provider_config(
            db,
            user_id=user.id,
            api_key=api_key,
            enabled=bool(enabled),
            consent=bool(consent),
            default_mode=default_mode,
            daily_request_limit=request_limit,
            daily_token_limit=token_limit,
        )
    except (TypeError, ValueError) as exc:
        db.rollback()
        flash(request, str(exc), "danger")
        return RedirectResponse(url="/settings#deepseek", status_code=303)

    if not config.enabled:
        record_audit(
            db,
            user=user,
            action="deepseek_settings_saved",
            object_type="ai_provider",
            details={"enabled": False, "mode": config.default_mode},
        )
        db.commit()
        flash(request, "DeepSeek 设置已安全保存；当前保持停用。规则分析仍正常工作。", "success")
        return RedirectResponse(url="/settings#deepseek", status_code=303)

    try:
        await verify_connection(db, user_id=user.id)
    except AIProviderError as exc:
        config.enabled = False
        db.add(config)
        record_audit(
            db,
            user=user,
            action="deepseek_connection_failed",
            object_type="ai_provider",
            details={"error_code": exc.code},
        )
        db.commit()
        flash(
            request,
            f"{exc.user_message} 密钥仍以加密形式保存，但 DeepSeek 已自动停用；规则分析不受影响。",
            "danger",
        )
        return RedirectResponse(url="/settings#deepseek", status_code=303)

    record_audit(
        db,
        user=user,
        action="deepseek_enabled",
        object_type="ai_provider",
        details={"mode": config.default_mode},
    )
    db.commit()
    flash(request, "DeepSeek 已保存、验证并启用。以后导入岗位会自动增强分析。", "success")
    return RedirectResponse(url="/settings#deepseek", status_code=303)


@router.post("/settings/deepseek/test")
async def test_deepseek_connection(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    config = get_or_create_config(db, user.id)
    try:
        await verify_connection(db, user_id=user.id)
    except AIProviderError as exc:
        config.enabled = False
        db.add(config)
        record_audit(
            db,
            user=user,
            action="deepseek_connection_failed",
            object_type="ai_provider",
            details={"error_code": exc.code},
        )
        db.commit()
        flash(request, f"连通验证失败：{exc.user_message} 规则分析仍可使用。", "danger")
        return RedirectResponse(url="/settings#deepseek", status_code=303)

    config.enabled = True
    db.add(config)
    record_audit(db, user=user, action="deepseek_connection_verified", object_type="ai_provider")
    db.commit()
    flash(request, "DeepSeek 连接验证通过，增强分析已启用。", "success")
    return RedirectResponse(url="/settings#deepseek", status_code=303)


@router.post("/settings/deepseek/revoke")
def revoke_deepseek(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    before = provider_view(db, user.id)
    revoke_database_key(db, user.id)
    record_audit(
        db,
        user=user,
        action="deepseek_revoked",
        object_type="ai_provider",
        details={"previous_key_source": before.key_source},
    )
    db.commit()
    if before.key_source in {"server_environment", "server_secret_file"}:
        flash(
            request,
            "DeepSeek 已在产品中停用。密钥由服务器 Secret 管理；如需彻底删除，请由部署 Agent 删除对应 Secret。",
            "success",
        )
    else:
        flash(request, "网页保存的 DeepSeek 密钥已删除，增强分析已停用。", "success")
    return RedirectResponse(url="/settings#deepseek", status_code=303)


@router.post("/settings/password")
def change_password(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    if not verify_password(current_password, user.password_hash):
        flash(request, "当前密码不正确。", "danger")
        return RedirectResponse(url="/settings#security", status_code=303)
    if new_password != confirm_password:
        flash(request, "两次输入的新密码不一致。", "danger")
        return RedirectResponse(url="/settings#security", status_code=303)
    if len(new_password) < 14 or new_password.lower() == new_password or new_password.upper() == new_password:
        flash(request, "新密码至少 14 位，并同时包含大小写字符。", "danger")
        return RedirectResponse(url="/settings#security", status_code=303)
    user.password_hash = hash_password(new_password)
    user.session_version += 1
    db.add(user)
    record_audit(db, user=user, action="password_changed", object_type="user", object_id=user.id)
    db.commit()
    request.session.clear()
    flash(request, "密码已更新，请使用新密码重新登录。", "success")
    return RedirectResponse(url="/login", status_code=303)


@router.post("/settings/export")
def export_now(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    path = ensure_canonical_export(db)
    record_audit(db, user=user, action="canonical_exported", object_type="system", details={"file": path.name})
    db.commit()
    flash(request, "结构化事实已导出；长期同步状态以本页显示为准。", "success")
    return RedirectResponse(url="/settings#data", status_code=303)


@router.get("/settings/export/download")
def download_export(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    payload = owner_readable_export(db)
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="jobhuntos_owner_export.json"'},
    )


@router.post("/settings/backup")
def backup_now(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
    csrf_token: Annotated[str, Form()],
):
    verify_csrf(request, csrf_token)
    try:
        path = create_backup(db)
    except (OSError, RuntimeError, ValueError) as exc:
        record_audit(db, user=user, action="backup_failed", object_type="system", details={"error": str(exc)})
        db.commit()
        flash(request, "备份创建失败；未改变现有数据。请查看部署诊断。", "danger")
        return RedirectResponse(url="/settings#data", status_code=303)
    record_audit(db, user=user, action="backup_created", object_type="backup", details={"file": path.name})
    db.commit()
    flash(request, "加密备份已创建。", "success")
    return RedirectResponse(url="/settings#data", status_code=303)


@router.get("/settings/backups/{filename}")
def download_backup(
    filename: str,
    request: Request,
    user: CurrentUser,
):
    safe_name = Path(filename).name
    if safe_name != filename or not safe_name.endswith(".jhbbackup"):
        return RedirectResponse(url="/settings#data", status_code=303)
    path = (settings.data_dir / "backups" / safe_name).resolve()
    backups_root = (settings.data_dir / "backups").resolve()
    if path.parent != backups_root or not path.is_file():
        flash(request, "没有找到该备份。", "danger")
        return RedirectResponse(url="/settings#data", status_code=303)
    encoded = quote(safe_name)
    return FileResponse(
        path,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
