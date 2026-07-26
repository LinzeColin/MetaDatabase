#!/usr/bin/env python3
"""Validate the frozen P0.5 / CB-040 implementation baseline.

Use --baseline before the self-identifying baseline commit is created. The
default mode additionally validates the recorded commit and closed task state.
The validator is read-only and performs no provider, deployment or remote write.
"""

from __future__ import annotations

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
EVIDENCE = PROJECT / "docs/evidence/CB-040"
BASE_COMMIT = "539a15e0cbebce6b6dd016316721085576dba0d6"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"

EXPECTED_FLAGS = {
    "CB_DURABLE_INBOX": True,
    "CB_DURABLE_OUTBOX": True,
    "CB_PRIVATE_DB_CANONICAL_SYNC": True,
    "CB_TIMELINE_WEB": True,
    "CB_STATUS_EXPORTER": True,
    "CB_R2_SNAPSHOT": True,
    "CB_OCI_BACKUP": False,
    "CB_CLAUDE_RUNTIME": False,
    "CB_FILE_ATTACHMENTS": False,
    "CB_STORE_FULL_CONTENT": False,
    "CB_AUTONOMOUS_MUTATION": False,
}

STALE_FLAG_ALIASES = {
    "CB_CANONICAL_STORE_CONTENT",
    "CB_GITHUB_CANONICAL_SYNC",
    "CB_CANONICAL_SYNC",
    "CB_GLOBAL_STATUS",
    "CB_R2_BACKUP",
    "CB_ATTACHMENTS",
    "CB_AUTONOMOUS_IRREVERSIBLE",
    "CB_TIMELINE_SEARCH",
    "CB_MULTI_WORKSPACE_ACTIVE",
}

EXACT_ALLOWED_PATHS = {
    "CyberBoss/docs/governance/RUN_CONTRACT_P0_5_CB_040.md",
    "CyberBoss/scripts/validate_cb040.py",
    "CyberBoss/docs/product_design/v0.0.0.4/01_PRFAQ_STRATEGY_OKR.md",
    "CyberBoss/docs/product_design/v0.0.0.4/03_ARCHITECTURE_DATA_SECURITY.md",
    "CyberBoss/docs/product_design/v0.0.0.4/05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md",
    "CyberBoss/docs/product_design/v0.0.0.4/09_PREAUTHORIZED_DECISIONS_ACTIVATION_INPUTS.md",
    "CyberBoss/docs/product_design/v0.0.0.4/MANIFEST.sha256",
    "CyberBoss/machine/facts/task_state.json",
    "CyberBoss/README.md",
    "CyberBoss/HANDOFF.md",
    "CyberBoss/CHANGELOG.md",
}

BASELINE_REQUIRED = {
    "implementation-baseline.md",
    "environment-substitutions.json",
    "implementation-plan.json",
    "canonical-conflict-scan.json",
    "traceability-sample.json",
    "activation-continuation.json",
    "dag-validation.txt",
    "taskpack-validations.txt",
}

FINAL_REQUIRED = BASELINE_REQUIRED | {
    "baseline-commit.json",
    "VALIDATION_REPORT.md",
}


def git(*args: str, check: bool = True) -> str:
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
    return result.stdout.rstrip()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest(path: Path, errors: list[str]) -> None:
    base = path.parent
    listed: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", raw)
        if not match:
            errors.append(f"manifest_invalid_line:{path.relative_to(REPO)}:{number}")
            continue
        digest, relative = match.groups()
        if relative in listed or Path(relative).is_absolute() or ".." in Path(relative).parts:
            errors.append(f"manifest_unsafe_or_duplicate:{path.relative_to(REPO)}:{relative}")
            continue
        listed[relative] = digest

    actual = {
        item.relative_to(base).as_posix(): sha256(item)
        for item in base.rglob("*")
        if item.is_file() and item != path
    }
    for relative in sorted(set(actual) - set(listed)):
        errors.append(f"manifest_unlisted:{path.relative_to(REPO)}:{relative}")
    for relative in sorted(set(listed) - set(actual)):
        errors.append(f"manifest_missing:{path.relative_to(REPO)}:{relative}")
    for relative in sorted(set(actual) & set(listed)):
        if actual[relative] != listed[relative]:
            errors.append(f"manifest_hash:{path.relative_to(REPO)}:{relative}")


def feature_table_flags(path: Path, start: str, end: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    section = text.split(start, 1)[1].split(end, 1)[0]
    return set(re.findall(r"\|\s*`(CB_[A-Z0-9_]+)`\s*\|", section))


def environment_flags(path: Path) -> dict[str, bool]:
    values: dict[str, bool] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"(CB_[A-Z0-9_]+)=(true|false)", raw.strip())
        if match and match.group(1) in EXPECTED_FLAGS:
            values[match.group(1)] = match.group(2) == "true"
    return values


def changed_paths() -> set[str]:
    committed = set(filter(None, git("diff", "--name-only", BASE_COMMIT, "HEAD").splitlines()))
    working: set[str] = set()
    for raw in git("status", "--porcelain", "--untracked-files=all").splitlines():
        if not raw:
            continue
        path = raw[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        working.add(path)
    return committed | working


def allowed_path(path: str) -> bool:
    return path in EXACT_ALLOWED_PATHS or path.startswith("CyberBoss/docs/evidence/CB-040/")


def find_secret_material(value: Any) -> bool:
    serialized = json.dumps(value, ensure_ascii=False)
    patterns = [
        r"\bsk-[A-Za-z0-9_-]{16,}\b",
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        r"\bBearer\s+[A-Za-z0-9._~-]{20,}",
    ]
    return any(re.search(pattern, serialized) for pattern in patterns)


def main() -> int:
    baseline_mode = "--baseline" in sys.argv[1:]
    unknown_args = [arg for arg in sys.argv[1:] if arg != "--baseline"]
    if unknown_args:
        print(f"ERROR=unknown_arguments:{','.join(unknown_args)}")
        return 2

    errors: list[str] = []

    def expect(condition: bool, code: str) -> None:
        if not condition:
            errors.append(code)

    required = BASELINE_REQUIRED if baseline_mode else FINAL_REQUIRED
    for name in sorted(required):
        expect((EVIDENCE / name).is_file(), f"missing_evidence:{name}")

    # Git/worktree scope and separation.
    expect(git("rev-parse", "HEAD") != "", "git_head_missing")
    expect(git("branch", "--show-current") == EXPECTED_BRANCH, "branch_identity")
    expect(git("remote", "get-url", "origin") == EXPECTED_ORIGIN, "origin_identity")
    expect(git("remote").splitlines() == ["origin"], "unexpected_remote")
    expect(
        git("merge-base", "--is-ancestor", BASE_COMMIT, "HEAD", check=False) == "",
        "base_not_ancestor",
    )
    for path in sorted(changed_paths()):
        expect(allowed_path(path), f"scope_violation:{path}")
        expect(not path.startswith("CyberBoss/app/"), f"app_changed:{path}")
        expect(not path.startswith("CyberBoss/vendor/"), f"vendor_changed:{path}")
    expect(not list(PROJECT.rglob(".git")), "nested_git_repository")
    for row in git("ls-files", "-s", "CyberBoss").splitlines():
        expect(not row.startswith("160000 "), f"gitlink_in_project:{row}")

    run_contract = PROJECT / "docs/governance/RUN_CONTRACT_P0_5_CB_040.md"
    contract_text = run_contract.read_text(encoding="utf-8")
    for required_text in [
        "P0.5 / CB-040",
        BASE_COMMIT,
        "不执行 `PG-0`",
        "不 push",
        "GO_TO_PG-0",
        "Feature Flag 别名",
    ]:
        expect(required_text in contract_text, f"run_contract_missing:{required_text}")

    # Canonical owner/source/identity facts.
    owner = load_json(PROJECT / "machine/facts/owner_decisions.json")
    source = load_json(PROJECT / "machine/source-lock.json")
    identity = load_json(KIT / "config/identity-scope.policy.json")
    credentials = load_json(KIT / "config/credential-slots.json")
    task_state = load_json(PROJECT / "machine/facts/task_state.json")
    dag = yaml.safe_load((PACK / "04_TASK_DAG_EXECUTION_PACK.yaml").read_text(encoding="utf-8"))

    expect(owner["project"]["repository"] == "LinzeColin/MetaDatabase", "owner_repo")
    expect(owner["project"]["subpath"] == "CyberBoss/", "owner_subpath")
    expect(owner["project"]["independent_repository_allowed"] is False, "owner_new_repo")
    expect(owner["workspace"]["default_write_globs"] == ["CyberBoss/**"], "owner_write_scope")
    expect(owner["execution"]["max_phases_per_run"] == 1, "owner_phase_limit")
    expect(owner["execution"]["intermediate_push_allowed"] is False, "owner_push_policy")
    expect(
        owner["execution"]["intermediate_pull_request_allowed"] is False,
        "owner_pr_policy",
    )
    for key in [
        "upstream_remote_allowed",
        "git_submodule_allowed",
        "git_url_runtime_dependency_allowed",
        "automatic_sync_allowed",
        "runtime_source_fetch_allowed",
        "periodic_rebase_allowed",
    ]:
        expect(owner["upstream_separation"][key] is False, f"owner_upstream:{key}")

    expect(source["repository"] == "LinzeColin/MetaDatabase", "source_repo")
    expect(source["project_subpath"] == "CyberBoss/", "source_subpath")
    expect(source["codex_cli"]["exact_tested_version"] == "0.146.0-alpha.3.1", "codex_pin")
    expect(source["upstream_relationship"] == {
        "automatic_sync_allowed": False,
        "git_url_dependency_allowed": False,
        "periodic_rebase_allowed": False,
        "remote_allowed": False,
        "runtime_source_fetch_allowed": False,
        "submodule_allowed": False,
    }, "source_upstream_relationship")
    whereabouts = source["whereabouts_license_conflict"]
    expect(
        whereabouts["compliance_expression"] == "GPL-3.0-only AND AGPL-3.0-only",
        "whereabouts_expression",
    )
    expect(whereabouts["preserve_original_license_and_source"] is True, "whereabouts_preserve")
    expect(whereabouts["upstream_clarification_received"] is False, "whereabouts_clarification")
    expect(whereabouts["must_not_claim_upstream_clarification"] is True, "whereabouts_claim_rule")

    expect(identity["code"]["repository"] == "LinzeColin/MetaDatabase", "identity_repo")
    expect(identity["code"]["project_subpath"] == "CyberBoss", "identity_subpath")
    expect(identity["code"]["new_repository_allowed"] is False, "identity_new_repo")
    expect(identity["data"]["repository"] == "LinzeColin/Private-Database", "identity_data_repo")
    expect(identity["data"]["branch"] == "main", "identity_data_branch")
    expect(identity["data"]["area"] == "Private-MetaDatabase", "identity_data_area")
    expect(identity["data"]["domain"] == "CyberBoss", "identity_data_domain")
    expect(identity["data"]["access_mode"] == "no_clone_client", "identity_data_mode")
    expect(
        identity["data"]["allowed_operations"] == ["ingest", "get", "list", "verify"],
        "identity_data_operations",
    )
    expect(identity["cloudflare"]["hostname"] == "cyberboss.linzezhang.com", "identity_hostname")
    expect(identity["cloudflare"]["r2"]["bucket"] == "cyberboss-cold", "identity_r2_bucket")
    expect(
        identity["cloudflare"]["r2"]["object_prefix"] == "ovh-singapore-vps-1/",
        "identity_r2_prefix",
    )
    expect(identity["oci"]["region"] == "ap-sydney-1", "identity_oci_region")
    expect(
        identity["oci"]["object_prefix"]
        == "cyberboss-cold-backup/ovh-singapore-vps-1/",
        "identity_oci_prefix",
    )

    # Manifest integrity after the narrowly scoped flag-name errata.
    verify_manifest(PACK / "MANIFEST.sha256", errors)
    verify_manifest(KIT / "MANIFEST.sha256", errors)

    # Exact feature flag identity in architecture, verification and runtime config.
    architecture_flags = feature_table_flags(
        PACK / "03_ARCHITECTURE_DATA_SECURITY.md",
        "## 14. Feature Flags",
        "## 15.",
    )
    verification_flags = feature_table_flags(
        PACK / "05_ACCELERATED_VERIFICATION_MODEL_SECURITY_RELEASE.md",
        "## 8. Feature Flags",
        "## 9.",
    )
    configured_flags = environment_flags(KIT / "config/cyberboss.env.example")
    expect(architecture_flags == set(EXPECTED_FLAGS), "architecture_flag_set")
    expect(verification_flags == set(EXPECTED_FLAGS), "verification_flag_set")
    expect(configured_flags == EXPECTED_FLAGS, "environment_flag_set_or_default")
    active_docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACK.glob("[0-9][0-9]_*.md"))
    )
    for alias in sorted(STALE_FLAG_ALIASES):
        expect(not re.search(rf"\b{re.escape(alias)}\b", active_docs), f"stale_flag:{alias}")

    # Frozen substitutions and secret-slot references.
    substitutions = load_json(EVIDENCE / "environment-substitutions.json")
    expect(not find_secret_material(substitutions), "secret_material_in_substitutions")
    expect(substitutions["status"] == "frozen_non_secret_baseline", "substitution_status")
    expect(substitutions["code_identity"]["repository"] == owner["project"]["repository"], "sub_repo")
    expect(substitutions["code_identity"]["project_subpath"] == "CyberBoss", "sub_path")
    expect(substitutions["code_identity"]["base_commit"] == BASE_COMMIT, "sub_base")
    expect(substitutions["code_identity"]["new_repository_allowed"] is False, "sub_new_repo")
    expect(substitutions["source_and_license"]["upstream_remote_allowed"] is False, "sub_upstream")
    expect(
        substitutions["source_and_license"]["whereabouts_compliance_expression"]
        == "GPL-3.0-only AND AGPL-3.0-only",
        "sub_license_expression",
    )
    expect(
        substitutions["source_and_license"]["upstream_clarification_received"] is False,
        "sub_clarification",
    )
    expect(substitutions["paths"]["app_root"] == "/opt/cyberboss-cloud", "sub_app_root")
    expect(substitutions["paths"]["state_root"] == "/var/lib/cyberboss", "sub_state_root")
    expect(
        substitutions["paths"]["workspace_root"] == "/srv/cyberboss-workspaces",
        "sub_workspace_root",
    )
    expect(
        substitutions["services_and_ports"]["codex_endpoint"] == "ws://127.0.0.1:8765",
        "sub_codex_endpoint",
    )
    expect(substitutions["services_and_ports"]["http_bind"] == "127.0.0.1", "sub_http_bind")
    expect(substitutions["services_and_ports"]["http_port"] == 8780, "sub_http_port")
    expect(
        substitutions["services_and_ports"]["primary_service"] == "cyberboss-cloud.service",
        "sub_service",
    )
    expect(
        substitutions["canonical_data"]["repository"] == "LinzeColin/Private-Database",
        "sub_data_repo",
    )
    expect(substitutions["canonical_data"]["area"] == "Private-MetaDatabase", "sub_data_area")
    expect(substitutions["canonical_data"]["domain"] == "CyberBoss", "sub_data_domain")
    expect(substitutions["canonical_data"]["access_mode"] == "no_clone_client", "sub_data_mode")
    expect(
        substitutions["cloudflare"]["hostname"] == "cyberboss.linzezhang.com",
        "sub_hostname",
    )
    expect(substitutions["object_storage"]["r2_bucket"] == "cyberboss-cold", "sub_r2_bucket")
    expect(
        substitutions["object_storage"]["r2_prefix"] == "ovh-singapore-vps-1/",
        "sub_r2_prefix",
    )
    expect(
        substitutions["object_storage"]["oci_prefix"]
        == "cyberboss-cold-backup/ovh-singapore-vps-1/",
        "sub_oci_prefix",
    )
    expect(substitutions["resource_limits"]["memory_high"] == "768M", "sub_memory_high")
    expect(substitutions["resource_limits"]["memory_max"] == "1152M", "sub_memory_max")
    expect(substitutions["resource_limits"]["tasks_max"] == 256, "sub_tasks_max")
    expect(substitutions["resource_limits"]["queue_limit"] == 20, "sub_queue_limit")
    frozen_flags = {
        row["name"]: row["value"] for row in substitutions.get("feature_flags", [])
    }
    expect(frozen_flags == EXPECTED_FLAGS, "substitution_flag_set_or_default")

    canonical_slots = {
        row["id"]: row["path"] for row in credentials.get("slots", [])
    }
    frozen_slots = {
        row["id"]: row["path"]
        for row in substitutions["credential_references"].get("slots", [])
    }
    expect(frozen_slots == canonical_slots, "credential_slot_identity")
    expect(len(frozen_slots) == 15, "credential_slot_count")
    expect(
        substitutions["credential_references"]["values_in_repository"] is False,
        "credential_values_repo",
    )
    expect(
        substitutions["credential_references"]["values_in_environment"] is False,
        "credential_values_env",
    )
    expect(
        all("value" not in row for row in substitutions["credential_references"]["slots"]),
        "credential_value_field",
    )
    expect(substitutions["activation_states"]["global_wait_nodes"] == 0, "activation_wait")
    expect(
        substitutions["activation_states"]["target_codex_adapter"] == "activation_pending",
        "target_codex_state",
    )
    expect(
        substitutions["activation_states"]["target_wechat_adapter"] == "activation_pending",
        "target_wechat_state",
    )
    expect(
        substitutions["activation_states"]["cloudflare_r2_real_write"] == "hazard_blocked",
        "target_r2_state",
    )

    # Complete future implementation plan with exact DAG acceptance sets.
    plan = load_json(EVIDENCE / "implementation-plan.json")
    future_dag = [task for task in dag["tasks"] if task["id"] >= "CB-100"]
    future_by_id = {task["id"]: task for task in future_dag}
    plan_by_id = {task["id"]: task for task in plan.get("tasks", [])}
    expect(len(future_dag) == 25, "future_dag_count")
    expect(set(plan_by_id) == set(future_by_id), "implementation_plan_task_set")
    expect(len(plan.get("tasks", [])) == len(plan_by_id), "implementation_plan_duplicate")
    existing_dispositions = {
        "reuse_existing",
        "extend_existing",
        "preserve_existing",
        "evaluate_existing",
        "rehearse_existing",
        "retain_disabled",
    }
    for task_id, row in sorted(plan_by_id.items()):
        expected = future_by_id[task_id]
        expect(row.get("phase") == expected["phase"], f"plan_phase:{task_id}")
        expect(row.get("status") == "not_started", f"plan_status:{task_id}")
        expect(
            row.get("acceptance_criteria") == expected["acceptance_criteria"],
            f"plan_acceptance:{task_id}",
        )
        expect(bool(row.get("modules")), f"plan_modules:{task_id}")
        expect(bool(row.get("tests")), f"plan_tests:{task_id}")
        expect(bool(row.get("evidence")), f"plan_evidence:{task_id}")
        expect(bool(row.get("release_artifacts")), f"plan_release:{task_id}")
        for item in row.get("modules", []) + row.get("tests", []):
            if item.get("disposition") in existing_dispositions:
                expect((REPO / item["path"]).exists(), f"plan_existing_path:{task_id}:{item['path']}")

    # Deterministic requirement sample and full six-link location.
    prd_text = (PACK / "02_PRD_ACCEPTANCE_CONTRACT.md").read_text(encoding="utf-8")
    requirement_rows = re.findall(
        r"^\|\s*((?:FR|NFR)-\d{3})\s*\|.*?\|\s*(AC-\d{3})\s*\|\s*$",
        prd_text,
        re.MULTILINE,
    )
    expect(len(requirement_rows) == 53, "trace_population_count")
    seed = BASE_COMMIT
    expected_sample = sorted(
        (
            hashlib.sha256(f"{seed}:{requirement}".encode()).hexdigest(),
            requirement,
            acceptance,
        )
        for requirement, acceptance in requirement_rows
    )[:10]
    trace = load_json(EVIDENCE / "traceability-sample.json")
    expect(trace["sampling"]["population_size"] == 53, "trace_recorded_population")
    expect(trace["sampling"]["seed"] == seed, "trace_seed")
    expect(trace["sampling"]["sample_size"] == 10, "trace_sample_size")
    sample_rows = trace.get("sample", [])
    expect(len(sample_rows) == 10, "trace_row_count")
    dag_acceptance_tasks: dict[str, list[str]] = {}
    for task in dag["tasks"]:
        for acceptance in task.get("acceptance_criteria", []):
            dag_acceptance_tasks.setdefault(acceptance, []).append(task["id"])
    for index, expected in enumerate(expected_sample):
        if index >= len(sample_rows):
            break
        digest, requirement, acceptance = expected
        row = sample_rows[index]
        expect(row.get("selection_digest_prefix") == digest[:12], f"trace_digest:{index}")
        expect(row.get("requirement") == requirement, f"trace_requirement:{index}")
        expect(row.get("acceptance") == acceptance, f"trace_acceptance:{index}")
        expect(
            row.get("tasks") == dag_acceptance_tasks.get(acceptance),
            f"trace_tasks:{requirement}",
        )
        for link in ["tests", "evidence", "release"]:
            expect(bool(row.get(link)), f"trace_link:{requirement}:{link}")
        expect(row.get("traceability_status") == "located", f"trace_status:{requirement}")
        expect(row.get("acceptance_status") == "not_started", f"trace_claim:{requirement}")
    expect(trace.get("result") == "pass", "trace_result")

    conflict = load_json(EVIDENCE / "canonical-conflict-scan.json")
    expect(conflict.get("result") == "pass", "conflict_result")
    expect(conflict.get("unresolved_conflicts") == [], "unresolved_conflicts")
    expect(conflict.get("stale_active_feature_flag_alias_hits") == 0, "stale_alias_count")
    expect(
        {row["old"] for row in conflict.get("resolved_conflicts", [])}
        == STALE_FLAG_ALIASES,
        "resolved_alias_inventory",
    )
    for row in conflict.get("checks", []):
        expect(row.get("status") == "pass", f"conflict_check:{row.get('id')}")
        expect(row.get("conflicts") == 0, f"conflict_count:{row.get('id')}")

    activation = load_json(EVIDENCE / "activation-continuation.json")
    expect(activation.get("result") == "pass", "activation_continuation_result")
    expect(activation["continuation"]["global_wait_nodes"] == 0, "activation_global_wait")
    expect(
        activation["continuation"]["dependency_independent_tasks_blocked"] is False,
        "activation_unrelated_block",
    )
    expect(
        activation["continuation"]["real_activation_claimed"] is False,
        "activation_false_claim",
    )
    expect(
        set(activation["states"].values()) <= {"activation_pending", "hazard_blocked"},
        "activation_state_vocabulary",
    )

    validation_text = (EVIDENCE / "taskpack-validations.txt").read_text(encoding="utf-8")
    for required_line in [
        "DAG_VALIDATION=PASS tasks=30 stages=6",
        "TRACEABILITY_VALIDATION=PASS requirements=53 oracles=53 mapped_oracles=53 tasks=30 task_refs=30 gate_refs=6",
        "NO_WAIT_VALIDATION=PASS real_time_soak_nodes=0 credential_wait_nodes=0 fixed_sleep_scripts=0",
        "TASKPACK_VALIDATION=PASS files=81 required_items=16 seven_is_minimum_not_limit=true",
    ]:
        expect(required_line in validation_text, f"recorded_validation:{required_line}")

    baseline_text = (EVIDENCE / "implementation-baseline.md").read_text(encoding="utf-8")
    for required_text in [
        "GO_TO_PG-0",
        "GPL-3.0-only AND AGPL-3.0-only",
        "upstream_clarification_received=false",
        "seven core control files are a minimum",
        "CB-100",
        "not_started",
    ]:
        expect(required_text in baseline_text, f"baseline_text:{required_text}")

    # Task state closes only in default/final mode.
    task_by_id = {row["id"]: row for row in task_state["tasks"]}
    for dependency in ["CB-000", "CB-010", "CB-020", "CB-030"]:
        expect(task_by_id[dependency]["status"] == "passed", f"dependency_state:{dependency}")
    for task_id, row in task_by_id.items():
        if task_id >= "CB-100":
            expect(row["status"] == "not_started", f"future_task_started:{task_id}")
    expect(
        set(task_state["pass_gates"].values()) == {"not_started"},
        "pass_gate_started",
    )
    if baseline_mode:
        expect(task_state["current_run"]["run_id"] == "P0.4", "baseline_current_run")
        expect(task_state["current_run"]["task_id"] == "CB-030", "baseline_current_task")
        expect(task_by_id["CB-040"]["status"] == "not_started", "baseline_cb040_state")
    else:
        expect(task_state["current_run"]["run_id"] == "P0.5", "final_current_run")
        expect(task_state["current_run"]["task_id"] == "CB-040", "final_current_task")
        expect(task_state["current_run"]["status"] == "passed", "final_current_status")
        expect(task_by_id["CB-040"]["status"] == "passed", "final_cb040_state")

        commit_record = load_json(EVIDENCE / "baseline-commit.json")
        commit_sha = commit_record.get("commit_sha", "")
        expect(re.fullmatch(r"[0-9a-f]{40}", commit_sha) is not None, "baseline_commit_format")
        if re.fullmatch(r"[0-9a-f]{40}", commit_sha):
            expect(git("cat-file", "-t", commit_sha, check=False) == "commit", "baseline_commit_object")
            expect(git("rev-parse", f"{commit_sha}^") == BASE_COMMIT, "baseline_commit_parent")
            expect(
                git("rev-parse", f"{commit_sha}^{{tree}}") == commit_record.get("tree_sha"),
                "baseline_commit_tree",
            )
            expect(
                git("show", "-s", "--format=%s", commit_sha) == commit_record.get("subject"),
                "baseline_commit_subject",
            )
            expect(
                git("merge-base", "--is-ancestor", commit_sha, "HEAD", check=False) == "",
                "baseline_commit_not_ancestor",
            )
            commit_paths = sorted(
                filter(
                    None,
                    git(
                        "diff-tree",
                        "--no-commit-id",
                        "--name-only",
                        "-r",
                        commit_sha,
                    ).splitlines(),
                )
            )
            expect(commit_paths == commit_record.get("changed_paths"), "baseline_commit_paths")
            for path in commit_paths:
                expect(allowed_path(path), f"baseline_commit_scope:{path}")
                expect(
                    path not in {
                        "CyberBoss/machine/facts/task_state.json",
                        "CyberBoss/README.md",
                        "CyberBoss/HANDOFF.md",
                        "CyberBoss/CHANGELOG.md",
                        "CyberBoss/docs/evidence/CB-040/baseline-commit.json",
                        "CyberBoss/docs/evidence/CB-040/VALIDATION_REPORT.md",
                    },
                    f"closure_path_in_baseline_commit:{path}",
                )
        expect(commit_record.get("parent_sha") == BASE_COMMIT, "recorded_parent")
        expect(commit_record.get("branch") == EXPECTED_BRANCH, "recorded_branch")
        publication = commit_record.get("remote_publication", {})
        expect(publication.get("state") == "none", "remote_publication_state")
        expect(publication.get("remote_branch_matches") == [], "remote_branch_matches")
        expect(publication.get("open_pull_request_matches") == [], "remote_pr_matches")
        expect(publication.get("remote_tag_matches") == [], "remote_tag_matches")

    if errors:
        for error in sorted(set(errors)):
            print(f"ERROR={error}")
        print("CB040_REPO_VALIDATION=FAIL")
        return 1

    if baseline_mode:
        print(
            "CB040_BASELINE_VALIDATION=PASS "
            "requirements_sampled=10 future_tasks_mapped=25 "
            "unresolved_conflicts=0 remote_writes=0"
        )
    else:
        commit_sha = load_json(EVIDENCE / "baseline-commit.json")["commit_sha"]
        print(
            "CB040_REPO_VALIDATION=PASS "
            f"baseline_commit={commit_sha} requirements_sampled=10 "
            "future_tasks_mapped=25 unresolved_conflicts=0 remote_writes=0"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
