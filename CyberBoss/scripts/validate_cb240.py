#!/usr/bin/env python3
"""Merge-safe, credential-free validator for CyberBoss P2.5 / CB-240."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-240"

PUBLIC_IMPLEMENTATION_COMMIT = "839014fc4bcd52e11c8ff50331ff9dbd55fe0827"
PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = (
    "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
)
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
MATERIAL_EVENT_TYPES = [
    "incident_declared",
    "recovery_completed",
    "release_completed",
]
NATIVE_EXECUTION_ORDER = [
    "CB-240",
    "PG-2",
    "CB-300",
    "CB-310",
    "CB-320",
    "CB-330",
    "CB-340",
    "PG-3",
    "CB-400",
    "CB-410",
    "CB-420",
    "CB-430",
    "CB-440",
    "PG-4",
    "CB-500",
    "CB-510",
    "CB-520",
    "CB-530",
    "CB-540",
    "PG-5",
]
AMENDMENT_ORACLES = [
    "FA-AC-001",
    "FA-AC-002",
    "FA-AC-003",
    "FA-AC-004",
    "FA-AC-005",
    "FA-AC-006",
]

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/scripts/canonical-sync-acceptance.js",
    "CyberBoss/app/scripts/canonical-sync-data.js",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/services/canonical/canonical-sync.js",
    "CyberBoss/app/src/services/db/database-adapter.js",
    "CyberBoss/app/test/canonical-sync.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P2_5_CB_240.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-canonical-sync.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.service",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync.timer",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync-material.service",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-canonical-sync-material.path",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
    "CyberBoss/scripts/validate_cb240.py",
    "CyberBoss/tests/canonical-sync.test.js",
    "CyberBoss/machine/facts/task_state.json",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/docs/evidence/CB-240/summary.json",
    "CyberBoss/docs/evidence/CB-240/subject.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bwxid_[A-Za-z0-9_-]+\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def git(*args: str, check: bool = True) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git_failed")
    return result.returncode, result.stdout.rstrip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def verify_manifest(path: Path, errors: list[str]) -> None:
    root = path.parent
    entries: dict[str, str] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            errors.append(f"manifest_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if relative in entries or relative.startswith("/") or ".." in Path(relative).parts:
            errors.append(f"manifest_path:{path.relative_to(REPO)}:{relative}")
            continue
        entries[relative] = digest
    actual = {
        candidate.relative_to(root).as_posix()
        for candidate in root.rglob("*")
        if candidate.is_file()
        and candidate != path
        and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def run_command(
    name: str,
    args: list[str],
    errors: list[str],
    *,
    cwd: Path,
    markers: tuple[str, ...] = (),
    timeout: int = 900,
) -> None:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(f"command_exception:{name}:{type(error).__name__}")
        return
    if result.returncode != 0:
        tail = result.stdout.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command:{name}:{result.returncode}:{tail[0][:180]}")
    for marker in markers:
        if marker not in result.stdout:
            errors.append(f"command_marker:{name}:{marker}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior_passed = {
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040",
        "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230",
    }
    for task_id in prior_passed:
        if statuses.get(task_id) != "passed":
            errors.append(f"task_state_prior:{task_id}")
    expected_cb240 = "passed" if final else "implemented_not_accepted"
    if statuses.get("CB-240") != expected_cb240:
        errors.append(f"task_state_cb240:{statuses.get('CB-240')}:{expected_cb240}")
    for task_id in (
        "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440",
        "CB-500", "CB-510", "CB-520", "CB-530", "CB-540",
    ):
        if statuses.get(task_id) != "not_started":
            errors.append(f"task_state_future:{task_id}")
    gates = state.get("pass_gates") or {}
    if gates.get("PG-0") != "passed" or gates.get("PG-1") != "passed":
        errors.append("task_state_prior_gates")
    for gate in ("PG-2", "PG-3", "PG-4", "PG-5"):
        if gates.get(gate) != "not_started":
            errors.append(f"task_state_future_gate:{gate}")
    expected_current = {
        "run_id": "P2.5",
        "gate_id": None,
        "task_id": "CB-240",
        "scope": "canonical_sync_rebuild",
        "status": expected_cb240,
    }
    if state.get("current_run") != expected_current:
        errors.append("task_state_current_run")
    overlay = state.get("taskpack_overlay") or {}
    if (
        state.get("taskpack_version") != TASKPACK_VERSION
        or overlay.get("product_version") != PRODUCT_VERSION
        or overlay.get("design_baseline_version") != "v0.0.0.4"
        or overlay.get("taskpack_zip_sha256") != TASKPACK_ZIP_SHA256
        or overlay.get("native_execution_order") != NATIVE_EXECUTION_ORDER
        or overlay.get("control_plane_llm_calls") != 0
        or overlay.get("operations_llm_calls") != 0
        or overlay.get("macos_launchd_dependency") is not False
    ):
        errors.append("task_state_overlay")


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P2_5_CB_240.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "P2.5 / CB-240",
        PRODUCT_VERSION,
        TASKPACK_VERSION,
        TASKPACK_ZIP_SHA256,
        "03:20 UTC",
        "release_completed",
        "incident_declared",
        "recovery_completed",
        "noop_no_commit",
        "same event ID/different record hash",
        "Private-MetaDatabase",
        "ingest|get|list|verify",
        "CB-300",
        "PG-2",
        "不创建新 repo",
        "activation_pending",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")


def validate_code_markers(errors: list[str]) -> None:
    canonical = (PROJECT / "app/src/services/canonical/canonical-sync.js").read_text(
        encoding="utf-8"
    )
    database = (PROJECT / "app/src/services/db/database-adapter.js").read_text(
        encoding="utf-8"
    )
    data_cli = (PROJECT / "app/scripts/canonical-sync-data.js").read_text(
        encoding="utf-8"
    )
    timer = (KIT / "systemd/cyberboss-canonical-sync.timer").read_text(
        encoding="utf-8"
    )
    material_service = (
        KIT / "systemd/cyberboss-canonical-sync-material.service"
    ).read_text(encoding="utf-8")
    material_path = (
        KIT / "systemd/cyberboss-canonical-sync-material.path"
    ).read_text(encoding="utf-8")
    for marker in (
        "canonicalDeliveryClass",
        "materialRetryCount",
        "noop_no_commit",
        "DEFAULT_MATERIAL_EVENT_TYPES",
    ):
        if marker not in canonical:
            errors.append(f"code_marker:{marker}")
    if "ordinaryLagExceeded" not in database:
        errors.append("database_marker:ordinaryLagExceeded")
    for marker in ("--mode=", "CANONICAL_MODE_INVALID"):
        if marker not in data_cli:
            errors.append(f"data_cli_marker:{marker}")
    if (
        "OnCalendar=*-*-* 03:20:00 UTC" not in timer
        or "Persistent=true" not in timer
        or "OnUnitActiveSec=1min" in timer
    ):
        errors.append("daily_timer_contract")
    if (
        "canonical-sync-data.js --mode=material" not in material_service
        or "User=cyberboss-data" not in material_service
        or "PathChanged=/var/lib/cyberboss/canonical-spool/outgoing"
        not in material_path
        or "Unit=cyberboss-canonical-sync-material.service" not in material_path
    ):
        errors.append("material_trigger_contract")


def validate_subject_and_evidence(errors: list[str]) -> str | None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_missing")
        return None
    inventory = {path.name for path in EVIDENCE.iterdir() if path.is_file()}
    if inventory != FINAL_EVIDENCE:
        errors.append(f"evidence_inventory:{sorted(inventory)}")
        return None
    summary_path = EVIDENCE / "summary.json"
    subject_path = EVIDENCE / "subject.json"
    try:
        summary = load_json(summary_path)
        subject = load_json(subject_path)
    except (OSError, ValueError, TypeError):
        errors.append("evidence_json")
        return None
    implementation_commit = str(subject.get("implementation_commit") or "")
    implementation_tree = str(subject.get("implementation_tree") or "")
    if not re.fullmatch(r"[0-9a-f]{40}", implementation_commit):
        errors.append("subject_implementation_commit")
        return None
    if (
        subject.get("schema_version") != "cyberboss.cb240.subject.v1"
        or subject.get("task_id") != "CB-240"
        or subject.get("product_version") != PRODUCT_VERSION
        or subject.get("taskpack_version") != TASKPACK_VERSION
        or subject.get("taskpack_zip_sha256") != TASKPACK_ZIP_SHA256
        or subject.get("public_implementation_commit") != PUBLIC_IMPLEMENTATION_COMMIT
        or git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[0] != 0
        or git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1]
        != implementation_tree
        or git("merge-base", "--is-ancestor", PUBLIC_IMPLEMENTATION_COMMIT, implementation_commit, check=False)[0]
        != 0
        or subject.get("summary_sha256") != sha256(summary_path)
        or subject.get("deployment_release_pointer") != "activation_pending"
        or subject.get("real_private_database_operations") != 0
        or subject.get("real_r2_operations") != 0
        or subject.get("control_plane_llm_calls") != 0
        or subject.get("operations_llm_calls") != 0
    ):
        errors.append("subject_contract")
    if (
        summary.get("schema_version") != "cyberboss.cb240.closure-summary.v1"
        or summary.get("task_id") != "CB-240"
        or summary.get("product_version") != PRODUCT_VERSION
        or summary.get("taskpack_version") != TASKPACK_VERSION
        or summary.get("taskpack_zip_sha256") != TASKPACK_ZIP_SHA256
        or summary.get("implementation_commit") != implementation_commit
        or summary.get("implementation_tree") != implementation_tree
        or summary.get("public_implementation_commit") != PUBLIC_IMPLEMENTATION_COMMIT
        or summary.get("acceptance") != {oracle: "passed" for oracle in AMENDMENT_ORACLES}
        or summary.get("private_database_activation") != "activation_pending"
        or summary.get("real_private_database_operations") != 0
        or summary.get("real_r2_operations") != 0
        or summary.get("control_plane_llm_calls") != 0
        or summary.get("operations_llm_calls") != 0
        or summary.get("macos_launchd_dependency") is not False
        or summary.get("pg_2_executed") is not False
        or summary.get("result") != "passed"
    ):
        errors.append("summary_contract")
    for path in EVIDENCE.iterdir():
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "CB240-PRIVATE" in text:
            errors.append(f"evidence_secret:{path.name}")
        if "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_absolute_path:{path.name}")
    return implementation_commit


def validate_commit_boundaries(
    implementation_commit: str | None,
    final: bool,
    errors: list[str],
) -> None:
    if implementation_commit is None:
        return
    implementation_paths = commit_paths(implementation_commit)
    unexpected_implementation = sorted(implementation_paths - IMPLEMENTATION_PATHS)
    errors.extend(f"implementation_path:{path}" for path in unexpected_implementation)
    if final:
        closure_paths = set(
            filter(
                None,
                git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines(),
            )
        )
        unexpected_closure = sorted(closure_paths - CLOSURE_PATHS)
        errors.extend(f"closure_path:{path}" for path in unexpected_closure)
        if not CLOSURE_PATHS <= closure_paths:
            errors.append("closure_atomic_inventory")


def validate(final: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    branch = git("branch", "--show-current")[1]
    if not branch.startswith("codex/cyberboss-"):
        errors.append("branch_scope")
    if git("merge-base", "--is-ancestor", PUBLIC_IMPLEMENTATION_COMMIT, "HEAD", check=False)[0] != 0:
        errors.append("public_implementation_missing")
    if git("status", "--porcelain=v1", "--untracked-files=all")[1]:
        errors.append("worktree_dirty")
    if list(PROJECT.rglob(".git")):
        errors.append("nested_git_repository")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        if row.startswith("160000 "):
            errors.append(f"gitlink:{row}")

    validate_state(final, errors)
    validate_contract(errors)
    validate_code_markers(errors)
    try:
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        verify_manifest(KIT / "MANIFEST.sha256", errors)
    except (OSError, ValueError) as error:
        errors.append(f"manifest_exception:{type(error).__name__}")

    implementation_commit = validate_subject_and_evidence(errors) if final else git("rev-parse", "HEAD")[1]
    validate_commit_boundaries(implementation_commit, final, errors)

    for name, args, cwd, markers, timeout in (
        (
            "canonical_sync",
            ["node", "--test", "test/canonical-sync.test.js", "test/job-scheduler.test.js"],
            PROJECT / "app",
            ("fail 0",),
            300,
        ),
        (
            "root_contract",
            ["node", "--test", "tests/canonical-sync.test.js"],
            PROJECT,
            ("fail 0",),
            360,
        ),
        (
            "identity_scope",
            [sys.executable, str(KIT / "tests/test_identity_scope.py")],
            REPO,
            ("OK",),
            300,
        ),
        (
            "config",
            [
                "node", str(KIT / "tests/validate_config.js"), "--allow-placeholders",
                str(KIT / "config/cyberboss.env.example"),
                str(KIT / "config/workspaces.json.example"),
            ],
            REPO,
            ("CONFIG_VALIDATION=PASS",),
            300,
        ),
        (
            "install_check",
            ["bash", str(KIT / "scripts/install-canonical-sync.sh"), "--check", "--release-id", "0" * 40],
            REPO,
            ("CANONICAL_SYNC_INSTALL_CHECK=PASS",),
            300,
        ),
        (
            "acceptance_check",
            ["bash", str(KIT / "scripts/accept-canonical-sync.sh"), "--check", "--release-id", "0" * 40],
            REPO,
            ("CANONICAL_SYNC_ACCEPTANCE_CHECK=PASS",),
            300,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
        ("app_test", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            REPO,
            ("TASKPACK_VALIDATION=PASS",),
            300,
        ),
    ):
        run_command(name, args, errors, cwd=cwd, markers=markers, timeout=timeout)

    reports = [
        f"mode={'final' if final else 'prepare'}",
        f"branch={branch}",
        f"errors={len(errors)}",
    ]
    return errors, reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Validate the clean implemented_not_accepted CB-240 subject.",
    )
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for report in reports:
        print(report)
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB240_VALIDATION=FAIL")
        return 1
    print("CB240_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
