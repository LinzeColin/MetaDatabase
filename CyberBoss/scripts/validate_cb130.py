#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P1.4 / CB-130."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-130"
BASE_COMMIT = "9e1c128aa3890f7c0ea0e69000fdb46e32a4bb00"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
EXPECTED_CURRENT = "b2a603e415a2045b441f31e07cf74ac451ba6240"
EXPECTED_WORKSPACE = "10d988e908d72ea1a43bbed04a2130a338663363"
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"

APP_PATHS = {
    "CyberBoss/app/package.json",
    "CyberBoss/app/scripts/cloud-supervisor.js",
    "CyberBoss/app/test/cloud-supervisor.test.js",
}

IMPLEMENTATION_PATHS = APP_PATHS | {
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_4_CB_130.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cloud-process-health.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cloud-process-tree.txt",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/accept-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-cloud-process-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/health-check.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-cloud-process-family.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/run-cyberboss.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/simulators/weixin-ilink-simulator.mjs",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/simulator-contract.test.mjs",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb130.py",
    "CyberBoss/tests/cloud-process-family.test.js",
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
    "cloud-process-acceptance.redacted.json",
    "external-port-scan.redacted.json",
    "implementation-commit.json",
    "install-apply.redacted.json",
    "journal-excerpt.redacted.txt",
    "process-tree.redacted.txt",
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
    "CyberBoss/docs/evidence/PG-0",
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
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/systemd/cyberboss-cloud.service",
    "CyberBoss/machine/source-lock.json",
    "CyberBoss/LICENSE",
    "CyberBoss/THIRD_PARTY_NOTICES.md",
    "CyberBoss/UPSTREAM_PROVENANCE.md",
]


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
            f"{result.stderr.strip()}"
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
        if (
            relative in entries
            or relative.startswith("/")
            or ".." in Path(relative).parts
        ):
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
) -> None:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        tail = result.stdout.strip().splitlines()[-1:] or ["no_output"]
        errors.append(f"command:{name}:{result.returncode}:{tail[0][:180]}")


def validate_state(final: bool, errors: list[str]) -> None:
    state = load_json(PROJECT / "machine/facts/task_state.json")
    statuses = {item["id"]: item["status"] for item in state["tasks"]}
    expected_passed = {
        "CB-000",
        "CB-010",
        "CB-020",
        "CB-030",
        "CB-040",
        "CB-100",
        "CB-110",
        "CB-120",
    }
    if final:
        expected_passed.add("CB-130")
    for task_id, status in statuses.items():
        expected = "passed" if task_id in expected_passed else "not_started"
        if status != expected:
            errors.append(f"task_state:{task_id}:{status}:{expected}")
    gates = state.get("pass_gates") or {}
    if gates.get("PG-0") != "passed":
        errors.append("gate_pg0")
    for gate in ("PG-1", "PG-2", "PG-3", "PG-4", "PG-5"):
        if gates.get(gate) != "not_started":
            errors.append(f"gate_not_started:{gate}")
    current = state.get("current_run") or {}
    if final:
        if (
            current.get("run_id") != "P1.4"
            or current.get("task_id") != "CB-130"
            or current.get("scope") != "supervised_loopback_cloud_process_family"
            or current.get("status") != "passed"
        ):
            errors.append("state_current_run")
    elif (
        current.get("run_id") != "P1.3"
        or current.get("task_id") != "CB-120"
        or current.get("status") != "passed"
    ):
        errors.append("state_prepare_baseline")


def validate_final_evidence(errors: list[str]) -> None:
    if not EVIDENCE.is_dir():
        errors.append("evidence_directory")
        return
    actual = {
        candidate.name for candidate in EVIDENCE.iterdir() if candidate.is_file()
    }
    if actual != FINAL_EVIDENCE:
        errors.append("evidence_inventory")
        return

    implementation = load_json(EVIDENCE / "implementation-commit.json")
    implementation_commit = implementation.get("implementation_commit", "")
    if not re.fullmatch(r"[0-9a-f]{40}", implementation_commit):
        errors.append("implementation_commit_format")
        return
    if (
        implementation.get("task_id") != "CB-130"
        or implementation.get("phase") != "P1.4"
        or implementation.get("base_commit") != BASE_COMMIT
        or implementation.get("parent_commit") != BASE_COMMIT
        or implementation.get("branch") != EXPECTED_BRANCH
        or implementation.get("remote_publication") != "none"
    ):
        errors.append("implementation_commit_contract")
    if git("cat-file", "-e", f"{implementation_commit}^{{commit}}", check=False)[0]:
        errors.append("implementation_commit_missing")
        return
    if git("rev-parse", f"{implementation_commit}^")[1] != BASE_COMMIT:
        errors.append("implementation_parent")
    implementation_diff = set(
        filter(
            None,
            git("diff", "--name-only", BASE_COMMIT, implementation_commit)[
                1
            ].splitlines(),
        )
    )
    if implementation_diff != IMPLEMENTATION_PATHS:
        errors.append("implementation_commit_paths")
    if git("rev-parse", "HEAD^")[1] != implementation_commit:
        errors.append("closure_parent")
    if implementation.get("repository_tree") != git(
        "rev-parse", f"{implementation_commit}^{{tree}}"
    )[1]:
        errors.append("implementation_repository_tree")
    if implementation.get("cyberboss_tree") != git(
        "rev-parse", f"{implementation_commit}:CyberBoss"
    )[1]:
        errors.append("implementation_cyberboss_tree")

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    if (
        artifact.get("task_id") != "CB-130"
        or artifact.get("phase") != "P1.4"
        or artifact.get("release_commit") != implementation_commit
        or artifact.get("branch") != EXPECTED_BRANCH
        or artifact.get("source", {}).get("license_expression") != STRICT_LICENSE
        or artifact.get("source", {}).get("corresponding_source_complete")
        is not True
        or artifact.get("source", {}).get("original_licenses_preserved")
        is not True
        or artifact.get("source", {}).get("upstream_clarification_received")
        is not False
        or artifact.get("process_family", {}).get("kill_mode")
        != "control-group"
        or artifact.get("process_family", {}).get("detached_children") is not False
        or artifact.get("process_family", {}).get("runtime_endpoint")
        != "ws://127.0.0.1:8765"
        or artifact.get("deployment", {}).get("switch_current") is not False
        or artifact.get("deployment", {}).get("enable_service") is not False
        or artifact.get("deployment", {}).get("activate_real_credentials")
        is not False
        or artifact.get("deployment", {}).get("clone_private_database") is not False
        or artifact.get("deployment", {}).get("remote_publication") != "none"
    ):
        errors.append("artifact_manifest")

    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    if (
        preflight.get("task_id") != "CB-130"
        or preflight.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or preflight.get("strict_known_host") is not True
        or preflight.get("key_only_batch_mode") is not True
        or preflight.get("sudo_noninteractive") is not True
        or preflight.get("service_active") is not False
        or preflight.get("service_enabled") is not False
        or preflight.get("current_release_commit") != EXPECTED_CURRENT
        or preflight.get("workspace_head") != EXPECTED_WORKSPACE
        or preflight.get("workspace_clean") is not True
        or preflight.get("processes_before_apply") != 0
        or preflight.get("listeners_before_apply") != 0
        or preflight.get("staging_conflicts") != 0
        or preflight.get("credential_content_reads") != 0
        or preflight.get("result") != "passed"
    ):
        errors.append("target_preflight")

    install = load_json(EVIDENCE / "install-apply.redacted.json")
    if (
        install.get("task_id") != "CB-130"
        or install.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or install.get("implementation_commit") != implementation_commit
        or install.get("check_passed") is not True
        or install.get("check_persistent_writes") is not False
        or install.get("check_live_commands") is not False
        or install.get("apply_passes") != 2
        or install.get("verify_passed") is not True
        or install.get("second_apply_idempotent") is not True
        or install.get("candidate_release_immutable") is not True
        or install.get("candidate_tests_passed") is not True
        or not isinstance(install.get("candidate_test_count"), int)
        or install.get("candidate_test_count", 0) < 170
        or install.get("corresponding_source_complete") is not True
        or install.get("license_expression") != STRICT_LICENSE
        or install.get("current_changed") is not False
        or install.get("workspace_changed") is not False
        or install.get("service_started_during_install") is not False
        or install.get("service_enabled") is not False
        or install.get("real_adapter_activation") != "activation_pending"
        or install.get("real_credential_operations") != 0
        or install.get("private_database_cloned") is not False
    ):
        errors.append("install_acceptance")

    external = load_json(EVIDENCE / "external-port-scan.redacted.json")
    if (
        external.get("task_id") != "CB-130"
        or external.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or external.get("operator_host_scan") is not True
        or external.get("service_ready_before_scan") is not True
        or external.get("port_8765_publicly_reachable") is not False
        or external.get("port_8780_publicly_reachable") is not False
        or external.get("target_address_persisted") is not False
        or external.get("result") != "passed"
    ):
        errors.append("external_port_scan")

    acceptance = load_json(
        EVIDENCE / "cloud-process-acceptance.redacted.json"
    )
    process = acceptance.get("process_family") or {}
    singleton = acceptance.get("singleton") or {}
    restart = acceptance.get("restart") or {}
    faults = acceptance.get("fault_matrix") or {}
    final_state = acceptance.get("final") or {}
    if (
        acceptance.get("task_id") != "CB-130"
        or acceptance.get("implementation_commit") != implementation_commit
        or set((acceptance.get("acceptance") or {}).values()) != {"passed"}
        or set((acceptance.get("acceptance") or {}).keys())
        != {"AC-011", "AC-040", "AC-044", "AC-062"}
        or acceptance.get("health_fixture", {}).get("health_status") != 200
        or acceptance.get("health_fixture", {}).get("ready_status") != 200
        or acceptance.get("health_fixture", {}).get("unready_health_status")
        != 200
        or acceptance.get("health_fixture", {}).get("unready_ready_status")
        != 503
        or acceptance.get("health_fixture", {}).get(
            "snapshot_unauthorized_status"
        )
        != 401
        or acceptance.get("health_fixture", {}).get("snapshot_forbidden_hits")
        != 0
        or acceptance.get("network", {}).get("runtime_listener")
        != "127.0.0.1:8765"
        or acceptance.get("network", {}).get("status_listener")
        != "127.0.0.1:8780"
        or acceptance.get("network", {}).get("external_8765_unreachable")
        is not True
        or acceptance.get("network", {}).get("external_8780_unreachable")
        is not True
        or acceptance.get("network", {}).get("public_listeners") != 0
        or process.get("one_systemd_cgroup") is not True
        or process.get("kill_mode") != "control-group"
        or process.get("detached_children") is not False
        or any(
            process.get(key) != 1
            for key in (
                "supervisor_count",
                "runtime_count",
                "channel_count",
                "bridge_count",
            )
        )
        or singleton.get("concurrent_start_attempts") != 100
        or singleton.get("concurrent_start_passes") != 100
        or singleton.get("lock_contenders") != 100
        or singleton.get("lock_denials") != 100
        or singleton.get("active_owner") != 1
        or restart.get("kill_restart_attempts") != 100
        or restart.get("kill_restart_passes") != 100
        or restart.get("ready_predicate") is not True
        or restart.get("fixed_wait") is not False
        or restart.get("llm_calls") != 0
        or any(
            faults.get(role) != {"down_observed": True, "recovered": True}
            for role in ("runtime", "channel", "bridge", "service")
        )
        or faults.get("false_green_observed") is not False
        or acceptance.get("adapters", {}).get("real_codex")
        != "activation_pending"
        or acceptance.get("adapters", {}).get("real_wechat")
        != "activation_pending"
        or acceptance.get("adapters", {}).get("real_credential_operations") != 0
        or final_state.get("service_enabled") is not False
        or final_state.get("service_active") is not False
        or final_state.get("current_changed") is not False
        or final_state.get("workspace_changed") is not False
        or final_state.get("processes") != 0
        or final_state.get("listeners_8765_8780_19080") != 0
        or final_state.get("transient_dropins") != 0
        or final_state.get("ephemeral_tokens") != 0
        or acceptance.get("target_address_persisted") is not False
        or acceptance.get("result") != "passed"
    ):
        errors.append("cloud_process_acceptance")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("task_id") != "CB-130"
        or publication.get("remote_branch_exists") is not False
        or publication.get("pull_request_exists") is not False
        or publication.get("tag_or_release_exists") is not False
        or publication.get("remote_publication") != "none"
    ):
        errors.append("publication")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("task_id") != "CB-130"
        or security.get("p0_findings") != 0
        or security.get("p1_findings") != 0
        or security.get("secret_value_hits") != 0
        or security.get("snapshot_forbidden_hits") != 0
        or security.get("non_loopback_listeners") != 0
        or security.get("detached_orphans") != 0
        or security.get("duplicate_owners") != 0
        or security.get("real_credential_operations") != 0
        or security.get("private_database_operations") != 0
        or security.get("license_expression") != STRICT_LICENSE
        or security.get("upstream_clarification_received") is not False
    ):
        errors.append("security")

    source = load_json(EVIDENCE / "source-modification-record.json")
    if (
        source.get("task_id") != "CB-130"
        or source.get("base_commit") != BASE_COMMIT
        or source.get("implementation_commit") != implementation_commit
        or set(source.get("changed_app_paths") or []) != APP_PATHS
        or source.get("strict_compliance_expression") != STRICT_LICENSE
        or source.get("original_source_and_licenses_preserved") is not True
        or source.get("conflict_record_preserved") is not True
        or source.get("upstream_clarification_received") is not False
        or source.get("upstream_sync_enabled") is not False
        or source.get("vendor_original_paths_changed") != []
        or source.get("remote_publication") != "none"
    ):
        errors.append("source_modification_record")

    rollback = load_json(EVIDENCE / "rollback-plan.json")
    if (
        rollback.get("task_id") != "CB-130"
        or rollback.get("kill_scope") != "systemd_control_group"
        or rollback.get("current_pointer_must_not_move") is not True
        or rollback.get("workspace_must_not_move") is not True
        or rollback.get("transient_dropin_removed") is not True
        or rollback.get("ephemeral_token_removed") is not True
        or rollback.get("credential_delete_allowed") is not False
        or rollback.get("private_database_delete_allowed") is not False
    ):
        errors.append("rollback")

    journal = (EVIDENCE / "journal-excerpt.redacted.txt").read_text(
        encoding="utf-8"
    )
    for marker in (
        "event=component_ready role=runtime",
        "event=component_ready role=channel",
        "event=component_ready role=bridge",
        "event=service_ready claim=fixture",
        "event=component_exit role=runtime",
        "event=component_exit role=channel",
        "event=component_exit role=bridge",
    ):
        if marker not in journal:
            errors.append(f"journal_marker:{marker}")
    process_tree = (EVIDENCE / "process-tree.redacted.txt").read_text(
        encoding="utf-8"
    )
    for marker in (
        "ONE_SYSTEMD_CGROUP=true",
        "KILL_MODE=control-group",
        "DETACHED_CHILDREN=false",
        "SUPERVISOR_COUNT=1",
        "RUNTIME_COUNT=1",
        "CHANNEL_COUNT=1",
        "BRIDGE_COUNT=1",
        "FINAL_PROCESS_COUNT=0",
    ):
        if marker not in process_tree:
            errors.append(f"process_tree:{marker}")

    ipv4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
    for candidate in EVIDENCE.iterdir():
        if not candidate.is_file():
            continue
        text = candidate.read_text(encoding="utf-8", errors="ignore")
        exposed = {value for value in ipv4.findall(text) if value != "127.0.0.1"}
        if exposed:
            errors.append(f"evidence_non_loopback_ip:{candidate.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    args = parser.parse_args()
    final = not args.prepare
    errors: list[str] = []

    try:
        if git("rev-parse", BASE_COMMIT)[1] != BASE_COMMIT:
            errors.append("base_commit")
        if git("branch", "--show-current")[1] != EXPECTED_BRANCH:
            errors.append("branch")
        if git("remote", "get-url", "origin")[1] != EXPECTED_ORIGIN:
            errors.append("origin")
        if set(git("remote")[1].splitlines()) != {"origin"}:
            errors.append("remotes")
        if git(
            "for-each-ref",
            "--format=%(refname:short)",
            "refs/remotes/origin/codex/cyberboss*",
        )[1]:
            errors.append("remote_phase_branch")

        changed = changed_paths()
        allowed = IMPLEMENTATION_PATHS | CLOSURE_PATHS
        unexpected = {
            value
            for value in changed
            if value not in allowed
            and not value.startswith("CyberBoss/docs/evidence/CB-130/")
        }
        if unexpected:
            errors.append(f"changed_paths:{','.join(sorted(unexpected))}")
        missing = IMPLEMENTATION_PATHS - changed
        if missing:
            errors.append(f"implementation_paths_missing:{','.join(sorted(missing))}")
        app_changed = {
            value for value in changed if value.startswith("CyberBoss/app/")
        }
        if app_changed != APP_PATHS:
            errors.append("app_changed_paths")
        if git("diff", "--quiet", BASE_COMMIT, "--", *FROZEN_PATHS, check=False)[0]:
            errors.append("frozen_paths_modified")

        ledger = load_json(PROJECT / "machine/facts/post-baseline-change-ledger.json")
        entry = next(
            item
            for item in ledger.get("entries", [])
            if item.get("task_id") == "CB-130"
        )
        if (
            ledger.get("strict_compliance_expression") != STRICT_LICENSE
            or ledger.get("upstream_clarification_received") is not False
            or ledger.get("upstream_clarification_claimed") is not False
            or ledger.get("original_source_and_licenses_preserved") is not True
            or entry.get("phase") != "P1.4"
            or entry.get("base_commit") != BASE_COMMIT
            or set(entry.get("changed_app_paths") or []) != APP_PATHS
            or entry.get("upstream_sync_enabled") is not False
            or entry.get("upstream_support_claimed") is not False
            or entry.get("upstream_endorsement_claimed") is not False
        ):
            errors.append("modification_ledger")

        package = load_json(PROJECT / "app/package.json")
        if (
            package.get("license") != "AGPL-3.0-only"
            or package.get("dependencies", {}).get("timeline-for-agent")
            != "file:../vendor/timeline-for-agent"
            or package.get("dependencies", {}).get("whereabouts-mcp")
            != "file:../vendor/whereabouts-mcp"
        ):
            errors.append("package_contract")

        dag = yaml.safe_load(
            (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
        )
        task = next(item for item in dag["tasks"] if item["id"] == "CB-130")
        if (
            task.get("title")
            != "Run the fixed local cloud bridge and Codex on loopback under one supervised process family"
            or task.get("dependencies") != ["CB-100", "CB-110", "CB-120"]
            or task.get("acceptance_criteria")
            != ["AC-011", "AC-040", "AC-044", "AC-062"]
            or task.get("pass_gate") != "PG-1"
        ):
            errors.append("task_contract")

        health = load_json(KIT / "config/cloud-process-health.json")
        if (
            health.get("task_id") != "CB-130"
            or health.get("runtime_endpoint") != "ws://127.0.0.1:8765"
            or health.get("health_endpoint")
            != "http://127.0.0.1:8780/healthz"
            or health.get("ready_endpoint")
            != "http://127.0.0.1:8780/readyz"
            or health.get("critical_components")
            != ["runtime", "channel", "bridge"]
            or health.get("recovery", {}).get("fixed_wait") is not False
            or health.get("recovery", {}).get("llm_call") is not False
        ):
            errors.append("health_contract")

        verify_manifest(KIT / "MANIFEST.sha256", errors)
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        validate_state(final, errors)

        run_command(
            "shell_syntax",
            [
                "bash",
                "-n",
                str(KIT / "scripts/run-cyberboss.sh"),
                str(KIT / "scripts/health-check.sh"),
                str(KIT / "scripts/install-cloud-process-family.sh"),
                str(KIT / "scripts/accept-cloud-process-family.sh"),
            ],
            errors,
        )
        run_command(
            "builder_compile",
            [
                sys.executable,
                "-m",
                "py_compile",
                str(KIT / "scripts/build-cloud-process-artifacts.py"),
            ],
            errors,
        )
        run_command(
            "installer_check",
            [
                "bash",
                str(KIT / "scripts/install-cloud-process-family.sh"),
                "--check",
                "--release-id",
                "0" * 40,
            ],
            errors,
        )
        run_command(
            "cloud_process_family",
            ["node", "--test", str(PROJECT / "tests/cloud-process-family.test.js")],
            errors,
        )
        run_command(
            "supervisor_contract",
            ["node", "--test", str(PROJECT / "app/test/cloud-supervisor.test.js")],
            errors,
        )
        run_command(
            "simulator_contract",
            ["node", "--test", str(KIT / "tests/simulator-contract.test.mjs")],
            errors,
        )
        run_command(
            "config",
            [
                "node",
                str(KIT / "tests/validate_config.js"),
                "--allow-placeholders",
                str(KIT / "config/cyberboss.env.example"),
                str(KIT / "config/workspaces.json.example"),
            ],
            errors,
        )
        run_command("app_check", ["npm", "run", "check"], errors, cwd=PROJECT / "app")
        run_command("app_test", ["npm", "test"], errors, cwd=PROJECT / "app")
        run_command(
            "prestage0",
            [sys.executable, str(PROJECT / "scripts/validate_prestage0.py")],
            errors,
        )
        for name, script, script_args in (
            (
                "task_dag",
                KIT / "tests/validate_task_dag.py",
                [str(PACK / "04_TASK_DAG_EXECUTION_PACK.yaml")],
            ),
            (
                "traceability",
                KIT / "tests/validate_traceability.py",
                [str(PACK)],
            ),
            ("no_wait", KIT / "tests/validate_no_wait.py", [str(PACK)]),
            ("taskpack", KIT / "tests/validate_taskpack.py", [str(PACK)]),
        ):
            run_command(name, [sys.executable, str(script), *script_args], errors)
        run_command("diff_check", ["git", "diff", "--check"], errors)

        if final:
            validate_final_evidence(errors)
            report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
            readme = (PROJECT / "README.md").read_text(encoding="utf-8")
            handoff = (PROJECT / "HANDOFF.md").read_text(encoding="utf-8")
            changelog = (PROJECT / "CHANGELOG.md").read_text(encoding="utf-8")
            if (
                "Task state: `passed`" not in report
                or "CB-140: `not_started`" not in report
                or "AC-011" not in report
                or "AC-062" not in report
            ):
                errors.append("validation_report_state")
            for name, text in (
                ("readme", readme),
                ("handoff", handoff),
                ("changelog", changelog),
            ):
                if "P1.4 / CB-130" not in text:
                    errors.append(f"closure_docs:{name}")
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        RuntimeError,
        yaml.YAMLError,
        json.JSONDecodeError,
    ) as error:
        errors.append(f"exception:{type(error).__name__}:{error}")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print(
            f"CB130_VALIDATION=FAIL mode={'final' if final else 'prepare'} "
            f"errors={len(set(errors))}"
        )
        return 1
    print(
        f"CB130_VALIDATION=PASS mode={'final' if final else 'prepare'} "
        "task=P1.4/CB-130 acceptances=AC-011,AC-040,AC-044,AC-062 "
        "runtime=loopback process_family=single_cgroup fixed_wait=false "
        "real_adapters=activation_pending upstream_clarification_received=false "
        "publication=none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
