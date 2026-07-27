#!/usr/bin/env python3
"""Fail-closed, credential-free validator for CyberBoss P4.4 / CB-430."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-430"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB420_CLOSURE = "9f70eb6629d84e675d8df7183ae072b7e9bff7d7"
CB420_TREE = "5d3e7c840bbbbdeabe283e825aef02616191cfcd"
MATRIX_SCHEMA = "cyberboss.fault-recovery-matrix.v1"
POSTDEPLOY_SCHEMA = "cyberboss.postdeploy-fault-matrix.v1"
MATRIX_REPORT_DIGEST = "c366ae9973ddb46eed5e02cfbe1539bdcd9c1fd403fcc6958d413b5c400c8e99"
POSTDEPLOY_PLAN_DIGEST = "0a942dd2f9db5955630806f7d507f47ee8903c8db3c1bab9c0c62182a5ea2d11"
MATRIX_CARD_SHA256 = "60f56c1261d1742453e7b0881772cc7efcdce523f825d0ab39912f1cc9c5808b"
ACCEPTANCE = ("FA-AC-018", "FA-AC-019", "FA-AC-027")
ROUTER_RESULT = {
    "task_id": "CB-430",
    "selected_skill": "output-skill",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 1,
    "fallback": "machine/skill_microplaybooks.json",
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/app/scripts/fault-recovery-suite.js",
    "CyberBoss/app/src/services/assurance/canonical-fault-recovery-matrix.js",
    "CyberBoss/app/test/canonical-fault-recovery-matrix.test.js",
    "CyberBoss/docs/governance/FAULT_RECOVERY_MATRIX_CB_430.md",
    "CyberBoss/docs/governance/RUN_CONTRACT_P4_4_CB_430.md",
    "CyberBoss/scripts/validate_cb430.py",
    "CyberBoss/tests/fault-recovery-suite.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/CB-430/subject.json",
    "CyberBoss/docs/evidence/CB-430/summary.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
LOCAL_VALIDATION = {
    "matrix_unit": "passed",
    "matrix_cli": "passed",
    "postdeploy_plan_cli": "passed",
    "matrix_root_cli": "passed",
    "canonical_sync": "passed",
    "inbox_crash_cut": "passed",
    "outbox_crash_cut": "passed",
    "scheduler_lease": "passed",
    "cloud_supervisor": "passed",
    "backup_restore": "passed",
    "resource_policy": "passed",
    "secret_scan": "passed",
    "cb420_anchor": "passed",
    "cb410_anchor": "passed",
    "cb400_anchor": "passed",
    "app_check": "passed",
    "app_regression": "passed",
    "identity_scope": "passed",
    "config": "passed",
    "dag": "passed",
    "traceability": "passed",
    "no_wait": "passed",
    "taskpack": "passed",
    "manifests": "passed",
}
EXTERNAL_ACTIVATION = {
    "private_database": "activation_pending",
    "r2": "hazard_blocked",
    "cloudflare_access": "activation_pending",
    "cloudflare_web_analytics": "activation_pending",
    "dns_route": "activation_pending",
    "oci": "activation_pending",
    "timeline": "activation_pending",
    "global_status": "activation_pending",
    "self_heal": "activation_pending",
    "timer": "activation_pending",
    "service_runtime_channel_recovery": "activation_pending",
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
        ["git", *args], cwd=REPO, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
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
    cache = root / "npm-cache"
    config = root / "config"
    temporary = root / "tmp"
    for directory in (cache, config, temporary):
        directory.mkdir(parents=True, exist_ok=True)
    environment.update({
        "CI": "1",
        "NO_COLOR": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(temporary),
        "XDG_CONFIG_HOME": str(config),
        "NPM_CONFIG_USERCONFIG": "/dev/null",
        "NPM_CONFIG_CACHE": str(cache),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    })
    return environment, removed


def run_command(
    name: str, command: list[str], cwd: Path, environment: dict[str, str],
    errors: list[str], *, markers: tuple[str, ...] = (), timeout: int = 900,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command, cwd=cwd, env=environment, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, check=False, timeout=timeout,
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
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as caught:
        errors.append(f"manifest_read:{path.relative_to(REPO)}:{type(caught).__name__}")
        return
    for number, line in enumerate(lines, 1):
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
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100", "CB-110",
        "CB-120", "CB-130", "CB-140", "CB-200", "CB-210", "CB-220", "CB-230",
        "CB-240", "CB-300", "CB-310", "CB-320", "CB-330", "CB-340", "CB-400",
        "CB-410", "CB-420",
    )
    for task_id in prior:
        report(errors, f"task_state_prior:{task_id}", statuses.get(task_id) == "passed")
    report(errors, "task_state_cb430", statuses.get("CB-430") == ("passed" if final else "not_started"))
    for task_id in ("CB-440", "CB-500", "CB-510", "CB-520", "CB-530", "CB-540"):
        report(errors, f"task_state_future:{task_id}", statuses.get(task_id) == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", all(gates.get(gate) == "passed" for gate in ("PG-0", "PG-1", "PG-2", "PG-3")))
    report(errors, "task_state_later_gates", all(gates.get(gate) == "not_started" for gate in ("PG-4", "PG-5")))
    expected_current = (
        {
            "run_id": "P4.4", "gate_id": None, "task_id": "CB-430",
            "scope": "deterministic_fault_crash_cut_recovery_restore_matrix", "status": "passed",
        }
        if final
        else {
            "run_id": "P4.3", "gate_id": None, "task_id": "CB-420",
            "scope": "security_supply_chain_privacy_agpl_assurance", "status": "passed",
        }
    )
    report(errors, "task_state_current_run", state.get("current_run") == expected_current)
    overlay = state.get("taskpack_overlay") or {}
    common = (
        state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("software_correctness_status") == "passed"
        and overlay.get("model_safety_evaluation_status") == "passed"
        and overlay.get("security_assurance_status") == "passed"
        and overlay.get("r2_backup_activation") == "hazard_blocked"
        and overlay.get("oci_backup_activation") == "activation_pending"
        and overlay.get("self_heal_activation") == "activation_pending"
        and overlay.get("timer_activation") == "activation_pending"
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_cb430_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("fault_recovery_matrix_status") == "passed"
            and overlay.get("fault_recovery_case_count") == 14
            and overlay.get("postdeploy_fault_matrix_status") == "passed"
            and overlay.get("fault_recovery_real_execution") == "activation_pending"
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_cb420_anchor(errors: list[str]) -> None:
    report(errors, "cb420_closure_commit", git("cat-file", "-e", f"{CB420_CLOSURE}^{{commit}}", check=False)[0] == 0)
    report(errors, "cb420_history", git("merge-base", "--is-ancestor", CB420_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "cb420_evidence_mutated", git("diff", "--quiet", CB420_CLOSURE, "--", "CyberBoss/docs/evidence/CB-420", check=False)[0] == 0)
    report(errors, "cb420_tree", git("rev-parse", f"{CB420_CLOSURE}^{{tree}}", check=False)[1] == CB420_TREE)
    try:
        summary = load_json(PROJECT / "docs/evidence/CB-420/summary.json")
        subject = load_json(PROJECT / "docs/evidence/CB-420/subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("cb420_evidence_read")
        return
    report(
        errors,
        "cb420_subject",
        summary.get("result") == "passed"
        and summary.get("next_native_node") == "CB-430"
        and subject.get("summary_sha256") == sha256(PROJECT / "docs/evidence/CB-420/summary.json"),
    )


def validate_prior_anchors(errors: list[str]) -> None:
    for label, commit, evidence in (
        ("cb410", "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4", "CyberBoss/docs/evidence/CB-410"),
        ("cb400", "55192340a3bc80ac979e283a5308daee9158ad3e", "CyberBoss/docs/evidence/CB-400"),
    ):
        report(errors, f"{label}_history", git("merge-base", "--is-ancestor", commit, "HEAD", check=False)[0] == 0)
        report(errors, f"{label}_evidence_mutated", git("diff", "--quiet", commit, "--", evidence, check=False)[0] == 0)


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P4_4_CB_430.md").read_text(encoding="utf-8")
    matrix = (PROJECT / "docs/governance/FAULT_RECOVERY_MATRIX_CB_430.md").read_text(encoding="utf-8")
    body_load = "实际 Skill body load 为 " + chr(96) + "1" + chr(96)
    launchd = "macOS " + chr(96) + "launchd" + chr(96)
    for marker in (
        "P4.4 / CB-430", PRODUCT_VERSION, TASKPACK_VERSION, TASKPACK_ZIP_SHA256,
        "FA-AC-018", "FA-AC-019", "FA-AC-027", "output-skill",
        "NATIVE_IF_PRESENT_ELSE_EMBEDDED", body_load, "crash-cut", "activation_pending",
        "Private-Database", launchd, "CB-440",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")
    for marker in (
        "14", "fake clock", "unknown outcome", "isolated restore", "loss=0",
        "duplicate", "activation_pending", "manual_or_ci", "launchd dependency",
    ):
        if marker.lower() not in matrix.lower():
            errors.append(f"matrix_card:{marker}")
    if SECRET_PATTERN.search(contract) or SECRET_PATTERN.search(matrix) or "/Users/" in contract or "/Users/" in matrix:
        errors.append("contract_or_matrix_sensitive_or_absolute")


def validate_code(errors: list[str]) -> None:
    evaluator = (PROJECT / "app/src/services/assurance/canonical-fault-recovery-matrix.js").read_text(encoding="utf-8")
    cli = (PROJECT / "app/scripts/fault-recovery-suite.js").read_text(encoding="utf-8")
    app_test = (PROJECT / "app/test/canonical-fault-recovery-matrix.test.js").read_text(encoding="utf-8")
    root_test = (PROJECT / "tests/fault-recovery-suite.test.js").read_text(encoding="utf-8")
    for marker in (
        "FAULT_RECOVERY_SCHEMA", "POSTDEPLOY_FAULT_PLAN_SCHEMA", "buildFaultRecoveryMatrix",
        "buildPostdeployFaultMatrixPlan", "assertFrozenFaultRecoveryCases", "FROZEN_FAULT_RECOVERY_CASES",
        "inbox_persist_before_cursor", "outbox_unknown_outcome", "canonical_unknown_outcome",
        "backup_isolated_restore", "resource_bounded_recovery", "activation_pending",
        "FAULT_RECOVERY_LOSS_DETECTED", "FAULT_RECOVERY_UNBOUNDED_RETRY_DETECTED",
    ):
        if marker not in evaluator:
            errors.append(f"evaluator_marker:{marker}")
    for marker in ("--mode=", "FAULT_RECOVERY_REAL_EXECUTION_DISABLED", "FAULT_RECOVERY_MATRIX=PASS"):
        if marker not in cli:
            errors.append(f"cli_marker:{marker}")
    for marker in ("deterministic", "fails closed", "postdeploy fault plan"):
        if marker.lower() not in app_test.lower():
            errors.append(f"app_test_marker:{marker}")
    for marker in ("local deterministic", "rejects real execution", "FAULT_RECOVERY_REAL_EXECUTION_DISABLED"):
        if marker.lower() not in root_test.lower():
            errors.append(f"root_test_marker:{marker}")
    forbidden = (
        "settimeout(", "setinterval(", "sleep(", "launchctl", "launchdaemon",
        "com.apple.launchd", "fetch(", "https.request", "http.request", "websocket",
        "systemctl", "codexrpcclient", "runtimeadapter", "child_process",
    )
    for label, content in (("evaluator", evaluator), ("cli", cli)):
        for marker in forbidden:
            if marker in content.lower():
                errors.append(f"forbidden_runtime:{label}:{marker}")


def run_clean_validation(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-cb430-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("matrix_unit", ["node", "--test", "test/canonical-fault-recovery-matrix.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("matrix_cli", ["node", "app/scripts/fault-recovery-suite.js", "evaluate", "--mode=matrix"], PROJECT, ("FAULT_RECOVERY_MATRIX=PASS", MATRIX_REPORT_DIGEST), 300),
            ("postdeploy_plan_cli", ["node", "app/scripts/fault-recovery-suite.js", "evaluate", "--mode=postdeploy-plan"], PROJECT, ("FAULT_RECOVERY_MATRIX=PASS", POSTDEPLOY_PLAN_DIGEST), 300),
            ("matrix_root_cli", ["node", "--test", "tests/fault-recovery-suite.test.js"], PROJECT, ("fail 0",), 300),
            ("canonical_sync", ["node", "--test", "test/canonical-sync.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("inbox_crash_cut", ["node", "--test", "test/durable-inbox-crash-cut.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("outbox_crash_cut", ["node", "--test", "test/durable-outbox-crash-cut.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("scheduler_lease", ["node", "--test", "test/job-scheduler.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("cloud_supervisor", ["node", "--test", "test/cloud-supervisor.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("backup_restore", ["node", "--test", "test/canonical-backup-runtime.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("resource_policy", ["node", "--test", "test/canonical-operations-policy.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("secret_scan", [sys.executable, str(KIT / "scripts/secret_scan.py"), "--repo", str(REPO), "--scope", "CyberBoss"], REPO, ('"result": "passed"', '"p0_findings": 0', '"p1_findings": 0'), 600),
            ("cb420_anchor", ["git", "diff", "--quiet", CB420_CLOSURE, "--", "CyberBoss/docs/evidence/CB-420"], REPO, (), 300),
            ("cb410_anchor", ["git", "diff", "--quiet", "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4", "--", "CyberBoss/docs/evidence/CB-410"], REPO, (), 300),
            ("cb400_anchor", ["git", "diff", "--quiet", "55192340a3bc80ac979e283a5308daee9158ad3e", "--", "CyberBoss/docs/evidence/CB-400"], REPO, (), 300),
            ("app_check", ["npm", "run", "check"], PROJECT / "app", (), 300),
            ("app_regression", ["npm", "test"], PROJECT / "app", ("fail 0",), 900),
            ("identity_scope", [sys.executable, str(KIT / "tests/test_identity_scope.py")], REPO, ("OK",), 300),
            ("config", ["node", str(KIT / "tests/validate_config.js"), "--allow-placeholders", str(KIT / "config/cyberboss.env.example"), str(KIT / "config/workspaces.json.example")], REPO, ("CONFIG_VALIDATION=PASS",), 300),
            ("dag", [sys.executable, str(KIT / "tests/validate_task_dag.py"), str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml")], REPO, ("DAG_VALIDATION=PASS tasks=30 stages=6",), 300),
            ("traceability", [sys.executable, str(KIT / "tests/validate_traceability.py"), str(PACK)], REPO, ("TRACEABILITY_VALIDATION=PASS requirements=53",), 300),
            ("no_wait", [sys.executable, str(KIT / "tests/validate_no_wait.py"), str(PACK)], REPO, ("NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0",), 300),
            ("taskpack", [sys.executable, str(KIT / "tests/validate_taskpack.py"), str(PACK)], REPO, ("TASKPACK_VALIDATION=PASS", "seven_is_minimum_not_limit=true"), 300),
        ]
        commands = [run_command(name, command, cwd, environment, errors, markers=markers, timeout=timeout) for name, command, cwd, markers, timeout in specs]
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
    implementation_commit = str(subject.get("implementation_commit") or "")
    implementation_tree = str(subject.get("implementation_tree") or "")
    report(
        errors,
        "subject_contract",
        bool(re.fullmatch(r"[0-9a-f]{40}", implementation_commit))
        and subject.get("schema_version") == "cyberboss.cb430.subject.v1"
        and subject.get("task_id") == "CB-430"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb_420_closure_commit") == CB420_CLOSURE
        and subject.get("cb_420_tree") == CB420_TREE
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", CB420_CLOSURE, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("matrix_card_sha256") == MATRIX_CARD_SHA256
        and subject.get("matrix_report_digest") == MATRIX_REPORT_DIGEST
        and subject.get("postdeploy_plan_digest") == POSTDEPLOY_PLAN_DIGEST
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
        summary.get("schema_version") == "cyberboss.cb430.closure-summary.v1"
        and summary.get("task_id") == "CB-430"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb_420_closure_commit") == CB420_CLOSURE
        and summary.get("cb_420_tree") == CB420_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("matrix_card_sha256") == MATRIX_CARD_SHA256
        and summary.get("matrix_report_digest") == MATRIX_REPORT_DIGEST
        and summary.get("postdeploy_plan_digest") == POSTDEPLOY_PLAN_DIGEST
        and summary.get("matrix_case_count") == 14
        and summary.get("acceptance") == {oracle: "passed" for oracle in ACCEPTANCE}
        and summary.get("local_validation") == LOCAL_VALIDATION
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("external_activation") == EXTERNAL_ACTIVATION
        and summary.get("aggregate") == {
            "lost_messages": 0,
            "duplicate_execution": 0,
            "duplicate_side_effects": 0,
            "unbounded_retries": 0,
            "rollback_restore_valid": True,
            "real_time_waits": 0,
            "network_or_provider_operations": 0,
            "control_plane_llm_calls": 0,
            "operations_llm_calls": 0,
            "macos_launchd_dependency": False,
        }
        and all(summary.get(key) == 0 for key in (
            "real_private_database_operations", "real_r2_operations", "real_cloudflare_operations",
            "real_oci_operations", "real_service_operations", "network_or_provider_operations",
            "control_plane_llm_calls", "operations_llm_calls", "real_time_waits",
        ))
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "CB-440",
    )
    for candidate in EVIDENCE.iterdir():
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", CB420_CLOSURE, implementation_commit, check=False)[0] == 0)
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
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(errors, "gitlink", not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()))
    source = Path(__file__).read_text(encoding="utf-8")
    report(errors, "validator_no_sleep", all(marker not in source for marker in ("time" + ".sleep", "asyncio" + ".sleep")))
    report(errors, "diff_check", git("diff", "--check", CB420_CLOSURE, "HEAD", check=False)[0] == 0)
    validate_state(final, errors)
    validate_cb420_anchor(errors)
    validate_prior_anchors(errors)
    validate_contract(errors)
    validate_code(errors)
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)
    matrix = run_clean_validation(errors)
    implementation_commit = validate_subject_and_evidence(errors) if final else git("rev-parse", "HEAD")[1]
    validate_commit_boundaries(implementation_commit, final, errors)
    return errors, {
        "mode": "final" if final else "prepare",
        "branch": branch,
        "commands": len(matrix["commands"]),
        "errors": len(errors),
        "matrix_digest": MATRIX_REPORT_DIGEST,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate CB-430 implementation before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for issue in errors:
            print(f"ERROR={issue}")
        print("CB430_VALIDATION=FAIL")
        return 1
    print("CB430_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
