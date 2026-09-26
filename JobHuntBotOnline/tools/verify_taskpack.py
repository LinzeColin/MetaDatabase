#!/usr/bin/env python3
"""Pre-deploy check of the release directory: no secrets or caches, config invariants hold,
sources compile, and the file inventory matches deploy/MANIFEST.json.

After adding or removing tracked files, refresh the inventory with `--write-manifest`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "AGENTS.md", "README.md", "LICENSE", "NOTICE", "Dockerfile", "Dockerfile.acceptance", "docker-compose.yml",
    "deploy/deploy.sh", "deploy/acceptance.sh", "deploy/backup.sh",
    "deploy/restore.sh", "deploy/rollback.sh", "deploy/diagnose.sh",
    "deploy/generate_env.py", "deploy/verify_taskpack.py", "deploy/MANIFEST.json",
    "tools/verify_taskpack.py", "tools/online_source_probe.py",
    "tools/deepseek_probe.py", "tools/e2e_production.py", "tools/mail_transport_probe.py",
    "tools/migrate_v02_sqlite.py", "tools/production_state_probe.py",
    "tools/finalize_acceptance.py", "tools/ops_probe.py", "alembic.ini",
    "alembic/versions/0001_saas_baseline.py", "alembic/versions/0002_email_delivery_recipient_lookup.py",
    "secrets/README.md",
]
FORBIDDEN_NAMES = {".env", "OWNER_LOGIN.txt", "postgres_password.txt"}
FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".venv", "playwright-report", "test-results"}
FAILURE_MARKERS = {"PYTEST_FAIL", "TASKPACK_FAIL", "LOCAL_ACCEPTANCE_FAIL"}
RUNTIME_SECRET_PATHS = {".env", "OWNER_LOGIN.txt", "secrets/postgres_password.txt"}
RUNTIME_GENERATED_EVIDENCE = {
    "evidence/predeploy-taskpack.json",
    "evidence/migration-result.json",
}
SERVER_ONLY_ENV_SNAPSHOTS = (".env.pre-", ".env.tmp.")


def runtime_artifact(rel: Path, *, deployment_runtime: bool) -> bool:
    value = rel.as_posix()
    # Deployment operators may retain an inactive, mode-restricted environment
    # snapshot while replacing server Secrets.  It is neither taskpack source
    # nor active configuration, and must never be copied into the manifest or
    # examined as source material.
    if rel.name.startswith(SERVER_ONLY_ENV_SNAPSHOTS):
        return True
    if value == "evidence/predeploy-taskpack.json":
        return True
    if not deployment_runtime:
        return False
    return (
        value in RUNTIME_SECRET_PATHS
        or value in RUNTIME_GENERATED_EVIDENCE
        or value == "ACCEPTANCE_RESULT.json"
        or value.startswith("evidence/target-")
        or (value.startswith("runtime-data/") and value != "runtime-data/.gitkeep")
    )


def secure_runtime_secret(path: Path) -> bool:
    return stat.S_IMODE(path.stat().st_mode) in {0o400, 0o600}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


MANIFEST_PATH = ROOT / "deploy/MANIFEST.json"


def release_inventory(*, deployment_runtime: bool) -> set[str]:
    return {
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file()
        and path != MANIFEST_PATH
        and not any(part in FORBIDDEN_PARTS for part in path.relative_to(ROOT).parts)
        and not runtime_artifact(path.relative_to(ROOT), deployment_runtime=deployment_runtime)
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--write-manifest", action="store_true", help="Rewrite deploy/MANIFEST.json from the current tree and exit.")
    parser.add_argument(
        "--deployment-runtime",
        action="store_true",
        help="Allow only documented runtime secrets and generated evidence after deployment configuration exists.",
    )
    args = parser.parse_args()
    if args.write_manifest:
        files = sorted(release_inventory(deployment_runtime=False))
        MANIFEST_PATH.write_text(json.dumps({"files": files}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST_PATH.relative_to(ROOT)} with {len(files)} files")
        return 0
    errors: list[str] = []

    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")

    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        rel_value = rel.as_posix()
        if path.name in FORBIDDEN_NAMES:
            if not (args.deployment_runtime and rel_value in RUNTIME_SECRET_PATHS):
                errors.append(f"forbidden secret-bearing filename: {rel}")
            elif not secure_runtime_secret(path):
                errors.append(f"runtime secret must be mode 0600 or 0400: {rel}")
        if path.name in FAILURE_MARKERS:
            errors.append(f"failure marker is present: {rel}")
        if any(part in FORBIDDEN_PARTS for part in rel.parts):
            errors.append(f"build/cache material is present: {rel}")
        if path.suffix in {".pyc", ".pyo"}:
            errors.append(f"compiled cache is present: {rel}")
        if path.name.endswith(".exit"):
            try:
                if path.read_text(encoding="utf-8").strip() not in {"", "0"}:
                    errors.append(f"non-zero historical exit marker is present: {rel}")
            except UnicodeDecodeError:
                errors.append(f"invalid exit marker: {rel}")

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8") if (ROOT / ".env.example").exists() else ""
    if not re.search(r"(?m)^DISCOVERY_REFRESH_HOURS=6$", env_example):
        errors.append(".env.example does not freeze DISCOVERY_REFRESH_HOURS=6")
    if re.search(r"(?mi)^NITROSEND_|https?://[^\s]*nitrosend", env_example):
        errors.append("NitroSend-specific configuration is present")
    if re.search(r"(?m)^SMTP_HOST=$", env_example) and not re.search(r"(?m)^ALLOW_REGISTRATION=false$", env_example):
        errors.append("blank SMTP example must keep public registration closed")
    if not re.search(r"(?m)^DOMAIN=", env_example):
        errors.append(".env.example does not define DOMAIN for HTTPS routing")
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    if "traefik.enable:" not in compose_text or "Host(`${DOMAIN}`)" not in compose_text:
        errors.append("docker compose does not define the HTTPS reverse-proxy route")
    generator_text = (ROOT / "deploy/generate_env.py").read_text(encoding="utf-8")
    if '"DOMAIN": args.domain' not in generator_text:
        errors.append("production env generator does not write DOMAIN")
    config_text = (ROOT / "app/config.py").read_text(encoding="utf-8")
    discovery_text = (ROOT / "app/discovery.py").read_text(encoding="utf-8")
    if "discovery_refresh_hours != 6" not in config_text:
        errors.append("runtime config does not reject non-six-hour refresh")
    if "timedelta(hours=6)" not in discovery_text:
        errors.append("discovery completion does not schedule exactly six hours later")

    for base_name in ["app", "tools", "alembic", "tests", "deploy"]:
        base = ROOT / base_name
        if not base.exists():
            continue
        for source in base.rglob("*.py"):
            try:
                compile(source.read_text(encoding="utf-8"), str(source), "exec")
            except Exception as exc:
                errors.append(f"Python compilation failed: {source.relative_to(ROOT)}: {exc}")

    for path in sorted((ROOT / "deploy").glob("*.sh")):
        check = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True)
        if check.returncode:
            errors.append(f"shell syntax failed: {path.relative_to(ROOT)}: {check.stderr.strip()}")
        if not os.access(path, os.X_OK):
            errors.append(f"deployment script is not executable: {path.relative_to(ROOT)}")

    # Scan for concrete secret material, not documentation patterns.
    concrete_secret_patterns = [
        ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}-----END", re.S)),
        ("github_pat", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{24,}\b")),
        ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ]
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".zip", ".db", ".enc"}:
            continue
        rel = path.relative_to(ROOT)
        if runtime_artifact(rel, deployment_runtime=args.deployment_runtime):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in concrete_secret_patterns:
            if pattern.search(text):
                errors.append(f"possible real {name} in {path.relative_to(ROOT)}")

    if MANIFEST_PATH.is_file():
        try:
            listed = set(read_json(MANIFEST_PATH).get("files", []))
            actual = release_inventory(deployment_runtime=args.deployment_runtime)
            if listed != actual:
                missing = sorted(actual - listed)[:20]
                stale = sorted(listed - actual)[:20]
                errors.append(f"manifest inventory drift; missing={missing}, stale={stale}")
        except Exception as exc:
            errors.append(f"invalid deploy manifest: {exc}")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "scope": "release inventory, source/config syntax, script executability and secret boundary",
        "deployment_runtime": args.deployment_runtime,
        "production_claimed": False,
        "errors": errors,
    }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        output = Path(args.output)
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
