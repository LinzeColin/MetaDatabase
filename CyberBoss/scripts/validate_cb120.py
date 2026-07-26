#!/usr/bin/env python3
"""Fail-closed validator for CyberBoss P1.3 / CB-120."""

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
EVIDENCE = PROJECT / "docs/evidence/CB-120"
BASE_COMMIT = "bacb20147b1f9971b8d47c578599fd3494bed5c3"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_TARGET_HASH = "7865f743d174"
CLIENT_SHA256 = (
    "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa"
)
GH_SHA256 = (
    "83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60"
)
STRICT_LICENSE = "AGPL-3.0-only AND GPL-3.0-only"

APP_PATHS = {
    "CyberBoss/app/README.en.md",
    "CyberBoss/app/README.md",
    "CyberBoss/app/README.zh-CN.md",
    "CyberBoss/app/package.json",
    "CyberBoss/app/src/core/app.js",
    "CyberBoss/app/src/core/command-registry.js",
    "CyberBoss/app/src/core/config.js",
    "CyberBoss/app/src/core/workspace-registry.js",
    "CyberBoss/app/src/index.js",
    "CyberBoss/app/src/services/system-message-service.js",
    "CyberBoss/app/test/claudecode-approval.test.js",
    "CyberBoss/app/test/turn-gate-store.test.js",
    "CyberBoss/app/test/upstream-separation.test.js",
    "CyberBoss/app/test/workspace-scope.test.js",
}

IMPLEMENTATION_PATHS = APP_PATHS | {
    "CyberBoss/docs/governance/RUN_CONTRACT_P1_3_CB_120.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/MANIFEST.sha256",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/README.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/VALIDATION_REPORT.md",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/credential-slots.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.gitconfig",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/cyberboss.env.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/identity-scope.policy.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/no-clone-client-versions.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/workspace-budget.json",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/config/workspaces.json.example",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/build-controlled-workspace-artifacts.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/install-controlled-workspace.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/private_db_client_safe.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/scope_policy.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/workspace-maintenance.sh",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/scripts/workspace_budget.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_identity_scope.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/test_workspace_budget.py",
    "CyberBoss/docs/product_design/v0.0.0.4/implementation-kit/tests/validate_config.js",
    "CyberBoss/machine/facts/post-baseline-change-ledger.json",
    "CyberBoss/scripts/validate_cb120.py",
    "CyberBoss/tests/cloud-controlled-workspace.test.js",
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
    "du.redacted.txt",
    "identity-negative.redacted.json",
    "implementation-commit.json",
    "install-acceptance.redacted.json",
    "publication-check.json",
    "resource-pressure.redacted.json",
    "rollback-plan.json",
    "security-report.json",
    "source-modification-record.json",
    "target-preflight.redacted.json",
    "validation.txt",
    "workspace-budget.redacted.json",
    "workspace-registry-transcript.txt",
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
    "CyberBoss/docs/evidence/PG-0",
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
        if candidate.is_file() and candidate != path
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
        errors.append(f"command:{name}:{result.returncode}:{tail[0][:160]}")


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
    }
    if final:
        expected_passed.add("CB-120")
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
    if final:
        current = state.get("current_run") or {}
        if (
            current.get("run_id") != "P1.3"
            or current.get("task_id") != "CB-120"
            or current.get("status") != "passed"
        ):
            errors.append("state_current_run")


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
        implementation.get("task_id") != "CB-120"
        or implementation.get("base_commit") != BASE_COMMIT
        or implementation.get("branch") != EXPECTED_BRANCH
        or implementation.get("remote_publication") != "none"
    ):
        errors.append("implementation_commit_contract")
    if git("cat-file", "-e", f"{implementation_commit}^{{commit}}", check=False)[0]:
        errors.append("implementation_commit_missing")
    else:
        implementation_diff = set(
            filter(
                None,
                git(
                    "diff",
                    "--name-only",
                    BASE_COMMIT,
                    implementation_commit,
                )[1].splitlines(),
            )
        )
        if implementation_diff != IMPLEMENTATION_PATHS:
            errors.append("implementation_commit_paths")

    artifact = load_json(EVIDENCE / "artifact-manifest.json")
    if (
        artifact.get("task_id") != "CB-120"
        or artifact.get("release_commit") != implementation_commit
        or artifact.get("branch") != EXPECTED_BRANCH
        or artifact.get("source", {}).get("license_expression") != STRICT_LICENSE
        or artifact.get("source", {}).get("upstream_clarification_received")
        is not False
        or artifact.get("workspace_seed", {}).get("filter") != "blob:none"
        or artifact.get("workspace_seed", {}).get("sparse_paths")
        != ["CyberBoss", ".github"]
        or artifact.get("private_db_client", {}).get("sha256") != CLIENT_SHA256
        or artifact.get("github_cli", {}).get("sha256") != GH_SHA256
        or artifact.get("deployment", {}).get("switch_current") is not False
        or artifact.get("deployment", {}).get("clone_private_database") is not False
        or artifact.get("deployment", {}).get("remote_publication") != "none"
    ):
        errors.append("artifact_manifest")

    preflight = load_json(EVIDENCE / "target-preflight.redacted.json")
    if (
        preflight.get("task_id") != "CB-120"
        or preflight.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or preflight.get("strict_known_host") is not True
        or preflight.get("key_only_batch_mode") is not True
        or preflight.get("sudo_noninteractive") is not True
        or preflight.get("service_active") is not False
        or preflight.get("service_enabled") is not False
        or preflight.get("guard_state") != "recover"
        or preflight.get("secret_content_reads") != 0
    ):
        errors.append("target_preflight")

    install = load_json(EVIDENCE / "install-acceptance.redacted.json")
    if (
        install.get("task_id") != "CB-120"
        or install.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or install.get("implementation_commit") != implementation_commit
        or install.get("check_passed") is not True
        or install.get("apply_passes") != 2
        or install.get("verify_passed") is not True
        or install.get("second_apply_idempotent") is not True
        or install.get("candidate_release_immutable") is not True
        or install.get("candidate_tests_passed") is not True
        or install.get("workspace_head") != implementation_commit
        or install.get("workspace_filter") != "blob:none"
        or install.get("workspace_sparse_paths") != [".github", "CyberBoss"]
        or install.get("workspace_remote_kind") != "local_immutable_seed"
        or install.get("current_changed") is not False
        or install.get("service_active") is not False
        or install.get("service_enabled") is not False
        or install.get("business_runtime_started") is not False
        or install.get("private_database_cloned") is not False
        or install.get("real_data_operations") != 0
    ):
        errors.append("install_acceptance")

    budget = load_json(EVIDENCE / "workspace-budget.redacted.json")
    usage = budget.get("usage") or {}
    limits = budget.get("limits") or {}
    if (
        budget.get("task_id") != "CB-120"
        or budget.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or budget.get("state") != "recover"
        or budget.get("result") != "pass"
        or budget.get("hard_stop_workspace_bytes") != 8589934592
        or budget.get("no_prune_now") is not True
        or not isinstance(usage.get("workspace_bytes"), int)
        or usage.get("workspace_bytes", 8589934593) > 4294967296
        or usage.get("host_available_bytes", 0) < 4294967296
        or limits.get("workspace_bytes") != 4294967296
    ):
        errors.append("workspace_budget")

    identity = load_json(EVIDENCE / "identity-negative.redacted.json")
    if (
        identity.get("task_id") != "CB-120"
        or identity.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or identity.get("code_identity_can_read_client") is not False
        or identity.get("code_identity_can_execute_wrapper") is not False
        or identity.get("data_identity_can_modify_workspace") is not False
        or identity.get("data_identity_plan_only_passed") is not True
        or identity.get("credential_file_present") is not False
        or identity.get("credential_content_reads") != 0
        or identity.get("real_data_operations") != 0
    ):
        errors.append("identity_negative")

    pressure = load_json(EVIDENCE / "resource-pressure.redacted.json")
    if (
        pressure.get("task_id") != "CB-120"
        or pressure.get("target_id_sha256") != EXPECTED_TARGET_HASH
        or pressure.get("evidence_scope") != "authorized_live_host_container"
        or pressure.get("guard_ladder_passed") is not True
        or pressure.get("protect_ladder_passed") is not True
        or pressure.get("recovery_passed") is not True
        or pressure.get("oom_events") != 0
        or pressure.get("fixed_sleep_seconds") != 0
        or pressure.get("real_time_soak") is not False
    ):
        errors.append("resource_pressure")

    security = load_json(EVIDENCE / "security-report.json")
    if (
        security.get("task_id") != "CB-120"
        or security.get("p0_findings") != 0
        or security.get("p1_findings") != 0
        or security.get("secret_content_reads") != 0
        or security.get("public_listeners_created") != 0
        or security.get("provider_writes") != 0
        or security.get("private_database_writes") != 0
        or security.get("upstream_clarification_received") is not False
    ):
        errors.append("security_report")

    publication = load_json(EVIDENCE / "publication-check.json")
    if (
        publication.get("task_id") != "CB-120"
        or publication.get("remote_branch") != "absent"
        or publication.get("pull_request") != "none"
        or publication.get("tag") != "none"
        or publication.get("release") != "none"
        or publication.get("push_performed") is not False
    ):
        errors.append("publication_check")

    source_record = load_json(EVIDENCE / "source-modification-record.json")
    if (
        source_record.get("task_id") != "CB-120"
        or source_record.get("base_commit") != BASE_COMMIT
        or source_record.get("implementation_commit") != implementation_commit
        or set(source_record.get("changed_app_paths") or []) != APP_PATHS
        or source_record.get("strict_compliance_expression") != STRICT_LICENSE
        or source_record.get("original_source_and_licenses_preserved") is not True
        or source_record.get("upstream_clarification_received") is not False
    ):
        errors.append("source_modification_record")

    transcript = (EVIDENCE / "workspace-registry-transcript.txt").read_text(
        encoding="utf-8"
    )
    for marker in (
        "BIND_ALIAS=PASS alias=cyberboss",
        "BIND_ABSOLUTE=REJECTED filesystem_changed=false",
        "BIND_UNKNOWN=REJECTED filesystem_changed=false",
        "SYMLINK_ESCAPE=REJECTED filesystem_changed=false",
        "RUNTIME_UNREGISTERED=REJECTED",
    ):
        if marker not in transcript:
            errors.append(f"workspace_transcript:{marker}")

    du = (EVIDENCE / "du.redacted.txt").read_text(encoding="utf-8")
    if (
        "WORKSPACE_BUDGET=PASS state=recover" not in du
        or "WORKSPACE_ABOVE_8_GIB=false" not in du
        or "TARGET_ADDRESS_REDACTED=true" not in du
    ):
        errors.append("du_evidence")

    rollback = load_json(EVIDENCE / "rollback-plan.json")
    if (
        rollback.get("task_id") != "CB-120"
        or rollback.get("current_pointer_must_not_move") is not True
        or rollback.get("credential_delete_allowed") is not False
        or rollback.get("prune_now_allowed") is not False
    ):
        errors.append("rollback_plan")


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
            path
            for path in changed
            if path not in allowed
            and not path.startswith("CyberBoss/docs/evidence/CB-120/")
        }
        if unexpected:
            errors.append(f"changed_paths:{','.join(sorted(unexpected))}")
        missing_implementation = IMPLEMENTATION_PATHS - changed
        if missing_implementation:
            errors.append(
                f"implementation_paths_missing:{','.join(sorted(missing_implementation))}"
            )

        app_changed = {path for path in changed if path.startswith("CyberBoss/app/")}
        if app_changed != APP_PATHS:
            errors.append("app_changed_paths")
        ledger = load_json(
            PROJECT / "machine/facts/post-baseline-change-ledger.json"
        )
        ledger_entry = ledger.get("entries", [{}])[0]
        if (
            ledger.get("strict_compliance_expression") != STRICT_LICENSE
            or ledger.get("upstream_clarification_received") is not False
            or ledger.get("upstream_clarification_claimed") is not False
            or ledger.get("original_source_and_licenses_preserved") is not True
            or set(ledger_entry.get("changed_app_paths") or []) != APP_PATHS
            or ledger_entry.get("base_commit") != BASE_COMMIT
            or ledger_entry.get("upstream_sync_enabled") is not False
        ):
            errors.append("modification_ledger")

        if git("diff", "--quiet", BASE_COMMIT, "--", *FROZEN_PATHS, check=False)[0]:
            errors.append("frozen_paths_modified")

        active_app_paths = {
            path
            for path in APP_PATHS
            if "/test/" not in path
        }
        active_app = "\n".join(
            (REPO / path).read_text(encoding="utf-8", errors="ignore")
            for path in active_app_paths
            if (REPO / path).is_file()
        )
        if re.search(r"WenXiaoWendy|github\.com/[^/\s]+/(?:cyberboss|timeline-for-agent|whereabouts-mcp)", active_app, re.I):
            errors.append("active_upstream_route")
        package = load_json(PROJECT / "app/package.json")
        if (
            package.get("dependencies", {}).get("timeline-for-agent")
            != "file:../vendor/timeline-for-agent"
            or package.get("dependencies", {}).get("whereabouts-mcp")
            != "file:../vendor/whereabouts-mcp"
        ):
            errors.append("local_vendor_dependencies")

        versions = load_json(KIT / "config/no-clone-client-versions.json")
        if (
            versions.get("private_db_client", {}).get("sha256") != CLIENT_SHA256
            or versions.get("github_cli", {}).get("archive_sha256") != GH_SHA256
            or versions.get("github_cli", {}).get("version") != "2.96.0"
        ):
            errors.append("no_clone_versions")
        budget = load_json(KIT / "config/workspace-budget.json")
        if (
            budget.get("workspace_max_bytes") != 4294967296
            or budget.get("hard_stop_workspace_bytes") != 8589934592
            or budget.get("host_reserve_min_bytes") != 4294967296
            or "--prune=now" in json.dumps(budget.get("cleanup_commands"))
        ):
            errors.append("budget_policy")
        workspaces = load_json(KIT / "config/workspaces.json.example")
        workspace = workspaces.get("workspaces", {}).get("cyberboss", {})
        if (
            workspaces.get("default_alias") != "cyberboss"
            or list(workspaces.get("workspaces", {})) != ["cyberboss"]
            or workspace.get("root") != "/srv/cyberboss-workspaces/cyberboss"
            or workspace.get("sparse_paths") != ["CyberBoss", ".github"]
            or workspace.get("root_integration_write") is not False
        ):
            errors.append("workspace_policy")

        dag = yaml.safe_load(
            (PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8")
        )
        task = next(item for item in dag["tasks"] if item["id"] == "CB-120")
        if (
            task.get("title")
            != "Install fixed source bundle, no-clone canonical client and bounded workspace"
            or task.get("dependencies") != ["CB-100", "CB-020"]
            or task.get("acceptance_criteria") != ["AC-013", "AC-014", "AC-064"]
            or task.get("pass_gate") != "PG-1"
        ):
            errors.append("task_contract")

        verify_manifest(KIT / "MANIFEST.sha256", errors)
        verify_manifest(PACK / "MANIFEST.sha256", errors)
        validate_state(final, errors)

        run_command(
            "bash_syntax",
            [
                "bash",
                "-n",
                str(KIT / "scripts/install-controlled-workspace.sh"),
                str(KIT / "scripts/workspace-maintenance.sh"),
            ],
            errors,
        )
        run_command(
            "installer_check",
            [
                "bash",
                str(KIT / "scripts/install-controlled-workspace.sh"),
                "--check",
                "--release-id",
                "0" * 40,
            ],
            errors,
        )
        run_command(
            "cloud_controlled_workspace",
            ["node", "--test", str(PROJECT / "tests/cloud-controlled-workspace.test.js")],
            errors,
        )
        run_command(
            "identity_scope",
            [sys.executable, str(KIT / "tests/test_identity_scope.py")],
            errors,
        )
        run_command(
            "workspace_budget",
            [sys.executable, str(KIT / "tests/test_workspace_budget.py")],
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
        run_command(
            "scope_policy",
            [sys.executable, str(KIT / "scripts/scope_policy.py"), "validate"],
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
            run_command(
                name,
                [sys.executable, str(script), *script_args],
                errors,
            )
        run_command("diff_check", ["git", "diff", "--check"], errors)

        if final:
            validate_final_evidence(errors)
            report = (EVIDENCE / "VALIDATION_REPORT.md").read_text(encoding="utf-8")
            root_readme = (PROJECT / "README.md").read_text(encoding="utf-8")
            handoff = (PROJECT / "HANDOFF.md").read_text(encoding="utf-8")
            if "Task state: `passed`" not in report or "CB-130: `not_started`" not in report:
                errors.append("validation_report_state")
            if "P1.3 / CB-120" not in root_readme or "CB-120" not in handoff:
                errors.append("closure_docs")
    except (
        OSError,
        ValueError,
        KeyError,
        IndexError,
        RuntimeError,
        yaml.YAMLError,
        json.JSONDecodeError,
    ) as error:
        errors.append(f"exception:{type(error).__name__}:{error}")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print(
            f"CB120_VALIDATION=FAIL mode={'final' if final else 'prepare'} "
            f"errors={len(set(errors))}"
        )
        return 1
    print(
        f"CB120_VALIDATION=PASS mode={'final' if final else 'prepare'} "
        "task=P1.3/CB-120 acceptances=AC-013,AC-014,AC-064 "
        "workspace_alias=cyberboss filter=blob:none "
        "private_database_clone=false upstream_clarification_received=false "
        "publication=none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
