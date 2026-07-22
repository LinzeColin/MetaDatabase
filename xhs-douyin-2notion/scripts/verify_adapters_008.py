#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.008."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
PREVIOUS_SPEC = importlib.util.spec_from_file_location(
    "verify_adapters_007_for_adapters_008",
    PROJECT_ROOT / "scripts/verify_adapters_007.py",
)
assert PREVIOUS_SPEC and PREVIOUS_SPEC.loader
PREVIOUS = importlib.util.module_from_spec(PREVIOUS_SPEC)
sys.modules[PREVIOUS_SPEC.name] = PREVIOUS
PREVIOUS_SPEC.loader.exec_module(PREVIOUS)

VerificationError = PREVIOUS.VerificationError
Check = PREVIOUS.Check
_require = PREVIOUS._require
_load_json = PREVIOUS._load_json
_read_blob_at = PREVIOUS._read_blob_at
_git = PREVIOUS._git
_porcelain_paths = PREVIOUS._porcelain_paths
_project_relative = PREVIOUS._project_relative
_task_block = PREVIOUS._task_block
_field = PREVIOUS._field
_list_field = PREVIOUS._list_field
_iter_files = PREVIOUS._iter_files
_isolated_env = PREVIOUS._isolated_env
_run_external = PREVIOUS._run_external
_json_line = PREVIOUS._json_line

TASK_ID = "TSK.x2n.adapters.008"
RUN_ID = "RUN-X2N-S03-A008"
PHASE = "PH.X2N.3.7"
BRANCH = "codex/xhs-douyin-2notion-v0001-s03-adapters008"
TASK_BASE_COMMIT = "a088ea8787acf5b4b2f358317135b089054f1160"
ORIGIN_CUTOFF = PREVIOUS.ORIGIN_CUTOFF

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_008.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
POLICY = PROJECT_ROOT / "machine/policy/weibo_selected_collection_policy.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/weibo_selected/fixture_manifest.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
COMPANION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/weibo_selected.py"
COMPANION_TEST = PROJECT_ROOT / "apps/companion/tests/test_weibo_selected.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
CHAOS_WORKER = PROJECT_ROOT / "scripts/weibo_selected_chaos_worker.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_008_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.008.json"

UNCHANGED_SECURITY_SURFACES = (
    PROJECT_ROOT / "apps/extension/manifest.json",
    PROJECT_ROOT / "apps/extension/src/service-worker.js",
    PROJECT_ROOT / "apps/extension/src/weibo-current-page.js",
    PROJECT_ROOT / "apps/companion/native-host/policy.json",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "machine/policy/weibo_current_page_policy.json",
    PROJECT_ROOT / "package-lock.json",
    PROJECT_ROOT / "uv.lock",
    PREVIOUS.EVIDENCE,
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/src/x2n_companion/weibo_selected.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_weibo_selected.py",
    "docs/governance/RUN_CONTRACT_S03_ADAPTERS_008.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.adapters.008.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/weibo_selected_collection_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/weibo_selected_chaos_worker.py",
    "scripts/run_adapters_008_acceptance.py",
    "scripts/verify_adapters_007.py",
    "scripts/verify_adapters_008.py",
    "tests/test_adapters_007.py",
    "tests/test_adapters_008.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/adapters/v1/weibo_selected/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    committed = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...HEAD"]).splitlines()
    working = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    relative_changes: list[str] = []
    for path in sorted(set(committed + working)):
        relative = _project_relative(path)
        _require(relative is not None, "Adapters008 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Adapters008 change: {relative}",
        )
        relative_changes.append(relative)

    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "/" + "Users/",
        "github" + "_pat_",
        "Bearer" + " ",
    )
    private_path_pattern = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+/")
    cdn_names = "|".join(
        (
            "xhs" + "cdn",
            "douyin" + "vod",
            "byte" + "img",
            "pstatp",
            "bili" + "video",
            "hdslb",
            "ks" + "cdn",
            "yx" + "imgs",
            "sina" + "img",
            "tb" + "cdn",
            r"(?:img|gw|video|vod|pic|media)\.ali" + "cdn",
        )
    )
    cdn_pattern = re.compile(rf"https?://[^\s'\"]*(?:{cdn_names})", flags=re.IGNORECASE)
    files = list(_iter_files())
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(not any(token in text for token in forbidden_tokens), "private or credential token entered x2n")
        _require(private_path_pattern.search(text) is None, "local user path entered x2n")
        _require(cdn_pattern.search(text) is None, "platform media CDN URL entered x2n")
    forbidden_suffixes = {
        ".sqlite",
        ".sqlite3",
        ".db",
        ".mp4",
        ".mov",
        ".m4a",
        ".mp3",
        ".wav",
        ".webm",
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".heic",
        ".pem",
        ".p12",
        ".pfx",
    }
    _require(
        not any(path.suffix.lower() in forbidden_suffixes for path in files),
        "private Runtime artifact entered x2n",
    )
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {
            "changed_files": len(relative_changes),
            "local_path_findings": 0,
            "out_of_scope_writes": 0,
            "runtime_artifacts": 0,
            "sensitive_or_media_url_hits": 0,
            "text_files_scanned": len(files),
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Adapters008 worktree branch")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Adapters008 branch no longer descends from Adapters007",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the Stage 2 cutoff",
    )
    origin_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{ORIGIN_CUTOFF}..{live_origin}"]
    ).splitlines()
    origin_overlap = sum(
        path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in origin_paths
    )
    _require(origin_overlap == 0, "origin/main changed x2n after the Stage 2 cutoff")
    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(["branch", "--show-current"], main_path) == "main", "main unavailable")
    main_paths = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], main_path)
    )
    main_overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in main_paths)
    _require(main_overlap == 0, "MetaDatabase main dirty state overlaps x2n")
    _require(allow_external_main_dirty or not main_paths, "MetaDatabase main worktree is dirty")
    return Check(
        "worktree_isolation",
        "PASS",
        {
            "branch": BRANCH,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": main_overlap,
        },
    )


def validate_predecessor() -> Check:
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Adapters007 final pin differs from Adapters008 base")
    _require(
        PREVIOUS.EVIDENCE.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, PREVIOUS.EVIDENCE),
        "Adapters007 evidence was rewritten",
    )
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Adapters007 historical regression failed")
    PREVIOUS.verify_evidence()
    return Check(
        "adapters_007_fixed_predecessor",
        "PASS",
        {"evidence_mutations": 0, "historical_checks": len(checks) + 1, "predecessor_commit": TASK_BASE_COMMIT},
    )


def validate_task_and_state() -> Check:
    taskpack_text = TASKPACK.read_text(encoding="utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Adapters008 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.3" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.adapters.001", "TSK.x2n.skeleton.008", "TSK.x2n.skeleton.004"],
        "Adapters008 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.wb.001", "ACC.x2n.wb.002", "ACC.x2n.batch.001"],
        "Adapters008 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    for future in ("TSK.x2n.adapters.009", "TSK.x2n.adapters.005"):
        _require(
            _task_block(taskpack_text, future) == _task_block(base_taskpack, future),
            f"{future} was entered by this Run",
        )
    taskpack = yaml.safe_load(taskpack_text)
    _require(isinstance(taskpack, dict), "Task Pack root must be an object")
    _require(
        taskpack.get("project", {}).get("status") == "STAGE_3_ADAPTERS_008_PASS_G3_NOT_RUN",
        "Task Pack status drifted",
    )
    authorization = taskpack.get("authorization", {})
    _require(
        authorization.get("stage_3_task_start") is True
        and authorization.get("real_account_execution") is False
        and authorization.get("public_release") is False,
        "Task Pack authorization drifted",
    )
    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.25", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.3" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Adapters008 state is not pass")
    _require("TSK.x2n.adapters.009" not in state.get("tasks", {}), "Adapters009 state was entered")
    _require("TSK.x2n.adapters.005" not in state.get("tasks", {}), "Adapters005 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.3.8" and state.get("next_run") == "TSK.x2n.adapters.009",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g3_pass",
        "G3/upload state overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.wb.001")
        == "pass_ci_synth_official_current_user_favorites_20_of_20_favorited_scan_confirmed_fake_like_saved_current_0_budget_zero_price_quota_unknown_owner_canary_not_run_production_disabled",
        "Weibo completeness Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.wb.002")
        == "pass_ci_synth_50_process_kills_lost_duplicate_0_auth_oauth_budget_policy_platform_kill_4_http_429_retry_after_120_early_resume_blocked_auto_retry_proxy_rotation_0",
        "Weibo Kill Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.batch.001")
        == "pass_ci_synth_8_non_authoritative_removed_0_adapter008_physical_content_delete_0_authorization_cleanup_required_1_reconciliation_downstream_not_run",
        "batch Acceptance drifted",
    )
    _require(
        state.get("weibo_selected_execution")
        == "pass_ci_synth_official_current_user_favorites_contract_only_20_favorited_scan_confirmed_50_process_kills_budget_quota_authorization_and_429_gated_real_transport_owner_canary_not_run",
        "Weibo execution boundary drifted",
    )
    for field in (
        "owner_profile_login",
        "owner_canary",
        "real_account_execution",
        "platform_calls",
        "model_calls",
        "media_processing",
    ):
        _require(state.get(field) == "not_run", f"external execution overstated: {field}")
    _require(
        _load_json(PROJECT_FACT).get("status") == "stage_3_adapters_008_pass_g3_not_run",
        "project status drifted",
    )
    architecture = _load_json(ARCHITECTURE_FACT)
    _require(
        architecture.get("phase") == PHASE
        and architecture.get("stage_gate") == "g3_not_run"
        and architecture.get("real_account_execution") is False,
        "architecture state drifted",
    )
    contract = RUN_CONTRACT.read_text(encoding="utf-8")
    for value in (
        TASK_ID,
        RUN_ID,
        PHASE,
        TASK_BASE_COMMIT,
        BRANCH,
        "GET /2/favorites.json",
        "Retry-After",
        "PASS_CI_SYNTH_SCOPED",
        "NOT_RUN",
    ):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 3,
            "next_task": "TSK.x2n.adapters.009",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
            "stage_gate": "G3_NOT_RUN",
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json(POLICY)
    flags = policy.get("feature_gate", {})
    _require(
        policy.get("policy_id") == "POLICY.X2N.WEIBO-SELECTED.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("reviewed_at") == "2026-07-23"
        and policy.get("default") == "deny"
        and flags.get("ci_synthetic_contract_enabled") is True
        and flags.get("owner_canary_enabled") is False
        and flags.get("production_enabled") is False
        and flags.get("platform_requests") is False,
        "Weibo policy identity or gate drifted",
    )
    capability = policy.get("official_capability", {})
    _require(
        capability.get("supported_contract_shape") == "current_authorized_user_favorites"
        and capability.get("documented_endpoint") == "GET /2/favorites.json"
        and capability.get("documented_access_level") == "ordinary_interface_with_frequency_limit"
        and capability.get("oauth_access_token_required") is True
        and capability.get("application_interface_permission_required") is True
        and capability.get("owner_oauth_required") is True
        and capability.get("selected_count_in_this_contract") == 20
        and capability.get("current_application_access") == "unknown_disabled"
        and capability.get("canonical_public_route_attested") is False
        and capability.get("likes_list_capability") == "unknown_disabled"
        and capability.get("inference_not_claim_of_nonexistence") is True,
        "Weibo documented capability boundary drifted",
    )
    research = policy.get("official_research", {})
    weibo_sources = research.get("weibo_sources", [])
    standard_sources = research.get("http_standard_sources", [])
    _require(
        len(weibo_sources) == 10
        and all(str(url).startswith("https://open.weibo.com/") for url in weibo_sources)
        and len(standard_sources) == 2
        and all(str(url).startswith("https://www.rfc-editor.org/") for url in standard_sources)
        and "robot" in str(research.get("frequency_constraint", ""))
        and "local-only SQLite" in str(research.get("storage_constraint", ""))
        and "zero" in str(research.get("pricing_constraint", "")),
        "Weibo first-party research registry drifted",
    )
    budget = policy.get("budget_and_quota", {})
    _require(
        budget.get("owner_approved_budget_units") == 0
        and budget.get("pricing_snapshot") == "unknown_not_approved"
        and budget.get("quota_snapshot") == "unknown_not_approved"
        and budget.get("automatic_plan_upgrade") is False
        and budget.get("automatic_purchase") is False
        and budget.get("real_requests_when_budget_zero") == 0
        and budget.get("real_requests_when_price_unknown") == 0
        and budget.get("real_requests_when_quota_unknown") == 0
        and budget.get("cost_receipt_per_run") is True
        and budget.get("capability_receipt_contains_credentials") is False,
        "Weibo budget and quota gate drifted",
    )
    owner_action = policy.get("owner_action", {})
    _require(
        owner_action.get("max_items") == 20
        and owner_action.get("single_page_number") == 1
        and owner_action.get("single_page_size") == 20
        and owner_action.get("automatic_pagination") is False
        and owner_action.get("automatic_scroll") is False
        and owner_action.get("automatic_retry") is False
        and owner_action.get("account_state_change") is False
        and owner_action.get("cursor_accepted") is False
        and owner_action.get("has_more_causes_request") is False
        and owner_action.get("full_source_list_completion_claim") is False,
        "Weibo Owner batch boundary drifted",
    )
    transport = policy.get("transport", {})
    _require(
        transport.get("implemented_in_this_task") is False
        and transport.get("network_client") is False
        and transport.get("browser_dom_iterator") is False
        and transport.get("undocumented_endpoint") is False
        and transport.get("cookie_export") is False
        and transport.get("signature_reverse_engineering") is False
        and transport.get("raw_open_api_response_accepted") is False
        and transport.get("sanitized_contract_only") is True
        and len(transport.get("forbidden_raw_fields", [])) == 14,
        "Weibo transport containment drifted",
    )
    canonical = policy.get("canonical", {})
    _require(
        canonical.get("truth_source") == "sqlite"
        and canonical.get("relation_type") == "favorited"
        and canonical.get("confirmed_by") == "scan"
        and canonical.get("source_collection_id") is None
        and canonical.get("full_scan_id") is None
        and canonical.get("full_source_list_completion") is False
        and canonical.get("removed_writes") == 0
        and canonical.get("tombstone_candidate_writes") == 0
        and canonical.get("physical_deletes") == 0
        and canonical.get("content_auto_deletes") == 0
        and canonical.get("classification_writes") == 0
        and canonical.get("taxonomy_mutations") == 0,
        "Weibo Canonical containment drifted",
    )
    authorization = policy.get("authorization_and_storage", {})
    _require(
        authorization.get("authorization_revocation_stops_new_requests") is True
        and authorization.get("new_requests_after_revocation") == 0
        and authorization.get("authorization_cleanup_required_receipt") is True
        and authorization.get("local_only_storage_attestation_required") is True
        and authorization.get("remote_collection_server") is False
        and authorization.get("automatic_historical_delete_in_this_task") is False
        and authorization.get("two_complete_scan_reconciliation_task") == "TSK.x2n.adapters.005"
        and authorization.get("reconciliation_entered") is False,
        "Weibo authorization and storage boundary drifted",
    )
    rate = policy.get("rate_limit", {})
    _require(
        rate.get("http_429_supported_by_contract") is True
        and rate.get("retry_after_required_for_429") is True
        and rate.get("maximum_bounded_hold_seconds") == 2_592_000
        and rate.get("checkpoint_advances_on_429") is False
        and rate.get("canonical_writes_on_429") == 0
        and rate.get("automatic_retry") is False
        and rate.get("proxy_rotation") is False
        and rate.get("arbitrary_url_proxy") is False
        and rate.get("retry_storm") is False,
        "Weibo 429 containment drifted",
    )

    source = COMPANION_SOURCE.read_text(encoding="utf-8")
    cli = CLI_SOURCE.read_text(encoding="utf-8")
    for token in (
        "class WeiboCapabilityReceipt",
        "class WeiboSelectedIterator",
        "class WeiboSelectedAdapter",
        "class WeiboSelectedBatchCoordinator",
        "evaluate_weibo_capability",
        "RelationType.FAVORITED",
        "ConfirmationSource.SCAN",
        "SourceMethod.SELECTED_COLLECTION",
        "full_scan_id = NULL",
        "PRODUCTION_ENABLED = False",
        "CANARY_ITEM_LIMIT = 20",
        '"rate_limited"',
        "Retry-After",
        '"new_requests_after_revocation": 0',
    ):
        _require(token in source, f"Weibo implementation contract missing: {token}")
    for forbidden in (
        "RelationType.LIKED",
        "RelationType.SAVED_CURRENT",
        "urllib.request",
        "requests.",
        "httpx.",
        "selenium",
        "playwright",
    ):
        _require(forbidden not in source, f"forbidden Weibo behavior entered Adapter: {forbidden}")
    _require(
        'subparsers.add_parser("weibo")' in cli
        and 'weibo_actions.add_parser("canary-plan")' in cli
        and "build_weibo_canary_plan" in cli,
        "non-executing Weibo Canary CLI is missing",
    )
    for path in UNCHANGED_SECURITY_SURFACES:
        _require(path.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, path), f"security surface changed: {path.name}")
    artifact = _load_json(ARTIFACT_POLICY)
    enforcement = artifact.get("enforcement", [])
    for required in (
        "scripts/weibo_selected_chaos_worker.py",
        "scripts/run_adapters_008_acceptance.py",
        "scripts/verify_adapters_008.py",
    ):
        _require(required in enforcement, f"Adapters008 enforcement is not registered: {required}")
    return Check(
        "official_scope_policy_and_adapter_containment",
        "PASS",
        {
            "automatic_pagination": 0,
            "documented_source_shapes": 1,
            "official_sources": len(weibo_sources) + len(standard_sources),
            "owner_canary": "NOT_RUN",
            "platform_requests": 0,
            "production_enabled": False,
            "raw_api_responses": 0,
            "relation_semantics": "official_favorited_scan_confirmed",
            "unsupported_personal_list_capabilities": 1,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json(FIXTURE)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S03.A008.001" and fixture.get("synthetic") is True,
        "Adapters008 fixture identity drifted",
    )
    for field in (
        "contains_accounts",
        "contains_cookies",
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
        "contains_profile_paths",
    ):
        _require(fixture.get(field) is False, f"fixture privacy drifted: {field}")
    source = fixture.get("source_contract", {})
    _require(
        source.get("source_kind") == "current_authorized_user_favorites"
        and source.get("official_endpoint") == "GET /2/favorites.json"
        and source.get("official_access") == "ordinary_interface_permission_plus_owner_oauth"
        and source.get("environment") == "ci_synthetic"
        and source.get("raw_open_api_response") is False
        and source.get("transport_present") is False
        and source.get("canonical_public_route") == "UNVERIFIED_DISABLED"
        and source.get("page_number") == 1
        and source.get("page_size") == 20
        and source.get("cursor_accepted") is False
        and source.get("automatic_pagination") is False
        and source.get("automatic_scroll") is False,
        "fixture source contract drifted",
    )
    mapping = fixture.get("mapping", {})
    _require(
        mapping.get("selected_manifest_items") == 20
        and mapping.get("expected_identified_items") == 20
        and mapping.get("expected_identified_percent") == 100
        and mapping.get("expected_silent_losses") == 0
        and mapping.get("expected_content_rows") == 20
        and mapping.get("expected_favorited_relations") == 20
        and mapping.get("expected_scan_confirmed_relations") == 20
        and mapping.get("expected_liked_relations") == 0
        and mapping.get("expected_saved_current_relations") == 0
        and mapping.get("expected_observations") == 20
        and mapping.get("expected_removed_relations") == 0
        and mapping.get("expected_tombstone_candidates") == 0
        and mapping.get("expected_physical_deletes") == 0
        and mapping.get("expected_content_auto_deletes") == 0
        and mapping.get("expected_classification_writes") == 0
        and mapping.get("expected_taxonomy_mutations") == 0
        and mapping.get("expected_persisted_media_urls") == 0
        and mapping.get("expected_persisted_credentials") == 0,
        "fixture mapping drifted",
    )
    authorization = fixture.get("authorization_and_storage", {})
    _require(
        authorization.get("owner_oauth_required") is True
        and authorization.get("interface_permission_required") is True
        and authorization.get("local_only_storage_required") is True
        and authorization.get("expected_new_requests_after_revocation") == 0
        and authorization.get("expected_authorization_cleanup_required_receipts") == 1
        and authorization.get("expected_historical_relation_deletes") == 0
        and authorization.get("real_historical_data_present") is False,
        "fixture authorization and storage contract drifted",
    )
    budget = fixture.get("budget_and_quota", {})
    _require(
        budget.get("approved_budget_units") == 0
        and budget.get("pricing_snapshot") == "UNKNOWN_NOT_APPROVED"
        and budget.get("quota_snapshot") == "UNKNOWN_NOT_APPROVED"
        and budget.get("expected_real_requests") == 0
        and budget.get("expected_automatic_plan_upgrades") == 0
        and budget.get("expected_cost_receipts") == 1,
        "fixture cost contract drifted",
    )
    rate = fixture.get("rate_limit", {})
    _require(
        rate.get("http_status") == 429
        and rate.get("retry_after_seconds") == 120
        and rate.get("expected_early_resume_blocks") == 1
        and rate.get("expected_checkpoint_advances_on_429") == 0
        and rate.get("expected_canonical_writes_on_429") == 0
        and rate.get("expected_proxy_rotations") == 0
        and rate.get("expected_automatic_retries") == 0,
        "fixture 429 contract drifted",
    )
    chaos = fixture.get("chaos", {})
    _require(
        chaos.get("kill_runs") == 50
        and chaos.get("items_per_batch") == 20
        and chaos.get("expected_lost_ids") == 0
        and chaos.get("expected_duplicate_side_effects") == 0
        and chaos.get("expected_checkpoint_advances_before_commit") == 0,
        "fixture chaos contract drifted",
    )
    cases = fixture.get("cases", [])
    _require(len(cases) == 58 and len(set(cases)) == 58, "Adapters008 fixture cases drifted")
    global_manifest = _load_json(GLOBAL_FIXTURE_MANIFEST)
    _require(
        global_manifest.get("manifest_id") == "FIXTURE.X2N.017" and global_manifest.get("phase") == PHASE,
        "global fixture manifest identity drifted",
    )
    global_rows = global_manifest.get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S03.A008.001",
            "path": "packages/test-fixtures/adapters/v1/weibo_selected/fixture_manifest.json",
            "case_count": 58,
            "purpose": "Weibo official current-user favorites selection, 20 scan-confirmed favorited mappings, zero-budget and unknown-price/quota gates, RFC Retry-After hold, eight blocked states and 50 process-kill recovery",
        }
        in global_rows,
        "Adapters008 fixture is not globally registered",
    )
    return Check(
        "synthetic_capability_mapping_and_chaos_fixtures",
        "PASS",
        {
            "blocked_states": len(fixture.get("blocked_states", [])),
            "contract_cases": len(cases),
            "kill_runs": chaos["kill_runs"],
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "selected_items": mapping["selected_manifest_items"],
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a008-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        output = _json_line(
            _run_external(
                "adapters_008_acceptance",
                (sys.executable, "-B", str(ACCEPTANCE_RUNNER)),
                env=_isolated_env(home),
                timeout=900,
            ),
            "Adapters008 acceptance",
        )
    expected = {
        "acceptance_scope": "ADAPTERS_008_WEIBO_SELECTED_CI_SYNTH",
        "automatic_pagination": 0,
        "automatic_scroll": 0,
        "canary_item_limit": 20,
        "canary_tooling": "PASS_NONEXECUTING",
        "identified_item_success_percent": 100.0,
        "network_calls": 0,
        "owner_canary": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "silent_losses": 0,
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
    }
    for field, value in expected.items():
        _require(output.get(field) == value, f"Adapters008 acceptance metric drifted: {field}")
    capability = output.get("capability", {})
    _require(
        capability.get("documented_source_kind") == "current_authorized_user_favorites"
        and capability.get("documented_endpoint") == "GET /2/favorites.json"
        and capability.get("official_scope") == "ordinary_interface_permission_plus_owner_oauth"
        and capability.get("canonical_public_route") == "UNVERIFIED_DISABLED"
        and capability.get("authorization_revoked_status") == "BLOCKED_AUTHORIZATION_REVOKED"
        and capability.get("authorization_cleanup_required") is True
        and capability.get("budget_zero_status") == "BLOCKED_BUDGET_ZERO"
        and capability.get("price_quota_unknown_status") == "BLOCKED_PRICE_OR_QUOTA_UNKNOWN"
        and capability.get("budget_exceeded_status") == "BLOCKED_BUDGET_EXCEEDED"
        and capability.get("quota_exhausted_status") == "BLOCKED_QUOTA_EXHAUSTED"
        and capability.get("owner_oauth_required") is True
        and capability.get("interface_permission_required") is True
        and capability.get("missing_requirement_count") == 6
        and capability.get("new_requests_after_revocation") == 0
        and capability.get("owner_runtime_status") == "BLOCKED_FEATURE_DISABLED"
        and capability.get("personal_favorites_api") == "DOCUMENTED_APP_ACCESS_UNKNOWN_DISABLED"
        and capability.get("personal_likes_api") == "UNKNOWN_DISABLED"
        and capability.get("platform_requests") == 0
        and capability.get("production_enabled") is False
        and capability.get("raw_open_api_responses") == 0,
        "Adapters008 capability acceptance failed",
    )
    chaos = output.get("chaos", {})
    _require(
        chaos.get("kill_runs") == 50
        and chaos.get("lost_ids") == 0
        and chaos.get("duplicate_side_effects") == 0
        and chaos.get("content_count") == 20
        and chaos.get("relation_count") == 20
        and chaos.get("scan_confirmed_favorited_relations") == 20
        and chaos.get("fake_liked_or_saved_current_relations") == 0
        and chaos.get("observation_count") == 20
        and chaos.get("identified_item_success_percent") == 100.0
        and chaos.get("silent_losses") == 0
        and chaos.get("removed_relations") == 0
        and chaos.get("tombstone_candidates") == 0
        and chaos.get("physical_deletes") == 0
        and chaos.get("content_auto_deletes") == 0
        and chaos.get("taxonomy_mutations") == 0
        and chaos.get("resume_from_durable_checkpoint") is True
        and chaos.get("authorization_cleanup_required") is False
        and chaos.get("approved_budget_units") == 0,
        "Adapters008 chaos acceptance failed",
    )
    blocked = output.get("blocked", {})
    _require(
        blocked.get("blocked_state_cases") == 7
        and blocked.get("canonical_writes") == 0
        and blocked.get("historical_relation_deletes") == 0
        and blocked.get("historical_relations_preserved") == 1
        and blocked.get("new_requests_after_revocation") == 0
        and blocked.get("partial_identified_percent") == 50.0
        and blocked.get("platform_kills") == 4
        and blocked.get("authorization_cleanup_required_receipts") == 1,
        "Adapters008 blocked-state acceptance failed",
    )
    rate = output.get("rate_limit", {})
    _require(
        rate.get("http_429_cases") == 1
        and rate.get("retry_after_seconds") == 120
        and rate.get("early_resume_blocks") == 1
        and rate.get("resume_after_hold") is True
        and rate.get("checkpoint_advances_on_429") == 0
        and rate.get("canonical_writes_on_429") == 0
        and rate.get("automatic_retries") == 0
        and rate.get("proxy_rotations") == 0,
        "Adapters008 rate-limit acceptance failed",
    )
    cost = output.get("cost_receipt", {})
    _require(
        cost.get("approved_budget_units") == 0
        and cost.get("price_state") == "UNKNOWN_NOT_APPROVED"
        and cost.get("quota_state") == "UNKNOWN_NOT_APPROVED"
        and cost.get("automatic_plan_upgrades") == 0
        and cost.get("platform_requests") == 0,
        "Adapters008 cost receipt acceptance failed",
    )
    unit = output.get("unit_suite", {})
    _require(
        unit.get("tests") == 18 and unit.get("errors") == 0 and unit.get("failures") == 0 and unit.get("skips") == 0,
        "Adapters008 unit acceptance failed",
    )
    return Check(
        "weibo_selected_scope_checkpoint_and_kill_acceptance",
        "PASS",
        {
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "blocked_state_cases": blocked["blocked_state_cases"],
            "content_count": chaos["content_count"],
            "duplicate_side_effects": chaos["duplicate_side_effects"],
            "approved_budget_units": cost["approved_budget_units"],
            "authorization_cleanup_required_receipts": blocked["authorization_cleanup_required_receipts"],
            "early_resume_blocks": rate["early_resume_blocks"],
            "fake_liked_or_saved_current_relations": chaos["fake_liked_or_saved_current_relations"],
            "identified_item_success_percent": chaos["identified_item_success_percent"],
            "kill_runs": chaos["kill_runs"],
            "lost_ids": chaos["lost_ids"],
            "owner_canary": "NOT_RUN",
            "scan_confirmed_favorited_relations": chaos["scan_confirmed_favorited_relations"],
            "platform_calls": 0,
            "new_requests_after_revocation": blocked["new_requests_after_revocation"],
            "removed_relations": chaos["removed_relations"],
            "retry_after_seconds": rate["retry_after_seconds"],
            "silent_losses": chaos["silent_losses"],
            "unit_tests": unit["tests"],
        },
    )


def validate_full_lane_report(path: Path) -> Check:
    result = PREVIOUS.validate_full_lane_report(path)
    return Check("full_lane_replay", result.status, result.details)


def _acceptance_input_receipt() -> str:
    digest = hashlib.sha256()
    for path in (
        TASKPACK,
        ACCEPTANCE,
        RUN_CONTRACT,
        POLICY,
        FIXTURE,
        COMPANION_SOURCE,
        COMPANION_TEST,
        CLI_SOURCE,
        CHAOS_WORKER,
        ACCEPTANCE_RUNNER,
    ):
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered, "evidence contains private data")
    _require("Bearer" + " " not in rendered and "https://" not in rendered, "evidence contains URL or secret data")
    _require(re.search(r"/(?:Users|home)/[A-Za-z0-9._-]+/", rendered) is None, "evidence contains local path")


def write_evidence(checks: list[Check]) -> None:
    details = {item.name: item.details for item in checks}
    acceptance = details.get("weibo_selected_scope_checkpoint_and_kill_acceptance", {})
    lane = details.get("full_lane_replay", {})
    _require(acceptance and lane, "final evidence requires acceptance and full lane")
    payload = {
        "acceptance_ids": ["ACC.x2n.wb.001", "ACC.x2n.wb.002", "ACC.x2n.batch.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.batch.001": "PASS_CI_SYNTH_EIGHT_NON_AUTHORITATIVE_REMOVED_ZERO_AUTHORIZATION_CLEANUP_REQUIRED_ONE_RECONCILIATION_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.wb.001": "PASS_CI_SYNTH_OFFICIAL_CURRENT_USER_FAVORITES_20_OF_20_SCAN_CONFIRMED_FAVORITED_ZERO_BUDGET_PRICE_QUOTA_UNKNOWN_OWNER_CANARY_NOT_RUN",
            "ACC.x2n.wb.002": "PASS_CI_SYNTH_FIFTY_PROCESS_KILLS_ZERO_LOSS_DUPLICATE_FOUR_PLATFORM_KILLS_HTTP_429_RETRY_AFTER_HOLD_AND_ZERO_AUTOMATIC_RETRY",
        },
        "checks": [{"name": item.name, "status": item.status, "details": item.details} for item in checks],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "owner_canary": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "private_content_included": False,
        "profile_path_included": False,
        "real_account_execution": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_G3_PASS",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.3",
        "stage_gate": "G3_NOT_RUN",
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "task_metrics": {
            "automatic_pagination": acceptance.get("automatic_pagination"),
            "automatic_scroll": acceptance.get("automatic_scroll"),
            "blocking_executions": lane.get("blocking_executions"),
            "content_count": acceptance.get("content_count"),
            "coverage_percent": lane.get("coverage_percent"),
            "duplicate_side_effects": acceptance.get("duplicate_side_effects"),
            "approved_budget_units": acceptance.get("approved_budget_units"),
            "authorization_cleanup_required_receipts": acceptance.get("authorization_cleanup_required_receipts"),
            "early_resume_blocks": acceptance.get("early_resume_blocks"),
            "fake_liked_or_saved_current_relations": acceptance.get("fake_liked_or_saved_current_relations"),
            "identified_item_success_percent": acceptance.get("identified_item_success_percent"),
            "kill_runs": acceptance.get("kill_runs"),
            "lost_ids": acceptance.get("lost_ids"),
            "new_requests_after_revocation": acceptance.get("new_requests_after_revocation"),
            "scan_confirmed_favorited_relations": acceptance.get("scan_confirmed_favorited_relations"),
            "removed_relations": acceptance.get("removed_relations"),
            "retry_after_seconds": acceptance.get("retry_after_seconds"),
            "silent_losses": acceptance.get("silent_losses"),
            "unit_tests": acceptance.get("unit_tests"),
        },
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(
        evidence.get("status") == "PASS_CI_SYNTH_SCOPED"
        and evidence.get("stage_gate") == "G3_NOT_RUN"
        and evidence.get("remote_upload") == "FORBIDDEN_UNTIL_G3_PASS",
        "evidence overstated",
    )
    _require(
        evidence.get("owner_profile_login") == "NOT_RUN"
        and evidence.get("owner_canary") == "NOT_RUN"
        and evidence.get("real_account_execution") == "NOT_RUN"
        and evidence.get("platform_calls") == 0,
        "real Profile/account execution overstated",
    )
    _require(
        evidence.get("profile_path_included") is False and evidence.get("private_content_included") is False,
        "evidence contains private scope",
    )
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains failed check")
    metrics = evidence.get("task_metrics", {})
    _require(
        metrics.get("automatic_pagination") == 0
        and metrics.get("automatic_scroll") == 0
        and metrics.get("approved_budget_units") == 0
        and metrics.get("authorization_cleanup_required_receipts") == 1
        and metrics.get("content_count") == 20
        and metrics.get("duplicate_side_effects") == 0
        and metrics.get("early_resume_blocks") == 1
        and metrics.get("fake_liked_or_saved_current_relations") == 0
        and metrics.get("identified_item_success_percent") == 100.0
        and metrics.get("kill_runs") == 50
        and metrics.get("lost_ids") == 0
        and metrics.get("new_requests_after_revocation") == 0
        and metrics.get("scan_confirmed_favorited_relations") == 20
        and metrics.get("removed_relations") == 0
        and metrics.get("retry_after_seconds") == 120
        and metrics.get("silent_losses") == 0
        and metrics.get("unit_tests") == 18
        and metrics.get("blocking_executions") == 24,
        "evidence metrics drifted",
    )
    return Check(
        "evidence",
        "PASS",
        {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID},
    )


def run_checks(
    *,
    verify_worktree: bool,
    allow_external_main_dirty: bool,
    run_external: bool,
    lane_report: Optional[Path] = None,
) -> list[Check]:
    checks = [
        validate_scope(),
        validate_predecessor(),
        validate_task_and_state(),
        validate_policy_and_implementation(),
        validate_fixtures(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_execution())
    if lane_report is not None:
        checks.append(validate_full_lane_report(lane_report))
    _require(all(check.status == "PASS" for check in checks), "an Adapters008 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.008")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--lane-report", type=Path)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_external=not args.skip_external,
            lane_report=args.lane_report,
        )
        if args.write_evidence:
            write_evidence(checks)
        if args.require_evidence:
            checks.append(verify_evidence())
        print(
            json.dumps(
                {
                    "checks": [{"name": item.name, "status": item.status} for item in checks],
                    "status": "PASS",
                    "task": TASK_ID,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, subprocess.TimeoutExpired, VerificationError) as error:
        print(
            json.dumps(
                {"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID}, ensure_ascii=False, sort_keys=True
            ),
            file=os.sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
