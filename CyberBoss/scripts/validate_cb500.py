#!/usr/bin/env python3
"""Fail-closed, credential-free validator for CyberBoss P5.1 / CB-500."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

REPO = Path(__file__).resolve().parents[2]
PROJECT = REPO / "CyberBoss"
PACK = PROJECT / "docs/product_design/v0.0.0.4"
KIT = PACK / "implementation-kit"
EVIDENCE = PROJECT / "docs/evidence/CB-500"
TASKPACK = Path("/tmp/cyberboss-taskpack.u01gsE/CyberBoss_v0.0.0.7_FORMAL_DEVELOPMENT_TASKPACK_FINAL_20260727")

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
PG4_CLOSURE = "a5802bca6ac63c435121ab3bc970a6adededb7de"
PG4_TREE = "a505be6c6c5d68090b5cd7eee3742377b7c6cbdf"
CANDIDATE_RELEASE_ID = "bb86be91fedac363301d7704030a67925c166dc826b11f97a0f5cf4222495ad0"
CANDIDATE_MANIFEST_DIGEST = "4f83d414e4d950506c9430665e2b4875d9ad58e68b2e75bd31c5722dca9a66e4"
OPERATOR_RUNBOOK_DIGEST = "d26533392f38e0de26e1deab4c07a9365cdbc97a5f948503554c1db35afc9c9f"
REHEARSAL_DIGEST = "dec0e1518a5f99751a3c04b2c59ed3079f78f5a9ac807ba44add179a206448e1"
ACTIVATION_PLAN_DIGEST = "cbfde621243f8dba41650895765aa4ecdd994899ee1b47a018bb9f8e89af125c"

ACCEPTANCE = ("FA-AC-015", "FA-AC-018", "FA-AC-019", "FA-AC-024")
ROUTER_RESULT = {
    "task_id": "CB-500",
    "selected_skill": "webapp-testing",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 0,
    "fallback": "machine/skill_microplaybooks.json",
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/app/scripts/dress-rehearsal-suite.js",
    "CyberBoss/app/src/services/release/canonical-dress-rehearsal.js",
    "CyberBoss/app/test/canonical-dress-rehearsal.test.js",
    "CyberBoss/docs/governance/DRESS_REHEARSAL_CB_500.md",
    "CyberBoss/docs/governance/RUN_CONTRACT_P5_1_CB_500.md",
    "CyberBoss/scripts/validate_cb500.py",
    "CyberBoss/tests/dress-rehearsal-suite.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/CB-500/subject.json",
    "CyberBoss/docs/evidence/CB-500/summary.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
VALIDATION_NAMES = (
    "rehearsal_unit",
    "rehearsal_cli",
    "activation_plan_cli",
    "rehearsal_root_cli",
    "timeline_status_access",
    "backup_restore",
    "fault_matrix",
    "fault_postdeploy_plan",
    "immutable_candidate",
    "immutable_operator_plan",
    "canonical_sync",
    "software_correctness",
    "software_predeploy",
    "security_assurance",
    "cloud_install_layout",
    "runtime_spool_migration",
    "operator_contract",
    "skill_router",
    "zero_agent",
    "secret_scan",
    "pg4_anchor",
    "app_check",
    "app_regression",
    "identity_scope",
    "config",
    "dag",
    "traceability",
    "no_wait",
    "taskpack",
    "manifests",
)
LOCAL_VALIDATION = {name: "passed" for name in VALIDATION_NAMES}
EXTERNAL_ACTIVATION = {
    "candidate_installation": "activation_pending",
    "current_switch": "activation_pending",
    "live_request_count_canary": "activation_pending",
    "live_rollback": "activation_pending",
    "private_database": "activation_pending",
    "r2": "hazard_blocked",
    "cloudflare_access": "activation_pending",
    "dns_route": "activation_pending",
    "analytics": "activation_pending",
    "oci": "activation_pending",
    "timeline": "activation_pending",
    "global_status": "activation_pending",
    "self_heal": "activation_pending",
    "timer": "activation_pending",
    "service": "activation_pending",
}
SENSITIVE_ENV_FRAGMENTS = (
    "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH", "COOKIE", "SESSION",
    "PRIVATE_KEY", "ACCESS_KEY", "API_KEY", "OPENAI", "CODEX", "WECHAT",
    "CLOUDFLARE", "GITHUB",
)
SENSITIVE_ENV_PREFIXES = ("AWS_", "OCI_", "CF_", "GH_", "SSH_")
SECRET_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"|\bgh[pousr]_[A-Za-z0-9]{20,}\b"
    r"|\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"
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


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def is_sensitive_environment_key(key: str) -> bool:
    upper = key.upper()
    return any(fragment in upper for fragment in SENSITIVE_ENV_FRAGMENTS) or upper.startswith(SENSITIVE_ENV_PREFIXES)


def credential_free_environment(root: Path) -> tuple[dict[str, str], int]:
    environment: dict[str, str] = {}
    removed = 0
    for key, value in os.environ.items():
        if is_sensitive_environment_key(key):
            removed += 1
            continue
        environment[key] = value
    if any(is_sensitive_environment_key(key) for key in environment):
        raise RuntimeError("credential_environment_scrub_failed")
    for directory in (root / "npm-cache", root / "config", root / "tmp"):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update({
        "CI": "1",
        "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(root / "tmp"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_CACHE": str(root / "npm-cache"),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return environment, removed


def run_command(
    name: str,
    command: list[str],
    cwd: Path,
    environment: dict[str, str],
    errors: list[str],
    *,
    markers: tuple[str, ...] = (),
    timeout: int = 900,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as caught:
        errors.append(f"command_exception:{name}:{type(caught).__name__}")
        return {"name": name, "exit_code": None}
    output = result.stdout or ""
    if result.returncode != 0:
        tail = output.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command_failed:{name}:{result.returncode}:{tail[0][:180]}")
    for marker in markers:
        if marker not in output:
            errors.append(f"command_marker:{name}:{marker}")
    return {"name": name, "exit_code": result.returncode}


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
        if candidate.is_file() and candidate != path and "__pycache__" not in candidate.parts
    }
    if set(entries) != actual:
        errors.append(f"manifest_inventory:{path.relative_to(REPO)}")
    for relative, digest in entries.items():
        candidate = root / relative
        if not candidate.is_file() or sha256(candidate) != digest:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def validate_state(final: bool, errors: list[str]) -> None:
    try:
        state = load_json(PROJECT / "machine/facts/task_state.json")
    except (OSError, ValueError, TypeError):
        errors.append("task_state_read")
        return
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040",
        "CB-100", "CB-110", "CB-120", "CB-130", "CB-140",
        "CB-200", "CB-210", "CB-220", "CB-230", "CB-240",
        "CB-300", "CB-310", "CB-320", "CB-330", "CB-340",
        "CB-400", "CB-410", "CB-420", "CB-430", "CB-440",
    )
    report(errors, "task_state_prior", all(statuses.get(task) == "passed" for task in prior))
    expected = "passed" if final else "not_started"
    report(errors, "task_state_cb500", statuses.get("CB-500") == expected)
    report(
        errors,
        "task_state_future",
        all(statuses.get(task) == "not_started" for task in ("CB-510", "CB-520", "CB-530", "CB-540"))
        and state.get("pass_gates", {}).get("PG-5") == "not_started",
    )
    overlay = state.get("taskpack_overlay", {})
    common = (
        state.get("schema_version") == 1
        and state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("pg_4_executed") is True
        and overlay.get("stage_4_safe_release_gate_status") == "passed"
        and overlay.get("stage_4_subject_digest") == "34f540bea38fbb4dfef0d6a08f15e06bf8fa5827b9023198a1fcaff639a8a512"
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("r2_backup_activation") == "hazard_blocked"
        and overlay.get("formal_final_acceptance") == "activation_pending"
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_cb500_overlay",
            state.get("current_run") == {
                "run_id": "P5.1",
                "gate_id": None,
                "task_id": "CB-500",
                "scope": "clean_ephemeral_staging_dress_rehearsal_activation_plan",
                "status": "passed",
            }
            and overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("clean_staging_rehearsal_status") == "passed"
            and overlay.get("clean_staging_rehearsal_digest") == REHEARSAL_DIGEST
            and overlay.get("clean_staging_activation_plan_digest") == ACTIVATION_PLAN_DIGEST
            and overlay.get("clean_staging_operator_contract_status") == "passed"
            and overlay.get("clean_staging_real_activation") == "activation_pending"
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )
    else:
        report(
            errors,
            "task_state_preparation_anchor",
            state.get("current_run", {}).get("task_id") is None
            and overlay.get("skill_router", {}).get("task_id") == "PG-4",
        )


def validate_pg4_anchor(errors: list[str]) -> None:
    report(errors, "pg4_closure_commit", git("cat-file", "-e", f"{PG4_CLOSURE}^{{commit}}", check=False)[0] == 0)
    report(errors, "pg4_history", git("merge-base", "--is-ancestor", PG4_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "pg4_evidence_mutated", git("diff", "--quiet", PG4_CLOSURE, "--", "CyberBoss/docs/evidence/PG-4", check=False)[0] == 0)
    report(errors, "pg4_tree", git("rev-parse", f"{PG4_CLOSURE}^{{tree}}", check=False)[1] == PG4_TREE)
    try:
        summary = load_json(PROJECT / "docs/evidence/PG-4/summary.json")
        subject = load_json(PROJECT / "docs/evidence/PG-4/subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("pg4_evidence_read")
        return
    report(
        errors,
        "pg4_subject",
        summary.get("result") == "passed"
        and summary.get("formal_final_acceptance") == "activation_pending"
        and subject.get("summary_sha256") == sha256(PROJECT / "docs/evidence/PG-4/summary.json")
        and subject.get("stage_4_evidence_digest") == "34f540bea38fbb4dfef0d6a08f15e06bf8fa5827b9023198a1fcaff639a8a512",
    )


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P5_1_CB_500.md").read_text(encoding="utf-8")
    card = (PROJECT / "docs/governance/DRESS_REHEARSAL_CB_500.md").read_text(encoding="utf-8")
    for marker in (
        "P5.1 / CB-500", PRODUCT_VERSION, TASKPACK_VERSION, TASKPACK_ZIP_SHA256,
        PG4_CLOSURE, "FA-AC-015", "FA-AC-018", "FA-AC-019", "FA-AC-024",
        "AC-056", "AC-067", "AC-068", "AC-070", "webapp-testing",
        "NATIVE_IF_PRESENT_ELSE_EMBEDDED", "实际 Skill body load 为 0",
        "Private-Database", "activation_pending", "hazard_blocked", "CB-510",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")
    for marker in (
        "staging", "candidate", "operator", "Status", "Access", "Timeline",
        "fault", "backup", "restore", "canary", "activation plan",
        "activation_pending", "hazard_blocked", "launchd dependency",
    ):
        if marker.lower() not in card.lower():
            errors.append(f"card:{marker}")
    if (
        SECRET_PATTERN.search(contract)
        or SECRET_PATTERN.search(card)
        or "/Users/" in contract
        or "/Users/" in card
        or "/var/lib/" in contract
        or "/var/lib/" in card
    ):
        errors.append("contract_or_card_sensitive_or_absolute")


def validate_code(errors: list[str]) -> None:
    evaluator = (PROJECT / "app/src/services/release/canonical-dress-rehearsal.js").read_text(encoding="utf-8")
    cli = (PROJECT / "app/scripts/dress-rehearsal-suite.js").read_text(encoding="utf-8")
    app_test = (PROJECT / "app/test/canonical-dress-rehearsal.test.js").read_text(encoding="utf-8")
    root_test = (PROJECT / "tests/dress-rehearsal-suite.test.js").read_text(encoding="utf-8")
    for marker in (
        "DRESS_REHEARSAL_SCHEMA", "ACTIVATION_PLAN_SCHEMA", "runEphemeralStagingFixture",
        "buildCleanStagingRehearsal", "buildActivationPlan", "FROZEN_DRESS_REHEARSAL_STEPS",
        "DRESS_REHEARSAL_STEP_SET_INVALID", "discard_staging_keep_current",
        "physical_staging_fixture_executed", "activation_pending",
    ):
        if marker not in evaluator:
            errors.append(f"evaluator_marker:{marker}")
    for marker in (
        "--mode=", "DRESS_REHEARSAL_EXTERNAL_EXECUTION_DISABLED", "DRESS_REHEARSAL=PASS",
    ):
        if marker not in cli:
            errors.append(f"cli_marker:{marker}")
    for marker in ("P0 rehearsal failure", "hidden prerequisites", "activation plan"):
        if marker.lower() not in app_test.lower():
            errors.append(f"app_test_marker:{marker}")
    for marker in ("sealed local receipt", "cannot activate", "EXTERNAL_EXECUTION_DISABLED"):
        if marker.lower() not in root_test.lower():
            errors.append(f"root_test_marker:{marker}")
    forbidden = (
        "settimeout(", "setinterval(", "sleep(", "fetch(", "https.request",
        "http.request", "websocket", "launchctl", "launchdaemon",
        "com.apple.launchd", "systemctl", "child_process",
    )
    for label, content in (("evaluator", evaluator), ("cli", cli)):
        for marker in forbidden:
            if marker in content.lower():
                errors.append(f"forbidden_runtime:{label}:{marker}")


def validate_no_launchd(errors: list[str]) -> None:
    forbidden = ("launchctl", "launchdaemon", "launchagents", "com.apple.launchd")
    for root in (PROJECT / "app/src", PROJECT / "app/scripts"):
        for candidate in root.rglob("*"):
            if not candidate.is_file() or "node_modules" in candidate.parts:
                continue
            content = candidate.read_text(encoding="utf-8", errors="ignore").lower()
            if any(marker in content for marker in forbidden):
                errors.append(f"macos_launchd_dependency:{candidate.relative_to(REPO)}")


def run_clean_validation(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-cb500-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("rehearsal_unit", ["node", "--test", "test/canonical-dress-rehearsal.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("rehearsal_cli", ["node", "app/scripts/dress-rehearsal-suite.js", "rehearse", "--mode=local"], PROJECT, ("DRESS_REHEARSAL=PASS", REHEARSAL_DIGEST, ACTIVATION_PLAN_DIGEST), 300),
            ("activation_plan_cli", ["node", "app/scripts/dress-rehearsal-suite.js", "rehearse", "--mode=activation-plan"], PROJECT, ("DRESS_REHEARSAL=PASS", ACTIVATION_PLAN_DIGEST, "activation_pending"), 300),
            ("rehearsal_root_cli", ["node", "--test", "tests/dress-rehearsal-suite.test.js"], PROJECT, ("fail 0",), 300),
            ("timeline_status_access", ["node", "--test", "app/test/canonical-timeline-projection.test.js", "app/test/canonical-status-export.test.js", "app/test/canonical-access-domain.test.js"], PROJECT, ("fail 0",), 600),
            ("backup_restore", ["node", "--test", "app/test/canonical-backup-runtime.test.js"], PROJECT, ("fail 0",), 600),
            ("fault_matrix", ["node", "app/scripts/fault-recovery-suite.js", "evaluate", "--mode=matrix"], PROJECT, ("FAULT_RECOVERY_MATRIX=PASS",), 300),
            ("fault_postdeploy_plan", ["node", "app/scripts/fault-recovery-suite.js", "evaluate", "--mode=postdeploy-plan"], PROJECT, ("FAULT_RECOVERY_MATRIX=PASS",), 300),
            ("immutable_candidate", ["node", "app/scripts/immutable-release-suite.js", "evaluate", "--mode=local"], PROJECT, ("IMMUTABLE_RELEASE_CANDIDATE=PASS", CANDIDATE_MANIFEST_DIGEST), 300),
            ("immutable_operator_plan", ["node", "app/scripts/immutable-release-suite.js", "evaluate", "--mode=operator-plan"], PROJECT, ("IMMUTABLE_RELEASE_CANDIDATE=PASS", OPERATOR_RUNBOOK_DIGEST), 300),
            ("canonical_sync", ["node", "--test", "test/canonical-sync.test.js"], PROJECT / "app", ("fail 0",), 900),
            ("software_correctness", ["node", "--test", "test/software-correctness-suite.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("software_predeploy", ["node", "app/scripts/software-correctness-suite.js", "--mode=predeploy"], PROJECT, ("FROZEN_CORE_SUITE=PASS",), 900),
            ("security_assurance", ["node", "app/scripts/security-assurance-suite.js", "evaluate", "--mode=local"], PROJECT, ("SECURITY_ASSURANCE=PASS",), 900),
            ("cloud_install_layout", ["node", "--test", "tests/cloud-install-layout.test.js"], PROJECT, ("fail 0",), 600),
            ("runtime_spool_migration", ["node", "--test", "test/runtime-spool.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("operator_contract", [sys.executable, str(TASKPACK / "scripts/operator_contract_validate.py"), str(TASKPACK)], REPO, ('"status": "PASS"',), 300),
            ("skill_router", [sys.executable, str(TASKPACK / "scripts/skill_router_validate.py"), str(TASKPACK)], REPO, ('"status": "PASS"',), 300),
            ("zero_agent", [sys.executable, str(TASKPACK / "scripts/zero_agent_lint.py"), str(TASKPACK / "machine/zero_agent_contract.json")], REPO, ('"status": "PASS"',), 300),
            ("secret_scan", [sys.executable, str(KIT / "scripts/secret_scan.py"), "--repo", str(REPO), "--scope", "CyberBoss"], REPO, ('"result": "passed"', '"p0_findings": 0', '"p1_findings": 0'), 600),
            ("pg4_anchor", ["git", "diff", "--quiet", PG4_CLOSURE, "--", "CyberBoss/docs/evidence/PG-4"], REPO, (), 300),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_regression", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
            ("identity_scope", [sys.executable, str(KIT / "tests/test_identity_scope.py")], REPO, ("OK",), 300),
            ("config", ["node", str(KIT / "tests/validate_config.js"), "--allow-placeholders", str(KIT / "config/cyberboss.env.example"), str(KIT / "config/workspaces.json.example")], REPO, ("CONFIG_VALIDATION=PASS",), 300),
            ("dag", [sys.executable, str(KIT / "tests/validate_task_dag.py"), str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml")], REPO, ("DAG_VALIDATION=PASS tasks=30 stages=6",), 300),
            ("traceability", [sys.executable, str(KIT / "tests/validate_traceability.py"), str(PACK)], REPO, ("TRACEABILITY_VALIDATION=PASS requirements=53",), 300),
            ("no_wait", [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)], REPO, ("NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0",), 300),
            ("taskpack", [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)], REPO, ("TASKPACK_VALIDATION=PASS", "seven_is_minimum_not_limit=true"), 300),
        ]
        commands = [
            run_command(name, command, cwd, environment, errors, markers=markers, timeout=timeout)
            for name, command, cwd, markers, timeout in specs
        ]
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        verify_manifest(KIT / "MANIFEST.sha256", errors)
        commands.append({"name": "manifests", "exit_code": 0 if not any(error.startswith("manifest_") for error in errors) else 1})
        return {
            "credential_named_environment_keys_removed": removed_count,
            "network_or_provider_operations": 0,
            "real_time_waits": 0,
            "commands": commands,
        }


def validate_subject_and_evidence(errors: list[str]) -> str | None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_missing")
        return None
    inventory = {candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()}
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
    card_sha = sha256(PROJECT / "docs/governance/DRESS_REHEARSAL_CB_500.md")
    implementation_commit = str(subject.get("implementation_commit") or "")
    implementation_tree = str(subject.get("implementation_tree") or "")
    report(
        errors,
        "subject_contract",
        bool(re.fullmatch(r"[0-9a-f]{40}", implementation_commit))
        and subject.get("schema_version") == "cyberboss.cb500.subject.v1"
        and subject.get("task_id") == "CB-500"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("pg_4_closure_commit") == PG4_CLOSURE
        and subject.get("pg_4_tree") == PG4_TREE
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", PG4_CLOSURE, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("rehearsal_card_sha256") == card_sha
        and subject.get("rehearsal_digest") == REHEARSAL_DIGEST
        and subject.get("activation_plan_digest") == ACTIVATION_PLAN_DIGEST
        and subject.get("candidate_release_id") == CANDIDATE_RELEASE_ID
        and subject.get("candidate_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
        and subject.get("operator_runbook_digest") == OPERATOR_RUNBOOK_DIGEST
        and subject.get("deployment_release_pointer") == "activation_pending"
        and all(subject.get(key) == 0 for key in (
            "real_private_database_operations", "real_r2_operations", "real_cloudflare_operations",
            "real_oci_operations", "real_service_operations", "network_or_provider_operations",
            "control_plane_llm_calls", "operations_llm_calls", "real_time_waits",
        ))
        and subject.get("macos_launchd_dependency") is False,
    )
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.cb500.closure-summary.v1"
        and summary.get("task_id") == "CB-500"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("pg_4_closure_commit") == PG4_CLOSURE
        and summary.get("pg_4_tree") == PG4_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("rehearsal_card_sha256") == card_sha
        and summary.get("rehearsal_digest") == REHEARSAL_DIGEST
        and summary.get("activation_plan_digest") == ACTIVATION_PLAN_DIGEST
        and summary.get("candidate_release_id") == CANDIDATE_RELEASE_ID
        and summary.get("candidate_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
        and summary.get("operator_runbook_digest") == OPERATOR_RUNBOOK_DIGEST
        and summary.get("rehearsal_step_count") == 12
        and summary.get("operator_corrections") == []
        and summary.get("acceptance") == {oracle: "passed" for oracle in ACCEPTANCE}
        and summary.get("local_validation") == LOCAL_VALIDATION
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("go_no_go") == {
            "local_rehearsal": "go_local_only",
            "production_promotion": "activation_pending",
            "rollback": "not_required_current_unchanged",
            "p0_failure_count": 0,
        }
        and summary.get("external_activation") == EXTERNAL_ACTIVATION
        and all(summary.get(key) == 0 for key in (
            "real_private_database_operations", "real_r2_operations", "real_cloudflare_operations",
            "real_oci_operations", "real_service_operations", "network_or_provider_operations",
            "deployment_mutations", "control_plane_llm_calls", "operations_llm_calls", "real_time_waits",
        ))
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "CB-510",
    )
    for candidate in EVIDENCE.iterdir():
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", PG4_CLOSURE, implementation_commit, check=False)[0] == 0)
    report(errors, "implementation_inventory", commit_paths(implementation_commit) == IMPLEMENTATION_PATHS)
    if final:
        report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False)[0] == 0)
        closure_paths = set(filter(None, git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines()))
        report(errors, "closure_atomic_inventory", closure_paths == CLOSURE_PATHS)


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    branch = git("branch", "--show-current")[1]
    report(errors, "branch_scope", branch.startswith("codex/cyberboss-"))
    if final:
        report(errors, "worktree_dirty", not git("status", "--porcelain=v1", "--untracked-files=all")[1])
    report(errors, "taskpack_root", TASKPACK.is_dir())
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(errors, "gitlink", not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()))
    source = Path(__file__).read_text(encoding="utf-8")
    report(errors, "validator_no_sleep", all(marker not in source for marker in ("time" + ".sleep", "asyncio" + ".sleep")))
    report(errors, "diff_check", git("diff", "--check", PG4_CLOSURE, "HEAD", check=False)[0] == 0)
    validate_state(final, errors)
    validate_pg4_anchor(errors)
    validate_contract(errors)
    validate_code(errors)
    validate_no_launchd(errors)
    matrix = run_clean_validation(errors)
    implementation_commit = validate_subject_and_evidence(errors) if final else git("rev-parse", "HEAD")[1]
    validate_commit_boundaries(implementation_commit, final, errors)
    return errors, {
        "mode": "final" if final else "prepare",
        "branch": branch,
        "commands": len(matrix["commands"]),
        "errors": len(errors),
        "rehearsal_digest": REHEARSAL_DIGEST,
        "activation_plan_digest": ACTIVATION_PLAN_DIGEST,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate CB-500 implementation before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for issue in errors:
            print(f"ERROR={issue}")
        print("CB500_VALIDATION=FAIL")
        return 1
    print("CB500_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
