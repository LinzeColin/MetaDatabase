#!/usr/bin/env python3
"""Fail-closed verifier for x2n Stage 0 / Phase 0.5 governance design.

No platform, browser, media, Notion or model action is performed here. Passing
means the design artifacts and synthetic abuse cases are internally complete;
downstream implementation/release acceptances remain NOT_RUN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
COMPETITOR = PROJECT_ROOT / "machine/facts/competitor_registry.json"
PLATFORMS = PROJECT_ROOT / "machine/facts/platform_scope_registry.json"
PLATFORM_POLICY = PROJECT_ROOT / "machine/policy/platform_policy_registry.json"
DECISIONS = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
STOP_KILL = PROJECT_ROOT / "machine/policy/stop_kill_registry.json"
WORKTREE_POLICY = PROJECT_ROOT / "machine/policy/worktree_isolation_policy.json"
FIXTURES = PROJECT_ROOT / "machine/fixtures/stage_0_governance_cases.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
OWNER_SCHEMA = PROJECT_ROOT / "machine/schemas/owner_input_contract.schema.json"
PATH_CONTRACT = PROJECT_ROOT / "machine/facts/path_contract.json"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_0/phase_0_5"
TEMP_COMPETITOR = (
    Path.home()
    / "Downloads"
    / "MediaCrawler"
    / "xhs-douyin-2notion"
    / "runtime"
    / "diagnostics"
    / "source-review-ShilongLee-Crawler-7652073"
)

PHASE_TASK = "TSK.x2n.discovery.005"
PLATFORM_IDS = {"xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"}
NEW_PLATFORM_TASKS = {
    "TSK.x2n.skeleton.006": "PH.X2N.2.3",
    "TSK.x2n.skeleton.007": "PH.X2N.2.4",
    "TSK.x2n.skeleton.008": "PH.X2N.2.5",
    "TSK.x2n.skeleton.009": "PH.X2N.2.6",
    "TSK.x2n.adapters.006": "PH.X2N.3.5",
    "TSK.x2n.adapters.007": "PH.X2N.3.6",
    "TSK.x2n.adapters.008": "PH.X2N.3.7",
    "TSK.x2n.adapters.009": "PH.X2N.3.8",
}
NEW_ACCEPTANCES = {
    "ACC.x2n.capture.003",
    "ACC.x2n.capture.004",
    "ACC.x2n.capture.005",
    "ACC.x2n.capture.006",
    "ACC.x2n.bili.001",
    "ACC.x2n.bili.002",
    "ACC.x2n.ks.001",
    "ACC.x2n.ks.002",
    "ACC.x2n.wb.001",
    "ACC.x2n.wb.002",
    "ACC.x2n.tb.001",
    "ACC.x2n.tb.002",
}


class VerificationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    details: dict[str, Any]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _load_json(path: Path) -> dict[str, Any]:
    _require(path.is_file(), f"missing JSON: {path.relative_to(PROJECT_ROOT) if path.is_relative_to(PROJECT_ROOT) else path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _load_yaml_unique(path: Path) -> dict[str, Any]:
    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_unique_mapping(loader: yaml.SafeLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        loader.flatten_mapping(node)
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            _require(key not in mapping, f"duplicate YAML key in {path.name}: {key}")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_unique_mapping)
    value = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    _require(isinstance(value, dict), f"YAML object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args: list[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, f"git command failed: {' '.join(args)}")
    return result.stdout.rstrip()


def validate_required_artifacts() -> Check:
    required = {
        "docs/governance/RUN_CONTRACT_S00_P05.md",
        "docs/governance/CHANGE_EVENT_S00_P05.md",
        "docs/governance/OWNER_INPUT_CONTRACT.md",
        "docs/governance/PLATFORM_POLICY_REGISTER_S00_P05.md",
        "docs/governance/PARALLEL_WORKTREE_ISOLATION.md",
        "docs/research/COMPETITOR_ANALYSIS_SHILONLEE_CRAWLER.md",
        "docs/architecture/ARCHITECTURE_DECISIONS_S00_P05.md",
        "docs/security/THREAT_MODEL_S00_P05.md",
        "docs/security/STOP_KILL_INCIDENT_REGISTER.md",
        "machine/schemas/owner_input_contract.schema.json",
        "machine/facts/architecture_decisions.json",
        "machine/facts/competitor_registry.json",
        "machine/facts/platform_scope_registry.json",
        "machine/policy/platform_policy_registry.json",
        "machine/policy/stop_kill_registry.json",
        "machine/policy/worktree_isolation_policy.json",
        "machine/fixtures/stage_0_governance_cases.json",
    }
    missing = sorted(relative for relative in required if not (PROJECT_ROOT / relative).is_file())
    _require(not missing, f"Phase 0.5 artifacts missing: {missing}")

    adr_text = (PROJECT_ROOT / "docs/architecture/ARCHITECTURE_DECISIONS_S00_P05.md").read_text(encoding="utf-8")
    adr_ids = re.findall(r"^## (ADR-\d{3})\b", adr_text, flags=re.MULTILINE)
    _require(adr_ids == [f"ADR-{index:03d}" for index in range(1, 11)], "ADR-001..010 must exist exactly once and in order")

    threat = (PROJECT_ROOT / "docs/security/THREAT_MODEL_S00_P05.md").read_text(encoding="utf-8")
    trust_boundaries = re.findall(r"^\| (TB-\d{2}) \|", threat, flags=re.MULTILINE)
    _require(trust_boundaries == [f"TB-{index:02d}" for index in range(1, 11)], "ten trust boundaries required")
    for token in ("Spoofing", "Tampering", "Repudiation", "Information Disclosure", "Denial of Service", "Elevation of Privilege"):
        _require(token in threat, f"STRIDE class missing: {token}")

    policy_doc = (PROJECT_ROOT / "docs/governance/PLATFORM_POLICY_REGISTER_S00_P05.md").read_text(encoding="utf-8")
    for host in ("developer.chrome.com", "developers.notion.com", "open.douyin.com", "openhome.bilibili.com", "open.kuaishou.com", "open.weibo.com", "developer.alibaba.com"):
        _require(host in policy_doc, f"first-party source missing: {host}")
    return Check("required_design_artifacts", "PASS", {"files": len(required), "adrs": 10, "trust_boundaries": 10})


def validate_worktree_isolation_policy() -> Check:
    policy = _load_json(WORKTREE_POLICY)
    _require(policy.get("schema_version") == "1.0", "worktree isolation policy schema drifted")
    _require(policy.get("policy_id") == "POLICY.X2N.WORKTREE_ISOLATION.001", "worktree isolation policy ID drifted")
    _require(policy.get("default_mode") == "require_clean_main", "default main-worktree gate was weakened")
    _require(policy.get("explicit_override_flag") == "--allow-external-main-dirty", "explicit override flag drifted")
    _require(policy.get("override_mode") == "external_main_dirty_zero_project_overlap", "override isolation mode drifted")
    _require(policy.get("project_prefix") == "xhs-douyin-2notion/", "project isolation prefix drifted")
    _require(policy.get("allowed_parent_paths") == ["README.md:single_project_index_rename"], "parent index exception drifted")
    _require(policy.get("transitional_rename_rule") == "legacy_project_prefix_deletions_only_during_owner_approved_short_name_migration", "transitional rename rule drifted")
    _require(policy.get("product_execution_authorized") is False, "isolation policy authorized product execution")
    _require(policy.get("remote_upload_authorized") is False, "isolation policy authorized remote upload")
    required_conditions = set(policy.get("required_conditions", []))
    _require(
        {
            "current_worktree_branch_matches_run",
            "current_worktree_changes_within_project_or_single_parent_index",
            "legacy_project_prefix_entries_are_deletions_only",
            "main_worktree_exists_and_branch_is_main",
            "external_main_dirty_paths_have_zero_current_or_legacy_project_overlap",
            "evidence_records_counts_only_not_external_paths_or_content",
        }.issubset(required_conditions),
        "worktree isolation conditions incomplete",
    )
    forbidden_actions = set(policy.get("forbidden_actions", []))
    _require(
        {
            "modify_external_main_dirty_files",
            "restore_or_stash_external_changes",
            "stage_or_commit_external_changes",
            "copy_external_diff_into_evidence",
            "merge_or_rebase_moving_main_inside_current_phase",
        }.issubset(forbidden_actions),
        "worktree isolation forbidden actions incomplete",
    )
    return Check("worktree_isolation_policy", "PASS", {"default_mode": "require_clean_main", "override_requires_zero_overlap": True})


def validate_taskpack_amendment() -> Check:
    taskpack = _load_yaml_unique(TASKPACK)
    tasks = taskpack.get("tasks", [])
    requirements = [item.get("id") for item in taskpack.get("requirements", [])]
    _require(len(tasks) == 43, "six-platform DAG must contain 43 tasks")
    _require(requirements == [f"REQ.X2N.{index:03d}" for index in range(1, 33)], "REQ.X2N.001-032 registry drifted")
    by_id = {item.get("id"): item for item in tasks}
    _require(len(by_id) == 43 and None not in by_id, "task IDs missing or duplicated")
    for task_id, phase in NEW_PLATFORM_TASKS.items():
        _require(by_id.get(task_id, {}).get("phase") == phase, f"new platform task phase mismatch: {task_id}")
        _require(by_id[task_id].get("status") == "planned", f"future platform task must remain planned: {task_id}")
    _require(by_id[PHASE_TASK].get("status") == "completed", "Phase 0.5 task must be completed")

    stage_counts = {f"STG.X2N.{index}": 0 for index in range(7)}
    for task in tasks:
        stage_counts[task["stage"]] += 1
    _require(stage_counts == {
        "STG.X2N.0": 5, "STG.X2N.1": 5, "STG.X2N.2": 9,
        "STG.X2N.3": 9, "STG.X2N.4": 5, "STG.X2N.5": 5, "STG.X2N.6": 5,
    }, "six-platform stage counts drifted")

    acceptance_ids = set(re.findall(r"^## (ACC\.x2n\.[a-z]+\.\d{3})\b", ACCEPTANCE.read_text(encoding="utf-8"), re.MULTILINE))
    _require(len(acceptance_ids) == 61, "acceptance registry must contain 61 unique IDs")
    _require(NEW_ACCEPTANCES.issubset(acceptance_ids), "new platform acceptances missing")
    for task in tasks:
        task_id = task["id"]
        _require(task.get("acceptance_ids") and set(task["acceptance_ids"]).issubset(acceptance_ids), f"task acceptance trace drifted: {task_id}")
        for field in ("tests", "evidence", "risks", "rollback", "stop_conditions"):
            _require(task.get(field), f"task completion contract missing {field}: {task_id}")

    validation = taskpack.get("validation_contract", {})
    order = validation.get("topological_order", [])
    _require(validation.get("task_count_expected") == 43, "validation task count drifted")
    _require(validation.get("calculated_task_count") == 43 and validation.get("calculated_dag_cycles") == 0, "declared DAG arithmetic drifted")
    _require(len(order) == 43 and len(set(order)) == 43 and set(order) == set(by_id), "topological order coverage drifted")
    position = {task_id: index for index, task_id in enumerate(order)}
    for task in tasks:
        for dependency in task.get("depends_on", []):
            _require(dependency in by_id, f"unknown task dependency: {dependency}")
            _require(position[dependency] < position[task["id"]], f"dependency order invalid: {dependency} -> {task['id']}")

    stage_gates = taskpack.get("stage_gates", [])
    _require([item.get("id") for item in stage_gates] == [f"G{index}" for index in range(7)], "stage gate registry drifted")
    for gate in stage_gates:
        stage = gate.get("after_stage")
        _require(set(gate.get("requires_tasks", [])) == {task["id"] for task in tasks if task["stage"] == stage}, f"stage gate task coverage drifted: {gate.get('id')}")

    effort_totals = {
        key: sum(task.get("effort_hours", {}).get(key, 0) for task in tasks)
        for key in ("low", "likely", "high")
    }
    _require(effort_totals == {"low": 350, "likely": 674, "high": 1288}, "task effort arithmetic drifted")
    return Check("six_platform_taskpack", "PASS", {
        "tasks": 43,
        "requirements": 32,
        "acceptances": 61,
        "stage_counts": stage_counts,
        "dag_cycles": 0,
        "stage_gates": 7,
        "effort_totals": effort_totals,
    })


def validate_platform_and_competitor_policy() -> Check:
    platforms = _load_json(PLATFORMS)
    platform_rows = platforms.get("platforms", [])
    _require({item.get("id") for item in platform_rows} == PLATFORM_IDS, "platform registry must contain exactly six platforms")
    _require(all(item.get("policy_state") == "unknown_disabled" for item in platform_rows), "pre-development platform must remain disabled")
    _require(platforms.get("implementation_started") is False and platforms.get("real_platform_calls") is False, "platform implementation/execution overstated")
    constraints = set(platforms.get("common_constraints", []))
    required_constraints = {
        "no_automatic_scrolling", "no_account_state_change", "no_access_control_bypass",
        "no_proxy_rotation_or_fingerprint_simulation", "no_credentials_or_cookie_persistence",
        "no_platform_cdn_url_or_raw_media_persistence",
    }
    _require(required_constraints.issubset(constraints), "platform constraints incomplete")

    policy = _load_json(PLATFORM_POLICY)
    _require(policy.get("default") == "deny" and policy.get("unknown_means") == "unknown_disabled", "policy is not deny-by-default")
    _require(set(policy.get("platform_states", {})) == PLATFORM_IDS, "policy platform set drifted")
    _require(set(policy.get("platform_states", {}).values()) == {"unknown_disabled"}, "a platform was prematurely enabled")
    official_sources = policy.get("official_sources", {})
    _require(set(official_sources) == PLATFORM_IDS | {"chrome", "notion"}, "official-source registry coverage drifted")
    _require(all(values and all(value.startswith("https://") for value in values) for values in official_sources.values()), "official-source registry contains empty or non-HTTPS entries")
    forbidden = set(policy.get("forbidden_methods", []))
    for method in ("automatic_scrolling", "captcha_or_access_control_bypass", "proxy_rotation_or_geo_rate_bypass", "cookie_export_ingest_log_or_persistence", "arbitrary_url_proxy"):
        _require(method in forbidden, f"forbidden method missing: {method}")

    competitor = _load_json(COMPETITOR)
    rows = competitor.get("competitors", [])
    _require(len(rows) == 1 and rows[0].get("id") == "ShilongLee-Crawler", "competitor registry mismatch")
    item = rows[0]
    _require(item.get("selected_commit") == "765207310a90a81c615c0ba2df124543b424af89", "competitor pin mismatch")
    _require(item.get("tree") == "3fe084d7e3835669ccdb4193312b065a48eeb5d7", "competitor tree mismatch")
    for digest in item.get("file_hashes", {}).values():
        _require(re.fullmatch(r"[0-9a-f]{64}", digest or "") is not None, "invalid competitor SHA-256")
    _require(item.get("observed_metrics") == {
        "non_git_files": 177,
        "content_and_account_routes": 56,
        "proxy_routes": 5,
        "total_routes": 61,
        "pinned_requirement_lines": 46,
    }, "competitor audit metrics drifted")
    _require(item.get("history_observation") == {
        "latest_substantive_code_commit_observed": "e3490ea66a93778ffd91d1bc002dc69bdf4df313",
        "latest_substantive_code_date_observed": "2024-10-16",
        "later_history_pattern": "primarily_readme_sponsorship_or_promotion_changes",
        "scope": "fixed_commit_history_only_not_future_prediction",
    }, "competitor history observation drifted")
    _require(item.get("license", {}).get("commercial_use_allowed") is False, "competitor commercial restriction weakened")
    _require(item.get("license", {}).get("code_copy_allowed_in_x2n") is False, "competitor code copy allowed")
    integration = item.get("integration", {})
    _require(integration == {
        "enabled": False,
        "bundled": False,
        "runtime_dependency": False,
        "vendored_files": 0,
        "mode": "research_only_excluded",
    }, "competitor integration boundary drifted")
    _require(competitor.get("restricted_research_boundary") == {
        "sources": ["ShilongLee-Crawler", "MediaCrawler"],
        "product_adapter_allowed": False,
        "installation_allowed": False,
        "execution_allowed": False,
        "output_ingest_allowed": False,
        "runtime_dependency_allowed": False,
        "vendoring_allowed": False,
        "prior_phase_audit_is_historical_evidence_only": True,
        "future_change_requires": "new_owner_change_event_and_independent_license_policy_run",
    }, "restricted upstream research boundary drifted")
    _require(competitor.get("actual_runtime_dependencies") == [] and competitor.get("code_copies") == 0, "competitor entered runtime or source tree")
    return Check("platform_and_competitor_policy", "PASS", {
        "platforms": 6,
        "all_disabled": True,
        "competitor_code_copies": 0,
        "competitor_routes_observed": 61,
    })


def validate_architecture_and_stop_kill() -> Check:
    decisions = _load_json(DECISIONS)
    rows = decisions.get("decisions", [])
    _require([item.get("id") for item in rows] == [f"ADR-{index:03d}" for index in range(1, 11)], "decision registry mismatch")
    _require(decisions.get("status") == "accepted_design_not_implemented", "design status overstated")
    _require(decisions.get("implementation_started") is False and decisions.get("real_account_execution") is False, "implementation/account state overstated")
    _require(decisions.get("stage_gate") == "not_run", "Stage gate changed")

    stop_kill = _load_json(STOP_KILL)
    rules = stop_kill.get("rules", [])
    _require([item.get("id") for item in rules] == [f"SK-X2N-{index:03d}" for index in range(1, 21)], "stop/kill registry must contain SK-X2N-001..020")
    _require(len({item.get("id") for item in rules}) == 20, "duplicate stop/kill ID")
    return Check("architecture_and_stop_kill", "PASS", {"adrs": 10, "stop_kill_rules": 20, "stage_gate": "NOT_RUN"})


def validate_synthetic_cases() -> Check:
    fixture = _load_json(FIXTURES)
    manifest = _load_json(FIXTURE_MANIFEST)
    _require(fixture.get("synthetic_only") is True, "governance fixture is not synthetic-only")
    _require(fixture.get("real_accounts") is False and fixture.get("real_media") is False, "real input entered governance fixture")
    cases = fixture.get("cases", [])
    _require(len(cases) >= 40, "at least 40 synthetic governance cases required")
    ids = [item.get("id") for item in cases]
    _require(ids == [f"GOV-{index:03d}" for index in range(1, len(cases) + 1)], "synthetic case IDs must be contiguous")
    _require(len(ids) == len(set(ids)), "duplicate synthetic case ID")
    rows = manifest.get("fixtures", [])
    _require(len(rows) == 1 and rows[0].get("path") == "machine/fixtures/stage_0_governance_cases.json", "synthetic fixture manifest path drifted")
    _require(rows[0].get("case_count") == len(cases) == 50, "synthetic fixture count drifted")
    by_id = {item["id"]: item for item in cases}
    _require(by_id["GOV-049"].get("expected_decision") == "incident_delete_clone_rotate_or_prove_expiry", "credentialed remote incident case missing")
    _require(by_id["GOV-050"].get("expected_decision") == "reject_product_adapter", "restricted crawler isolation case missing")
    categories = {item.get("category") for item in cases}
    _require({"platform", "batch", "network", "media", "ipc", "privacy", "ai", "license", "release"}.issubset(categories), "synthetic category coverage incomplete")
    rendered = json.dumps(fixture, ensure_ascii=False)
    for pattern in (re.escape("/" + "Users/"), r"https?://", r"(?i)bearer\s+", r"(?i)(?:cookie|token)\s*[:=]", r"(?i)(?:xhs.?cdn|douyin.?vod|byteimg|pstatp)"):
        _require(re.search(pattern, rendered) is None, f"sensitive/real-shaped fixture value matched: {pattern}")
    return Check("synthetic_governance_cases", "PASS", {"cases": len(cases), "categories": len(categories), "real_inputs": 0})


def validate_task_state() -> Check:
    project = _load_json(PROJECT_FACT)
    _require(project.get("name") == "xhs-douyin-2notion" and project.get("project_path") == "xhs-douyin-2notion/", "project identity drifted")
    _require(project.get("parent_repository") == "LinzeColin/MetaDatabase", "parent repository drifted")
    _require(project.get("runtime_root_ref") == "X2N_DATA_ROOT" and project.get("downloads_root_ref") == "X2N_DATA_ROOT", "runtime/download root drifted")
    _require(project.get("download_destination_ref") == "X2N_DOWNLOAD_DESTINATION", "download destination reference missing")
    _require(project.get("download_destination_required_basename") == "MediaCrawler", "download destination drifted")
    _require(project.get("data_root_namespace") == "xhs-douyin-2notion", "private namespace drifted")
    _require(project.get("source_taskpack_absolute_path_status") == "unspecified_owner_resolved", "original taskpack path gap not recorded")
    _require(project.get("platform_scope") == ["xiaohongshu", "douyin", "bilibili", "kuaishou", "weibo", "taobao"], "project platform scope drifted")
    _require(project.get("status") == "stage_0_review_complete_g0_blocked_owner_action", "project readiness status is not the reviewed state")
    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.1", "task_state schema is not the Stage Review schema")
    _require(state.get("last_completed_phase") == "PH.X2N.0.5", "last completed Phase drifted")
    _require(state.get("review_id") == "STG.X2N.0.REVIEW" and state.get("run_id") == "RUN-X2N-S00-REVIEW", "current task state is not Stage 0 Review")
    _require(state.get("run_kind") == "stage_review_no_new_dag_task", "Stage Review scope is ambiguous")
    _require(state.get("state") == "review_complete_gate_blocked", "Stage Review state is not finalized")
    _require(state.get("tasks", {}).get(PHASE_TASK) == "pass", "Phase 0.5 task not pass")
    acceptances = state.get("acceptance_status", {})
    _require(acceptances.get("ACC.x2n.gov.003") == "pass_current_artifact_scope", "governance acceptance status mismatch")
    _require(acceptances.get("ACC.x2n.media.003") == "design_fixture_pass_downstream_not_run", "media acceptance overstated")
    _require(acceptances.get("ACC.x2n.rel.003") == "design_supply_chain_pass_downstream_not_run", "release acceptance overstated")
    _require(state.get("blocking_followups") == [{
        "id": "INC-X2N-S00-P05-001",
        "scope": "before_g0_pass",
        "status": "owner_action_pending",
        "action": "rotate_or_prove_expiry_of_credential_used_by_temporary_source_remote",
    }], "contained credential follow-up missing or weakened")
    _require(state.get("next_phase") is None and state.get("next_run") == "STG.X2N.0.REVIEW.RESUME", "Stage review resume routing mismatch")
    _require(state.get("next_phase_authorized") is False and state.get("stage_1_authorized") is False, "Stage 1 was auto-authorized")
    _require(state.get("stage_gate") == "blocked_owner_action" and state.get("remote_upload") == "forbidden_until_g0_pass", "Stage/upload gate weakened")
    return Check("phase_task_state", "PASS", {"task": PHASE_TASK, "stage_gate": "BLOCKED_OWNER_ACTION", "next": "STG.X2N.0.REVIEW.RESUME"})


def validate_owner_input(root: Path) -> Check:
    root = root.expanduser().resolve()
    contract = _load_json(PATH_CONTRACT)
    _require(root.name == contract.get("required_basename"), "private root basename mismatch")
    _require(contract.get("external_research_directory_scope") == "temporary_anonymous_source_audit_only_no_execution_or_product_output", "external research directory scope drifted")
    owner_file = root / "runtime/owner_input_contract.local.json"
    _require(owner_file.is_file() and not owner_file.is_symlink(), "private owner input file missing")
    _require(stat.S_IMODE(owner_file.stat().st_mode) == 0o600, "private owner input must be 0600")
    owner = _load_json(owner_file)
    schema = _load_json(OWNER_SCHEMA)
    required = set(schema.get("required", []))
    _require(required.issubset(owner), f"owner input missing keys: {sorted(required - set(owner))}")
    _require(owner.get("schema_version") == "1.0" and owner.get("project") == "x2n", "owner input identity mismatch")
    _require(owner.get("input_state") == "conservative_defaults", "owner defaults unexpectedly unlocked")
    _require(owner.get("environment") == {"os_strategy": "auto_detect", "hardware_strategy": "auto_detect", "detected_snapshot": "not_run"}, "environment defaults mismatch")
    _require(set(owner.get("platforms", {})) == PLATFORM_IDS, "owner platform set mismatch")
    for value in owner["platforms"].values():
        _require(value == {"login_state": "not_run", "real_execution_authorized": False}, "real platform execution enabled")
    _require(owner.get("first_sync") == "disabled_synthetic_only", "first sync enabled")
    _require(owner.get("taxonomy") == {"top_level_categories": ["Unclassified"], "ai_may_create_top_level": False}, "taxonomy defaults unsafe")
    _require(owner.get("notion") == {"enabled": False, "credential_reference": "unset", "parent_reference": "unset"}, "Notion defaults unsafe")
    _require(owner.get("models") == {"cloud_enabled": False, "monthly_budget": 0, "currency": "AUD"}, "model defaults unsafe")
    _require(owner.get("gold_set") == "synthetic_only", "private Gold Set unexpectedly claimed")
    media = owner.get("media_retention", {})
    _require(media == {"success": "delete_immediately", "failure_max_hours": 24, "persist_platform_cdn_urls": False, "persist_raw_media": False}, "media retention defaults unsafe")
    rendered = owner_file.read_text(encoding="utf-8")
    for pattern in (r"https?://", re.escape("/" + "Users/"), r"(?i)bearer\s+", r"(?i)(?:cookie|token)\s*[:=]"):
        _require(re.search(pattern, rendered) is None, f"owner input contains forbidden value: {pattern}")
    marker = _load_json(root / contract["private_marker"])
    _require(marker.get("real_data_state") == "stage_0_owner_input_defaults_no_content", "private marker state mismatch")
    _require(marker.get("product_execution_authorized") is False, "private marker enabled execution")
    return Check("private_owner_input", "PASS", {"platforms": 6, "real_accounts": 0, "external_integrations_enabled": 0})


def _porcelain_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _scope_status(status: str) -> tuple[bool, int]:
    legacy_name = "xiao" + "hongshu-douyin-2notion"
    legacy_deletions = 0
    for line in status.splitlines():
        if not line:
            continue
        path = _porcelain_paths(line)[0]
        if path == "README.md" or path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/"):
            continue
        if (path == legacy_name or path.startswith(f"{legacy_name}/")) and "D" in line[:2]:
            legacy_deletions += 1
            continue
        return False, legacy_deletions
    return True, legacy_deletions


def _validate_parent_index_diff(diff: str) -> None:
    legacy_name = "xiao" + "hongshu-douyin-2notion"
    changed_lines = [
        line
        for line in diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    _require(len(changed_lines) == 2, "parent README change must be one project-index rename")
    removed, added = changed_lines
    _require(removed.startswith(f"-| {legacy_name} |"), "parent README removed line is not the legacy project index")
    _require(added.startswith("+| xhs-douyin-2notion |"), "parent README added line is not the owner-approved project index")
    _require(removed[1:].replace(legacy_name, "xhs-douyin-2notion", 1) == added[1:], "parent README change modified more than the project name")


def _evaluate_main_isolation(changed_paths: list[str], allow_external_main_dirty: bool) -> dict[str, Any]:
    legacy_name = "xiao" + "hongshu-douyin-2notion"
    overlap_count = sum(
        path == "xhs-douyin-2notion"
        or path.startswith("xhs-douyin-2notion/")
        or path == legacy_name
        or path.startswith(f"{legacy_name}/")
        for path in changed_paths
    )
    _require(overlap_count == 0, "MetaDatabase main worktree changes overlap the x2n project")
    _require(allow_external_main_dirty or not changed_paths, "MetaDatabase main worktree is dirty")
    return {
        "main_worktree_clean": not changed_paths,
        "isolation_mode": "strict_main_clean" if not changed_paths else "external_main_dirty_zero_project_overlap",
        "external_main_dirty_paths": len(changed_paths),
        "project_overlap_paths": overlap_count,
    }


def validate_worktree_scope(allow_external_main_dirty: bool = False) -> Check:
    branch = _git(["branch", "--show-current"])
    _require(
        branch in {
            "codex/xhs-douyin-2notion-v0001-s00-p05",
            "codex/xhs-douyin-2notion-v0001-s00-review",
        },
        "wrong Phase 0.5-compatible branch",
    )
    status = _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    changed = _porcelain_paths(status)
    scope_allowed, legacy_deletions = _scope_status(status)
    _require(scope_allowed, "changed scope escaped project")
    if "README.md" in changed:
        _validate_parent_index_diff(_git(["diff", "HEAD", "--unified=0", "--no-color", "--", "README.md"]))
    blocks = _git(["worktree", "list", "--porcelain"]).split("\n\n")
    main_path: Path | None = None
    for block in blocks:
        fields = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in fields if line.startswith("worktree ")), None)
        branch_field = next((line for line in fields if line.startswith("branch ")), None)
        if worktree and branch_field == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None, "MetaDatabase main worktree is missing")
    _require(_git(["branch", "--show-current"], main_path) == "main", "main worktree is not on main")
    main_status = _git(
        ["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        main_path,
    )
    isolation = _evaluate_main_isolation(_porcelain_paths(main_status), allow_external_main_dirty)
    return Check(
        "worktree_scope",
        "PASS",
        {"branch": branch, "changed_paths": len(changed), "legacy_project_deletions": legacy_deletions, **isolation},
    )


def validate_temp_cleanup() -> Check:
    _require(not TEMP_COMPETITOR.exists(), "temporary competitor source review still exists")
    return Check("temporary_competitor_cleanup", "PASS", {"remaining_entries": 0, "source_retained": False})


def run_core_checks() -> list[Check]:
    return [
        validate_required_artifacts(),
        validate_taskpack_amendment(),
        validate_platform_and_competitor_policy(),
        validate_architecture_and_stop_kill(),
        validate_synthetic_cases(),
        validate_worktree_isolation_policy(),
        validate_task_state(),
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_evidence(checks: list[Check]) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    common = {
        "schema_version": "1.0",
        "project": "x2n",
        "stage": "STG.X2N.0",
        "phase": "PH.X2N.0.5",
        "run_id": "RUN-X2N-S00-P05",
        "generated_at": now,
        "git_base_commit": _git(["rev-parse", "HEAD"]),
        "product_code": "NOT_STARTED",
        "real_account_execution": "NOT_RUN",
        "platform_calls": "NOT_RUN",
        "stage_gate": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_STAGE_GATE",
        "redaction": {"private_content_included": False, "secrets_included": False, "cdn_urls_included": False},
    }
    verification = dict(common)
    verification.update({
        "status": "PASS",
        "checks": [check.__dict__ for check in checks],
        "owner_route": {
            "parent_repository": "LinzeColin/MetaDatabase",
            "project_path": "xhs-douyin-2notion/",
            "source_taskpack_absolute_path": "UNSPECIFIED_OWNER_RESOLVED",
            "data_root_ref": "X2N_DATA_ROOT",
            "download_destination_ref": "X2N_DOWNLOAD_DESTINATION",
            "data_root_namespace": "xhs-douyin-2notion",
            "existing_destination_entries_touched": 0,
            "existing_destination_metadata_audit": "AGGREGATE_COUNT_AND_FINGERPRINT_ONLY",
            "destination_name_semantics": "STORAGE_PARENT_ONLY_NO_UPSTREAM_AUTHORIZATION",
        },
        "hashes": {
            "competitor_registry": _sha256(COMPETITOR),
            "platform_scope_registry": _sha256(PLATFORMS),
            "platform_policy_registry": _sha256(PLATFORM_POLICY),
            "architecture_decisions": _sha256(DECISIONS),
            "stop_kill_registry": _sha256(STOP_KILL),
            "synthetic_cases": _sha256(FIXTURES),
        },
        "acceptance_status": {
            "ACC.x2n.gov.003": "PASS_CURRENT_ARTIFACT_SCOPE",
            "ACC.x2n.media.003": "DESIGN_FIXTURE_PASS_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.rel.003": "DESIGN_SUPPLY_CHAIN_PASS_DOWNSTREAM_NOT_RUN",
        },
    })
    _write_json(EVIDENCE_DIR / "verification.json", verification)

    task = dict(common)
    task.update({"task_id": PHASE_TASK, "task_status": "PASS", "outputs_verified": True, "downstream_product_acceptance": "NOT_RUN"})
    _write_json(EVIDENCE_DIR / f"{PHASE_TASK}.json", task)

    statuses = {
        "ACC.x2n.gov.003": "PASS_CURRENT_ARTIFACT_SCOPE",
        "ACC.x2n.media.003": "DESIGN_FIXTURE_PASS_DOWNSTREAM_NOT_RUN",
        "ACC.x2n.rel.003": "DESIGN_SUPPLY_CHAIN_PASS_DOWNSTREAM_NOT_RUN",
    }
    for acceptance_id, status in statuses.items():
        receipt = dict(common)
        receipt.update({"acceptance_id": acceptance_id, "status": status, "implementation_or_release_oracle": "NOT_RUN"})
        _write_json(EVIDENCE_DIR / f"{acceptance_id}.json", receipt)

    cleanup = dict(common)
    cleanup.update({"status": "PASS", "temporary_source": "ShilongLee/Crawler", "remaining_entries": 0})
    _write_json(EVIDENCE_DIR / "cleanup.json", cleanup)

    incident = dict(common)
    incident.update({
        "incident_id": "INC-X2N-S00-P05-001",
        "trigger": "credential_shaped_remote_url_in_temporary_read_only_clone",
        "status": "CONTAINED_OWNER_ACTION_PENDING",
        "actions": [
            "temporary_clone_deleted",
            "scoped_repository_and_private_root_file_scan_zero",
        ],
        "credential_value_in_evidence": False,
        "affected_product_or_runtime_files": 0,
        "owner_action_required": "rotate_or_prove_expiry_before_G0",
        "recovery_gate": "owner_reauthentication_or_expiry_evidence_and_stage_review",
    })
    _write_json(EVIDENCE_DIR / "INC-X2N-S00-P05-001.json", incident)


def validate_evidence() -> Check:
    expected = {
        "verification.json",
        f"{PHASE_TASK}.json",
        "ACC.x2n.gov.003.json",
        "ACC.x2n.media.003.json",
        "ACC.x2n.rel.003.json",
        "cleanup.json",
        "INC-X2N-S00-P05-001.json",
    }
    actual = {path.name for path in EVIDENCE_DIR.glob("*.json")}
    _require(actual == expected, f"Phase 0.5 evidence file set mismatch: {sorted(actual)}")
    verification = _load_json(EVIDENCE_DIR / "verification.json")
    _require(verification.get("status") == "PASS" and verification.get("stage_gate") == "NOT_RUN", "verification evidence overstated")
    _require(verification.get("remote_upload") == "FORBIDDEN_UNTIL_STAGE_GATE", "upload gate weakened in evidence")
    _require(verification.get("acceptance_status", {}).get("ACC.x2n.media.003") == "DESIGN_FIXTURE_PASS_DOWNSTREAM_NOT_RUN", "media evidence overstated")
    _require(verification.get("owner_route") == {
        "parent_repository": "LinzeColin/MetaDatabase",
        "project_path": "xhs-douyin-2notion/",
        "source_taskpack_absolute_path": "UNSPECIFIED_OWNER_RESOLVED",
        "data_root_ref": "X2N_DATA_ROOT",
        "download_destination_ref": "X2N_DOWNLOAD_DESTINATION",
        "data_root_namespace": "xhs-douyin-2notion",
        "existing_destination_entries_touched": 0,
        "existing_destination_metadata_audit": "AGGREGATE_COUNT_AND_FINGERPRINT_ONLY",
        "destination_name_semantics": "STORAGE_PARENT_ONLY_NO_UPSTREAM_AUTHORIZATION",
    }, "owner project/download route evidence mismatch")
    worktree_checks = [item for item in verification.get("checks", []) if item.get("name") == "worktree_scope"]
    _require(len(worktree_checks) == 1, "worktree isolation evidence missing or duplicated")
    worktree_details = worktree_checks[0].get("details", {})
    _require(worktree_details.get("project_overlap_paths") == 0, "worktree evidence reports project overlap")
    _require(isinstance(worktree_details.get("external_main_dirty_paths"), int), "worktree evidence must record only an aggregate dirty-path count")
    _require("external_main_paths" not in worktree_details and "external_paths" not in worktree_details, "worktree evidence leaked external paths")
    incident = _load_json(EVIDENCE_DIR / "INC-X2N-S00-P05-001.json")
    _require(incident.get("status") == "CONTAINED_OWNER_ACTION_PENDING", "credential incident state overstated")
    _require(incident.get("credential_value_in_evidence") is False and incident.get("affected_product_or_runtime_files") == 0, "credential incident evidence is unsafe or inaccurate")
    _require(incident.get("owner_action_required") == "rotate_or_prove_expiry_before_G0", "credential incident recovery gate missing")
    return Check("evidence_receipts", "PASS", {"files": len(actual), "stage_gate": "NOT_RUN"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--validate-owner-input", type=Path)
    parser.add_argument("--verify-temp-cleanup", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        _require(not args.allow_external_main_dirty or args.verify_worktree, "--allow-external-main-dirty requires --verify-worktree")
        checks = run_core_checks()
        if args.validate_owner_input:
            checks.append(validate_owner_input(args.validate_owner_input))
        if args.verify_worktree:
            checks.append(validate_worktree_scope(args.allow_external_main_dirty))
        if args.verify_temp_cleanup:
            checks.append(validate_temp_cleanup())
        if args.write_evidence:
            write_evidence(checks)
            checks.append(validate_evidence())
        elif args.require_evidence:
            checks.append(validate_evidence())
        print(json.dumps({
            "status": "PASS",
            "phase": "PH.X2N.0.5",
            "checks": [check.__dict__ for check in checks],
            "product_code": "NOT_STARTED",
            "real_account_execution": "NOT_RUN",
            "stage_gate": "BLOCKED_OWNER_ACTION",
            "phase_evidence_stage_gate": "NOT_RUN",
            "remote_upload": "FORBIDDEN_UNTIL_G0_PASS",
        }, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, VerificationError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
