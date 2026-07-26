#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P2.2 / CB-210."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-210"
BASE_COMMIT = "4f914e3b6ed3145a16c1572f4176068b9829b920"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
EXPECTED_ACCEPTANCE = ["AC-004", "AC-023", "AC-063"]

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/package.json",
    "CyberBoss/app/scripts/durable-inbox-acceptance.js",
    "CyberBoss/app/src/adapters/channel/weixin/index.js",
    "CyberBoss/app/src/adapters/channel/weixin/message-utils.js",
    "CyberBoss/app/src/adapters/channel/weixin/sync-buffer-store.js",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/services/db/database-adapter.js",
    "CyberBoss/app/src/services/inbox/durable-inbox.js",
    "CyberBoss/app/test/cloud-walking-skeleton-live.test.js",
    "CyberBoss/app/test/durable-inbox-crash-cut.test.js",
    "CyberBoss/app/test/weixin-cursor-commit.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P2_2_CB_210.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-inbox.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-durable-inbox-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-durable-inbox.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb210.py",
    "CyberBoss/tests/durable-inbox.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {
    "VALIDATION_REPORT.md",
    "artifact-checksums.txt",
    "artifact-manifest.json",
    "crash-matrix.redacted.json",
    "cursor-transcript.redacted.json",
    "db-query-results.redacted.json",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "ordering-property-report.json",
    "publication-check.json",
    "replay-report.json",
    "rollback-plan.json",
    "security-report.json",
    "source-modification-record.json",
    "target-preflight.redacted.json",
    "validation.txt",
}
FROZEN_PATHS = [
    "CyberBoss/vendor",
    "CyberBoss/docs/evidence/CB-000",
    "CyberBoss/docs/evidence/CB-010",
    "CyberBoss/docs/evidence/CB-020",
    "CyberBoss/docs/evidence/CB-030",
    "CyberBoss/docs/evidence/CB-040",
    "CyberBoss/docs/evidence/CB-100",
    "CyberBoss/docs/evidence/CB-110",
    "CyberBoss/docs/evidence/CB-120",
    "CyberBoss/docs/evidence/CB-130",
    "CyberBoss/docs/evidence/CB-140",
    "CyberBoss/docs/evidence/CB-200",
    "CyberBoss/docs/evidence/PG-0",
    "CyberBoss/docs/evidence/PG-1",
    "CyberBoss/docs/product_design/v0.0.0.4/00_README_FIRST.md",
    "CyberBoss/docs/product_design/v0.0.0.4/01_PRFAQ_STRATEGY_OKR.md",
    "CyberBoss/docs/product_design/v0.0.0.4/02_PRD_ACCEPTANCE_CONTRACT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
    "CyberBoss/docs/product_design/v0.0.0.4/04_TASK_DAG_EXECUTION_PACK.yaml",
    "CyberBoss/docs/product_design/v0.0.0.4/05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md",
    "CyberBoss/docs/product_design/v0.0.0.4/06_OPERATIONS_STATUS_HANDOVER.md",
    "CyberBoss/docs/product_design/v0.0.0.4/07_RESEARCH_COMPETITOR_UPSTREAM_FINDINGS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/08_UPSTREAM_CODE_CHANGE_MAP.md",
    "CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/10_TRACEABILITY_RELEASE_CHECKLIST.md",
    "CyberBoss/docs/product_design/v0.0.0.4/11_AGENT_EXECUTION_PROMPTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/12_CURRENT_ROADMAP.md",
    "CyberBoss/docs/product_design/v0.0.0.4/13_STAGE2B_STAGE3_UPGRADES.md",
    "CyberBoss/docs/product_design/v0.0.0.4/14_PURSUING_GOAL.txt",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/sql/runtime-spool.sql",
    "CyberBoss/machine/source-lock.json",
    "CyberBoss/LICENSE",
    "CyberBoss/THIRD_PARTY_NOTICES.md",
    "CyberBoss/UPSTREAM_PROVENANCE.md",
]
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
    r"|\bwxid_[A-Za-z0-9_-]+\b"
    r"|\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._~-]{20,}",
    re.IGNORECASE,
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        raise RuntimeError(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{result.stderr.strip()[:180]}"
        )
    return result.returncode, result.stdout.rstrip()


def changed_paths() -> set[str]:
    paths = set(
        filter(None, git("diff", "--name-only", BASE_COMMIT, "HEAD")[1].splitlines())
    )
    status = git("status", "--porcelain=v1", "--untracked-files=all")[1]
    for raw in status.splitlines():
        value = raw[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        if value:
            paths.add(value)
    return paths


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
    cwd: Path = REPO,
    required: tuple[str, ...] = (),
    timeout: int = 600,
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
    for marker in required:
        if marker not in result.stdout:
            errors.append(f"command_marker:{name}:{marker}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row["id"]: row["status"] for row in state["tasks"]}
    passed = {
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040",
        "CB-100", "CB-110", "CB-120", "CB-130", "CB-140", "CB-200",
    }
    if final:
        passed.add("CB-210")
    for task_id, status in statuses.items():
        expected = "passed" if task_id in passed else "not_started"
        if status != expected:
            errors.append(f"task_state:{task_id}:{status}:{expected}")
    gates = state.get("pass_gates") or {}
    if gates.get("PG-0") != "passed" or gates.get("PG-1") != "passed":
        errors.append("prior_gates")
    for gate in ("PG-2", "PG-3", "PG-4", "PG-5"):
        if gates.get(gate) != "not_started":
            errors.append(f"later_gate:{gate}")
    expected_current = (
        {
            "run_id": "P2.2",
            "gate_id": None,
            "task_id": "CB-210",
            "scope": "durable_inbox_before_weixin_cursor",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P2.1",
            "gate_id": None,
            "task_id": "CB-200",
            "scope": "sqlite_wal_spool_and_job_state_machine",
            "status": "passed",
        }
    )
    if state.get("current_run") != expected_current:
        errors.append("current_run")


def validate_final_evidence(errors: list[str]) -> None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_missing")
        return
    inventory = {path.name for path in EVIDENCE.iterdir() if path.is_file()}
    if inventory != FINAL_EVIDENCE:
        errors.append(
            "evidence_inventory:"
            f"missing={sorted(FINAL_EVIDENCE - inventory)}:"
            f"extra={sorted(inventory - FINAL_EVIDENCE)}"
        )
        return

    implementation = load_json(EVIDENCE / "implementation-commit.json")
    implementation_commit = implementation.get("implementation_commit")
    if (
        implementation.get("task_id") != "CB-210"
        or implementation.get("phase") != "P2.2"
        or implementation.get("base_commit") != BASE_COMMIT
        or not re.fullmatch(r"[0-9a-f]{40}", str(implementation_commit))
        or git("rev-parse", f"{implementation_commit}^")[1] != BASE_COMMIT
        or git("diff", "--quiet", implementation_commit, "HEAD", "--",
               *sorted(IMPLEMENTATION_PATHS), check=False)[0] != 0
    ):
        errors.append("evidence_implementation")

    crash = load_json(EVIDENCE / "crash-matrix.redacted.json")
    cases = crash.get("cases") or []
    expected_cuts = {
        "after_fetch_before_durable",
        "after_durable_before_cursor",
        "after_cursor",
    }
    if (
        crash.get("task_id") != "CB-210"
        or crash.get("phase") != "P2.2"
        or crash.get("result") != "passed"
        or {row.get("cut") for row in cases} != expected_cuts
        or any(
            row.get("message_lost") is not False
            or row.get("inbox_count") != 1
            or row.get("job_count") != 1
            or row.get("execution_count") != 1
            for row in cases
        )
    ):
        errors.append("evidence_crash")

    replay = load_json(EVIDENCE / "replay-report.json")
    if (
        replay.get("replay_count") != 1000
        or replay.get("inbox_count") != 1
        or replay.get("job_count") != 1
        or replay.get("execution_count") != 1
        or replay.get("result") != "passed"
    ):
        errors.append("evidence_replay")

    ordering = load_json(EVIDENCE / "ordering-property-report.json")
    if (
        ordering.get("result") != "passed"
        or ordering.get("numeric_contiguous_commit") is not True
        or ordering.get("reversed_batch_sorted") is not True
        or ordering.get("gap_rejected") is not True
        or ordering.get("duplicate_sequence_rejected") is not True
        or ordering.get("regression_rejected") is not True
    ):
        errors.append("evidence_ordering")

    queries = load_json(EVIDENCE / "db-query-results.redacted.json")
    if (
        queries.get("integrity_check") != "ok"
        or queries.get("committed_inbox_rpo") != 0
        or queries.get("canonical_reconcile_set_diff") != 0
        or queries.get("result") != "passed"
    ):
        errors.append("evidence_queries")

    cursor = load_json(EVIDENCE / "cursor-transcript.redacted.json")
    if (
        cursor.get("fetch_writes_cursor") is not False
        or cursor.get("cursor_commit_after_durable") is not True
        or cursor.get("cursor_regression_allowed") is not False
        or cursor.get("stale_writer_allowed") is not False
        or cursor.get("result") != "passed"
    ):
        errors.append("evidence_cursor")

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    artifact_source = artifact.get("source") or {}
    durable_inbox = artifact.get("durable_inbox") or {}
    if (
        artifact.get("task_id") != "CB-210"
        or artifact.get("phase") != "P2.2"
        or artifact.get("release_commit") != implementation_commit
        or artifact_source.get("license_expression") != STRICT_LICENSE
        or artifact_source.get("upstream_clarification_received") is not False
        or durable_inbox.get("candidate_cursor_api") is not True
        or durable_inbox.get("cursor_commit_after_durable") is not True
        or durable_inbox.get("numeric_continuity_guard") is not True
        or durable_inbox.get("stable_source_id_required") is not True
        or durable_inbox.get("replay_count") != 1000
        or durable_inbox.get("scheduler_integrated") is not False
        or durable_inbox.get("outbox_worker_integrated") is not False
        or durable_inbox.get("real_wechat") is not False
        or durable_inbox.get("real_runtime") is not False
        or durable_inbox.get("pg_2_executed") is not False
    ):
        errors.append("evidence_artifact")

    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    install = load_json(EVIDENCE / "install-apply.redacted.json")
    for name, document in (("preflight", preflight), ("install", install)):
        if (
            document.get("target_id_sha256") != EXPECTED_TARGET_HASH
            or document.get("current_release_before") != EXPECTED_CURRENT
            or document.get("current_release_after") != EXPECTED_CURRENT
            or document.get("workspace_release_before") != EXPECTED_WORKSPACE
            or document.get("workspace_release_after") != EXPECTED_WORKSPACE
            or document.get("service_enabled") is not False
            or document.get("service_active") is not False
            or document.get("process_count") != 0
            or document.get("listener_count") != 0
            or document.get("incoming_count") != 0
            or document.get("canonical_runtime_db_present") is not False
            or document.get("result") != "passed"
        ):
            errors.append(f"evidence_target_{name}")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("plaintext_scan_hits") != 0
        or security.get("secret_scan_hits") != 0
        or security.get("real_credentials_used") is not False
        or security.get("real_provider_used") is not False
        or security.get("result") != "passed"
    ):
        errors.append("evidence_security")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("remote_branch_count") != 0
        or publication.get("pr_count") != 0
        or publication.get("tag_count") != 0
        or publication.get("release_count") != 0
        or publication.get("push_performed") is not False
        or publication.get("result") != "passed"
    ):
        errors.append("evidence_publication")

    report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "CB-210 Validation Report",
        "Task state: `passed`",
        "CB-220: `not_started`",
        "synthetic execution",
        "CB-220",
        "activation_pending",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
    ):
        if marker not in report:
            errors.append(f"evidence_report:{marker}")

    for path in EVIDENCE.iterdir():
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text):
            errors.append(f"evidence_secret:{path.name}")
        ipv4_values = re.findall(
            r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])",
            text,
        )
        if any(value != "127.0.0.1" for value in ipv4_values):
            errors.append(f"evidence_ipv4:{path.name}")


def validate(final: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    reports: list[str] = []
    if git("branch", "--show-current")[1] != EXPECTED_BRANCH:
        errors.append("branch")
    if git("remote")[1].splitlines() != ["origin"]:
        errors.append("remotes")
    if git("remote", "get-url", "origin")[1] != EXPECTED_ORIGIN:
        errors.append("origin")
    remote_code, remote = git(
        "ls-remote",
        "--exit-code",
        "--heads",
        "origin",
        f"refs/heads/{EXPECTED_BRANCH}",
        check=False,
    )
    if remote_code != 2 or remote:
        errors.append("remote_publication")
    if git("merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False)[0] != 0:
        errors.append("base_not_ancestor")

    allowed = IMPLEMENTATION_PATHS | CLOSURE_PATHS
    unexpected = sorted(
        path
        for path in changed_paths()
        if path not in allowed
        and not path.startswith("CyberBoss/docs/evidence/CB-210/")
    )
    errors.extend(f"unexpected_path:{path}" for path in unexpected)
    for frozen in FROZEN_PATHS:
        if git("diff", "--quiet", BASE_COMMIT, "--", frozen, check=False)[0] != 0:
            errors.append(f"frozen_path:{frozen}")
    if list(PROJECT.rglob(".git")):
        errors.append("nested_git_repository")
    for row in git("ls-files", "-s", "CyberBoss")[1].splitlines():
        if row.startswith("160000 "):
            errors.append(f"gitlink:{row}")

    contract = (
        PROJECT / "docs/governance/RUN_CONTRACT_P2_2_CB_210.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P2.2 / CB-210",
        BASE_COMMIT,
        "AC-004",
        "AC-023",
        "AC-063",
        "INV-001",
        "INV-002",
        "after_fetch_before_durable",
        "after_durable_before_cursor",
        "after_cursor",
        "1,000",
        "CB-220",
        "CB-230",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "不创建新 repo",
        "不 push",
    ):
        if marker not in contract:
            errors.append(f"contract:{marker}")

    dag = yaml.safe_load(
        (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
    )
    task = next(row for row in dag["tasks"] if row["id"] == "CB-210")
    if (
        task.get("phase") != "P2.2"
        or task.get("dependencies") != ["CB-200"]
        or task.get("acceptance_criteria") != EXPECTED_ACCEPTANCE
        or task.get("pass_gate") != "PG-2"
    ):
        errors.append("task_contract")

    source = load_json(PROJECT / "machine/source-lock.json")
    conflict = source["whereabouts_license_conflict"]
    if {
        item.strip() for item in conflict["compliance_expression"].split("AND")
    } != {"AGPL-3.0-only", "GPL-3.0-only"}:
        errors.append("license")
    if (
        conflict.get("preserve_original_license_and_source") is not True
        or conflict.get("upstream_clarification_received") is not False
        or any(source["upstream_relationship"].values())
        or source.get("repository") != "LinzeColin/MetaDatabase"
    ):
        errors.append("source_boundary")

    ledger = load_json(PROJECT / "machine/facts/post-baseline-change-ledger.json")
    entries = [
        row for row in ledger.get("entries", []) if row.get("task_id") == "CB-210"
    ]
    if len(entries) != 1 or entries[0].get("base_commit") != BASE_COMMIT:
        errors.append("modification_ledger")
    if (
        ledger.get("strict_compliance_expression") != STRICT_LICENSE
        or ledger.get("upstream_clarification_received") is not False
    ):
        errors.append("ledger_license")

    try:
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        verify_manifest(KIT / "MANIFEST.sha256", errors)
    except (OSError, ValueError) as error:
        errors.append(f"manifest_exception:{type(error).__name__}")

    validate_state(final, errors)
    if final:
        validate_final_evidence(errors)

    implementation_ready = all(
        (REPO / path).is_file()
        for path in (
            "CyberBoss/app/src/services/inbox/durable-inbox.js",
            "CyberBoss/app/test/durable-inbox-crash-cut.test.js",
            "CyberBoss/app/test/weixin-cursor-commit.test.js",
            "CyberBoss/tests/durable-inbox.test.js",
        )
    )
    if implementation_ready:
        commands = [
            (
                "cursor",
                ["node", "--test", "test/weixin-cursor-commit.test.js"],
                PROJECT / "app",
                ("fail 0",),
                240,
            ),
            (
                "durable_inbox",
                ["node", "--test", "test/durable-inbox-crash-cut.test.js"],
                PROJECT / "app",
                ("fail 0",),
                600,
            ),
            (
                "root_contract",
                ["node", "--test", "tests/durable-inbox.test.js"],
                PROJECT,
                ("fail 0",),
                240,
            ),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_test", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
        ]
        for name, args, cwd, required, timeout in commands:
            run_command(
                name, args, errors, cwd=cwd, required=required, timeout=timeout
            )
    elif final:
        errors.append("implementation_missing")

    for name, args, required, timeout in (
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            ("PRESTAGE0_VALIDATION=PASS",),
            300,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            ("TASKPACK_VALIDATION=PASS",),
            300,
        ),
    ):
        run_command(name, args, errors, required=required, timeout=timeout)

    reports.extend(
        [
            f"mode={'final' if final else 'prepare'}",
            f"base_commit={BASE_COMMIT}",
            f"changed_paths={len(changed_paths())}",
            f"errors={len(errors)}",
        ]
    )
    return errors, reports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="Validate the frozen CB-200 state before CB-210 closure.",
    )
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for report in reports:
        print(report)
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB210_VALIDATION=FAIL")
        return 1
    print("CB210_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
