#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.005."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
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
    "verify_adapters_009_for_adapters_005",
    PROJECT_ROOT / "scripts/verify_adapters_009.py",
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

TASK_ID = "TSK.x2n.adapters.005"
RUN_ID = "RUN-X2N-S03-A005"
PHASE = "PH.X2N.3.9"
BRANCH = "codex/xhs-douyin-2notion-v0001-s03-adapters005"
TASK_BASE_COMMIT = "8c6442a251f73e645e292a4e77dd03448d153b64"
ORIGIN_CUTOFF = PREVIOUS.ORIGIN_CUTOFF

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_005.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
POLICY = PROJECT_ROOT / "machine/policy/relation_reconciliation_policy.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/relation_reconciliation/fixture_manifest.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
COMPANION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/relation_reconciliation.py"
COMPANION_TEST = PROJECT_ROOT / "apps/companion/tests/test_relation_reconciliation.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
CHAOS_WORKER = PROJECT_ROOT / "scripts/relation_reconciliation_chaos_worker.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_005_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.005.json"

UNCHANGED_SECURITY_SURFACES = (
    PROJECT_ROOT / "apps/extension/manifest.json",
    PROJECT_ROOT / "apps/extension/src/service-worker.js",
    PROJECT_ROOT / "apps/companion/native-host/policy.json",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/xiaohongshu_favorites.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/xiaohongshu_likes.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/douyin_adapter.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/bilibili_selected.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/kuaishou_selected.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/weibo_selected.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/taobao_selected.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "package-lock.json",
    PROJECT_ROOT / "uv.lock",
    PREVIOUS.EVIDENCE,
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/src/x2n_companion/relation_reconciliation.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_relation_reconciliation.py",
    "docs/governance/RUN_CONTRACT_S03_ADAPTERS_005.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.adapters.005.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/relation_reconciliation_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/relation_reconciliation_chaos_worker.py",
    "scripts/run_adapters_005_acceptance.py",
    "scripts/verify_adapters_005.py",
    "scripts/verify_adapters_009.py",
    "tests/test_adapters_005.py",
    "tests/test_adapters_009.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/adapters/v1/relation_reconciliation/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    committed = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...HEAD"]).splitlines()
    working = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    relative_changes: list[str] = []
    for path in sorted(set(committed + working)):
        relative = _project_relative(path)
        _require(relative is not None, "Adapters005 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Adapters005 change: {relative}",
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
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Adapters005 worktree branch")
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
        "Adapters005 branch no longer descends from Adapters009",
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
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Adapters009 final pin differs from Adapters005 base")
    _require(
        PREVIOUS.EVIDENCE.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, PREVIOUS.EVIDENCE),
        "Adapters009 evidence was rewritten",
    )
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Adapters009 historical regression failed")
    PREVIOUS.verify_evidence()
    return Check(
        "adapters_009_fixed_predecessor",
        "PASS",
        {"evidence_mutations": 0, "historical_checks": len(checks) + 1, "predecessor_commit": TASK_BASE_COMMIT},
    )


def validate_task_and_state() -> Check:
    taskpack_text = TASKPACK.read_text(encoding="utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Adapters005 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.3" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on")
        == [
            "TSK.x2n.adapters.002",
            "TSK.x2n.adapters.003",
            "TSK.x2n.adapters.004",
            "TSK.x2n.adapters.006",
            "TSK.x2n.adapters.007",
            "TSK.x2n.adapters.008",
            "TSK.x2n.adapters.009",
            "TSK.x2n.foundation.003",
        ],
        "Adapters005 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.batch.001", "ACC.x2n.data.002", "ACC.x2n.rel.006"],
        "Adapters005 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    _require(
        _task_block(taskpack_text, "TSK.x2n.multimodal.001") == _task_block(base_taskpack, "TSK.x2n.multimodal.001"),
        "Stage 4 was entered by this Run",
    )
    taskpack = yaml.safe_load(taskpack_text)
    _require(isinstance(taskpack, dict), "Task Pack root must be an object")
    _require(
        taskpack.get("project", {}).get("status") == "STAGE_3_ADAPTERS_005_PASS_G3_NOT_RUN",
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
    _require(state.get("schema_version") == "1.27", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.3" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Adapters005 state is not pass")
    _require(
        state.get("next_phase") == "STG.X2N.3.REVIEW" and state.get("next_run") == "STG.X2N.3.REVIEW",
        "next Stage Review routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g3_pass",
        "G3/upload state overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.batch.001")
        == "pass_ci_synth_two_distinct_full_scans_candidate_10_removed_0_five_non_authoritative_relation_writes_0_50_process_kills_content_auto_delete_0",
        "batch Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.data.002")
        == "pass_ci_synth_reconciliation_80x2_100_concurrent_duplicate_content_relation_artifact_markdown_notion_page_0_real_notion_not_run",
        "idempotency Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.rel.006")
        == "tooling_ready_owner_alpha_not_run_owner_alpha_private_manifest_not_created_platform_calls_0",
        "Owner Alpha Acceptance was overstated or drifted",
    )
    _require(
        state.get("relation_reconciliation_execution")
        == "pass_ci_synth_xhs_authoritative_two_scan_state_machine_80x2_100_concurrent_50_process_kills_non_authoritative_no_write_owner_alpha_not_run",
        "reconciliation execution boundary drifted",
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
        _load_json(PROJECT_FACT).get("status") == "stage_3_adapters_005_pass_g3_not_run",
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
        "active -> unknown -> tombstone_candidate",
        "PASS_CI_SYNTH_SCOPED",
        "OWNER_ALPHA_NOT_RUN",
        "G3_NOT_RUN",
    ):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 3,
            "next_run": "STG.X2N.3.REVIEW",
            "owner_alpha": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
            "stage_gate": "G3_NOT_RUN",
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json(POLICY)
    flags = policy.get("feature_gate", {})
    _require(
        policy.get("policy_id") == "POLICY.X2N.RELATION-RECONCILIATION.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("phase") == PHASE
        and policy.get("reviewed_at") == "2026-07-23"
        and policy.get("default") == "deny"
        and flags.get("ci_synthetic_enabled") is True
        and flags.get("owner_alpha_enabled") is False
        and flags.get("production_enabled") is False
        and flags.get("real_account_execution") is False
        and flags.get("platform_requests") is False,
        "reconciliation policy identity or gate drifted",
    )
    scope = policy.get("scope", {})
    _require(
        scope.get("truth_source") == "local_sqlite_canonical_store"
        and scope.get("maximum_relations_per_scope") == 10_000
        and scope.get("cross_platform_scope") is False
        and scope.get("cross_relation_type_scope") is False
        and scope.get("physical_delete") is False
        and scope.get("content_auto_delete") is False
        and scope.get("removed_write") is False,
        "reconciliation scope boundary drifted",
    )
    sources = policy.get("authoritative_sources", {})
    _require(
        sources.get("xhs_favorites", {}).get("full_scan_permitted") is True
        and sources.get("xhs_likes", {}).get("full_scan_permitted") is True
        and sources.get("xhs_favorites", {}).get("required_observation_method") == "selected_collection"
        and sources.get("xhs_likes", {}).get("required_observation_method") == "selected_collection"
        and all(
            sources.get(name, {}).get("full_scan_permitted") is False
            for name in (
                "douyin_upstream",
                "bilibili_selected_collection",
                "kuaishou_selected_collection",
                "weibo_selected_collection",
                "taobao_selected_collection",
            )
        ),
        "authoritative source allowlist drifted",
    )
    proof = policy.get("full_scan_proof", {})
    _require(
        proof.get("empty_scan_permitted") is False
        and proof.get("distinct_source_run_required") is True
        and proof.get("strictly_newer_source_checkpoint_required") is True
        and proof.get("source_run_must_be_succeeded") is True
        and proof.get("source_run_checkpoint_reconciliation_time_must_be_ordered") is True
        and proof.get("source_relation_set_must_match_manifest") is True
        and proof.get("source_content_set_must_match_observations") is True
        and proof.get("source_observation_adapter_version_method_must_match") is True
        and proof.get("source_relations_must_be_scan_confirmed") is True
        and proof.get("relation_columns_payload_and_hash_must_match") is True,
        "full-scan proof drifted",
    )
    machine = policy.get("state_machine", {})
    _require(
        machine.get("first_consecutive_complete_missing") == "unknown"
        and machine.get("second_consecutive_distinct_complete_missing") == "tombstone_candidate"
        and machine.get("observed_again") == "active"
        and machine.get("removed_relation") == "preserve_removed"
        and machine.get("automatic_removed_transition") is False
        and machine.get("owner_confirmation_required_for_removed") is True
        and machine.get("physical_delete_transition") is False,
        "relation state machine drifted",
    )
    non_authoritative = policy.get("non_authoritative_outcomes", {})
    _require(
        set(non_authoritative) == {"auth_expired", "http_error", "platform_changed", "empty_response", "partial_scan"}
        and set(non_authoritative.values()) == {"clear_pending_chain_no_relation_write"},
        "non-authoritative outcome policy drifted",
    )
    durability = policy.get("durability", {})
    _require(
        durability.get("state_store") == "checkpoint.cursor_value_private"
        and durability.get("event_ledger") == "run_record"
        and durability.get("transaction") == "sqlite_begin_immediate"
        and durability.get("exact_event_replay") == "return_replayed_no_write"
        and durability.get("succeeded_run_requires_existing_scope_checkpoint") is True
        and durability.get("cursor_last_event_requires_succeeded_run") is True
        and durability.get("pending_relation_keys_must_be_unknown_or_currently_observed_active_in_scope") is True
        and durability.get("process_kill_before_commit") == "rollback_all_relation_run_checkpoint_changes",
        "reconciliation durability contract drifted",
    )
    public_receipt = policy.get("public_receipt", {})
    _require(
        all(
            public_receipt.get(field) is False
            for field in (
                "relation_keys",
                "account_ref_hash",
                "source_checkpoint_id",
                "source_scan_receipt_id",
                "local_paths",
                "credentials",
                "media_urls",
            )
        )
        and public_receipt.get("hashed_scope_and_source_refs_only") is True,
        "public receipt boundary drifted",
    )
    owner_alpha = policy.get("owner_alpha", {})
    _require(
        owner_alpha.get("execution") == "NOT_RUN"
        and owner_alpha.get("item_count") == 80
        and owner_alpha.get("private_manifest_required") is True
        and sum(owner_alpha.get("scopes", {}).values()) == 80
        and owner_alpha.get("public_plan_contains_relation_keys") is False
        and owner_alpha.get("platform_calls") == 0,
        "Owner Alpha tooling boundary drifted",
    )

    source = COMPANION_SOURCE.read_text(encoding="utf-8")
    cli = CLI_SOURCE.read_text(encoding="utf-8")
    for token in (
        "class ReconciliationManifest",
        "class ReconciliationReceipt",
        "class RelationReconciler",
        "SOURCE_RULES",
        "authoritative_visible_end",
        "last_source_checkpoint_at",
        "pending_missing_relation_keys",
        "RelationStatus.UNKNOWN",
        "RelationStatus.TOMBSTONE_CANDIDATE",
        "build_owner_alpha_80_manifest_plan",
        '"owner_alpha": "NOT_RUN"',
        '"physical_deletes": 0',
        '"removed_writes": 0',
    ):
        _require(token in source, f"reconciliation implementation contract missing: {token}")
    for forbidden in ("DELETE FROM user_relation", "DELETE FROM content", "requests.", "httpx.", "playwright"):
        _require(forbidden not in source, f"forbidden reconciliation behavior entered implementation: {forbidden}")
    _require(
        'subparsers.add_parser("reconcile")' in cli
        and 'reconcile_actions.add_parser("owner-alpha-plan")' in cli
        and "build_owner_alpha_80_manifest_plan" in cli,
        "non-executing Owner Alpha CLI is missing",
    )
    for path in UNCHANGED_SECURITY_SURFACES:
        _require(path.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, path), "security surface changed: " + path.name)
    artifact = _load_json(ARTIFACT_POLICY)
    enforcement = artifact.get("enforcement", [])
    for required in (
        "scripts/relation_reconciliation_chaos_worker.py",
        "scripts/run_adapters_005_acceptance.py",
        "scripts/verify_adapters_005.py",
    ):
        _require(required in enforcement, f"Adapters005 enforcement is not registered: {required}")
    return Check(
        "authoritative_scan_policy_and_reconciliation_containment",
        "PASS",
        {
            "authoritative_sources": 2,
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "bounded_sources_blocked_from_full_scan": 5,
            "owner_alpha": "NOT_RUN",
            "physical_delete_paths": 0,
            "platform_calls": 0,
            "production_enabled": False,
            "removed_write_paths": 0,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json(FIXTURE)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S03.A005.001" and fixture.get("synthetic") is True,
        "Adapters005 fixture identity drifted",
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
    source = fixture.get("authoritative_source_contract", {})
    _require(
        source.get("permitted_sources") == ["xhs_favorites", "xhs_likes"]
        and len(source.get("blocked_full_scan_sources", [])) == 5
        and source.get("required_checkpoint_state") == "complete"
        and source.get("required_cursor_kind") == "authoritative_visible_end"
        and source.get("required_confidence") == 1.0
        and source.get("exact_receipt_relation_observation_graph") is True
        and source.get("distinct_strictly_newer_source_scan") is True
        and source.get("empty_full_scan") is False,
        "fixture full-scan contract drifted",
    )
    machine = fixture.get("state_machine", {})
    _require(
        machine.get("initial_scope_relations") == 40
        and machine.get("observed_relations_per_missing_scan") == 30
        and machine.get("missing_relations") == 10
        and machine.get("expected_unknown_after_first_complete_missing_scan") == 10
        and machine.get("expected_candidates_after_second_complete_missing_scan") == 10
        and machine.get("expected_removed_relations") == 0
        and machine.get("expected_content_auto_deletes") == 0
        and machine.get("expected_physical_deletes") == 0
        and machine.get("same_source_scan_relabelled_expected_blocks") == 1,
        "fixture state machine drifted",
    )
    non_authoritative = fixture.get("non_authoritative", {})
    _require(
        len(non_authoritative.get("outcomes", [])) == 5
        and non_authoritative.get("expected_pending_chain_after_each") == 0
        and non_authoritative.get("expected_relation_writes") == 0
        and non_authoritative.get("expected_removed_writes") == 0,
        "fixture non-authoritative contract drifted",
    )
    idempotency = fixture.get("idempotency", {})
    _require(
        idempotency.get("input_items") == 80
        and idempotency.get("sequential_runs") == 2
        and idempotency.get("concurrent_duplicate_messages") == 100
        and idempotency.get("expected_concurrent_replays") == 100
        and all(
            idempotency.get(field) == 0
            for field in (
                "expected_duplicate_content",
                "expected_duplicate_relations",
                "expected_duplicate_artifacts",
                "expected_duplicate_markdown",
                "expected_duplicate_notion_pages",
            )
        ),
        "fixture idempotency contract drifted",
    )
    chaos = fixture.get("chaos", {})
    _require(
        chaos.get("seed") == 5005
        and chaos.get("kill_runs") == 50
        and chaos.get("required_kill_boundaries")
        == [
            "before_reconciliation",
            "after_observed_row",
            "after_missing_row",
            "before_checkpoint",
            "after_checkpoint",
            "before_commit",
        ]
        and chaos.get("expected_lost_status_transitions") == 0
        and chaos.get("expected_partial_relation_writes") == 0
        and chaos.get("expected_checkpoint_advances_before_commit") == 0
        and chaos.get("expected_duplicate_reconciliation_runs") == 0
        and chaos.get("expected_synthetic_chaos_manifest_residuals") == 0,
        "fixture chaos contract drifted",
    )
    owner = fixture.get("owner_alpha_tooling", {})
    _require(
        owner.get("execution") == "NOT_RUN"
        and owner.get("item_count") == 80
        and owner.get("private_manifest_created") is False
        and owner.get("public_relation_keys") == 0
        and owner.get("platform_calls") == 0,
        "fixture Owner Alpha boundary drifted",
    )
    cases = fixture.get("cases", [])
    _require(len(cases) == 40 and len(set(cases)) == 40, "Adapters005 fixture cases drifted")
    global_manifest = _load_json(GLOBAL_FIXTURE_MANIFEST)
    _require(
        global_manifest.get("manifest_id") == "FIXTURE.X2N.019" and global_manifest.get("phase") == PHASE,
        "global fixture manifest identity drifted",
    )
    _require(
        {
            "id": "FIXTURE.X2N.S03.A005.001",
            "path": "packages/test-fixtures/adapters/v1/relation_reconciliation/fixture_manifest.json",
            "case_count": 40,
            "purpose": "Two-distinct-authoritative-scan reconciliation, five non-authoritative no-write outcomes, 80x2 plus 100 duplicate idempotency, stable collection identity and 50 process-kill recovery",
        }
        in global_manifest.get("fixtures", []),
        "Adapters005 fixture is not globally registered",
    )
    return Check(
        "synthetic_reconciliation_state_idempotency_and_chaos_fixtures",
        "PASS",
        {
            "contract_cases": len(cases),
            "concurrent_duplicates": idempotency["concurrent_duplicate_messages"],
            "input_items": idempotency["input_items"],
            "kill_runs": chaos["kill_runs"],
            "non_authoritative_cases": len(non_authoritative["outcomes"]),
            "owner_alpha": "NOT_RUN",
            "platform_calls": 0,
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a005-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        output = _json_line(
            _run_external(
                "adapters_005_acceptance",
                (sys.executable, "-B", str(ACCEPTANCE_RUNNER)),
                env=_isolated_env(home),
                timeout=900,
            ),
            "Adapters005 acceptance",
        )
    expected = {
        "acceptance_scope": "ADAPTERS_005_RELATION_RECONCILIATION_CI_SYNTH",
        "automatic_pagination": 0,
        "automatic_scroll": 0,
        "model_calls": 0,
        "owner_alpha": "NOT_RUN",
        "owner_alpha_private_manifest": "NOT_CREATED",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "status": "PASS_CI_SYNTH_SCOPED",
        "synthetic_chaos_manifest": "TEMPORARY_TEST_ONLY_REMOVED",
        "task_id": TASK_ID,
    }
    for field, value in expected.items():
        _require(output.get(field) == value, f"Adapters005 acceptance metric drifted: {field}")
    batch = output.get("batch_protection", {})
    _require(
        batch.get("checkpoint_advances_before_commit") == 0
        and batch.get("content_auto_deletes") == 0
        and batch.get("critical_kill_boundaries_covered") == 6
        and batch.get("lost_status_transitions") == 0
        and batch.get("non_authoritative_cases") == 5
        and batch.get("non_authoritative_removed_writes") == 0
        and batch.get("physical_deletes") == 0
        and batch.get("process_kills") == 50
        and batch.get("relabelled_source_scan_blocks") == 1
        and batch.get("removed_relations") == 0
        and batch.get("synthetic_chaos_manifest_residuals") == 0
        and batch.get("tombstone_candidates") == 10
        and batch.get("unknown_after_first_missing_scan") == 10,
        "Adapters005 batch protection acceptance failed",
    )
    idempotency = output.get("idempotency", {})
    _require(
        idempotency.get("input_items") == 80
        and idempotency.get("sequential_runs") == 2
        and idempotency.get("concurrent_duplicate_messages") == 100
        and idempotency.get("concurrent_replays") == 100
        and all(
            idempotency.get(field) == 0
            for field in (
                "content_duplicates",
                "relation_duplicates",
                "artifact_duplicates",
                "markdown_duplicates",
                "notion_page_duplicates",
            )
        ),
        "Adapters005 idempotency acceptance failed",
    )
    integrity = output.get("integrity", {})
    _require(
        integrity.get("integrity_check") == "ok"
        and integrity.get("foreign_key_violations") == 0
        and integrity.get("orphan_relations") == 0,
        "Adapters005 Canonical integrity acceptance failed",
    )
    plan = output.get("owner_alpha_tooling", {})
    _require(
        plan.get("acceptance_id") == "ACC.x2n.rel.006"
        and plan.get("execution") == "NOT_RUN"
        and plan.get("item_count") == 80
        and sum(item.get("count", 0) for item in plan.get("scopes", [])) == 80
        and plan.get("relation_keys_in_plan") == 0
        and plan.get("platform_calls") == 0,
        "Adapters005 Owner Alpha tooling acceptance failed",
    )
    unit = output.get("unit_suite", {})
    _require(
        unit.get("tests") == 15 and unit.get("errors") == 0 and unit.get("failures") == 0 and unit.get("skips") == 0,
        "Adapters005 unit acceptance failed",
    )
    return Check(
        "relation_reconciliation_state_idempotency_checkpoint_and_kill_acceptance",
        "PASS",
        {
            "automatic_pagination": 0,
            "automatic_scroll": 0,
            "candidate_relations": batch["tombstone_candidates"],
            "concurrent_duplicates": idempotency["concurrent_duplicate_messages"],
            "duplicate_entities": 0,
            "input_items": idempotency["input_items"],
            "kill_runs": batch["process_kills"],
            "non_authoritative_cases": batch["non_authoritative_cases"],
            "owner_alpha": "NOT_RUN",
            "physical_deletes": batch["physical_deletes"],
            "platform_calls": 0,
            "relabelled_source_scan_blocks": batch["relabelled_source_scan_blocks"],
            "removed_relations": batch["removed_relations"],
            "synthetic_chaos_manifest_residuals": batch["synthetic_chaos_manifest_residuals"],
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
    acceptance = details.get("relation_reconciliation_state_idempotency_checkpoint_and_kill_acceptance", {})
    lane = details.get("full_lane_replay", {})
    _require(acceptance and lane, "final evidence requires acceptance and full lane")
    payload = {
        "acceptance_ids": ["ACC.x2n.batch.001", "ACC.x2n.data.002", "ACC.x2n.rel.006"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.batch.001": "PASS_CI_SYNTH_TWO_DISTINCT_FULL_SCANS_CANDIDATE_TEN_REMOVED_ZERO_FIVE_NON_AUTHORITATIVE_NO_WRITE_FIFTY_KILLS",
            "ACC.x2n.data.002": "PASS_CI_SYNTH_RECONCILIATION_80X2_100_CONCURRENT_DUPLICATE_ENTITIES_ZERO_REAL_NOTION_NOT_RUN",
            "ACC.x2n.rel.006": "TOOLING_READY_OWNER_ALPHA_NOT_RUN_OWNER_ALPHA_PRIVATE_MANIFEST_NOT_CREATED",
        },
        "checks": [{"name": item.name, "status": item.status, "details": item.details} for item in checks],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "owner_alpha": "NOT_RUN",
        "owner_alpha_private_manifest_created": False,
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
            "candidate_relations": acceptance.get("candidate_relations"),
            "concurrent_duplicates": acceptance.get("concurrent_duplicates"),
            "coverage_percent": lane.get("coverage_percent"),
            "duplicate_entities": acceptance.get("duplicate_entities"),
            "input_items": acceptance.get("input_items"),
            "kill_runs": acceptance.get("kill_runs"),
            "non_authoritative_cases": acceptance.get("non_authoritative_cases"),
            "physical_deletes": acceptance.get("physical_deletes"),
            "relabelled_source_scan_blocks": acceptance.get("relabelled_source_scan_blocks"),
            "removed_relations": acceptance.get("removed_relations"),
            "synthetic_chaos_manifest_residuals": acceptance.get("synthetic_chaos_manifest_residuals"),
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
        and evidence.get("owner_alpha") == "NOT_RUN"
        and evidence.get("real_account_execution") == "NOT_RUN"
        and evidence.get("platform_calls") == 0,
        "real Profile/account execution overstated",
    )
    _require(
        evidence.get("profile_path_included") is False
        and evidence.get("private_content_included") is False
        and evidence.get("owner_alpha_private_manifest_created") is False,
        "evidence contains private scope",
    )
    _require(evidence.get("acceptance_input_sha256") == _acceptance_input_receipt(), "evidence input receipt is stale")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains failed check")
    metrics = evidence.get("task_metrics", {})
    _require(
        metrics.get("automatic_pagination") == 0
        and metrics.get("automatic_scroll") == 0
        and metrics.get("candidate_relations") == 10
        and metrics.get("concurrent_duplicates") == 100
        and metrics.get("duplicate_entities") == 0
        and metrics.get("input_items") == 80
        and metrics.get("kill_runs") == 50
        and metrics.get("non_authoritative_cases") == 5
        and metrics.get("physical_deletes") == 0
        and metrics.get("relabelled_source_scan_blocks") == 1
        and metrics.get("removed_relations") == 0
        and metrics.get("synthetic_chaos_manifest_residuals") == 0
        and metrics.get("unit_tests") == 15
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
    _require(all(check.status == "PASS" for check in checks), "an Adapters005 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.005")
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
                {"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
