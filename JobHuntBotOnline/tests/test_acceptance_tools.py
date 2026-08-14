from __future__ import annotations

import email
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path

from sqlalchemy import text
import pytest

from app.db import Base, make_engine, make_session_factory
from app.models import CandidateProfile, User, utcnow
from app.security import email_lookup

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
    result = json.loads(output.read_text())
    assert result["core_verdict"] == "PASS"
    assert result["production_claimed"] is False
    assert result["completion_authority"] == "root ACCEPTANCE_RESULT.json on the production target only"
    (evidence / "target-browser.json").write_text('{"verdict":"PASS","production_claimed":true}\n', encoding="utf-8")
    assert subprocess.run(cmd, cwd=ROOT).returncode == 1
    assert json.loads(output.read_text())["core_verdict"] == "BLOCKED"
    (evidence / "target-browser.json").write_text('{"verdict":"PASS"}\n', encoding="utf-8")
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


def test_production_e2e_rejects_alias_fallback_and_same_recipient(tmp_path):
    output = tmp_path / "target-browser.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/e2e_production.py"), "--output", str(output)],
        cwd=ROOT,
        env={
            "BASE_URL": "https://jobhunt.example.test",
            "ALLOW_REGISTRATION": "true",
            "SMTP_HOST": "smtp.example.test",
            "ACCEPTANCE_EMAIL_A": "same@example.test",
            "ACCEPTANCE_EMAIL_B": "SAME@example.test",
            "ACCEPTANCE_IMAP_HOST": "imap.example.test",
            "ACCEPTANCE_IMAP_USERNAME": "acceptance@example.test",
            "ACCEPTANCE_IMAP_PASSWORD": "synthetic-password",
            "RUN_REAL_EMAIL_ACCEPTANCE": "true",
            "REAL_EMAIL_ACCEPTANCE_RUN_ID": "mail-safety-run-20260811",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["verdict"] == "BLOCKED"
    assert result["blocker"] == "EMAIL_ONLY_BLOCKED"
    assert result["acceptance_recipient_configured"] is False
    assert result["email_delivery_sent"] is False


def test_production_e2e_requires_explicit_shared_inbox_permission_for_plus_aliases(tmp_path):
    output = tmp_path / "target-browser.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools/e2e_production.py"), "--output", str(output)],
        cwd=ROOT,
        env={
            "BASE_URL": "https://jobhunt.example.test",
            "ALLOW_REGISTRATION": "true",
            "SMTP_HOST": "smtp.example.test",
            "ADMIN_EMAIL": "owner@example.test",
            "ACCEPTANCE_EMAIL_A": "owner+acceptance-a@example.test",
            "ACCEPTANCE_EMAIL_B": "owner+acceptance-b@example.test",
            "ACCEPTANCE_IMAP_HOST": "imap.example.test",
            "ACCEPTANCE_IMAP_USERNAME": "acceptance@example.test",
            "ACCEPTANCE_IMAP_PASSWORD": "synthetic-password",
            "RUN_REAL_EMAIL_ACCEPTANCE": "true",
            "REAL_EMAIL_ACCEPTANCE_RUN_ID": "mail-safety-alias-run-20260811",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2, completed.stderr
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["verdict"] == "BLOCKED"
    assert result["blocker"] == "EMAIL_ONLY_BLOCKED"
    assert result["acceptance_recipient_configured"] is False
    assert result["acceptance_recipient_identity_conflict"] is True
    assert result["acceptance_shared_imap_inbox_explicitly_allowed"] is False
    assert result["email_delivery_sent"] is False


def test_production_e2e_accepts_explicit_shared_inbox_for_distinct_aliases(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_production", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("ADMIN_EMAIL", "owner@example.test")
    monkeypatch.setenv("ACCEPTANCE_EMAIL_A", "owner+acceptance-a@example.test")
    monkeypatch.setenv("ACCEPTANCE_EMAIL_B", "owner+acceptance-b@example.test")
    monkeypatch.setenv("ACCEPTANCE_ALLOW_SHARED_IMAP_INBOX", "true")
    monkeypatch.setenv("ALLOW_REGISTRATION", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("ACCEPTANCE_IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("ACCEPTANCE_IMAP_USERNAME", "owner@example.test")
    monkeypatch.setenv("ACCEPTANCE_IMAP_PASSWORD", "synthetic-password")
    monkeypatch.setenv("RUN_REAL_EMAIL_ACCEPTANCE", "true")
    monkeypatch.setenv("REAL_EMAIL_ACCEPTANCE_RUN_ID", "shared-inbox-run-20260811")

    assert module.acceptance_recipient_identity_conflict() is False
    assert module.has_distinct_acceptance_recipients() is True
    assert module.email_lifecycle_preflight() is None


def test_shared_inbox_aliases_remain_distinct_saas_account_identities():
    secret = "synthetic-email-lookup-secret"
    first = email_lookup("owner+acceptance-a@example.test", secret)
    second = email_lookup("owner+acceptance-b@example.test", secret)

    assert first != second


def test_acceptance_shell_rejects_plus_alias_pair_before_creating_evidence(tmp_path):
    pack = tmp_path / "pack"
    copy_taskpack_source(pack)
    (pack / ".env").write_text(
        "\n".join([
            "RUN_REAL_EMAIL_ACCEPTANCE=true",
            "REAL_EMAIL_ACCEPTANCE_RUN_ID=mail-safety-shell-alias-run-20260811",
            "ADMIN_EMAIL=owner@example.test",
            "ACCEPTANCE_EMAIL_A=owner+acceptance-a@example.test",
            "ACCEPTANCE_EMAIL_B=owner+acceptance-b@example.test",
        ]) + "\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        ["bash", "deploy/acceptance.sh"],
        cwd=pack,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "ACCEPTANCE_ALLOW_SHARED_IMAP_INBOX=true" in completed.stderr
    assert "no email has been sent" in completed.stderr
    assert not (pack / "ACCEPTANCE_RESULT.json").exists()


def test_real_email_guard_consumes_each_run_id_and_enforces_cooldown(tmp_path):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_production", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = tmp_path / "runtime-data" / "real-email-acceptance-guard.json"

    module.reserve_real_email_acceptance(
        state_path=state,
        run_id="mail-safety-run-20260811",
        cooldown_hours=24,
        minimum_gap_seconds=1800,
    )
    payload = json.loads(state.read_text(encoding="utf-8"))
    assert payload["maximum_real_messages"] == 3
    assert payload["minimum_email_gap_seconds"] == 1800
    assert "recipient" not in payload

    with pytest.raises(RuntimeError, match="already been consumed"):
        module.reserve_real_email_acceptance(
            state_path=state,
            run_id="mail-safety-run-20260811",
            cooldown_hours=24,
            minimum_gap_seconds=1800,
        )
    with pytest.raises(RuntimeError, match="cooldown"):
        module.reserve_real_email_acceptance(
            state_path=state,
            run_id="mail-safety-next-20260811",
            cooldown_hours=24,
            minimum_gap_seconds=1800,
        )


def test_imap_connection_has_a_bounded_socket_timeout(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_imap_timeout", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed: dict[str, int] = {}

    class FakeImapClient:
        def login(self, _username, _password):
            return "OK", []

    def fake_imap_ssl(_host, _port, *, timeout):
        observed["timeout"] = timeout
        return FakeImapClient()

    monkeypatch.setenv("ACCEPTANCE_IMAP_HOST", "imap.example.test")
    monkeypatch.setenv("ACCEPTANCE_IMAP_USERNAME", "acceptance@example.test")
    monkeypatch.setenv("ACCEPTANCE_IMAP_PASSWORD", "synthetic-password")
    monkeypatch.setenv("ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS", "20")
    monkeypatch.setattr(module.imaplib, "IMAP4_SSL", fake_imap_ssl)

    assert isinstance(module.imap_connection(), FakeImapClient)
    assert observed["timeout"] == 20
    monkeypatch.setenv("ACCEPTANCE_IMAP_CONNECT_TIMEOUT_SECONDS", "0")
    with pytest.raises(RuntimeError, match="between 1 and 60"):
        module.imap_connection()


def test_mail_wait_retries_a_bounded_imap_timeout_without_resending(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_imap_retry", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    attempts = {"count": 0}
    times = iter([0.0, 0.0, 241.0])

    def timed_out_connection():
        attempts["count"] += 1
        raise TimeoutError("synthetic timeout")

    monkeypatch.setattr(module, "imap_connection", timed_out_connection)
    monkeypatch.setattr(module.time, "time", lambda: next(times))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setenv("ACCEPTANCE_MAIL_TIMEOUT_SECONDS", "240")

    with pytest.raises(RuntimeError, match="timed out waiting for verify email"):
        module.wait_mail_link("acceptance@example.test", "verify", "https://jobhunt.example.test", 0.0)
    assert attempts["count"] == 1


def test_mail_wait_matches_a_distinct_plus_alias_in_a_shared_imap_inbox(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_imap_alias", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    message = EmailMessage()
    message["Date"] = email.utils.format_datetime(datetime.now(timezone.utc))
    message["To"] = "owner+acceptance-a@example.test"
    message.set_content(
        "确认链接：https://jobhunt.example.test/verify-email?token=synthetic-verification-token"
    )

    class FakeImapClient:
        def select(self, _folder, readonly):
            assert readonly is True
            return "OK", []

        def search(self, *_args):
            return "OK", [b"101"]

        def fetch(self, _message_id, _query):
            return "OK", [(b"101 (RFC822)", message.as_bytes())]

        def logout(self):
            return "BYE", []

    monkeypatch.setattr(module, "imap_connection", FakeImapClient)
    monkeypatch.setenv("ACCEPTANCE_MAIL_TIMEOUT_SECONDS", "240")

    link = module.wait_mail_link(
        "owner+acceptance-a@example.test",
        "verify",
        "https://jobhunt.example.test",
        time.time(),
    )
    assert link == "https://jobhunt.example.test/verify-email?token=synthetic-verification-token"


def test_email_pacer_adds_a_rate_limit_boundary_buffer(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_pacer", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monotonic_values = iter([0.0, 1800.0, 1800.0])
    sleeps: list[float] = []
    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(seconds))

    pacer = module.EmailPacer(1800, 30)
    pacer.wait_before_request()
    pacer.wait_before_request()

    assert sleeps == [30.0]


def test_e2e_failure_cleanup_deletes_verified_synthetic_accounts_without_mail(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_cleanup", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    base_url = "https://jobhunt.example.test"
    visited: list[str] = []
    clicks: list[str] = []

    class Node:
        def fill(self, _value):
            return None

    class Page:
        url = ""

        def set_default_timeout(self, _value):
            return None

        def set_default_navigation_timeout(self, _value):
            return None

        def goto(self, url, **_kwargs):
            visited.append(url)
            self.url = url

        def get_by_test_id(self, _name):
            return Node()

        def once(self, _event, _callback):
            return None

    page = Page()

    class Context:
        def new_page(self):
            return page

        def close(self):
            return None

    class Browser:
        def new_context(self, **_kwargs):
            return Context()

        def close(self):
            return None

    class Playwright:
        class Chromium:
            @staticmethod
            def launch(**_kwargs):
                return Browser()

        chromium = Chromium()

    class PlaywrightContext:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *_args):
            return False

    def fake_click(target, selector):
        clicks.append(selector)
        if selector == '[data-testid="login-submit"]':
            target.url = f"{base_url}/dashboard"
        elif selector == '[data-testid="delete-account-submit"]':
            target.url = f"{base_url}/"

    monkeypatch.setattr(module, "sync_playwright", lambda: PlaywrightContext())
    monkeypatch.setattr(module, "click_wait", fake_click)

    accounts = {
        "acceptance-a@example.test": "synthetic-a",
        "acceptance-b@example.test": "synthetic-b",
    }
    assert module.cleanup_verified_synthetic_accounts(base_url, accounts) == []
    assert accounts == {}
    assert clicks.count('[data-testid="delete-account-submit"]') == 2
    assert all("/login" in url or "/settings/data" in url for url in visited)


def test_email_pacer_rejects_removing_the_rate_limit_boundary_buffer(monkeypatch):
    spec = importlib.util.spec_from_file_location("jobhunt_e2e_pacer_config", ROOT / "tools/e2e_production.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("ACCEPTANCE_EMAIL_REQUEST_SAFETY_SECONDS", "0")

    with pytest.raises(RuntimeError, match="between 30 and 300"):
        module.acceptance_email_request_safety_seconds()


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


def test_ops_probe_all_pass_does_not_claim_production(tmp_path):
    output = tmp_path / "target-ops.json"
    evidence_paths = []
    for name in ["status", "private-db", "r2"]:
        path = tmp_path / f"{name}.json"
        path.write_text('{"verdict":"PASS"}\n', encoding="utf-8")
        evidence_paths.append(path)
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "STATUS_REGISTRATION_EVIDENCE": str(evidence_paths[0]),
        "PRIVATE_DATABASE_SYNC_EVIDENCE": str(evidence_paths[1]),
        "R2_SYNC_EVIDENCE": str(evidence_paths[2]),
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
    assert result["verdict"] == "PASS"
    assert result["production_claimed"] is False
    assert result["completion_authority"] == "root ACCEPTANCE_RESULT.json only"


def test_production_state_probe_checks_exact_six_hours(tmp_path):
    db_path = tmp_path / "state.db"
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version(version_num VARCHAR(64) NOT NULL)"))
        conn.execute(text("INSERT INTO alembic_version(version_num) VALUES ('0002_delivery_lookup')"))
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
    assert payload["production_claimed"] is False
    assert payload["completion_authority"] == "root ACCEPTANCE_RESULT.json only"
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
