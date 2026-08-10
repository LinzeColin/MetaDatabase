from __future__ import annotations

import json
import os
import sqlite3
from argparse import Namespace
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select

from app.db import make_engine, make_session_factory
from app.discovery import safe_http_url
from app.models import ApplicationPack, CandidateProfile, Job, Recommendation, Resume, User
from tools.migrate_v02_sqlite import PREFIX, connect_source, migrate


def seal(cipher: Fernet, value: str) -> str:
    if not value:
        return ""
    return PREFIX + cipher.encrypt(value.encode()).decode()


def build_v02(path: Path, key: str, data_root: Path) -> None:
    cipher = Fernet(key.encode())
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE users(id INTEGER PRIMARY KEY,email TEXT,password_hash TEXT,display_name TEXT,is_active INTEGER,session_version INTEGER,created_at TEXT,last_login_at TEXT);
    CREATE TABLE candidate_profiles(id INTEGER PRIMARY KEY,user_id INTEGER,work_authorization_text TEXT,sponsorship_now TEXT,sponsorship_future TEXT,target_roles_json TEXT,secondary_roles_json TEXT,roles_to_avoid_json TEXT,industries_to_avoid_json TEXT,target_locations_json TEXT,work_mode TEXT,relocation_policy TEXT,available_start_date TEXT,onboarding_completed INTEGER);
    CREATE TABLE resumes(id INTEGER PRIMARY KEY,user_id INTEGER,label TEXT,role_family TEXT,source_filename TEXT,file_type TEXT,encrypted_file_path TEXT,extracted_text TEXT,skills_json TEXT,is_default INTEGER,created_at TEXT,updated_at TEXT);
    CREATE TABLE experiences(id INTEGER PRIMARY KEY,user_id INTEGER,resume_id INTEGER,category TEXT,title TEXT,organization TEXT,date_range TEXT,description TEXT,tags_json TEXT,source_ref TEXT,created_at TEXT,updated_at TEXT);
    CREATE TABLE jobs(id INTEGER PRIMARY KEY,user_id INTEGER,url TEXT,source TEXT,company TEXT,title TEXT,location TEXT,posted_date TEXT,description TEXT,snapshot_text TEXT,status TEXT,recommendation TEXT,fit_label TEXT,eligibility_status TEXT,freshness_status TEXT,application_effort TEXT,reasons_json TEXT,risks_json TEXT,unknowns_json TEXT,matched_skills_json TEXT,missing_skills_json TEXT,selected_resume_id INTEGER,next_action TEXT,next_action_date TEXT,current_stage TEXT,notes TEXT,applied_at TEXT,created_at TEXT,updated_at TEXT);
    CREATE TABLE application_packs(id INTEGER PRIMARY KEY,user_id INTEGER,job_id INTEGER,resume_id INTEGER,experience_ids_json TEXT,fit_summary TEXT,why_role_draft TEXT,why_company_draft TEXT,work_authorization_answer TEXT,sponsorship_answer TEXT,salary_answer TEXT,checklist_json TEXT,user_reviewed INTEGER,created_at TEXT,updated_at TEXT);
    CREATE TABLE ai_provider_configs(id INTEGER PRIMARY KEY,user_id INTEGER,api_key TEXT);
    CREATE TABLE ai_usage_records(id INTEGER PRIMARY KEY,user_id INTEGER,job_id INTEGER,total_tokens INTEGER,created_at TEXT);
    CREATE TABLE job_events(id INTEGER PRIMARY KEY,user_id INTEGER,job_id INTEGER,event_type TEXT,note TEXT,occurred_at TEXT);
    """)
    upload = data_root / "uploads/legacy.bin"; upload.parent.mkdir(parents=True); upload.write_bytes(cipher.encrypt(b"legacy resume bytes"))
    now = "2026-08-01T10:00:00+00:00"
    conn.execute("INSERT INTO users VALUES(1,?,?,?,?,?,?,?)", ("owner@example.com", "$argon2id$v=19$m=65536,t=3,p=2$dGVzdHRlc3R0ZXN0dGVzdA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA", "Owner", 1, 1, now, None))
    conn.execute("INSERT INTO candidate_profiles VALUES(1,1,?,?,?,?,?,?,?,?,?,?,?,1)", (
        seal(cipher,"Australian full working rights"), seal(cipher,"false"), seal(cipher,"false"), seal(cipher,json.dumps(["Finance","Data"])), seal(cipher,"[]"), seal(cipher,json.dumps(["Sales"])), seal(cipher,json.dumps(["Gambling"])), seal(cipher,json.dumps(["Sydney"])), seal(cipher,"hybrid, remote"), seal(cipher,"no"), seal(cipher,"2026-11")))
    conn.execute("INSERT INTO resumes VALUES(1,1,?,?,?,?,?,?,?,?,?,?)", (seal(cipher,"Primary"), seal(cipher,"Finance"), seal(cipher,"resume.pdf"), "application/pdf", str(upload.relative_to(data_root)), seal(cipher,"Excel SQL financial analysis"), seal(cipher,json.dumps(["excel","sql"])), 1, now, now))
    conn.execute("INSERT INTO experiences VALUES(1,1,1,?,?,?,?,?,?,?,?,?)", ("experience", seal(cipher,"Finance Intern"), seal(cipher,"Example Co"), seal(cipher,"2025"), seal(cipher,"Built reporting model"), seal(cipher,"[]"), seal(cipher,"resume"), now, now))
    conn.execute("INSERT INTO jobs VALUES(1,1,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", ("https://company.example/jobs/1","Manual","Example Co","Graduate Analyst","Sydney","2026-08-01","Excel analyst role","", "Pending","Prioritize","High","Eligible","Fresh","Low",seal(cipher,json.dumps(["Strong role match"])),seal(cipher,"[]"),seal(cipher,"[]"),seal(cipher,json.dumps(["excel"])),seal(cipher,"[]"),1,seal(cipher,"Apply"),seal(cipher,""),seal(cipher,""),seal(cipher,""),None,now,now))
    conn.execute("INSERT INTO application_packs VALUES(1,1,1,1,'[]',?,?,?,?,?,?,'[]',1,?,?)", (seal(cipher,"fit"),seal(cipher,"why role"),seal(cipher,"why company"),seal(cipher,"rights"),seal(cipher,"no sponsor"),seal(cipher,"negotiable"),now,now))
    conn.execute("INSERT INTO ai_provider_configs VALUES(1,1,?)", (seal(cipher,"legacy-secret-key"),))
    conn.execute("INSERT INTO ai_usage_records VALUES(1,1,1,12,?)", (now,))
    conn.execute("INSERT INTO job_events VALUES(1,1,1,'submitted',?,?)", (seal(cipher,"application id 1"),now))
    conn.commit(); conn.close()


def test_v02_migration_reencrypts_and_preserves_counts(tmp_path, monkeypatch):
    old_key = Fernet.generate_key().decode(); new_key = Fernet.generate_key().decode()
    source = tmp_path / "old.db"; old_root = tmp_path / "old-data"; build_v02(source, old_key, old_root)
    raw = sqlite3.connect(source)
    raw.execute("UPDATE resumes SET encrypted_file_path = ?", ("/data/uploads/legacy.bin",))
    raw.commit(); raw.close()
    target = tmp_path / "new.db"; upload_root = tmp_path / "new-uploads"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{target}")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", new_key)
    monkeypatch.setenv("EMAIL_LOOKUP_SECRET", "migration-email-secret")
    monkeypatch.setenv("UPLOAD_ROOT", str(upload_root))
    monkeypatch.setenv("DISCOVERY_REFRESH_HOURS", "6")
    result = migrate(Namespace(source=str(source), old_data_root=str(old_root), old_key=old_key, target_key=new_key, target_database_url=f"sqlite+pysqlite:///{target}", platform_key_output="", allow_create_schema=True, force=False))
    assert result["verdict"] == "PASS"
    assert result["old_platform_key_in_business_db"] is False
    engine = make_engine(f"sqlite+pysqlite:///{target}"); factory = make_session_factory(engine)
    with factory() as db:
        assert db.scalar(select(func.count(User.id))) == 1
        assert db.scalar(select(func.count(CandidateProfile.id))) == 1
        assert db.scalar(select(func.count(Resume.id))) == 1
        assert db.scalar(select(func.count(Job.id))) == 1
        assert db.scalar(select(func.count(Recommendation.id))) == 1
        assert db.scalar(select(func.count(ApplicationPack.id))) == 1
        resume = db.scalar(select(Resume))
        assert resume is not None and resume.size_bytes == len(b"legacy resume bytes")
    raw = sqlite3.connect(target)
    columns = {row[1] for row in raw.execute("PRAGMA table_info(users)")}
    assert "email_encrypted" in columns and "api_key" not in columns
    assert b"owner@example.com" not in target.read_bytes()
    assert b"legacy-secret-key" not in target.read_bytes()


def test_v02_source_connection_is_immutable_and_read_only(tmp_path):
    source = tmp_path / "isolated-v02.db"
    writable = sqlite3.connect(source)
    writable.execute("CREATE TABLE source_check(value TEXT)")
    writable.execute("INSERT INTO source_check VALUES('ok')")
    writable.commit(); writable.close()

    readonly = connect_source(source)
    assert readonly.execute("SELECT value FROM source_check").fetchone()[0] == "ok"
    with pytest.raises(sqlite3.OperationalError):
        readonly.execute("CREATE TABLE must_not_persist(value TEXT)")
    readonly.close()


def test_safe_http_url_rejects_private_and_malformed_ports():
    assert safe_http_url("https://company.example/jobs/1") == "https://company.example/jobs/1"
    assert safe_http_url("http://127.0.0.1/private") == ""
    assert safe_http_url("http://10.0.0.1/private") == ""
    assert safe_http_url("https://example.com:bad/path") == ""
    assert safe_http_url("file:///etc/passwd") == ""
