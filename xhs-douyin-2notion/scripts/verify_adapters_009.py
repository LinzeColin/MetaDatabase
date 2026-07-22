#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.009."""

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
    "verify_adapters_008_for_adapters_009",
    PROJECT_ROOT / "scripts/verify_adapters_008.py",
)
assert PREVIOUS_SPEC and PREVIOUS_SPEC.loader
PREVIOUS = importlib.util.module_from_spec(PREVIOUS_SPEC)
sys.modules[PREVIOUS_SPEC.name] = PREVIOUS
PREVIOUS_SPEC.loader.exec_module(PREVIOUS)

VerificationError = PREVIOUS.VerificationError
Check = PREVIOUS.Check
_require = PREVIOUS._require
_load_json = PREVIOUS._load_json
_load_json_at = PREVIOUS._load_json_at
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

TASK_ID = "TSK.x2n.adapters.009"
RUN_ID = "RUN-X2N-S03-A009"
PHASE = "PH.X2N.3.8"
BRANCH = "codex/xhs-douyin-2notion-v0001-s03-adapters009"
TASK_BASE_COMMIT = "a0f4a34675d4b2b8b02c9195976a787d2fbf9c59"
FINAL_COMMIT = "8c6442a251f73e645e292a4e77dd03448d153b64"
ORIGIN_CUTOFF = PREVIOUS.ORIGIN_CUTOFF

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_009.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
POLICY = PROJECT_ROOT / "machine/policy/taobao_selected_collection_policy.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/taobao_selected/fixture_manifest.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
COMPANION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/taobao_selected.py"
COMPANION_TEST = PROJECT_ROOT / "apps/companion/tests/test_taobao_selected.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
CHAOS_WORKER = PROJECT_ROOT / "scripts/taobao_selected_chaos_worker.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_009_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.009.json"

UNCHANGED_SECURITY_SURFACES = (
    PROJECT_ROOT / "apps/extension/manifest.json",
    PROJECT_ROOT / "apps/extension/src/service-worker.js",
    PROJECT_ROOT / "apps/extension/src/taobao-current-page.js",
    PROJECT_ROOT / "apps/companion/native-host/policy.json",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "machine/policy/taobao_current_page_policy.json",
    PROJECT_ROOT / "package-lock.json",
    PROJECT_ROOT / "uv.lock",
    PREVIOUS.EVIDENCE,
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/src/x2n_companion/taobao_selected.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_taobao_selected.py",
    "docs/governance/RUN_CONTRACT_S03_ADAPTERS_009.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.adapters.009.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/taobao_selected_collection_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/taobao_selected_chaos_worker.py",
    "scripts/run_adapters_009_acceptance.py",
    "scripts/verify_adapters_008.py",
    "scripts/verify_adapters_009.py",
    "tests/test_adapters_008.py",
    "tests/test_adapters_009.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/adapters/v1/taobao_selected/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    relative_changes: list[str] = []
    for path in sorted(set(committed)):
        relative = _project_relative(path)
        _require(relative is not None, "Adapters009 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Adapters009 change: {relative}",
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
    current_branch = _git(["branch", "--show-current"])
    _require(current_branch not in {"", "main"}, "Adapters009 regression requires a non-main worktree")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote)
        is not None,
        "wrong or authenticated persisted origin",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, FINAL_COMMIT],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Adapters009 final commit no longer descends from Adapters008",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer descends from Adapters009",
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
            "historical_branch": BRANCH,
            "current_branch": current_branch,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": main_overlap,
        },
    )


def validate_predecessor() -> Check:
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Adapters008 final pin differs from Adapters009 base")
    _require(
        PREVIOUS.EVIDENCE.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, PREVIOUS.EVIDENCE),
        "Adapters008 evidence was rewritten",
    )
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Adapters008 historical regression failed")
    PREVIOUS.verify_evidence()
    return Check(
        "adapters_008_fixed_predecessor",
        "PASS",
        {"evidence_mutations": 0, "historical_checks": len(checks) + 1, "predecessor_commit": TASK_BASE_COMMIT},
    )


def validate_task_and_state() -> Check:
    taskpack_text = _read_blob_at(FINAL_COMMIT, TASKPACK).decode("utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Adapters009 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.3" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.adapters.001", "TSK.x2n.skeleton.009", "TSK.x2n.skeleton.004"],
        "Adapters009 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.tb.001", "ACC.x2n.tb.002", "ACC.x2n.batch.001"],
        "Adapters009 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    for future in ("TSK.x2n.adapters.005",):
        _require(
            _task_block(taskpack_text, future) == _task_block(base_taskpack, future),
            f"{future} was entered by this Run",
        )
    taskpack = yaml.safe_load(taskpack_text)
    _require(isinstance(taskpack, dict), "Task Pack root must be an object")
    _require(
        taskpack.get("project", {}).get("status") == "STAGE_3_ADAPTERS_009_PASS_G3_NOT_RUN",
        "Task Pack status drifted",
    )
    authorization = taskpack.get("authorization", {})
    _require(
        authorization.get("stage_3_task_start") is True
        and authorization.get("real_account_execution") is False
        and authorization.get("public_release") is False,
        "Task Pack authorization drifted",
    )
    state = _load_json_at(FINAL_COMMIT, TASK_STATE)
    _require(state.get("schema_version") == "1.26", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.3" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Adapters009 state is not pass")
    _require("TSK.x2n.adapters.005" not in state.get("tasks", {}), "Adapters005 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.3.9" and state.get("next_run") == "TSK.x2n.adapters.005",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g3_pass",
        "G3/upload state overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.tb.001")
        == "pass_ci_synth_owner_explicit_item_get_minimum_fields_20_of_20_saved_current_owner_confirmed_fake_like_favorite_0_budget_scope_retention_unknown_owner_canary_not_run_production_disabled",
        "Taobao completeness Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.tb.002")
        == "pass_ci_synth_50_process_kills_lost_duplicate_0_auth_oauth_budget_retention_policy_platform_kill_5_cookie_signing_undocumented_endpoint_0_http_429_retry_after_120_auto_retry_proxy_rotation_0",
        "Taobao Kill Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.batch.001")
        == "pass_ci_synth_9_non_authoritative_removed_0_adapter009_physical_content_delete_0_authorization_cleanup_required_1_retention_receipt_1_reconciliation_downstream_not_run",
        "batch Acceptance drifted",
    )
    _require(
        state.get("taobao_selected_execution")
        == "pass_ci_synth_owner_explicit_item_ids_authorized_item_get_contract_only_20_saved_current_owner_confirmed_50_process_kills_budget_scope_retention_and_429_gated_real_transport_owner_canary_not_run",
        "Taobao execution boundary drifted",
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
        _load_json_at(FINAL_COMMIT, PROJECT_FACT).get("status") == "stage_3_adapters_009_pass_g3_not_run",
        "project status drifted",
    )
    architecture = _load_json_at(FINAL_COMMIT, ARCHITECTURE_FACT)
    _require(
        architecture.get("phase") == PHASE
        and architecture.get("stage_gate") == "g3_not_run"
        and architecture.get("real_account_execution") is False,
        "architecture state drifted",
    )
    contract = _read_blob_at(FINAL_COMMIT, RUN_CONTRACT).decode("utf-8")
    for value in (
        TASK_ID,
        RUN_ID,
        PHASE,
        TASK_BASE_COMMIT,
        BRANCH,
        "taobao.item.get",
        "retention",
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
            "next_task": "TSK.x2n.adapters.005",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
            "stage_gate": "G3_NOT_RUN",
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json_at(FINAL_COMMIT, POLICY)
    flags = policy.get("feature_gate", {})
    _require(
        policy.get("policy_id") == "POLICY.X2N.TAOBAO-SELECTED.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("phase") == PHASE
        and policy.get("reviewed_at") == "2026-07-23"
        and policy.get("default") == "deny"
        and flags.get("ci_synthetic_contract_enabled") is True
        and flags.get("owner_canary_enabled") is False
        and flags.get("production_enabled") is False
        and flags.get("real_account_execution") is False
        and flags.get("platform_requests") is False,
        "Taobao policy identity or gate drifted",
    )
    capability = policy.get("official_capability", {})
    _require(
        capability.get("supported_contract_shape") == "owner_explicit_item_ids_hydrated_by_authorized_item_get"
        and capability.get("documented_endpoint") == "taobao.item.get"
        and capability.get("documented_endpoint_requires_authorization") is True
        and capability.get("documented_endpoint_fee_class") == "value_added_api"
        and capability.get("minimum_requested_fields") == ["num_iid", "title"]
        and capability.get("application_registration_required") is True
        and capability.get("owner_oauth_required") is True
        and capability.get("item_get_scope_required") is True
        and capability.get("personal_favorites_list_endpoint") == "not_verified_unknown_disabled"
        and capability.get("personal_likes_list_endpoint") == "not_verified_unknown_disabled"
        and capability.get("selected_collection_is_local_owner_manifest") is True
        and capability.get("selection_does_not_prove_platform_favorite") is True
        and capability.get("inference_not_claim_of_nonexistence") is True,
        "Taobao documented capability boundary drifted",
    )
    research = policy.get("official_research", {})
    official_sources = research.get("sources", [])
    _require(
        research.get("source_class") == "alibaba_first_party_only"
        and len(official_sources) == 8
        and all(str(url).startswith("https://developer.alibaba.com/") for url in official_sources)
        and "did not establish" in str(research.get("finding", ""))
        and "unauthorized crawling" in str(research.get("crawler_constraint", ""))
        and "retention expiry" in str(research.get("retention_constraint", "")),
        "Taobao first-party research registry drifted",
    )
    budget = policy.get("budget_and_quota", {})
    _require(
        budget.get("owner_approved_budget_units") == 0
        and budget.get("pricing_snapshot") == "unknown_not_approved"
        and budget.get("quota_snapshot") == "unknown_not_approved"
        and budget.get("automatic_plan_upgrade") is False
        and budget.get("request_when_budget_zero") is False
        and budget.get("request_when_price_or_quota_unknown") is False,
        "Taobao budget and quota gate drifted",
    )
    retention = policy.get("retention_gate", {})
    _require(
        retention.get("retention_receipt_required") is True
        and retention.get("purpose_and_scope_disclosure_approved") is False
        and retention.get("retention_period_approved") is False
        and retention.get("user_delete_and_revoke_flow_ready") is False
        and retention.get("deletion_receipt_ready") is False
        and retention.get("authorization_trace_required") is True
        and retention.get("delete_on_withdrawal_required") is True
        and retention.get("delete_on_service_end_required") is True
        and retention.get("delete_on_retention_expiry_required") is True
        and retention.get("delete_on_cooperation_end_required") is True
        and retention.get("unknown_scope_or_retention_state") == "UNKNOWN_DISABLED",
        "Taobao retention gate drifted",
    )
    owner_action = policy.get("owner_action", {})
    _require(
        owner_action.get("explicit_selection_required") is True
        and owner_action.get("selection_input") == "local_owner_manifest_of_num_iid_values"
        and owner_action.get("max_items") == 20
        and owner_action.get("single_page_number") == 1
        and owner_action.get("single_page_size") == 20
        and owner_action.get("automatic_pagination") is False
        and owner_action.get("automatic_scroll") is False
        and owner_action.get("automatic_retry") is False
        and owner_action.get("account_state_change") is False
        and owner_action.get("next_page_token_accepted") is False
        and owner_action.get("full_source_list_completion_claim") is False,
        "Taobao Owner batch boundary drifted",
    )
    transport = policy.get("transport", {})
    forbidden_raw = set(transport.get("forbidden_raw_fields", []))
    _require(
        transport.get("implemented_in_this_task") is False
        and transport.get("network_client") is False
        and transport.get("oauth_client") is False
        and transport.get("official_top_sdk_or_protocol_transport") is False
        and transport.get("browser_dom_iterator") is False
        and transport.get("browser_mtop_cookie_signing") is False
        and transport.get("cookie_derived_token_input") is False
        and transport.get("signature_material_input") is False
        and transport.get("undocumented_endpoint") is False
        and transport.get("cookie_export") is False
        and transport.get("signature_reverse_engineering") is False
        and transport.get("proxy_rotation") is False
        and transport.get("raw_open_api_response_accepted") is False
        and transport.get("sanitized_contract_only") is True
        and transport.get("allowed_sanitized_item_fields") == ["num_iid", "title"]
        and {"cookie", "session", "sign", "app_secret", "_m_h5_tk", "h5st", "x-sign", "api", "data", "pic_url", "price"}
        <= forbidden_raw,
        "Taobao transport containment drifted",
    )
    rate = policy.get("rate_limit", {})
    _require(
        rate.get("retry_after_required_for_429") is True
        and rate.get("automatic_retry") is False
        and rate.get("proxy_rotation") is False
        and rate.get("maximum_retry_after_seconds") == 2_592_000,
        "Taobao 429 containment drifted",
    )
    canonical = policy.get("canonical", {})
    _require(
        canonical.get("truth_source") == "sqlite"
        and canonical.get("platform") == "taobao"
        and canonical.get("content_type") == "unknown"
        and canonical.get("canonical_source_url") == "https://item.taobao.com/item.htm"
        and canonical.get("semantic_query_persisted") is False
        and canonical.get("relation_type") == "saved_current"
        and canonical.get("confirmed_by") == "owner"
        and canonical.get("relation_semantics") == "local_owner_selection_not_taobao_like_or_favorite"
        and canonical.get("source_collection_id") is None
        and canonical.get("full_scan_id") is None
        and canonical.get("full_source_list_completion") is False
        and canonical.get("removed_writes") == 0
        and canonical.get("tombstone_candidate_writes") == 0
        and canonical.get("physical_deletes") == 0
        and canonical.get("content_auto_deletes") == 0
        and canonical.get("classification_writes") == 0
        and canonical.get("taxonomy_mutations") == 0,
        "Taobao Canonical containment drifted",
    )
    source = _read_blob_at(FINAL_COMMIT, COMPANION_SOURCE).decode("utf-8")
    cli = _read_blob_at(FINAL_COMMIT, CLI_SOURCE).decode("utf-8")
    for token in (
        "class TaobaoCapabilityReceipt",
        "class TaobaoSelectedIterator",
        "class TaobaoSelectedAdapter",
        "class TaobaoSelectedBatchCoordinator",
        "evaluate_taobao_capability",
        "RelationType.SAVED_CURRENT",
        "ConfirmationSource.OWNER",
        "SourceMethod.SELECTED_COLLECTION",
        'expected = {"num_iid", "title"}',
        "full_scan_id = NULL",
        "PRODUCTION_ENABLED = False",
        "CANARY_ITEM_LIMIT = 20",
        "taobao.item.get",
        "BLOCKED_RETENTION_UNKNOWN",
        "retention_receipt_sha256",
        '"new_requests_after_revocation": 0',
    ):
        _require(token in source, "Taobao implementation contract missing: " + token)
    for forbidden in (
        "RelationType.LIKED",
        "RelationType.FAVORITED",
        "urllib.request",
        "requests.",
        "httpx.",
        "selenium",
        "playwright",
        "document.cookie",
        "fetch(",
    ):
        _require(forbidden not in source, "forbidden Taobao behavior entered Adapter: " + forbidden)
    _require(
        'subparsers.add_parser("taobao")' in cli
        and 'taobao_actions.add_parser("canary-plan")' in cli
        and "build_taobao_canary_plan" in cli,
        "non-executing Taobao Canary CLI is missing",
    )
    for path in UNCHANGED_SECURITY_SURFACES:
        _require(
            _read_blob_at(FINAL_COMMIT, path) == _read_blob_at(TASK_BASE_COMMIT, path),
            "security surface changed: " + path.name,
        )
    artifact = _load_json_at(FINAL_COMMIT, ARTIFACT_POLICY)
    enforcement = artifact.get("enforcement", [])
    for required in (
        "scripts/taobao_selected_chaos_worker.py",
        "scripts/run_adapters_009_acceptance.py",
        "scripts/verify_adapters_009.py",
    ):
        _require(required in enforcement, "Adapters009 enforcement is not registered: " + required)
    return Check(
        "official_scope_retention_policy_and_adapter_containment",
        "PASS",
        {
            "automatic_pagination": 0,
            "minimum_sanitized_fields": 2,
            "official_sources": len(official_sources),
            "owner_canary": "NOT_RUN",
            "platform_requests": 0,
            "production_enabled": False,
            "raw_api_responses": 0,
            "relation_semantics": "owner_saved_current",
            "retention_ready": False,
            "undocumented_cookie_signing": 0,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json_at(FINAL_COMMIT, FIXTURE)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S03.A009.001"
        and fixture.get("task_id") == TASK_ID
        and fixture.get("synthetic") is True
        and fixture.get("platform_calls") == 0
        and fixture.get("network_calls") == 0
        and fixture.get("real_account_execution") == "NOT_RUN",
        "Adapters009 fixture identity drifted",
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
        _require(fixture.get(field) is False, "fixture privacy drifted: " + field)
    source = fixture.get("source_contract", {})
    _require(
        source.get("source_kind") == "owner_explicit_item_ids_for_authorized_item_get"
        and source.get("official_endpoint") == "taobao.item.get"
        and source.get("official_access") == "approved_application_item_get_scope_owner_oauth_and_value_added_plan"
        and source.get("environment") == "ci_synthetic"
        and source.get("raw_open_api_response") is False
        and source.get("transport_present") is False
        and source.get("personal_favorites_list_enumeration") is False
        and source.get("minimum_sanitized_fields") == ["num_iid", "title"]
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
        and mapping.get("expected_saved_current_relations") == 20
        and mapping.get("expected_owner_confirmed_relations") == 20
        and mapping.get("expected_favorited_relations") == 0
        and mapping.get("expected_liked_relations") == 0
        and mapping.get("expected_observations") == 20
        and mapping.get("expected_removed_relations") == 0
        and mapping.get("expected_tombstone_candidates") == 0
        and mapping.get("expected_physical_deletes") == 0
        and mapping.get("expected_content_auto_deletes") == 0
        and mapping.get("expected_classification_writes") == 0
        and mapping.get("expected_taxonomy_mutations") == 0
        and mapping.get("expected_persisted_media_urls") == 0
        and mapping.get("expected_persisted_credentials") == 0
        and mapping.get("expected_persisted_raw_response_fields") == 0,
        "fixture mapping drifted",
    )
    authorization = fixture.get("authorization_and_storage", {})
    _require(
        authorization.get("owner_oauth_required") is True
        and authorization.get("item_get_scope_required") is True
        and authorization.get("official_top_transport_required") is True
        and authorization.get("local_only_storage_required") is True
        and authorization.get("expected_authorization_cleanup_required_receipts") == 1
        and authorization.get("real_historical_data_present") is False,
        "fixture authorization and storage contract drifted",
    )
    retention = fixture.get("retention", {})
    _require(
        retention.get("purpose_scope_disclosure_approved") is False
        and retention.get("retention_period_approved") is False
        and retention.get("delete_revoke_flow_ready") is False
        and retention.get("deletion_receipt_ready") is False
        and retention.get("expected_retention_receipts") == 1
        and retention.get("expected_new_data_when_unknown") == 0
        and retention.get("expected_new_requests_after_revocation") == 0
        and retention.get("expected_historical_relation_deletes") == 0,
        "fixture retention contract drifted",
    )
    signing = fixture.get("undocumented_signing_rejection", {})
    _require(
        signing.get("cookie_or_session_inputs") == 2
        and signing.get("signature_or_mtop_inputs") == 9
        and signing.get("expected_rejections") == 11
        and signing.get("expected_cookie_reads") == 0
        and signing.get("expected_signature_operations") == 0
        and signing.get("expected_undocumented_endpoint_calls") == 0,
        "fixture undocumented signing rejection drifted",
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
    _require(len(cases) == 70 and len(set(cases)) == 70, "Adapters009 fixture cases drifted")
    _require(len(fixture.get("blocked_states", [])) == 9, "Adapters009 blocked states drifted")
    global_manifest = _load_json_at(FINAL_COMMIT, GLOBAL_FIXTURE_MANIFEST)
    _require(
        global_manifest.get("manifest_id") == "FIXTURE.X2N.018" and global_manifest.get("phase") == PHASE,
        "global fixture manifest identity drifted",
    )
    global_rows = global_manifest.get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S03.A009.001",
            "path": "packages/test-fixtures/adapters/v1/taobao_selected/fixture_manifest.json",
            "case_count": 70,
            "purpose": "Taobao Owner-explicit item IDs through minimal sanitized taobao.item.get shape, retention and budget gates, undocumented Cookie or signing rejection, Retry-After, nine blocked states and 50 process-kill recovery",
        }
        in global_rows,
        "Adapters009 fixture is not globally registered",
    )
    return Check(
        "synthetic_capability_retention_signing_and_chaos_fixtures",
        "PASS",
        {
            "blocked_states": len(fixture.get("blocked_states", [])),
            "contract_cases": len(cases),
            "kill_runs": chaos["kill_runs"],
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "selected_items": mapping["selected_manifest_items"],
            "synthetic_only": True,
            "undocumented_signing_rejections": signing["expected_rejections"],
        },
    )


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a009-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        output = _json_line(
            _run_external(
                "adapters_009_acceptance",
                (sys.executable, "-B", str(ACCEPTANCE_RUNNER)),
                env=_isolated_env(home),
                timeout=900,
            ),
            "Adapters009 acceptance",
        )
    expected = {
        "acceptance_scope": "ADAPTERS_009_TAOBAO_SELECTED_CI_SYNTH",
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
    for field, expected_value in expected.items():
        _require(output.get(field) == expected_value, "Adapters009 acceptance metric drifted: " + field)
    capability = output.get("capability", {})
    _require(
        capability.get("documented_source_kind") == "owner_explicit_item_ids_for_authorized_item_get"
        and capability.get("documented_endpoint") == "taobao.item.get"
        and capability.get("official_scope") == "minimum_num_iid_and_title_fields_plus_owner_oauth"
        and capability.get("canonical_public_route") == "UNVERIFIED_DISABLED"
        and capability.get("authorization_revoked_status") == "BLOCKED_AUTHORIZATION_REVOKED"
        and capability.get("authorization_cleanup_required") is True
        and capability.get("budget_zero_status") == "BLOCKED_BUDGET_ZERO"
        and capability.get("price_quota_unknown_status") == "BLOCKED_PRICE_OR_QUOTA_UNKNOWN"
        and capability.get("budget_exceeded_status") == "BLOCKED_BUDGET_EXCEEDED"
        and capability.get("quota_exhausted_status") == "BLOCKED_QUOTA_EXHAUSTED"
        and capability.get("retention_unknown_status") == "BLOCKED_RETENTION_UNKNOWN"
        and capability.get("retention_receipt_required") is True
        and capability.get("owner_oauth_required") is True
        and capability.get("item_get_scope_required") is True
        and capability.get("missing_requirement_count") == 7
        and capability.get("new_requests_after_revocation") == 0
        and capability.get("owner_runtime_status") == "BLOCKED_FEATURE_DISABLED"
        and capability.get("personal_favorites_list_api") == "NOT_VERIFIED_UNKNOWN_DISABLED"
        and capability.get("owner_explicit_item_ids_only") is True
        and capability.get("platform_requests") == 0
        and capability.get("production_enabled") is False
        and capability.get("raw_open_api_responses") == 0,
        "Adapters009 capability acceptance failed",
    )
    chaos = output.get("chaos", {})
    _require(
        chaos.get("kill_runs") == 50
        and chaos.get("lost_ids") == 0
        and chaos.get("duplicate_side_effects") == 0
        and chaos.get("content_count") == 20
        and chaos.get("relation_count") == 20
        and chaos.get("owner_confirmed_saved_current_relations") == 20
        and chaos.get("fake_liked_or_favorited_relations") == 0
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
        and chaos.get("approved_budget_units") == 0
        and chaos.get("retention_policy_ready") is False
        and chaos.get("retention_receipt_sha256") == "f" * 64,
        "Adapters009 chaos acceptance failed",
    )
    blocked = output.get("blocked", {})
    _require(
        blocked.get("blocked_state_cases") == 8
        and blocked.get("canonical_writes") == 0
        and blocked.get("historical_relation_deletes") == 0
        and blocked.get("historical_relations_preserved") == 1
        and blocked.get("new_requests_after_revocation") == 0
        and blocked.get("partial_identified_percent") == 50.0
        and blocked.get("platform_kills") == 5
        and blocked.get("authorization_cleanup_required_receipts") == 1,
        "Adapters009 blocked-state acceptance failed",
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
        "Adapters009 rate-limit acceptance failed",
    )
    cost = output.get("cost_receipt", {})
    _require(
        cost.get("approved_budget_units") == 0
        and cost.get("price_state") == "UNKNOWN_NOT_APPROVED"
        and cost.get("quota_state") == "UNKNOWN_NOT_APPROVED"
        and cost.get("automatic_plan_upgrades") == 0
        and cost.get("platform_requests") == 0,
        "Adapters009 cost receipt acceptance failed",
    )
    retention = output.get("retention_receipt", {})
    _require(
        retention.get("delete_revoke_flow") == "UNKNOWN_DISABLED"
        and retention.get("deletion_receipt") == "NOT_IMPLEMENTED"
        and retention.get("retention_period") == "UNKNOWN_NOT_APPROVED"
        and retention.get("receipt_sha256") == "f" * 64,
        "Adapters009 retention receipt acceptance failed",
    )
    unit = output.get("unit_suite", {})
    _require(
        unit.get("tests") == 18 and unit.get("errors") == 0 and unit.get("failures") == 0 and unit.get("skips") == 0,
        "Adapters009 unit acceptance failed",
    )
    return Check(
        "taobao_selected_scope_retention_checkpoint_and_kill_acceptance",
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
            "fake_liked_or_favorited_relations": chaos["fake_liked_or_favorited_relations"],
            "identified_item_success_percent": chaos["identified_item_success_percent"],
            "kill_runs": chaos["kill_runs"],
            "lost_ids": chaos["lost_ids"],
            "owner_canary": "NOT_RUN",
            "owner_confirmed_saved_current_relations": chaos["owner_confirmed_saved_current_relations"],
            "platform_calls": 0,
            "new_requests_after_revocation": blocked["new_requests_after_revocation"],
            "removed_relations": chaos["removed_relations"],
            "retention_receipts": 1,
            "retry_after_seconds": rate["retry_after_seconds"],
            "silent_losses": chaos["silent_losses"],
            "undocumented_signing_rejections": 11,
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
        digest.update(_read_blob_at(FINAL_COMMIT, path))
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered, "evidence contains private data")
    _require("Bearer" + " " not in rendered and "https://" not in rendered, "evidence contains URL or secret data")
    _require(re.search(r"/(?:Users|home)/[A-Za-z0-9._-]+/", rendered) is None, "evidence contains local path")


def write_evidence(checks: list[Check]) -> None:
    details = {item.name: item.details for item in checks}
    acceptance = details.get("taobao_selected_scope_retention_checkpoint_and_kill_acceptance", {})
    lane = details.get("full_lane_replay", {})
    _require(acceptance and lane, "final evidence requires acceptance and full lane")
    payload = {
        "acceptance_ids": ["ACC.x2n.tb.001", "ACC.x2n.tb.002", "ACC.x2n.batch.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.batch.001": "PASS_CI_SYNTH_NINE_NON_AUTHORITATIVE_REMOVED_ZERO_RETENTION_RECEIPT_ONE_RECONCILIATION_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.tb.001": "PASS_CI_SYNTH_OWNER_EXPLICIT_ITEM_GET_MINIMUM_FIELDS_20_OF_20_OWNER_CONFIRMED_SAVED_CURRENT_ZERO_FAKE_LIKE_FAVORITE_OWNER_CANARY_NOT_RUN",
            "ACC.x2n.tb.002": "PASS_CI_SYNTH_FIFTY_PROCESS_KILLS_ZERO_LOSS_DUPLICATE_FIVE_PLATFORM_KILLS_ZERO_UNDOCUMENTED_COOKIE_SIGNING_HTTP_429_RETRY_AFTER_HOLD",
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
            "fake_liked_or_favorited_relations": acceptance.get("fake_liked_or_favorited_relations"),
            "identified_item_success_percent": acceptance.get("identified_item_success_percent"),
            "kill_runs": acceptance.get("kill_runs"),
            "lost_ids": acceptance.get("lost_ids"),
            "new_requests_after_revocation": acceptance.get("new_requests_after_revocation"),
            "owner_confirmed_saved_current_relations": acceptance.get("owner_confirmed_saved_current_relations"),
            "removed_relations": acceptance.get("removed_relations"),
            "retention_receipts": acceptance.get("retention_receipts"),
            "retry_after_seconds": acceptance.get("retry_after_seconds"),
            "silent_losses": acceptance.get("silent_losses"),
            "undocumented_signing_rejections": acceptance.get("undocumented_signing_rejections"),
            "unit_tests": acceptance.get("unit_tests"),
        },
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json_at(FINAL_COMMIT, EVIDENCE)
    _require(EVIDENCE.read_bytes() == _read_blob_at(FINAL_COMMIT, EVIDENCE), "historical evidence was rewritten")
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
        and metrics.get("fake_liked_or_favorited_relations") == 0
        and metrics.get("identified_item_success_percent") == 100.0
        and metrics.get("kill_runs") == 50
        and metrics.get("lost_ids") == 0
        and metrics.get("new_requests_after_revocation") == 0
        and metrics.get("owner_confirmed_saved_current_relations") == 20
        and metrics.get("removed_relations") == 0
        and metrics.get("retention_receipts") == 1
        and metrics.get("retry_after_seconds") == 120
        and metrics.get("silent_losses") == 0
        and metrics.get("undocumented_signing_rejections") == 11
        and metrics.get("unit_tests") == 18
        and metrics.get("blocking_executions") == 24,
        "evidence metrics drifted",
    )
    return Check(
        "evidence",
        "PASS",
        {"receipt_sha256": hashlib.sha256(_read_blob_at(FINAL_COMMIT, EVIDENCE)).hexdigest(), "task": TASK_ID},
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
    _require(all(check.status == "PASS" for check in checks), "an Adapters009 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.009")
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
