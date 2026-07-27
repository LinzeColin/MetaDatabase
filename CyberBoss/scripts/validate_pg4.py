#!/usr/bin/env python3
"""Fail-closed, credential-free Stage 4 safe-release gate validator for PG-4."""

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
EVIDENCE = PROJECT / "docs/evidence/PG-4"

PRODUCT_VERSION = "v0.0.0.5"
TASKPACK_VERSION = "v0.0.0.7"
TASKPACK_ZIP_SHA256 = "77666f5d2fdb60be6f103540d1d8947a1eb20c7084ed6036c97f213534fda48a"
STAGE4_ANCHOR = "5ac84f31e6889dc416cad405011dda572a463d38"
STAGE4_ANCHOR_TREE = "70913b5a040bed7929e01de9d3492b0b7187dce9"
STAGE4_TASKS = ("CB-400", "CB-410", "CB-420", "CB-430", "CB-440")
STAGE4_SPECS = {
    "CB-400": {
        "phase": "P4.1",
        "closure": "55192340a3bc80ac979e283a5308daee9158ad3e",
        "implementation": "3e203ba760cab21b1a8d0bbd5d7f1b76d2fb884c",
        "tree": "3717f5aa708f96ccaf3ae298d0312c18756576a6",
        "schema": "cyberboss.cb400",
        "next": "CB-410",
    },
    "CB-410": {
        "phase": "P4.2",
        "closure": "ea82f02b175e864d754ab5bdfaccd0e84a89e6d4",
        "implementation": "911d14c83a313f5a611d595acd72ee80415d97fa",
        "tree": "2d9ab76492ff13925e98a01c5d7ba751e3206abd",
        "schema": "cyberboss.cb410",
        "next": "CB-420",
    },
    "CB-420": {
        "phase": "P4.3",
        "closure": "9f70eb6629d84e675d8df7183ae072b7e9bff7d7",
        "implementation": "307810329127910b4e0ef64e435099d02c74bd6e",
        "tree": "5d9bc218bc8be077d3d793562aaf74d5f47b0d0b",
        "schema": "cyberboss.cb420",
        "next": "CB-430",
    },
    "CB-430": {
        "phase": "P4.4",
        "closure": "045682e330f20ce4a5271f1a444c17bf1e2bf42c",
        "implementation": "088f04c786870c176681d92b8d01027baa7314b7",
        "tree": "db648d19ee2650d1be59bfde7f4b9ad39166ae18",
        "schema": "cyberboss.cb430",
        "next": "CB-440",
    },
    "CB-440": {
        "phase": "P4.5",
        "closure": STAGE4_ANCHOR,
        "implementation": "78cdc61a484fee5ae05e4ac63cd146557a32a7e9",
        "tree": "8c2a400d5063876955a790b65e892aded696976d",
        "schema": "cyberboss.cb440",
        "next": "PG-4",
    },
}
PG4_ORACLES = (
    "FA-AC-015",
    "FA-AC-016",
    "FA-AC-017",
    "FA-AC-018",
    "FA-AC-019",
    "FA-AC-029",
)
ROUTER_RESULT = {
    "task_id": "PG-4",
    "selected_skill": None,
    "mode": "DETERMINISTIC_TEST_ONLY",
    "max_lightweight_skill_loads": 0,
    "prohibited_skill_loads": 0,
}
CANDIDATE_RELEASE_ID = "bb86be91fedac363301d7704030a67925c166dc826b11f97a0f5cf4222495ad0"
CANDIDATE_MANIFEST_DIGEST = "4f83d414e4d950506c9430665e2b4875d9ad58e68b2e75bd31c5722dca9a66e4"
OPERATOR_RUNBOOK_DIGEST = "d26533392f38e0de26e1deab4c07a9365cdbc97a5f948503554c1db35afc9c9f"

IMPLEMENTATION_PATHS = {
    "CyberBoss/docs/governance/RUN_CONTRACT_PG_4.md",
    "CyberBoss/docs/governance/STAGE4_SAFE_RELEASE_GATE_PG4.md",
    "CyberBoss/scripts/validate_pg4.py",
}
CLOSURE_PATHS = {
    "CyberBoss/CHANGELOG.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/README.md",
    "CyberBoss/docs/evidence/PG-4/subject.json",
    "CyberBoss/docs/evidence/PG-4/summary.json",
    "CyberBoss/machine/facts/task_state.json",
}
FINAL_EVIDENCE = {"summary.json", "subject.json"}
LOCAL_VALIDATION = {
    "stage4_focused_app": "passed",
    "stage4_focused_root": "passed",
    "software_predeploy": "passed",
    "model_safety_fixture": "passed",
    "security_assurance": "passed",
    "corresponding_source": "passed",
    "fault_matrix": "passed",
    "fault_postdeploy_plan": "passed",
    "immutable_candidate": "passed",
    "immutable_operator_plan": "passed",
    "cloud_install_layout": "passed",
    "runtime_spool_migration": "passed",
    "access_policy": "passed",
    "secret_scan": "passed",
    "app_check": "passed",
    "app_regression": "passed",
    "identity_scope": "passed",
    "config": "passed",
    "dag": "passed",
    "traceability": "passed",
    "no_wait": "passed",
    "taskpack": "passed",
    "manifests": "passed",
    "subject_evidence_hashes": "passed",
    "unaccepted_finding_review": "passed",
}
DUAL_PIPELINE = {
    "software_correctness_pipeline": "passed",
    "model_safety_fixture_pipeline": "passed",
    "model_safety_real_trial": "activation_pending",
    "security_privacy_supply_chain_pipeline": "passed",
    "fault_restore_pipeline": "passed",
    "unaccepted_p0_p1_findings": 0,
}
RELEASE_CANDIDATE = {
    "candidate_release_id": CANDIDATE_RELEASE_ID,
    "candidate_manifest_digest": CANDIDATE_MANIFEST_DIGEST,
    "operator_runbook_digest": OPERATOR_RUNBOOK_DIGEST,
    "candidate_local_seal": "passed",
    "request_count_predicates": 8,
    "rollback_contract": "passed",
    "candidate_installation": "activation_pending",
    "current_switch": "activation_pending",
    "live_request_count_canary": "activation_pending",
    "live_rollback": "activation_pending",
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
    "candidate_installation": "activation_pending",
    "current_switch": "activation_pending",
    "live_request_count_canary": "activation_pending",
    "live_rollback": "activation_pending",
}
SENSITIVE_ENV_FRAGMENTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
    "SESSION",
    "PRIVATE_KEY",
    "ACCESS_KEY",
    "API_KEY",
    "OPENAI",
    "CODEX",
    "WECHAT",
    "CLOUDFLARE",
    "GITHUB",
)
SENSITIVE_ENV_PREFIXES = ("AWS_", "OCI_", "CF_", "GH_", "SSH_")
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


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def report(errors: list[str], code: str, condition: bool) -> None:
    if not condition:
        errors.append(code)


def commit_paths(commit: str) -> set[str]:
    parent = git("rev-parse", f"{commit}^")[1]
    return set(filter(None, git("diff", "--name-only", parent, commit)[1].splitlines()))


def tree_at(commit: str, path: str) -> str | None:
    code, output = git("rev-parse", f"{commit}:{path}", check=False)
    return output if code == 0 else None


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
    environment.update(
        {
            "CI": "1",
            "NO_COLOR": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(root / "tmp"),
            "XDG_CONFIG_HOME": str(root / "config"),
            "NPM_CONFIG_USERCONFIG": "/dev/null",
            "NPM_CONFIG_CACHE": str(root / "npm-cache"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
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


def stage4_index(errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task_id in STAGE4_TASKS:
        spec = STAGE4_SPECS[task_id]
        evidence_tree = tree_at(STAGE4_ANCHOR, f"CyberBoss/docs/evidence/{task_id}")
        if evidence_tree is None:
            errors.append(f"anchor_evidence_tree:{task_id}")
            evidence_tree = ""
        rows.append(
            {
                "task_id": task_id,
                "phase": spec["phase"],
                "status": "passed",
                "closure_commit": spec["closure"],
                "implementation_commit": spec["implementation"],
                "repository_tree": spec["tree"],
                "evidence_tree": evidence_tree,
            }
        )
    return rows


def stage4_digest(rows: list[dict[str, Any]]) -> str:
    return canonical_sha256(
        {
            "anchor_commit": STAGE4_ANCHOR,
            "anchor_tree": STAGE4_ANCHOR_TREE,
            "tasks": rows,
        }
    )


def validate_stage4_history(errors: list[str]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    report(errors, "stage4_anchor_commit", git("cat-file", "-e", f"{STAGE4_ANCHOR}^{{commit}}", check=False)[0] == 0)
    report(errors, "stage4_anchor_tree", git("rev-parse", f"{STAGE4_ANCHOR}^{{tree}}", check=False)[1] == STAGE4_ANCHOR_TREE)
    for task_id in STAGE4_TASKS:
        spec = STAGE4_SPECS[task_id]
        evidence_dir = PROJECT / "docs/evidence" / task_id
        summary_path = evidence_dir / "summary.json"
        subject_path = evidence_dir / "subject.json"
        report(errors, f"closure_missing:{task_id}", git("cat-file", "-e", f"{spec['closure']}^{{commit}}", check=False)[0] == 0)
        report(errors, f"closure_in_anchor:{task_id}", git("merge-base", "--is-ancestor", spec["closure"], STAGE4_ANCHOR, check=False)[0] == 0)
        report(errors, f"history_mutated:{task_id}", git("diff", "--quiet", STAGE4_ANCHOR, "--", f"CyberBoss/docs/evidence/{task_id}", check=False)[0] == 0)
        report(errors, f"implementation_missing:{task_id}", git("cat-file", "-e", f"{spec['implementation']}^{{commit}}", check=False)[0] == 0)
        report(errors, f"implementation_tree:{task_id}", git("rev-parse", f"{spec['implementation']}^{{tree}}", check=False)[1] == spec["tree"])
        try:
            summary = load_json(summary_path)
            subject = load_json(subject_path)
        except (OSError, ValueError, TypeError):
            errors.append(f"evidence_read:{task_id}")
            continue
        summaries[task_id] = summary
        acceptance = summary.get("acceptance")
        report(
            errors,
            f"evidence_contract:{task_id}",
            summary.get("schema_version") == f"{spec['schema']}.closure-summary.v1"
            and summary.get("task_id") == task_id
            and summary.get("product_version") == PRODUCT_VERSION
            and summary.get("taskpack_version") == TASKPACK_VERSION
            and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
            and summary.get("implementation_commit") == spec["implementation"]
            and summary.get("implementation_tree") == spec["tree"]
            and summary.get("result") == "passed"
            and summary.get("next_native_node") == spec["next"]
            and isinstance(acceptance, dict)
            and bool(acceptance)
            and all(value == "passed" for value in acceptance.values())
            and subject.get("schema_version") == f"{spec['schema']}.subject.v1"
            and subject.get("task_id") == task_id
            and subject.get("product_version") == PRODUCT_VERSION
            and subject.get("taskpack_version") == TASKPACK_VERSION
            and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
            and subject.get("implementation_commit") == spec["implementation"]
            and subject.get("implementation_tree") == spec["tree"]
            and subject.get("summary_sha256") == sha256(summary_path),
        )
        external = summary.get("external_activation") or {}
        report(
            errors,
            f"truth_state:{task_id}",
            external.get("private_database") == "activation_pending"
            and external.get("r2") == "hazard_blocked"
            and external.get("cloudflare_access") == "activation_pending"
            and external.get("oci") == "activation_pending"
            and summary.get("real_private_database_operations") == 0
            and summary.get("real_r2_operations") == 0
            and summary.get("real_cloudflare_operations") == 0
            and summary.get("real_oci_operations") == 0
            and summary.get("real_service_operations") == 0
            and summary.get("control_plane_llm_calls") == 0
            and summary.get("operations_llm_calls") == 0
            and summary.get("macos_launchd_dependency") is False,
        )
    return summaries


def validate_critical_findings(summaries: dict[str, dict[str, Any]], errors: list[str]) -> None:
    report(errors, "critical_summary_inventory", set(summaries) == set(STAGE4_TASKS))
    if set(summaries) != set(STAGE4_TASKS):
        return
    cb400 = summaries["CB-400"]
    cb410 = summaries["CB-410"]
    cb420 = summaries["CB-420"]
    cb430 = summaries["CB-430"]
    cb440 = summaries["CB-440"]
    report(
        errors,
        "software_pipeline",
        cb400.get("acceptance", {}).get("FA-AC-015") == "passed"
        and cb400.get("acceptance", {}).get("FA-AC-018") == "passed"
        and cb400.get("acceptance", {}).get("FA-AC-029") == "passed",
    )
    scorecard = cb410.get("model_safety_scorecard") or {}
    report(
        errors,
        "model_safety_pipeline",
        cb410.get("acceptance", {}).get("FA-AC-016") == "passed"
        and scorecard.get("evaluation_mode") == "deterministic_fixture_only"
        and scorecard.get("status") == "passed"
        and scorecard.get("secret_exfiltration_count") == 0
        and scorecard.get("unauthorized_irreversible_action_count") == 0
        and scorecard.get("false_success_release_count") == 0
        and scorecard.get("real_model_calls") == 0
        and scorecard.get("control_plane_llm_calls") == 0
        and scorecard.get("operations_llm_calls") == 0
        and scorecard.get("real_codex_trial_state") == "activation_pending"
        and scorecard.get("budget_latency_state") == "activation_pending",
    )
    assurance = cb420.get("security_assurance_report") or {}
    security = assurance.get("security") or {}
    report(
        errors,
        "security_privacy_pipeline",
        cb420.get("acceptance", {}).get("FA-AC-017") == "passed"
        and assurance.get("status") == "passed"
        and security.get("high_confidence_secret_hits") == 0
        and security.get("environment_file_hits") == 0
        and security.get("unaccepted_p0_p1_findings") == 0
        and security.get("control_plane_llm_calls") == 0
        and security.get("operations_llm_calls") == 0
        and assurance.get("access_and_analytics_privacy", {}).get("analytics_state") == "activation_pending"
        and assurance.get("external_activation", {}).get("release_distribution") == "activation_pending",
    )
    aggregate = cb430.get("aggregate") or {}
    report(
        errors,
        "fault_restore_pipeline",
        cb430.get("acceptance", {}).get("FA-AC-018") == "passed"
        and cb430.get("acceptance", {}).get("FA-AC-019") == "passed"
        and aggregate.get("lost_messages") == 0
        and aggregate.get("duplicate_execution") == 0
        and aggregate.get("duplicate_side_effects") == 0
        and aggregate.get("unbounded_retries") == 0
        and aggregate.get("rollback_restore_valid") is True
        and aggregate.get("real_time_waits") == 0,
    )
    rollback = cb440.get("rollback") or {}
    release_external = cb440.get("external_activation") or {}
    report(
        errors,
        "safe_release_seal",
        cb440.get("acceptance", {}).get("FA-AC-019") == "passed"
        and cb440.get("acceptance", {}).get("FA-AC-024") == "passed"
        and cb440.get("acceptance", {}).get("FA-AC-029") == "passed"
        and cb440.get("candidate_release_id") == CANDIDATE_RELEASE_ID
        and cb440.get("candidate_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
        and cb440.get("operator_runbook_digest") == OPERATOR_RUNBOOK_DIGEST
        and cb440.get("canary_request_count") == 8
        and rollback.get("pointer") == "previous"
        and rollback.get("p0_action") == "immediate_pointer_restore_no_wait"
        and rollback.get("current_unchanged") is True
        and rollback.get("valid") is True
        and all(
            release_external.get(key) == "activation_pending"
            for key in ("candidate_installation", "current_switch", "live_request_count_canary", "live_rollback")
        ),
    )


def validate_state(final: bool, evidence_digest: str, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {row.get("id"): row.get("status") for row in state.get("tasks", [])}
    prior = (
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
        "CB-230",
        "CB-240",
        "CB-300",
        "CB-310",
        "CB-320",
        "CB-330",
        "CB-340",
        *STAGE4_TASKS,
    )
    for task_id in prior:
        report(errors, f"task_state_prior:{task_id}", statuses.get(task_id) == "passed")
    for task_id in ("CB-500", "CB-510", "CB-520", "CB-530", "CB-540"):
        report(errors, f"task_state_future:{task_id}", statuses.get(task_id) == "not_started")
    gates = state.get("pass_gates") or {}
    report(errors, "task_state_prior_gates", all(gates.get(gate) == "passed" for gate in ("PG-0", "PG-1", "PG-2", "PG-3")))
    report(errors, "task_state_pg4", gates.get("PG-4") == ("passed" if final else "not_started"))
    report(errors, "task_state_pg5", gates.get("PG-5") == "not_started")
    expected_current = (
        {
            "run_id": "PG-4",
            "gate_id": "PG-4",
            "task_id": None,
            "scope": "stage_4_dual_pipeline_safe_release_gate",
            "status": "passed",
        }
        if final
        else {
            "run_id": "P4.5",
            "gate_id": None,
            "task_id": "CB-440",
            "scope": "immutable_release_candidate_slots_canary_rollback_contract",
            "status": "passed",
        }
    )
    report(errors, "task_state_current_run", state.get("current_run") == expected_current)
    overlay = state.get("taskpack_overlay") or {}
    common = (
        state.get("taskpack_version") == TASKPACK_VERSION
        and overlay.get("product_version") == PRODUCT_VERSION
        and overlay.get("design_baseline_version") == "v0.0.0.4"
        and overlay.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and overlay.get("software_correctness_status") == "passed"
        and overlay.get("model_safety_evaluation_status") == "passed"
        and overlay.get("security_assurance_status") == "passed"
        and overlay.get("fault_recovery_matrix_status") == "passed"
        and overlay.get("immutable_release_candidate_status") == "passed"
        and overlay.get("immutable_release_candidate_id") == CANDIDATE_RELEASE_ID
        and overlay.get("immutable_release_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
        and overlay.get("immutable_release_operator_runbook_digest") == OPERATOR_RUNBOOK_DIGEST
        and overlay.get("r2_backup_activation") == "hazard_blocked"
        and overlay.get("release_candidate_real_activation") == "activation_pending"
        and overlay.get("control_plane_llm_calls") == 0
        and overlay.get("operations_llm_calls") == 0
        and overlay.get("macos_launchd_dependency") is False
    )
    report(errors, "task_state_overlay", common)
    if final:
        report(
            errors,
            "task_state_pg4_overlay",
            overlay.get("skill_router") == ROUTER_RESULT
            and overlay.get("pg_4_executed") is True
            and overlay.get("stage_4_anchor_commit") == STAGE4_ANCHOR
            and overlay.get("stage_4_anchor_tree") == STAGE4_ANCHOR_TREE
            and overlay.get("stage_4_subject_digest") == evidence_digest
            and overlay.get("stage_4_safe_release_gate_status") == "passed"
            and overlay.get("stage_4_unaccepted_p0_p1_findings") == 0
            and overlay.get("formal_final_acceptance") == "activation_pending"
            and overlay.get("acceptance_state") == "passed"
            and overlay.get("acceptance_scope") == "local_deterministic_only",
        )


def validate_contract(errors: list[str]) -> None:
    contract_path = PROJECT / "docs/governance/RUN_CONTRACT_PG_4.md"
    card_path = PROJECT / "docs/governance/STAGE4_SAFE_RELEASE_GATE_PG4.md"
    contract = contract_path.read_text(encoding="utf-8")
    card = card_path.read_text(encoding="utf-8")
    for marker in (
        "PG-4",
        PRODUCT_VERSION,
        TASKPACK_VERSION,
        TASKPACK_ZIP_SHA256,
        STAGE4_ANCHOR,
        *PG4_ORACLES,
        "DETERMINISTIC_TEST_ONLY",
        "不加载任何 Skill",
        "Private-Database",
        "macOS launchd",
        "activation_pending",
        "hazard_blocked",
        "CB-500",
    ):
        if marker.lower() not in contract.lower():
            errors.append(f"contract:{marker}")
    for marker in (
        CANDIDATE_RELEASE_ID,
        CANDIDATE_MANIFEST_DIGEST,
        OPERATOR_RUNBOOK_DIGEST,
        "8",
        "immediate_pointer_restore_no_wait",
        "activation_pending",
        "hazard_blocked",
        "launchd dependency",
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


def validate_no_launchd(errors: list[str]) -> None:
    roots = (PROJECT / "app/src", PROJECT / "app/scripts", KIT / "systemd", KIT / "scripts")
    forbidden = ("launchctl", "launchdaemon", "launchagents", "com.apple.launchd")
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or "node_modules" in path.parts:
                continue
            content = path.read_text(encoding="utf-8", errors="ignore").lower()
            if any(marker in content for marker in forbidden):
                errors.append(f"macos_launchd_dependency:{path.relative_to(REPO)}")


def run_clean_validation(errors: list[str]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-pg4-") as raw_root:
        root = Path(raw_root)
        environment, removed_count = credential_free_environment(root)
        app_tests = [
            "test/software-correctness-suite.test.js",
            "test/canonical-model-safety-evaluation.test.js",
            "test/canonical-security-assurance.test.js",
            "test/canonical-fault-recovery-matrix.test.js",
            "test/canonical-immutable-release.test.js",
        ]
        root_tests = [
            "tests/software-correctness-suite.test.js",
            "tests/canonical-model-safety-evaluation.test.js",
            "tests/security-assurance-suite.test.js",
            "tests/fault-recovery-suite.test.js",
            "tests/immutable-release-suite.test.js",
        ]
        specs: list[tuple[str, list[str], Path, tuple[str, ...], int]] = [
            ("stage4_focused_app", ["node", "--test", *app_tests], PROJECT / "app", ("fail 0",), 900),
            ("stage4_focused_root", ["node", "--test", *root_tests], PROJECT, ("fail 0",), 900),
            ("software_predeploy", ["node", "app/scripts/software-correctness-suite.js", "--mode=predeploy"], PROJECT, ("FROZEN_CORE_SUITE=PASS",), 900),
            ("model_safety_fixture", ["node", "app/scripts/canonical-model-safety-evaluation.js", "evaluate", "--mode=fixture"], PROJECT, ("MODEL_SAFETY_EVALUATION=PASS",), 300),
            ("security_assurance", ["node", "app/scripts/security-assurance-suite.js", "evaluate", "--mode=local"], PROJECT, ("SECURITY_ASSURANCE=PASS",), 900),
            ("corresponding_source", ["node", "app/scripts/security-assurance-suite.js", "evaluate", "--mode=source-package"], PROJECT, ("SECURITY_ASSURANCE=PASS",), 900),
            ("fault_matrix", ["node", "app/scripts/fault-recovery-suite.js", "evaluate", "--mode=matrix"], PROJECT, ("FAULT_RECOVERY_MATRIX=PASS",), 300),
            ("fault_postdeploy_plan", ["node", "app/scripts/fault-recovery-suite.js", "evaluate", "--mode=postdeploy-plan"], PROJECT, ("FAULT_RECOVERY_MATRIX=PASS",), 300),
            ("immutable_candidate", ["node", "app/scripts/immutable-release-suite.js", "evaluate", "--mode=local"], PROJECT, ("IMMUTABLE_RELEASE_CANDIDATE=PASS", CANDIDATE_MANIFEST_DIGEST), 300),
            ("immutable_operator_plan", ["node", "app/scripts/immutable-release-suite.js", "evaluate", "--mode=operator-plan"], PROJECT, ("IMMUTABLE_RELEASE_CANDIDATE=PASS", OPERATOR_RUNBOOK_DIGEST), 300),
            ("cloud_install_layout", ["node", "--test", "tests/cloud-install-layout.test.js"], PROJECT, ("fail 0",), 600),
            ("runtime_spool_migration", ["node", "--test", "test/runtime-spool.test.js"], PROJECT / "app", ("fail 0",), 600),
            ("access_policy", ["node", "--test", "tests/access-policy-contract.test.js"], KIT, ("fail 0",), 300),
            ("secret_scan", [sys.executable, str(KIT / "scripts/secret_scan.py"), "--repo", str(REPO), "--scope", "CyberBoss"], REPO, ('"result": "passed"', '"p0_findings": 0', '"p1_findings": 0'), 600),
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
        return {
            "credential_named_environment_keys_removed": removed_count,
            "network_or_provider_operations": 0,
            "real_time_waits": 0,
            "commands": commands,
        }


def validate_subject_and_evidence(rows: list[dict[str, Any]], evidence_digest: str, errors: list[str]) -> str | None:
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
        and subject.get("schema_version") == "cyberboss.pg4.subject.v1"
        and subject.get("task_id") == "PG-4"
        and subject.get("product_version") == PRODUCT_VERSION
        and subject.get("taskpack_version") == TASKPACK_VERSION
        and subject.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and subject.get("stage_4_anchor_commit") == STAGE4_ANCHOR
        and subject.get("stage_4_anchor_tree") == STAGE4_ANCHOR_TREE
        and subject.get("stage_4_evidence_digest") == evidence_digest
        and git("rev-parse", f"{implementation_commit}^{{tree}}", check=False)[1] == implementation_tree
        and git("merge-base", "--is-ancestor", STAGE4_ANCHOR, implementation_commit, check=False)[0] == 0
        and subject.get("summary_sha256") == sha256(summary_path)
        and subject.get("artifact_manifest_sha256") == sha256(PACK / "MANIFEST.sha256")
        and subject.get("implementation_kit_manifest_sha256") == sha256(KIT / "MANIFEST.sha256")
        and subject.get("candidate_release_id") == CANDIDATE_RELEASE_ID
        and subject.get("candidate_manifest_digest") == CANDIDATE_MANIFEST_DIGEST
        and subject.get("operator_runbook_digest") == OPERATOR_RUNBOOK_DIGEST
        and subject.get("formal_final_acceptance") == "activation_pending"
        and subject.get("unaccepted_p0_p1_findings") == 0
        and subject.get("real_private_database_operations") == 0
        and subject.get("real_r2_operations") == 0
        and subject.get("real_cloudflare_operations") == 0
        and subject.get("real_oci_operations") == 0
        and subject.get("real_service_operations") == 0
        and subject.get("network_or_provider_operations") == 0
        and subject.get("control_plane_llm_calls") == 0
        and subject.get("operations_llm_calls") == 0
        and subject.get("real_time_waits") == 0
        and subject.get("macos_launchd_dependency") is False,
    )
    report(
        errors,
        "summary_contract",
        summary.get("schema_version") == "cyberboss.pg4.closure-summary.v1"
        and summary.get("task_id") == "PG-4"
        and summary.get("product_version") == PRODUCT_VERSION
        and summary.get("taskpack_version") == TASKPACK_VERSION
        and summary.get("taskpack_zip_sha256") == TASKPACK_ZIP_SHA256
        and summary.get("stage_4_anchor_commit") == STAGE4_ANCHOR
        and summary.get("stage_4_anchor_tree") == STAGE4_ANCHOR_TREE
        and summary.get("implementation_commit") == implementation_commit
        and summary.get("implementation_tree") == implementation_tree
        and summary.get("stage_4_evidence") == rows
        and summary.get("stage_4_evidence_digest") == evidence_digest
        and summary.get("acceptance") == {oracle: "passed" for oracle in PG4_ORACLES}
        and summary.get("local_validation") == LOCAL_VALIDATION
        and summary.get("skill_router") == ROUTER_RESULT
        and summary.get("dual_pipeline") == DUAL_PIPELINE
        and summary.get("release_candidate") == RELEASE_CANDIDATE
        and summary.get("external_activation") == EXTERNAL_ACTIVATION
        and summary.get("unaccepted_p0_p1_findings") == 0
        and summary.get("real_private_database_operations") == 0
        and summary.get("real_r2_operations") == 0
        and summary.get("real_cloudflare_operations") == 0
        and summary.get("real_oci_operations") == 0
        and summary.get("real_service_operations") == 0
        and summary.get("network_or_provider_operations") == 0
        and summary.get("control_plane_llm_calls") == 0
        and summary.get("operations_llm_calls") == 0
        and summary.get("real_time_waits") == 0
        and summary.get("macos_launchd_dependency") is False
        and summary.get("result") == "passed"
        and summary.get("evidence_scope") == "local_deterministic_only"
        and summary.get("formal_final_acceptance") == "activation_pending"
        and summary.get("next_native_node") == "CB-500",
    )
    for candidate in EVIDENCE.iterdir():
        content = candidate.read_text(encoding="utf-8", errors="replace")
        if SECRET_PATTERN.search(content) or "/Users/" in content or "/var/lib/" in content:
            errors.append(f"evidence_sensitive_or_absolute:{candidate.name}")
    return implementation_commit


def validate_commit_boundaries(implementation_commit: str | None, final: bool, errors: list[str]) -> None:
    if implementation_commit is None:
        return
    report(errors, "implementation_anchor", git("merge-base", "--is-ancestor", STAGE4_ANCHOR, implementation_commit, check=False)[0] == 0)
    report(errors, "implementation_inventory", commit_paths(implementation_commit) == IMPLEMENTATION_PATHS)
    if final:
        report(errors, "implementation_in_history", git("merge-base", "--is-ancestor", implementation_commit, "HEAD", check=False)[0] == 0)
        closure_paths = set(filter(None, git("diff", "--name-only", implementation_commit, "HEAD")[1].splitlines()))
        report(errors, "closure_atomic_inventory", closure_paths == CLOSURE_PATHS)


def validate(final: bool) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    rows = stage4_index(errors)
    evidence_digest = stage4_digest(rows)
    branch = git("branch", "--show-current")[1]
    report(errors, "branch_scope", branch == "codex/cyberboss-v5-cb240-closure")
    report(errors, "worktree_dirty", not git("status", "--porcelain=v1", "--untracked-files=all")[1])
    report(errors, "nested_git_repository", not list(PROJECT.rglob(".git")))
    report(errors, "gitlink", not any(line.startswith("160000 ") for line in git("ls-files", "-s", "CyberBoss")[1].splitlines()))
    source = Path(__file__).read_text(encoding="utf-8")
    report(errors, "validator_no_sleep", all(marker not in source for marker in ("time" + ".sleep", "asyncio" + ".sleep")))
    report(errors, "diff_check", git("diff", "--check", STAGE4_ANCHOR, "HEAD", check=False)[0] == 0)
    validate_state(final, evidence_digest, errors)
    summaries = validate_stage4_history(errors)
    validate_critical_findings(summaries, errors)
    validate_contract(errors)
    validate_no_launchd(errors)
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)
    matrix = run_clean_validation(errors)
    implementation_commit = (
        validate_subject_and_evidence(rows, evidence_digest, errors)
        if final
        else git("rev-parse", "HEAD")[1]
    )
    validate_commit_boundaries(implementation_commit, final, errors)
    return errors, {
        "mode": "final" if final else "prepare",
        "branch": branch,
        "commands": len(matrix["commands"]),
        "errors": len(errors),
        "stage_4_evidence_digest": evidence_digest,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true", help="Validate PG-4 implementation before closure evidence.")
    args = parser.parse_args()
    errors, reports = validate(final=not args.prepare)
    for key, value in reports.items():
        print(f"{key}={value}")
    if errors:
        for error in errors:
            print(f"ERROR={error}")
        print("PG4_VALIDATION=FAIL")
        return 1
    print("PG4_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
