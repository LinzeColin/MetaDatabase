#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P2.4 / CB-230."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-230"
BASE_COMMIT = "916651854a6402254724c885398060b2e267e496"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"
EXPECTED_ACCEPTANCE = [
    "AC-020",
    "AC-021",
    "AC-022",
    "AC-024",
    "AC-025",
    "AC-062",
]

IMPLEMENTATION_PATHS = {
    "CyberBoss/app/migrations/004_cb230_durable_outbox.sql",
    "CyberBoss/app/package.json",
    "CyberBoss/app/scripts/durable-outbox-acceptance.js",
    "CyberBoss/app/src/adapters/channel/weixin/api.js",
    "CyberBoss/app/src/adapters/channel/weixin/index.js",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/core/stream-delivery.js",
    "CyberBoss/app/src/services/db/database-adapter.js",
    "CyberBoss/app/src/services/inbox/durable-inbox.js",
    "CyberBoss/app/src/services/jobs/job-scheduler.js",
    "CyberBoss/app/src/services/outbox/durable-outbox.js",
    "CyberBoss/app/test/durable-inbox-crash-cut.test.js",
    "CyberBoss/app/test/durable-outbox-crash-cut.test.js",
    "CyberBoss/app/test/runtime-spool.test.js",
    "CyberBoss/app/test/stream-delivery.test.js",
    "CyberBoss/app/test/turn-gate-store.test.js",
    "CyberBoss/app/test/weixin-outbox-transport.test.js",
    "CyberBoss/docs/governance/RUN_CONTRACT_P2_4_CB_230.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-durable-outbox.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-durable-outbox-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-durable-outbox.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb230.py",
    "CyberBoss/tests/durable-outbox.test.js",
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
    "implementation-commit.json",
    "install-apply.redacted.json",
    "outbox-recovery-matrix.redacted.json",
    "publication-check.json",
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
    "CyberBoss/docs/evidence/CB-210",
    "CyberBoss/docs/evidence/CB-220",
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
        "CB-000",
        "CB-010",
        "CB-020",
        "CB-030",
        "CB-040",
        "CB-100",
        "CB-110",
        "CB-120",
        "CB-130",
        "CB-140",
        "CB-200",
        "CB-210",
        "CB-220",
    }
    if final:
        passed.add("CB-230")
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
            "run_id": "P2.4",
            "gate_id": None,
            "task_id": "CB-230",
            "scope": "durable_outbox_delivery_truth",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P2.3",
            "gate_id": None,
            "task_id": "CB-220",
            "scope": "scheduler_resource_workspace_runtime_control",
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
        implementation.get("task_id") != "CB-230"
        or implementation.get("phase") != "P2.4"
        or implementation.get("base_commit") != BASE_COMMIT
        or not re.fullmatch(r"[0-9a-f]{40}", str(implementation_commit))
        or git("rev-parse", f"{implementation_commit}^")[1] != BASE_COMMIT
        or git(
            "diff",
            "--quiet",
            implementation_commit,
            "HEAD",
            "--",
            *sorted(IMPLEMENTATION_PATHS),
            check=False,
        )[0]
        != 0
    ):
        errors.append("evidence_implementation")

    matrix = load_json(EVIDENCE / "outbox-recovery-matrix.redacted.json")
    try:
        cases = matrix["ac_062_recovery"]["cases"]
        dispatched = next(
            row
            for row in cases
            if row["cut"] == "provider_returned_before_confirmation_commit"
        )
        confirmed = next(
            row
            for row in cases
            if row["cut"] == "confirmation_committed_before_crash"
        )
        if (
            matrix.get("task_id") != "CB-230"
            or matrix.get("phase") != "P2.4"
            or matrix.get("release_commit") != implementation_commit
            or matrix.get("target_id_sha256") != EXPECTED_TARGET_HASH
            or matrix.get("result") != "passed"
            or matrix["ac_020_send_before_crash"]["restart_delivery_count"] != 1
            or matrix["ac_021_retry"]["provider_sequence"] != [503, 503, 200]
            or matrix["ac_021_retry"]["attempts"] != 3
            or matrix["ac_021_retry"]["retry_delays_ms"] != [1000, 2000]
            or matrix["ac_021_retry"]["real_wait_calls"] != 0
            or matrix["ac_022_dedupe"]["stage_count"] != 1000
            or matrix["ac_022_dedupe"]["confirmed_delivery_count"] != 1
            or matrix["ac_024_terminal"]["raw_provider_detail_forwarded"] is not False
            or matrix["ac_025_chunks"]["source_sha256"]
            != matrix["ac_025_chunks"]["reconstructed_sha256"]
            or matrix["ac_025_chunks"][
                "replied_before_all_final_chunks_confirmed"
            ]
            is not False
            or matrix["ac_062_recovery"][
                "unknown_dispatch_auto_replay_count"
            ]
            != 0
            or dispatched["provider_calls"] != 1
            or dispatched["confirmation_state"] != "ambiguous"
            or confirmed["provider_calls"] != 1
            or confirmed["job_status"] != "replied"
            or matrix["confirmation_truth"]["void_receipt"][
                "void_response_confirmed"
            ]
            is not False
            or matrix["security"]["plaintext_db_wal_shm_hits"] != 0
            or matrix["security"]["encryption_key_hits"] != 0
            or matrix["boundaries"]["cb_240_executed"] is not False
            or matrix["boundaries"]["pg_2_executed"] is not False
        ):
            errors.append("evidence_outbox_matrix")
    except (KeyError, StopIteration, TypeError):
        errors.append("evidence_outbox_matrix_shape")

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    source = artifact.get("source") or {}
    outbox = artifact.get("durable_outbox") or {}
    if (
        artifact.get("task_id") != "CB-230"
        or artifact.get("phase") != "P2.4"
        or artifact.get("release_commit") != implementation_commit
        or source.get("license_expression") != STRICT_LICENSE
        or source.get("original_licenses_preserved") is not True
        or source.get("upstream_clarification_received") is not False
        or artifact.get("runtime_spool", {}).get("schema_version") != 4
        or artifact.get("runtime_spool", {}).get("outbox_worker_integrated")
        is not True
        or outbox.get("staged_before_provider") is not True
        or outbox.get("provider_confirmation_required") is not True
        or outbox.get("unknown_outcome_auto_replay") is not False
        or outbox.get("replay_count") != 1000
        or outbox.get("canonical_sync_integrated") is not False
        or outbox.get("cb_240_executed") is not False
        or outbox.get("pg_2_executed") is not False
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
    if (
        install.get("release_commit") != implementation_commit
        or install.get("apply_count") != 2
        or install.get("verify_count") != 1
        or install.get("idempotent_second_apply") is not True
        or install.get("candidate_retained") is not True
        or install.get("staging_cleaned") is not True
    ):
        errors.append("evidence_install")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("plaintext_scan_hits") != 0
        or security.get("secret_scan_hits") != 0
        or security.get("raw_target_hits") != 0
        or security.get("real_credentials_used") is not False
        or security.get("real_provider_used") is not False
        or security.get("private_database_operations") != 0
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

    source_record = load_json(EVIDENCE / "source-modification-record.json")
    if (
        source_record.get("license_expression") != STRICT_LICENSE
        or source_record.get("original_source_and_licenses_preserved") is not True
        or source_record.get("conflict_record_preserved") is not True
        or source_record.get("upstream_clarification_received") is not False
        or source_record.get("upstream_sync_enabled") is not False
        or source_record.get("result") != "passed"
    ):
        errors.append("evidence_source_record")

    rollback = load_json(EVIDENCE / "rollback-plan.json")
    if (
        rollback.get("candidate_retained_for_audit") is not True
        or rollback.get("current_release_rollback_required") is not False
        or rollback.get("canonical_database_rollback_required") is not False
        or rollback.get("exact_staging_cleanup_completed") is not True
        or rollback.get("result") != "passed"
    ):
        errors.append("evidence_rollback")

    report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
    for marker in (
        "CB-230 Validation Report",
        "Task state: `passed`",
        "CB-240: `not_started`",
        "PG-2: `not_started`",
        "confirmed delivery count: `1`",
        "unknown dispatch auto replay: `0`",
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
        if SECRET_PATTERN.search(text) or "CB230-FIXTURE" in text:
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
        and not path.startswith("CyberBoss/docs/evidence/CB-230/")
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
        PROJECT / "docs/governance/RUN_CONTRACT_P2_4_CB_230.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "P2.4 / CB-230",
        BASE_COMMIT,
        *EXPECTED_ACCEPTANCE,
        "ambiguous_send_outcome",
        "manual reconcile",
        "CB-240",
        "PG-2",
        STRICT_LICENSE,
        "upstream_clarification_received=false",
        "不创建新 repo",
        "不 push",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")

    dag = yaml.safe_load(
        (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
    )
    task = next((row for row in dag["tasks"] if row.get("id") == "CB-230"), {})
    if (
        task.get("phase") != "P2.4"
        or task.get("stage") != "S2"
        or task.get("dependencies") != ["CB-210", "CB-220"]
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
        row for row in ledger.get("entries", []) if row.get("task_id") == "CB-230"
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

    for name, args, cwd, required, timeout in (
        (
            "durable_outbox",
            ["node", "--test", "test/durable-outbox-crash-cut.test.js"],
            PROJECT / "app",
            ("fail 0",),
            300,
        ),
        (
            "root_contract",
            ["node", "--test", "tests/durable-outbox.test.js"],
            PROJECT,
            ("fail 0",),
            360,
        ),
        ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
        ("app_test", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
        (
            "prestage",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            REPO,
            ("PRESTAGE0_VALIDATION=PASS",),
            300,
        ),
        (
            "taskpack",
            [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)],
            REPO,
            ("TASKPACK_VALIDATION=PASS",),
            300,
        ),
    ):
        run_command(
            name,
            args,
            errors,
            cwd=cwd,
            required=required,
            timeout=timeout,
        )

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
        help="Validate the frozen CB-220 state before CB-230 closure.",
    )
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for report in reports:
        print(report)
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("CB230_VALIDATION=FAIL")
        return 1
    print("CB230_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
