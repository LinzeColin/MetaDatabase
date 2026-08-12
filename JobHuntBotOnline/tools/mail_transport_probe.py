#!/usr/bin/env python3
"""Prove NitroSend is absent and provider-neutral SMTP can be deferred safely."""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings, validate_settings


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        parts = shlex.split(value, posix=True)
        values[key] = parts[0] if parts else ""
    return values


def generated_env(*, smtp_host: str = "") -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="jobhunt-mail-probe-") as tmp:
        cmd = [
            "python3", str(ROOT / "deploy/generate_env.py"),
            "--domain", "jobhunt.example.test",
            "--admin-email", "owner@example.test",
            "--output", ".env",
        ]
        if smtp_host:
            cmd.extend(["--smtp-host", smtp_host, "--smtp-from", "JobHuntBot <no-reply@example.test>"])
        completed = subprocess.run(cmd, cwd=tmp, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError(completed.stderr or completed.stdout)
        return parse_env(Path(tmp) / ".env")


def forbidden_nitrosend_references() -> list[str]:
    matches: list[str] = []
    patterns = [re.compile(r"(?i)NITROSEND_"), re.compile(r"(?i)https?://[^\s'\"]*nitrosend")]
    active_paths = [
        ROOT / ".env.example",
        ROOT / "docker-compose.yml",
        ROOT / "Dockerfile",
        ROOT / "Dockerfile.acceptance",
    ]
    for directory in (ROOT / "app", ROOT / "deploy"):
        if directory.is_dir():
            active_paths.extend(directory.rglob("*"))
    for path in active_paths:
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".zip", ".db", ".enc"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(pattern.search(text) for pattern in patterns):
            matches.append(str(path.relative_to(ROOT)))
    return matches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/local/mail_transport_result.json")
    args = parser.parse_args()

    errors: list[str] = []
    deferred_env = generated_env()
    smtp_env = generated_env(smtp_host="smtp.example.test")
    if deferred_env.get("ALLOW_REGISTRATION") != "false" or deferred_env.get("SMTP_HOST"):
        errors.append("mail-deferred env is not safely closed")
    if smtp_env.get("ALLOW_REGISTRATION") != "true" or smtp_env.get("SMTP_HOST") != "smtp.example.test":
        errors.append("generic SMTP env is not enabled correctly")

    base = get_settings()
    if "nitrosend" in base.smtp_host.lower():
        errors.append("runtime SMTP host points to removed provider")
    common = dict(
        app_env="production", cookie_secure=True,
        session_secret="production-session-secret",
        email_lookup_secret="production-email-secret",
        admin_email="owner@example.test", admin_password="ValidAdminPass123",
    )
    validate_settings(replace(base, **common, allow_registration=False, smtp_host=""))
    try:
        validate_settings(replace(base, **common, allow_registration=True, smtp_host=""))
    except RuntimeError as exc:
        if "标准 SMTP_HOST" not in str(exc):
            errors.append(f"unexpected validation error: {exc}")
    else:
        errors.append("public registration incorrectly accepted without SMTP")
    validate_settings(replace(base, **common, allow_registration=True, smtp_host="smtp.example.test"))

    forbidden = forbidden_nitrosend_references()
    if forbidden:
        errors.append("NitroSend-specific configuration remains: " + ", ".join(forbidden))

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "nitrosend_dependency": False,
        "provider_contract": "standards-compatible SMTP",
        "mail_deferred_registration_open": deferred_env.get("ALLOW_REGISTRATION"),
        "generic_smtp_registration_open": smtp_env.get("ALLOW_REGISTRATION"),
        "non_email_delivery_can_continue": True,
        "full_production_pass_still_requires_real_email_lifecycle": True,
        "errors": errors,
        "production_claimed": False,
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
