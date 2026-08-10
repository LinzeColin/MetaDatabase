#!/usr/bin/env python3
"""Validate the deployable taskpack without claiming production readiness."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "START_HERE.md", "PURSUING_GOAL.txt", "PURSING_GOAL.txt", "AGENTS.md",
    "README.md", "LICENSE", "NOTICE", "Dockerfile", "Dockerfile.acceptance", "docker-compose.yml",
    "taskpack/CANONICAL_CONTRACT.md", "taskpack/task_dag.json",
    "taskpack/acceptance_contract.json", "taskpack/TRACEABILITY.md",
    "taskpack/ARCHITECTURE.md", "taskpack/DELIVERY_AND_ACCEPTANCE.md",
    "taskpack/ROADMAP.md", "taskpack/MANIFEST.json",
    "deploy/deploy.sh", "deploy/acceptance.sh", "deploy/backup.sh",
    "deploy/restore.sh", "deploy/rollback.sh", "deploy/diagnose.sh",
    "deploy/generate_env.py", "deploy/verify_taskpack.py",
    "tools/verify_taskpack.py", "tools/e2e_local.py", "tools/ui_contract.py",
    "tools/restart_readback.py", "tools/online_source_probe.py",
    "tools/deepseek_probe.py", "tools/e2e_production.py",
    "tools/migrate_v02_sqlite.py", "tools/production_state_probe.py",
    "tools/finalize_acceptance.py", "tools/ops_probe.py", "alembic.ini",
    "alembic/versions/0001_saas_baseline.py", "secrets/README.md",
]
FORBIDDEN_NAMES = {".env", "OWNER_LOGIN.txt", "postgres_password.txt"}
FORBIDDEN_PARTS = {"__pycache__", ".pytest_cache", ".venv", "playwright-report", "test-results"}
FAILURE_MARKERS = {"PYTEST_FAIL", "TASKPACK_FAIL", "LOCAL_ACCEPTANCE_FAIL"}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dag_errors(payload: dict) -> list[str]:
    errors: list[str] = []
    tasks = payload.get("tasks") or []
    ids = [item.get("id") for item in tasks]
    if len(ids) != len(set(ids)) or any(not item for item in ids):
        errors.append("task ids are missing or duplicated")
    known = set(ids)
    graph = {item["id"]: list(item.get("depends_on") or []) for item in tasks if item.get("id")}
    for task_id, deps in graph.items():
        unknown = sorted(set(deps) - known)
        if unknown:
            errors.append(f"{task_id} has unknown dependencies: {unknown}")
    state: dict[str, int] = {}

    def visit(node: str, stack: list[str]) -> None:
        mark = state.get(node, 0)
        if mark == 1:
            errors.append("DAG cycle: " + " -> ".join(stack + [node]))
            return
        if mark == 2:
            return
        state[node] = 1
        for dep in graph.get(node, []):
            visit(dep, stack + [node])
        state[node] = 2

    for node in graph:
        visit(node, [])
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="")
    parser.add_argument("--allow-missing-local-evidence", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []

    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")

    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if path.name in FORBIDDEN_NAMES:
            errors.append(f"forbidden secret-bearing filename: {rel}")
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

    if (ROOT / "taskpack/task_dag.json").is_file() and (ROOT / "taskpack/acceptance_contract.json").is_file():
        try:
            dag = read_json(ROOT / "taskpack/task_dag.json")
            errors.extend(dag_errors(dag))
            acceptance = read_json(ROOT / "taskpack/acceptance_contract.json")
            acceptance_ids = {item.get("id") for item in acceptance.get("items", [])}
            for task in dag.get("tasks", []):
                for ac in task.get("acceptance", []):
                    if ac not in acceptance_ids:
                        errors.append(f"{task.get('id')} references unknown acceptance {ac}")
        except Exception as exc:
            errors.append(f"taskpack JSON is invalid: {exc}")

    env_example = (ROOT / ".env.example").read_text(encoding="utf-8") if (ROOT / ".env.example").exists() else ""
    if not re.search(r"(?m)^DISCOVERY_REFRESH_HOURS=6$", env_example):
        errors.append(".env.example does not freeze DISCOVERY_REFRESH_HOURS=6")
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
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in concrete_secret_patterns:
            if pattern.search(text):
                errors.append(f"possible real {name} in {path.relative_to(ROOT)}")

    local_evidence = {
        "pytest": ROOT / "evidence/local/pytest_result.json",
        "ui_contract": ROOT / "evidence/local/ui_contract.json",
        "browser": ROOT / "evidence/local/browser-local/result.json",
        "restart": ROOT / "evidence/local/restart_readback.json",
        "migration": ROOT / "evidence/local/migration_test.json",
    }
    if not args.allow_missing_local_evidence:
        for name, path in local_evidence.items():
            if not path.is_file():
                errors.append(f"missing local evidence: {path.relative_to(ROOT)}")
                continue
            try:
                result = read_json(path)
            except Exception as exc:
                errors.append(f"invalid local evidence {name}: {exc}")
                continue
            if result.get("verdict") != "PASS":
                errors.append(f"local evidence is not PASS: {name}")

    manifest_path = ROOT / "taskpack/MANIFEST.json"
    if manifest_path.is_file():
        try:
            manifest = read_json(manifest_path)
            listed = set(manifest.get("files", []))
            actual = {
                str(path.relative_to(ROOT))
                for path in ROOT.rglob("*")
                if path.is_file() and path != manifest_path and not any(part in FORBIDDEN_PARTS for part in path.relative_to(ROOT).parts)
            }
            if listed != actual:
                missing = sorted(actual - listed)[:20]
                stale = sorted(listed - actual)[:20]
                errors.append(f"manifest inventory drift; missing={missing}, stale={stale}")
        except Exception as exc:
            errors.append(f"invalid taskpack manifest: {exc}")

    result = {
        "verdict": "PASS" if not errors else "FAIL",
        "scope": "taskpack structure, DAG, source/config syntax, script executability, secret boundary and local evidence",
        "production_claimed": False,
        "errors": errors,
        "warnings": warnings,
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
