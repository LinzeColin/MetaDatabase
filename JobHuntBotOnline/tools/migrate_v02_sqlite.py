#!/usr/bin/env python3
"""Migrate one v0.2.0 Owner SQLite database into the v0.3.0 SaaS schema.

The source database is opened read-only. Private fields and upload bytes are
re-encrypted with the v0.3 key. The old user-level DeepSeek key is never written
into the SaaS business database; with explicit authorization it can be written to
one mode-0600 server Secret file.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings
from app.db import Base, make_engine, make_session_factory
from app.discovery import NormalizedJob, _upsert_job, enrich
from app.models import (
    AIUsage, ApplicationEvent, ApplicationPack, CandidateProfile, Experience,
    Job, PlatformState, Recommendation, Resume, User, utcnow,
)
from app.security import CryptoBox, email_lookup, normalize_email

PREFIX = "enc:v1:"
MARKER = "migration_v02_sqlite_complete"


def connect_source(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()))}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def tables(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def rows(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if table not in tables(conn):
        return []
    return list(conn.execute(f'SELECT * FROM "{table}"'))


def old_plain(value: Any, cipher: Fernet) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text.startswith(PREFIX):
        return text
    token = text.removeprefix(PREFIX).encode("ascii")
    try:
        return cipher.decrypt(token).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("v0.2 encrypted field cannot be decrypted with OLD_DATA_ENCRYPTION_KEY") from exc


def old_json(value: Any, cipher: Fernet, default: Any) -> Any:
    text = old_plain(value, cipher)
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def old_bool(value: Any, cipher: Fernet) -> str:
    if value is None or value == "":
        return ""
    text = old_plain(value, cipher).strip().casefold()
    if text in {"1", "true", "yes", "on"}:
        return "yes"
    if text in {"0", "false", "no", "off"}:
        return "no"
    return "uncertain"


def dt(value: Any) -> datetime | None:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def label(value: str, mapping: dict[str, str], default: str) -> str:
    folded = value.casefold()
    for token, target in mapping.items():
        if token in folded:
            return target
    return default


def read_old_upload(old_root: Path, stored_path: str, old_cipher: Fernet, fallback: bytes) -> bytes:
    if not stored_path:
        return fallback
    path = Path(stored_path)
    if not path.is_absolute():
        path = old_root / path
    if not path.is_file():
        return fallback
    raw = path.read_bytes()
    try:
        return old_cipher.decrypt(raw)
    except InvalidToken:
        # A controlled legacy database may point to an unencrypted file.
        return raw


def migrate(args: argparse.Namespace) -> dict[str, Any]:
    source = Path(args.source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    old_key = args.old_key or os.getenv("OLD_DATA_ENCRYPTION_KEY", "")
    if not old_key:
        raise RuntimeError("OLD_DATA_ENCRYPTION_KEY is required")
    old_cipher = Fernet(old_key.encode("ascii"))
    settings = get_settings()
    target_key = args.target_key or settings.data_encryption_key
    crypto = CryptoBox(target_key)
    engine = make_engine(args.target_database_url or settings.database_url)
    if args.allow_create_schema:
        Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    conn = connect_source(source)
    source_tables = tables(conn)
    required = {"users", "candidate_profiles", "resumes", "experiences", "jobs", "application_packs"}
    missing = sorted(required - source_tables)
    if missing:
        raise RuntimeError("source v0.2 database is missing tables: " + ", ".join(missing))

    counts = defaultdict(int)
    old_root = Path(args.old_data_root).resolve() if args.old_data_root else source.parent
    with factory() as db:
        marker = db.get(PlatformState, MARKER)
        if marker and not args.force:
            return {"verdict": "NO_CHANGE", "reason": "v0.2 migration marker already exists", "counts": {}}

        user_rows = rows(conn, "users")
        if not user_rows:
            raise RuntimeError("source database has no owner user")
        old_user = user_rows[0]
        old_user_id = int(old_user["id"])
        email = normalize_email(str(old_user["email"]))
        lookup = email_lookup(email, settings.email_lookup_secret)
        user = db.scalar(select(User).where(User.email_lookup == lookup))
        if not user:
            user = User(
                email_lookup=lookup,
                email_encrypted=crypto.encrypt_text(email),
                display_name_encrypted=crypto.encrypt_text(str(old_user["display_name"] or "Owner")),
                password_hash=str(old_user["password_hash"]),
                is_verified=True,
                is_active=bool(old_user["is_active"]),
                is_admin=True,
                auth_version=max(1, int(old_user["session_version"] or 1)),
                daily_ai_request_limit=settings.deepseek_default_user_request_limit,
                created_at=dt(old_user["created_at"]) or utcnow(),
                last_login_at=dt(old_user["last_login_at"]),
                verified_at=utcnow(),
            )
            db.add(user); db.flush(); counts["users"] += 1
        old_to_new_resume: dict[int, int] = {}
        old_to_new_job: dict[int, int] = {}

        profiles = [r for r in rows(conn, "candidate_profiles") if int(r["user_id"]) == old_user_id]
        if profiles:
            p = profiles[0]
            payload = {
                "primary_role_families": old_json(p["target_roles_json"], old_cipher, []),
                "secondary_role_families": old_json(p["secondary_roles_json"], old_cipher, []),
                "target_locations": old_json(p["target_locations_json"], old_cipher, []),
                "work_mode": [x.strip().casefold() for x in old_plain(p["work_mode"], old_cipher).replace("/", ",").split(",") if x.strip()],
                "skills": [],
                "keywords": [],
                "work_authorization": old_plain(p["work_authorization_text"], old_cipher),
                "sponsorship_now": old_bool(p["sponsorship_now"], old_cipher),
                "sponsorship_future": old_bool(p["sponsorship_future"], old_cipher),
                "relocation": old_plain(p["relocation_policy"], old_cipher),
                "available_start": old_plain(p["available_start_date"], old_cipher),
                "avoid_roles": old_json(p["roles_to_avoid_json"], old_cipher, []),
                "avoid_industries": old_json(p["industries_to_avoid_json"], old_cipher, []),
            }
            row = db.scalar(select(CandidateProfile).where(CandidateProfile.user_id == user.id))
            if not row:
                row = CandidateProfile(user_id=user.id, payload_encrypted=crypto.encrypt_json(payload))
                db.add(row); counts["profiles"] += 1
            else:
                row.payload_encrypted = crypto.encrypt_json(payload)
            row.onboarding_state = "complete" if bool(p["onboarding_completed"]) else "needs_resume"
            row.discovery_enabled = bool(p["onboarding_completed"])
            row.next_discovery_at = utcnow() if row.discovery_enabled else None

        for r in rows(conn, "resumes"):
            if int(r["user_id"]) != old_user_id:
                continue
            text = old_plain(r["extracted_text"], old_cipher)
            source_name = old_plain(r["source_filename"], old_cipher) or "migrated-resume.txt"
            original = read_old_upload(old_root, str(r["encrypted_file_path"] or ""), old_cipher, text.encode("utf-8"))
            storage_name = f"migrated-{old_user_id}-{int(r['id'])}.bin"
            settings.upload_root.mkdir(parents=True, exist_ok=True)
            (settings.upload_root / storage_name).write_bytes(crypto.fernet.encrypt(original))
            parsed = {"skills": old_json(r["skills_json"], old_cipher, []), "role_families": [old_plain(r["role_family"], old_cipher)]}
            new = Resume(
                user_id=user.id,
                original_name_encrypted=crypto.encrypt_text(source_name),
                storage_name=storage_name,
                text_encrypted=crypto.encrypt_text(text),
                parsed_encrypted=crypto.encrypt_json(parsed),
                content_type=str(r["file_type"] or "application/octet-stream"),
                size_bytes=len(original),
                is_primary=bool(r["is_default"]),
                created_at=dt(r["created_at"]) or utcnow(),
            )
            db.add(new); db.flush(); old_to_new_resume[int(r["id"])] = new.id; counts["resumes"] += 1

        for r in rows(conn, "experiences"):
            if int(r["user_id"]) != old_user_id:
                continue
            title = old_plain(r["title"], old_cipher)
            organization = old_plain(r["organization"], old_cipher)
            date_range = old_plain(r["date_range"], old_cipher)
            detail_parts = [old_plain(r["description"], old_cipher), organization, date_range]
            detail = " · ".join(x for x in detail_parts if x)
            db.add(Experience(
                user_id=user.id,
                title_encrypted=crypto.encrypt_text(title or "Migrated experience"),
                detail_encrypted=crypto.encrypt_text(detail),
                kind=str(r["category"] or "experience"),
                strength="medium",
                created_at=dt(r["created_at"]) or utcnow(),
            )); counts["experiences"] += 1

        for r in rows(conn, "jobs"):
            if int(r["user_id"]) != old_user_id:
                continue
            item = enrich(NormalizedJob(
                source=f"v02:{str(r['source'] or 'manual')[:36]}",
                external_id=f"owner-{old_user_id}-job-{int(r['id'])}",
                owner_user_id=user.id,
                url=str(r["url"] or ""),
                title=str(r["title"] or "Unknown role"),
                company=str(r["company"] or "Unknown company"),
                location=str(r["location"] or ""),
                description=str(r["description"] or r["snapshot_text"] or ""),
                posted_at=dt(r["posted_date"]),
                skills=old_json(r["matched_skills_json"], old_cipher, []),
            ))
            job, _ = _upsert_job(db, item)
            old_to_new_job[int(r["id"])] = job.id
            rec = Recommendation(
                user_id=user.id,
                job_id=job.id,
                qualification=label(str(r["eligibility_status"]), {"eligible":"pass","pass":"pass","ineligible":"fail","fail":"fail"}, "pending"),
                relevance=label(str(r["fit_label"]), {"high":"high","strong":"high","medium":"medium","low":"low"}, "medium"),
                opportunity=label(str(r["recommendation"]), {"priorit":"high","apply":"high","skip":"low","avoid":"low"}, "medium"),
                rank_score=50,
                reasons_encrypted=crypto.encrypt_json(old_json(r["reasons_json"], old_cipher, [])),
                user_status="applied" if r["applied_at"] else "new",
                first_recommended_at=dt(r["created_at"]) or utcnow(),
                last_scored_at=dt(r["updated_at"]) or utcnow(),
            )
            db.add(rec); counts["jobs"] += 1; counts["recommendations"] += 1

        db.flush()
        for r in rows(conn, "application_packs"):
            if int(r["user_id"]) != old_user_id or int(r["job_id"]) not in old_to_new_job:
                continue
            content = {
                "job_title": db.get(Job, old_to_new_job[int(r["job_id"])]).title,
                "company": db.get(Job, old_to_new_job[int(r["job_id"])]).company,
                "job_url": db.get(Job, old_to_new_job[int(r["job_id"])]).url,
                "resume": "Migrated resume",
                "answers": {
                    "why_role": old_plain(r["why_role_draft"], old_cipher),
                    "why_company": old_plain(r["why_company_draft"], old_cipher),
                    "work_authorization": old_plain(r["work_authorization_answer"], old_cipher),
                    "sponsorship_now": old_plain(r["sponsorship_answer"], old_cipher),
                    "sponsorship_future": old_plain(r["sponsorship_answer"], old_cipher),
                    "available_start": "",
                },
                "selected_experiences": [],
                "review_required": json.loads(str(r["checklist_json"] or "[]")),
                "migrated_from_v02": True,
            }
            db.add(ApplicationPack(
                user_id=user.id,
                job_id=old_to_new_job[int(r["job_id"])],
                resume_id=old_to_new_resume.get(int(r["resume_id"])) if r["resume_id"] else None,
                content_encrypted=crypto.encrypt_json(content),
                created_at=dt(r["created_at"]) or utcnow(),
            )); counts["application_packs"] += 1

        for r in rows(conn, "job_events"):
            if int(r["user_id"]) != old_user_id or int(r["job_id"]) not in old_to_new_job:
                continue
            status = label(str(r["event_type"]), {
                "submit":"submitted", "apply":"submitted", "interview":"interview", "reject":"rejected",
                "offer":"offer", "withdraw":"withdrawn",
            }, "pending")
            note = old_plain(r["note"], old_cipher)
            db.add(ApplicationEvent(
                user_id=user.id,
                job_id=old_to_new_job[int(r["job_id"])],
                status=status,
                notes_encrypted=crypto.encrypt_text(note) if note else None,
                created_at=dt(r["occurred_at"]) or utcnow(),
            )); counts["application_events"] += 1

        usage_by_day: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
        for r in rows(conn, "ai_usage_records"):
            if int(r["user_id"]) != old_user_id:
                continue
            day = (dt(r["created_at"]) or utcnow()).date().isoformat()
            requests, tokens = usage_by_day[day]
            usage_by_day[day] = (requests + 1, tokens + int(r["total_tokens"] or 0))
        for day, (requests, tokens) in usage_by_day.items():
            db.add(AIUsage(scope_key=f"user:{user.id}", user_id=user.id, day_key=day, requests=requests, tokens=tokens))
            counts["ai_usage_days"] += 1

        if args.platform_key_output and "ai_provider_configs" in source_tables:
            config_rows = [r for r in rows(conn, "ai_provider_configs") if int(r["user_id"]) == old_user_id]
            if config_rows:
                key = old_plain(config_rows[0]["api_key"], old_cipher).strip()
                if key:
                    destination = Path(args.platform_key_output)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_text(key, encoding="utf-8")
                    os.chmod(destination, 0o600)
                    counts["platform_key_secret_file"] = 1

        marker = db.get(PlatformState, MARKER) or PlatformState(key=MARKER)
        marker.value = json.dumps({"source_name": source.name, "migrated_at": utcnow().isoformat(), "counts": dict(counts)}, separators=(",", ":"))
        db.add(marker)
        db.commit()

        readback = {
            "users": db.scalar(select(func.count(User.id))) or 0,
            "profiles": db.scalar(select(func.count(CandidateProfile.id)).where(CandidateProfile.user_id == user.id)) or 0,
            "resumes": db.scalar(select(func.count(Resume.id)).where(Resume.user_id == user.id)) or 0,
            "experiences": db.scalar(select(func.count(Experience.id)).where(Experience.user_id == user.id)) or 0,
            "recommendations": db.scalar(select(func.count(Recommendation.id)).where(Recommendation.user_id == user.id)) or 0,
            "packs": db.scalar(select(func.count(ApplicationPack.id)).where(ApplicationPack.user_id == user.id)) or 0,
        }
        if readback["users"] < 1 or readback["profiles"] < 1:
            raise RuntimeError("migration readback failed")

    conn.close(); engine.dispose()
    return {
        "verdict": "PASS",
        "source": source.name,
        "target": "configured database",
        "counts": dict(counts),
        "readback": readback,
        "old_platform_key_in_business_db": False,
        "secret_values_printed": False,
        "production_claimed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--old-data-root", default="")
    parser.add_argument("--old-key", default="")
    parser.add_argument("--target-key", default="")
    parser.add_argument("--target-database-url", default="")
    parser.add_argument("--platform-key-output", default="")
    parser.add_argument("--allow-create-schema", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    try:
        result = migrate(args); code = 0
    except Exception as exc:
        result = {"verdict": "FAIL", "error_type": type(exc).__name__, "error": str(exc), "secret_values_printed": False, "production_claimed": False}
        code = 1
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(text, encoding="utf-8")
    print(text, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
