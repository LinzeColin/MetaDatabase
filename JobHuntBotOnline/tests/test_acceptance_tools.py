from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text

from app.db import Base, make_engine, make_session_factory
from app.models import CandidateProfile, User, utcnow

ROOT = Path(__file__).resolve().parents[1]


def write_passes(root: Path) -> None:
    for name in [
        "target-taskpack.json", "target-browser.json", "target-deepseek.json",
        "target-state-after.json", "migration-result.json", "target-sources.json",
        "target-restart.json", "target-recovery.json", "target-ops.json",
    ]:
        (root / name).write_text('{"verdict":"PASS"}\n', encoding="utf-8")


def test_finalizer_requires_every_critical_evidence(tmp_path):
    evidence = tmp_path / "evidence"; evidence.mkdir(); write_passes(evidence)
    output = tmp_path / "result.json"
    cmd = [
        sys.executable, str(ROOT / "tools/finalize_acceptance.py"),
        "--evidence-root", str(evidence), "--output", str(output),
        "--base-url", "https://jobhunt.example.com", "--commit", "candidate-commit",
        "--deployment-id", "image-id", "--rollback-target", "previous-image",
    ]
    assert subprocess.run(cmd, cwd=ROOT).returncode == 0
    assert json.loads(output.read_text())["core_verdict"] == "PASS"
    (evidence / "target-deepseek.json").unlink()
    assert subprocess.run(cmd, cwd=ROOT).returncode == 1
    assert json.loads(output.read_text())["core_verdict"] == "BLOCKED"


def test_production_state_probe_checks_exact_six_hours(tmp_path):
    db_path = tmp_path / "state.db"
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version(version_num VARCHAR(64) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version(version_num) VALUES ('0001_saas_baseline')"))
    factory = make_session_factory(engine)
    completed = utcnow()
    with factory() as db:
        user = User(
            email_lookup="synthetic-lookup", email_encrypted=b"synthetic",
            password_hash="synthetic", is_verified=True, is_active=True, is_admin=False,
        )
        db.add(user); db.flush()
        db.add(CandidateProfile(
            user_id=user.id, payload_encrypted=b"synthetic", onboarding_state="complete",
            discovery_enabled=True, last_discovery_at=completed,
            next_discovery_at=completed + timedelta(hours=6),
        ))
        db.commit()
    engine.dispose()
    output = tmp_path / "probe.json"
    env = os.environ.copy()
    env.update({
        "APP_ENV": "test", "DATABASE_URL": f"sqlite+pysqlite:///{db_path}",
        "BASE_URL": "http://testserver", "SESSION_SECRET": "x",
        "DATA_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        "EMAIL_LOOKUP_SECRET": "x", "COOKIE_SECURE": "false",
        "ADMIN_EMAIL": "owner@example.com", "ADMIN_PASSWORD": "AdminPass!2026",
        "DISCOVERY_REFRESH_HOURS": "6",
    })
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/production_state_probe.py"), "--output", str(output)],
        cwd=ROOT, env=env,
    )
    assert result.returncode == 0
    payload = json.loads(output.read_text())
    assert payload["verdict"] == "PASS"
    assert payload["completed_refresh_intervals_checked"] == 1
