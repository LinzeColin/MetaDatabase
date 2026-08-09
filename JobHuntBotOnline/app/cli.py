from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.auth import hash_password, seed_admin
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import AuditLog, Resume, User, json_dumps
from app.services.backup import create_backup, restore_backup
from app.services.canonical import ensure_canonical_export, export_canonical
from app.services.data_migration import migrate_sensitive_storage, verify_sensitive_storage
from app.services.security import decrypt_bytes, encrypt_bytes


settings = get_settings()
ACCEPTANCE_EMAIL_SUFFIX = "@acceptance.invalid"
ACCEPTANCE_DISPLAY_NAME = "Acceptance Probe"


def command_init() -> int:
    init_db()
    with SessionLocal() as db:
        user = seed_admin(db)
    print(json.dumps({"result": "ready", "admin_email": user.email}, ensure_ascii=False))
    return 0


def command_doctor() -> int:
    checks: dict[str, str] = {}
    try:
        init_db()
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ready"
    except Exception as exc:
        checks["database"] = f"failed: {exc}"

    for name in ("uploads", "backups", "canonical"):
        path = settings.data_dir / name
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            checks[name] = "ready"
        except OSError as exc:
            checks[name] = f"failed: {exc}"

    try:
        probe = b"jobhuntos-encryption-probe"
        if decrypt_bytes(encrypt_bytes(probe)) != probe:
            raise ValueError("round trip mismatch")
        checks["encryption"] = "ready"
    except Exception as exc:
        checks["encryption"] = f"failed: {exc}"

    checks["disk_free"] = str(shutil.disk_usage(settings.data_dir).free)
    ok = all(not value.startswith("failed") for value in checks.values())
    print(json.dumps({"result": "ready" if ok else "failed", "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def command_export() -> int:
    init_db()
    with SessionLocal() as db:
        path = ensure_canonical_export(db)
    print(path)
    return 0


def command_reencrypt_sensitive() -> int:
    init_db()
    with SessionLocal() as db:
        result = migrate_sensitive_storage(db)
    print(json.dumps({"result": "ready", **result}, ensure_ascii=False))
    return 0


def command_verify_sensitive_storage() -> int:
    init_db()
    try:
        with SessionLocal() as db:
            result = verify_sensitive_storage(db)
    except Exception as exc:
        print(json.dumps({"result": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps({"result": "ready", **result}, ensure_ascii=False))
    return 0


def command_backup() -> int:
    init_db()
    with SessionLocal() as db:
        path = create_backup(db)
    print(path)
    return 0


def command_restore(source: str, destination: str) -> int:
    src = Path(source).expanduser().resolve()
    dest = Path(destination).expanduser().resolve()
    if not src.is_file():
        print("backup file not found", file=sys.stderr)
        return 2
    restore_backup(src, dest)
    print(dest)
    return 0


def _temporary_password() -> str:
    groups = (
        "ABCDEFGHJKLMNPQRSTUVWXYZ",
        "abcdefghijkmnopqrstuvwxyz",
        "23456789",
        "_-.@",
    )
    chars = [secrets.choice(group) for group in groups]
    alphabet = "".join(groups)
    chars.extend(secrets.choice(alphabet) for _ in range(20))
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def command_reset_owner_password(output: str | None) -> int:
    init_db()
    target = Path(output).expanduser().resolve() if output else settings.data_dir / "OWNER_PASSWORD_RESET.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    new_password = _temporary_password()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == settings.admin_email))
        if not user:
            user = seed_admin(db)
        user.password_hash = hash_password(new_password)
        user.session_version += 1
        db.add(user)
        db.add(
            AuditLog(
                user_id=user.id,
                action="owner_password_reset",
                object_type="user",
                object_id=str(user.id),
                details_json=json_dumps({"delivery_file": target.name}),
            )
        )
        db.commit()
    target.write_text(
        f"JobHuntBot Online Owner password reset\nEmail: {settings.admin_email}\nTemporary password: {new_password}\n\n"
        "Sign in and change this password immediately. Delete this file after secure delivery.\n",
        encoding="utf-8",
    )
    target.chmod(0o640)
    print(json.dumps({"result": "ready", "delivery_file": str(target)}, ensure_ascii=False))
    return 0


def _controlled_upload_paths(db: Session, user_id: int) -> list[Path]:
    uploads_root = (settings.data_dir / "uploads").resolve()
    result: list[Path] = []
    for raw in db.scalars(select(Resume.encrypted_file_path).where(Resume.user_id == user_id)):
        if not raw:
            continue
        path = Path(raw).expanduser().resolve()
        try:
            path.relative_to(uploads_root)
        except ValueError:
            continue
        result.append(path)
    return result


def _delete_acceptance_user_record(db: Session, user: User) -> list[Path]:
    if user.display_name != ACCEPTANCE_DISPLAY_NAME or not user.email.endswith(ACCEPTANCE_EMAIL_SUFFIX):
        raise ValueError("Refusing to delete a non-acceptance user.")
    paths = _controlled_upload_paths(db, user.id)
    db.execute(delete(AuditLog).where(AuditLog.user_id == user.id))
    db.delete(user)
    db.flush()
    return paths


def _remove_controlled_files(paths: list[Path]) -> int:
    removed = 0
    for path in paths:
        try:
            path.unlink(missing_ok=True)
            removed += 1
        except OSError:
            # Database cleanup is already complete. A later housekeeping pass may
            # remove an unreadable orphan without risking deletion outside uploads/.
            continue
    return removed


def command_create_acceptance_user(output: str) -> int:
    init_db()
    target = Path(output).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    stale_paths: list[Path] = []
    with SessionLocal() as db:
        stale = list(
            db.scalars(
                select(User).where(
                    User.display_name == ACCEPTANCE_DISPLAY_NAME,
                    User.email.like(f"%{ACCEPTANCE_EMAIL_SUFFIX}"),
                )
            )
        )
        for user in stale:
            stale_paths.extend(_delete_acceptance_user_record(db, user))

        token = secrets.token_urlsafe(18).replace("_", "").replace("-", "").lower()
        email = f"probe-{token}{ACCEPTANCE_EMAIL_SUFFIX}"
        password = _temporary_password()
        user = User(
            email=email,
            password_hash=hash_password(password),
            display_name=ACCEPTANCE_DISPLAY_NAME,
            is_active=True,
        )
        db.add(user)
        db.commit()
        payload = {"user_id": user.id, "email": email, "password": password}

    _remove_controlled_files(stale_paths)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    target.chmod(0o600)
    print(json.dumps({"result": "ready", "credential_file": str(target)}, ensure_ascii=False))
    return 0


def command_delete_acceptance_user(email: str) -> int:
    init_db()
    normalized = email.strip().lower()
    if not normalized.endswith(ACCEPTANCE_EMAIL_SUFFIX):
        print(json.dumps({"result": "failed", "error": "invalid acceptance identity"}, ensure_ascii=False))
        return 2

    paths: list[Path] = []
    deleted = 0
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == normalized))
        if user is not None:
            try:
                paths = _delete_acceptance_user_record(db, user)
            except ValueError as exc:
                print(json.dumps({"result": "failed", "error": str(exc)}, ensure_ascii=False))
                return 2
            db.commit()
            deleted = 1
        # Refresh the Owner-only canonical projection after the probe is gone.
        export_canonical(db)

    removed_files = _remove_controlled_files(paths)
    print(
        json.dumps(
            {"result": "ready", "deleted_users": deleted, "removed_files": removed_files},
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("doctor")
    sub.add_parser("export")
    sub.add_parser("backup")
    sub.add_parser("reencrypt-sensitive")
    sub.add_parser("verify-sensitive-storage")
    restore = sub.add_parser("restore")
    restore.add_argument("source")
    restore.add_argument("destination")
    reset = sub.add_parser("reset-owner-password")
    reset.add_argument("--output")
    create_probe = sub.add_parser("create-acceptance-user")
    create_probe.add_argument("--output", required=True)
    delete_probe = sub.add_parser("delete-acceptance-user")
    delete_probe.add_argument("--email", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init":
        return command_init()
    if args.command == "doctor":
        return command_doctor()
    if args.command == "export":
        return command_export()
    if args.command == "backup":
        return command_backup()
    if args.command == "reencrypt-sensitive":
        return command_reencrypt_sensitive()
    if args.command == "verify-sensitive-storage":
        return command_verify_sensitive_storage()
    if args.command == "restore":
        return command_restore(args.source, args.destination)
    if args.command == "reset-owner-password":
        return command_reset_owner_password(args.output)
    if args.command == "create-acceptance-user":
        return command_create_acceptance_user(args.output)
    if args.command == "delete-acceptance-user":
        return command_delete_acceptance_user(args.email)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
