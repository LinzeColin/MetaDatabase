from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import text

from app.db import Base, make_engine, make_session_factory
from app.models import CandidateProfile, User, utcnow

ROOT = Path(__file__).resolve().parents[1]


def ignore_server_only(_directory: str, names: list[str]) -> set[str]:
    ignored = {
        ".env", ".pytest_cache", "OWNER_LOGIN.txt", "ACCEPTANCE_RESULT.json",
    }
    ignored.update(name for name in names if name.startswith((".env.pre-", ".env.tmp.")))
    if Path(_directory) == ROOT / "evidence":
        ignored.update(name for name in names if name != "local")
    if Path(_directory) == ROOT / "secrets":
        ignored.update(name for name in names if name != "README.md")
    if Path(_directory) == ROOT / "runtime-data":
        ignored.update(name for name in names if name != ".gitkeep")
    return ignored.intersection(names)


def copy_taskpack_source(destination: Path) -> None:
    """Keep server-only configuration out of test fixtures."""
    shutil.copytree(
        ROOT,
        destination,
        ignore=ignore_server_only,
    )


def write_passes(root: Path) -> None:
    for name in [
        "target-taskpack.json", "target-browser.json", "target-deepseek.json",
        "target-state-after.json", "migration-result.json", "target-sources.json",
        "target-restart.json", "target-recovery.json", "target-ops.json",
    ]:
        (root / name).write_text('{"verdict":"PASS"}\n', encoding="utf-8")


def test_taskpack_verifier_is_reentrant_and_runtime_scoped(tmp_path):
    pack = tmp_path / "pack"
    copy_taskpack_source(pack)
    verifier = [sys.executable, str(pack / "tools/verify_taskpack.py")]

    first = subprocess.run([*verifier, "--output", "evidence/predeploy-taskpack.json"], cwd=pack, capture_output=True, text=True)
    second = subprocess.run([*verifier, "--output", "evidence/predeploy-taskpack.json"], cwd=pack, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr

    for relative, content in {
        ".env": "SYNTHETIC=1\n",
        "OWNER_LOGIN.txt": "synthetic\n",
        "secrets/postgres_password.txt": "synthetic\n",
        "evidence/target-current-truth.json": '{"verdict":"OBSERVED"}\n',
        "evidence/migration-result.json": '{"verdict":"PASS"}\n',
        "runtime-data/predeploy-backup.txt": "synthetic\n",
        "ACCEPTANCE_RESULT.json": '{"core_verdict":"BLOCKED"}\n',
    }.items():
        path = pack / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if relative in {".env", "OWNER_LOGIN.txt", "secrets/postgres_password.txt"}:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    runtime = subprocess.run(
        [*verifier, "--deployment-runtime", "--output", "evidence/target-taskpack.json"],
        cwd=pack,
        capture_output=True,
        text=True,
    )
    assert runtime.returncode == 0, runtime.stderr

    (pack / "evidence/unexpected.json").write_text('{"verdict":"UNKNOWN"}\n', encoding="utf-8")
    drift = subprocess.run(
        [*verifier, "--deployment-runtime", "--output", "evidence/target-taskpack.json"],
        cwd=pack,
        capture_output=True,
        text=True,
    )
    assert drift.returncode == 1
    assert "manifest inventory drift" in drift.stdout


def test_taskpack_verifier_ignores_server_only_environment_snapshots(tmp_path):
    pack = tmp_path / "pack"
    copy_taskpack_source(pack)
    (pack / ".env").write_text("SYNTHETIC=1\n", encoding="utf-8")
    (pack / ".env").chmod(stat.S_IRUSR | stat.S_IWUSR)
    (pack / "secrets/postgres_password.txt").write_text("synthetic\n", encoding="utf-8")
    (pack / "secrets/postgres_password.txt").chmod(stat.S_IRUSR | stat.S_IWUSR)
    (pack / ".env.pre-secret-rotation").write_text("SYNTHETIC_SNAPSHOT=1\n", encoding="utf-8")
    output = pack / "evidence/target-taskpack.json"

    completed = subprocess.run(
        [sys.executable, str(pack / "tools/verify_taskpack.py"), "--deployment-runtime", "--output", str(output)],
        cwd=pack,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout
    assert json.loads(output.read_text(encoding="utf-8"))["verdict"] == "PASS"


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


def test_production_e2e_marks_closed_email_lifecycle_as_email_only_blocked(tmp_path):
    output = tmp_path / "target-browser.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/e2e_production.py"), "--output", str(output)],
        cwd=ROOT,
        env={
            "BASE_URL": "https://jobhunt.example.test",
            "ALLOW_REGISTRATION": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["verdict"] == "BLOCKED"
    assert result["blocker"] == "EMAIL_ONLY_BLOCKED"
    assert result["registration_enabled"] is False
    assert result["standard_smtp_configured"] is False
    assert result["email_delivery_sent"] is False
    assert result["synthetic_accounts_created"] is False


def test_mail_transport_probe_ignores_generated_evidence(tmp_path):
    pack = tmp_path / "pack"
    copy_taskpack_source(pack)
    artifact = pack / "evidence/target-mail-transport.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text('{"nitrosend_dependency": false}\n', encoding="utf-8")
    (pack / ".env.pre-synthetic").write_text("NITROSEND_TOKEN=synthetic\n", encoding="utf-8")
    (pack / "OWNER_LOGIN.txt").write_text("NITROSEND_TOKEN=synthetic\n", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(pack / "tools/mail_transport_probe.py"), "--output", "evidence/target-mail-transport.json"],
        cwd=pack,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    result = json.loads(artifact.read_text(encoding="utf-8"))
    assert result["verdict"] == "PASS"
    assert result["nitrosend_dependency"] is False


def test_ops_probe_does_not_claim_production_when_optional_evidence_is_blocked(tmp_path):
    output = tmp_path / "target-ops.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/ops_probe.py"), "--output", str(output)],
        cwd=ROOT,
        env={"PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["verdict"] == "BLOCKED"
    assert result["critical"] is False
    assert result["production_claimed"] is False


def test_ops_probe_requires_pass_verdict_inside_configured_evidence(tmp_path):
    output = tmp_path / "target-ops.json"
    status = tmp_path / "status.json"
    private_db = tmp_path / "private-db.json"
    r2 = tmp_path / "r2.json"
    status.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    private_db.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
    r2.write_text('{"verdict":"NOT_CONFIGURED","reason":"no authorized project bucket"}\n', encoding="utf-8")
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "STATUS_REGISTRATION_EVIDENCE": str(status),
        "PRIVATE_DATABASE_SYNC_EVIDENCE": str(private_db),
        "R2_SYNC_EVIDENCE": str(r2),
    }
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/ops_probe.py"), "--output", str(output)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    r2_check = next(check for check in result["checks"] if check["name"] == "R2_SYNC_EVIDENCE")
    assert r2_check["status"] == "BLOCKED"
    assert r2_check["evidence_verdict"] == "NOT_CONFIGURED"
    assert result["production_claimed"] is False


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
        "APP_ENV": "production", "DATABASE_URL": f"sqlite+pysqlite:///{db_path}",
        "BASE_URL": "https://jobhunt.example.test", "SESSION_SECRET": "x",
        "DATA_ENCRYPTION_KEY": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        "EMAIL_LOOKUP_SECRET": "x", "COOKIE_SECURE": "true", "ALLOW_REGISTRATION": "false",
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
    assert payload["production_claimed"] is True
    assert payload["completed_refresh_intervals_checked"] == 1

    failed_output = tmp_path / "probe-failed.json"
    failed = subprocess.run(
        [
            sys.executable, str(ROOT / "tools/production_state_probe.py"),
            "--require-alembic-head", "not-the-live-revision", "--output", str(failed_output),
        ],
        cwd=ROOT, env=env,
    )
    assert failed.returncode == 1
    failed_payload = json.loads(failed_output.read_text())
    assert failed_payload["verdict"] == "FAIL"
    assert failed_payload["production_claimed"] is False
