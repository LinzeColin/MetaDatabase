#!/usr/bin/env python3
"""Fail-closed, credential-free validator for CyberBoss P4.5 / CB-440."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-440"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
CB430_CLOSURE = "045682e330f20ce4a5271f1a444c17bf1e2bf42c"
CB430_TREE = "e789acb494926742aa61c61dbac721807aae9f6c"
CANDIDATE_RELEASE_ID = "bb86be91fedac363301d7704030a67925c166dc826b11f97a0f5cf4222495ad0"
CANDIDATE_MANIFEST_DIGEST = "4f83d414e4d950506c9430665e2b4875d9ad58e68b2e75bd31c5722dca9a66e4"
OPERATOR_RUNBOOK_DIGEST = "d26533392f38e0de26e1deab4c07a9365cdbc97a5f948503554c1db35afc9c9f"
CANDIDATE_CARD_SHA256 = "cf4c5a68c3e747e5f1d2066105adb53fcc7ae21093593f777c2128d199d15667"
ACCEPTANCE = ("FA-AC-019", "FA-AC-024", "FA-AC-029")
ROUTER_RESULT = {
    "task_id": "CB-440",
    "selected_skill": "output-skill",
    "mode": "NATIVE_IF_PRESENT_ELSE_EMBEDDED",
    "max_lightweight_skill_loads": 1,
    "prohibited_skill_loads": 0,
    "actual_skill_body_loads": 1,
    "fallback": "machine/skill_microplaybooks.json",
}
IMPLEMENTATION_PATHS = {
    "CyberBoss/app/scripts/immutable-release-suite.js",
    "CyberBoss/app/src/services/release/canonical-immutable-release.js",
    "CyberBoss/app/test/canonical-immutable-release.test.js",
    "CyberBoss/docs/governance/IMMUTABLE_RELEASE_CANDIDATE_CB_440.md",
    "CyberBoss/docs/governance/RUN_CONTRACT_P4_5_CB_440.md",
    "CyberBoss/scripts/validate_cb440.py",
    "CyberBoss/tests/immutable-release-suite.test.js",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/CB-440/subject.json",
    "CyberBoss/docs/evidence/CB-440/summary.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
LOCAL_VALIDATION = {
    "candidate_unit": "passed",
    "candidate_cli": "passed",
    "operator_plan_cli": "passed",
    "candidate_root_cli": "passed",
    "cloud_layout": "passed",
    "runtime_spool_migration": "passed",
    "software_correctness_unit": "passed",
    "software_correctness_predeploy": "passed",
    "security_assurance": "passed",
    "secret_scan": "passed",
    "cb430_anchor": "passed",
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
    "candidate_installation": "activation_pending",
    "current_switch": "activation_pending",
    "live_request_count_canary": "activation_pending",
    "live_rollback": "activation_pending",
    "private_database": "activation_pending",
    "r2": "hazard_blocked",
    "cloudflare_access": "activation_pending",
    "oci": "activation_pending",
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
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior = (
        "CB-000", "CB-010", "CB-020", "CB-030", "CB-040", "CB-100", "CB-110",
        "CB-120", "CB-130", "CB-140", "CB-200", "CB-210", "CB-220", "CB-230",
        "CB-240", "CB-300", "CB-310", "CB-320", "CB-330", "CB-340", "CB-400",
        "CB-410", "CB-420", "CB-430",
    )
    for task_id in prior:
        report(errors, f"task_state_prior:{task_id}", statuses.get(task_id) == "passed")
    report(errors, "task_state_cb440", statuses.get("CB-440") == ("passed" if final else "not_started"))
    for task_id in ("CB-500", "CB-510", "CB-520", "CB-530", "CB-540"):
        report(errors, f"task_state_future:{task_id}", statuses.get(task_id) == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", all(gates.get(gate) == "passed" for gate in ("PG-0", "PG-1", "PG-2", "PG-3")))
    report(errors, "task_state_later_gates", all(gates.get(gate) == "not_started" for gate in ("PG-4", "PG-5")))
    expected_current = (
        {
            "run_id": "P4.5", "gate_id": None, "task_id": "CB-440",
            "scope": "immutable_release_candidate_slots_canary_rollback_contract", "status": "passed",
        }
        if final
        else {
            "run_id": "P4.4", "gate_id": None, "task_id": "CB-430",
            "scope": "deterministic_fault_crash_cut_recovery_restore_matrix", "status": "passed",
        }
    )
    report(errors, "task_state_current_run", state.get("current_run") == expected_current)
    overlay = state.get("taskpack_overlay") or {}
    common = (
        state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("fault_recovery_matrix_status") == "passed"
        and overlay.get("security_assurance_status") == "passed"
        and overlay.get("software_correctness_status") == "passed"
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
        and overlay.get("r2_backup_activation") == "hazard_blocked"
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_cb440_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("immutable_release_candidate_status") == "passed"
            and overlay.get("immutable_release_candidate_id") == CANDIDATE_RELEASE_ID
            and overlay.get("immutable_release_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
            and overlay.get("immutable_release_operator_runbook_status") == "passed"
            and overlay.get("release_candidate_real_activation") == "activation_pending"
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_cb430_anchor(errors: list[str]) -> None:
    report(errors, "cb430_closure_commit", git("cat-file", "-e", f"{CB430_CLOSURE}^{{commit}}", check=False)[0] == 0)
    report(errors, "cb430_history", git("merge-base", "--is-ancestor", CB430_CLOSURE, "HEAD", check=False)[0] == 0)
    report(errors, "cb430_evidence_mutated", git("diff", "--quiet", CB430_CLOSURE, "--", "CyberBoss/docs/evidence/CB-430", check=False)[0] == 0)
    report(errors, "cb430_tree", git("rev-parse", f"{CB430_CLOSURE}^{{tree}}", check=False)[1] == CB430_TREE)
    try:
        summary = load_json(PROJECT / "docs/evidence/CB-430/summary.json")
        subject = load_json(PROJECT / "docs/evidence/CB-430/subject.json")
    except (OSError, ValueError, TypeError):
        errors.append("cb430_evidence_read")
        return
    report(
        errors,
        "cb430_subject",
        summary.get("result") == "passed"
        and summary.get("next_native_node") == "CB-440"
        and subject.get("summary_sha256") == sha256(PROJECT / "docs/evidence/CB-430/summary.json"),
    )


def validate_prior_anchors(errors: list[str]) -> None:
    for label, commit, evidence in (
        ("cb420", "9f70eb6629d84e675d8df7183ae072b7e9bff7d7", "CyberBoss/docs/evidence/CB-420"),
        ("cb410", "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4", "CyberBoss/docs/evidence/CB-410"),
        ("cb400", "55192340a3bc80ac979e283a5308daee9158ad3e", "CyberBoss/docs/evidence/CB-400"),
    ):
        report(errors, f"{label}_history", git("merge-base", "--is-ancestor", commit, "HEAD", check=False)[0] == 0)
        report(errors, f"{label}_evidence_mutated", git("diff", "--quiet", commit, "--", evidence, check=False)[0] == 0)


def validate_contract(errors: list[str]) -> None:
    contract = (PROJECT / "docs/governance/RUN_CONTRACT_P4_5_CB_440.md").read_text(encoding="utf-8")
    card = (PROJECT / "docs/governance/IMMUTABLE_RELEASE_CANDIDATE_CB_440.md").read_text(encoding="utf-8")
    body_load = "实际 Skill body load 为 " + chr(96) + "1" + chr(96)
    for marker in (
        "P4.5 / CB-440", PRODUCT_VERSION, TASKPACK_VERSION, TASKPACK_ZIP_SHA256,
        "FA-AC-019", "FA-AC-024", "FA-AC-029", "output-skill",
        "NATIVE_IF_PRESENT_ELSE_EMBEDDED", body_load, "candidate/current/previous",
        "activation_pending", "Private-Database", "PG-4",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")
    for marker in (
        "provenance", "immutable", "7", "migration", "8", "rollback",
        "activation_pending", "launchd dependency", "hazard_blocked",
    ):
        if marker.lower() not in card.lower():
            errors.append(f"candidate_card:{marker}")
    if SECRET_PATTERN.search(contract) or SECRET_PATTERN.search(card) or "/Users/" in contract or "/Users/" in card:
        errors.append("contract_or_card_sensitive_or_absolute")


def validate_code(errors: list[str]) -> None:
    evaluator = (PROJECT / "app/src/services/release/canonical-immutable-release.js").read_text(encoding="utf-8")
    cli = (PROJECT / "app/scripts/immutable-release-suite.js").read_text(encoding="utf-8")
    app_test = (PROJECT / "app/test/canonical-immutable-release.test.js").read_text(encoding="utf-8")
    root_test = (PROJECT / "tests/immutable-release-suite.test.js").read_text(encoding="utf-8")
    for marker in (
        "IMMUTABLE_RELEASE_SCHEMA", "OPERATOR_RUNBOOK_SCHEMA", "buildImmutableReleaseCandidate",
        "buildOperatorRunbook", "evaluateRequestCountCanary", "FROZEN_FEATURE_FLAGS",
        "FROZEN_CANARY_RECEIPTS", "candidate_local_only_not_installed",
        "immediate_pointer_restore_no_wait", "RELEASE_FEATURE_FLAGS_OUT_OF_SCOPE",
        "RELEASE_CANARY_SIDE_EFFECT_FORBIDDEN", "activation_pending",
    ):
        if marker not in evaluator:
            errors.append(f"evaluator_marker:{marker}")
    for marker in ("--mode=", "IMMUTABLE_RELEASE_EXTERNAL_EXECUTION_DISABLED", "IMMUTABLE_RELEASE_CANDIDATE=PASS"):
        if marker not in cli:
            errors.append(f"cli_marker:{marker}")
    for marker in ("P0 request-count failure", "feature scope", "no-live-execution"):
        if marker.lower() not in app_test.lower():
            errors.append(f"app_test_marker:{marker}")
    for marker in ("without activation", "rejects live activation", "EXTERNAL_EXECUTION_DISABLED"):
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
    with tempfile.TemporaryDirectory(prefix="cyberboss-cb440-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("candidate_unit", ["node", "--test", "test/canonical-immutable-release.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("candidate_cli", ["node", "app/scripts/immutable-release-suite.js", "evaluate", "--mode=local"], PROJECT, ("IMMUTABLE_RELEASE_CANDIDATE=PASS", CANDIDATE_MANIFEST_DIGEST, CANDIDATE_RELEASE_ID), 300),
            ("operator_plan_cli", ["node", "app/scripts/immutable-release-suite.js", "evaluate", "--mode=operator-plan"], PROJECT, ("IMMUTABLE_RELEASE_CANDIDATE=PASS", OPERATOR_RUNBOOK_DIGEST), 300),
            ("candidate_root_cli", ["node", "--test", "tests/immutable-release-suite.test.js"], PROJECT, ("fail 0",), 300),
            ("cloud_layout", ["node", "--test", "tests/cloud-install-layout.test.js"], PROJECT, ("fail 0",), 600),
            ("runtime_spool_migration", ["node", "--test", "test/runtime-spool.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("software_correctness_unit", ["node", "--test", "test/software-correctness-suite.test.js"], PROJECT / "app", ("fail 0",), 300),
            ("software_correctness_predeploy", ["node", "app/scripts/software-correctness-suite.js", "--mode=predeploy"], PROJECT, ("FROZEN_CORE_SUITE=PASS",), 900),
            ("security_assurance", ["node", "--test", "test/canonical-security-assurance.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("secret_scan", [sys.executable, str(KIT / "scripts/secret_scan.py"), "--repo", str(REPO), "--scope", "CyberBoss"], REPO, ('"result": "passed"', '"p0_findings": 0', '"p1_findings": 0'), 600),
            ("cb430_anchor", ["git", "diff", "--quiet", CB430_CLOSURE, "--", "CyberBoss/docs/evidence/CB-430"], REPO, (), 300),
            ("cb420_anchor", ["git", "diff", "--quiet", "9f70eb6629d84e675d8df7183ae072b7e9bff7d7", "--", "CyberBoss/docs/evidence/CB-420"], REPO, (), 300),
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
        return {"credential_named_environment_keys_removed": removed_count, "commands": commands}


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
        and subject.get("schema_version") == "cyberboss.cb440.subject.v1"
        and subject.get("task_id") == "CB-440"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("cb_430_closure_commit") == CB430_CLOSURE
        and subject.get("cb_430_tree") == CB430_TREE
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", CB430_CLOSURE, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("candidate_card_sha256") == CANDIDATE_CARD_SHA256
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
        summary.get("schema_version") == "cyberboss.cb440.closure-summary.v1"
        and summary.get("task_id") == "CB-440"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("cb_430_closure_commit") == CB430_CLOSURE
        and summary.get("cb_430_tree") == CB430_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("candidate_card_sha256") == CANDIDATE_CARD_SHA256
        and summary.get("candidate_release_id") == CANDIDATE_RELEASE_ID
        and summary.get("candidate_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
        and summary.get("operator_runbook_digest") == OPERATOR_RUNBOOK_DIGEST
        and summary.get("canary_request_count") == 8
        and summary.get("acceptance") == {oracle: "passed" for oracle in ACCEPTANCE}
        and summary.get("local_validation") == LOCAL_VALIDATION
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("external_activation") == EXTERNAL_ACTIVATION
        and summary.get("rollback") == {
            "pointer": "previous",
            "target_release_id": "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4",
            "p0_action": "immediate_pointer_restore_no_wait",
            "current_unchanged": True,
            "valid": True,
        }
        and all(summary.get(key) == 0 for key in (
            "real_private_database_operations", "real_r2_operations", "real_cloudflare_operations",
            "real_oci_operations", "real_service_operations", "network_or_provider_operations",
            "control_plane_llm_calls", "operations_llm_calls", "real_time_waits",
        ))
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("next_native_node") == "PG-4",
    )
    for candidate in EVIDENCE.iterdir():
        text = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(text) or "/Users/" in text or "/var/lib/" in text:
            errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", CB430_CLOSURE, implementation_commit, check=False)[0] == 0)
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
    report(errors, "diff_check", git("diff", "--check", CB430_CLOSURE, "HEAD", check=False)[0] == 0)
    validate_state(final, errors)
    validate_cb430_anchor(errors)
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
        "candidate_manifest_digest": CANDIDATE_MANIFEST_DIGEST,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate CB-440 implementation before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for issue in errors:
            print(f"ERROR={issue}")
        print("CB440_VALIDATION=FAIL")
        return 1
    print("CB440_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
