#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.003."""

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
    "verify_adapters_002_for_adapters_003",
    PROJECT_ROOT / "scripts/verify_adapters_002.py",
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

TASK_ID = "TSK.x2n.adapters.003"
RUN_ID = "RUN-X2N-S03-A003"
PHASE = "PH.X2N.3.3"
BRANCH = "codex/xhs-douyin-2notion-v0001-s03-adapters003"
TASK_BASE_COMMIT = "050ec0c93ff4b1d6020a5c8e12f79320fc401f53"
ORIGIN_CUTOFF = PREVIOUS.ORIGIN_CUTOFF
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_003.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
POLICY = PROJECT_ROOT / "machine/policy/xhs_likes_policy.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/xhs_likes/fixture_manifest.json"
DOM_FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/xhs_likes/dom/fixture_manifest.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
EXTENSION_SOURCE = PROJECT_ROOT / "apps/extension/src/xhs-likes.js"
EXTENSION_RUNNER = PROJECT_ROOT / "apps/extension/scripts/xhs-likes-fixture-e2e.mjs"
EXTENSION_PACKAGE = PROJECT_ROOT / "apps/extension/package.json"
COMPANION_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/xiaohongshu_likes.py"
COMPANION_TEST = PROJECT_ROOT / "apps/companion/tests/test_xiaohongshu_likes.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
CHAOS_WORKER = PROJECT_ROOT / "scripts/xhs_likes_chaos_worker.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_003_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.003.json"

UNCHANGED_SECURITY_SURFACES = (
    PROJECT_ROOT / "apps/extension/manifest.json",
    PROJECT_ROOT / "apps/extension/src/service-worker.js",
    PROJECT_ROOT / "apps/companion/native-host/policy.json",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "package-lock.json",
    PROJECT_ROOT / "uv.lock",
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/src/x2n_companion/xiaohongshu_likes.py",
    "apps/companion/tests/test_xiaohongshu_likes.py",
    "apps/extension/package.json",
    "apps/extension/scripts/xhs-likes-fixture-e2e.mjs",
    "apps/extension/src/xhs-likes.js",
    "docs/governance/RUN_CONTRACT_S03_ADAPTERS_003.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.adapters.003.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/policy/xhs_likes_policy.json",
    "scripts/run_adapters_003_acceptance.py",
    "scripts/verify_adapters_002.py",
    "scripts/verify_adapters_003.py",
    "scripts/xhs_likes_chaos_worker.py",
    "tests/test_adapters_002.py",
    "tests/test_adapters_003.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/adapters/v1/xhs_likes/",)


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    committed = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...HEAD"]).splitlines()
    working = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    relative_changes: list[str] = []
    for path in sorted(set(committed + working)):
        relative = _project_relative(path)
        _require(relative is not None, "Adapters003 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Adapters003 change: {relative}",
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
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Adapters003 worktree branch")
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
        "Adapters003 branch no longer descends from Adapters002",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the Stage 2 merge cutoff",
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
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Adapters002 final pin differs from Adapters003 base")
    _require(
        PREVIOUS.EVIDENCE.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, PREVIOUS.EVIDENCE),
        "Adapters002 evidence was rewritten",
    )
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Adapters002 historical regression failed")
    PREVIOUS.verify_evidence()
    return Check(
        "adapters_002_fixed_predecessor",
        "PASS",
        {
            "evidence_mutations": 0,
            "historical_checks": len(checks) + 1,
            "predecessor_commit": TASK_BASE_COMMIT,
        },
    )


def validate_task_and_state() -> Check:
    taskpack_text = TASKPACK.read_text(encoding="utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Adapters003 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.3" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.adapters.001", "TSK.x2n.skeleton.001", "TSK.x2n.skeleton.004"],
        "Adapters003 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.xhs.002", "ACC.x2n.xhs.003", "ACC.x2n.batch.001"],
        "Adapters003 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    _require(
        _task_block(taskpack_text, "TSK.x2n.adapters.004") == _task_block(base_taskpack, "TSK.x2n.adapters.004"),
        "Adapters004 was entered by this Run",
    )
    taskpack = yaml.safe_load(taskpack_text)
    _require(isinstance(taskpack, dict), "Task Pack root must be an object")
    _require(
        taskpack.get("project", {}).get("status") == "STAGE_3_ADAPTERS_003_PASS_G3_NOT_RUN",
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
    _require(state.get("schema_version") == "1.21", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.3" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Adapters003 state is not pass")
    _require("TSK.x2n.adapters.004" not in state.get("tasks", {}), "Adapters004 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.3.4" and state.get("next_run") == "TSK.x2n.adapters.004",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g3_pass",
        "G3/upload state overstated",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.xhs.002")
        == "pass_ci_synth_dom_unclassified_inbox_duplicate_content_0_canary_tooling_owner_alpha_not_run_real_page_disabled",
        "XHS likes Owner Acceptance boundary drifted",
    )
    _require(
        acceptance.get("ACC.x2n.xhs.003") == "pass_ci_synth_100_items_50_process_kills_exact_resume_auto_scroll_0",
        "XHS checkpoint Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.batch.001")
        == "pass_ci_synth_5_non_authoritative_removed_0_adapter003_physical_content_and_unlike_delete_0_reconciliation_downstream_not_run",
        "batch Acceptance drifted",
    )
    _require(
        state.get("xhs_likes_execution")
        == "pass_ci_synth_visible_dom_100_items_50_process_kills_unclassified_inbox_20_favorite_overlap_canary_tooling_owner_alpha_not_run_real_page_disabled",
        "XHS likes execution boundary drifted",
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
        _load_json(PROJECT_FACT).get("status") == "stage_3_adapters_003_pass_g3_not_run",
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
    for value in (TASK_ID, RUN_ID, PHASE, TASK_BASE_COMMIT, BRANCH, "PASS_CI_SYNTH_SCOPED"):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 3,
            "next_task": "TSK.x2n.adapters.004",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
            "stage_gate": "G3_NOT_RUN",
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json(POLICY)
    _require(
        policy.get("policy_id") == "POLICY.X2N.XHS-LIKES.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("default") == "deny",
        "XHS likes policy identity drifted",
    )
    research = policy.get("official_research", {})
    _require(
        research.get("personal_ui_self_access") == "documented_for_my_notes_favorites_and_likes"
        and research.get("personal_likes_read_api") == "not_found_in_reviewed_official_sources"
        and research.get("inference_not_claim_of_nonexistence") is True
        and len(research.get("sources", [])) == 4,
        "official research boundary drifted",
    )
    flags = policy.get("feature_gate", {})
    clean = policy.get("clean_room", {})
    inbox = policy.get("inbox_policy", {})
    identity = policy.get("canonical_identity", {})
    checkpoint = policy.get("checkpoint", {})
    deletion = policy.get("deletion_protection", {})
    canary = policy.get("canary", {})
    _require(
        flags.get("flag") == "xhs_likes"
        and flags.get("ci_synthetic_enabled") is True
        and flags.get("owner_canary_enabled") is False
        and flags.get("production_enabled") is False
        and flags.get("current_page_fallback_preserved") is True,
        "XHS likes feature gate drifted",
    )
    _require(
        clean.get("chrome_permission") == "activeTab_after_explicit_owner_action"
        and clean.get("host_permissions") == 0
        and clean.get("static_content_scripts") == 0
        and clean.get("network_transport") is False
        and clean.get("private_or_undocumented_endpoint") is False
        and clean.get("cookie_or_credential_access") is False
        and clean.get("browser_profile_read") is False
        and clean.get("automatic_scroll") is False
        and clean.get("automatic_pagination") is False
        and clean.get("event_synthesis") is False
        and clean.get("account_state_change") is False
        and clean.get("unlike_or_like_mutation") is False
        and clean.get("verification_bypass") is False
        and clean.get("max_visible_items_per_action") == 20
        and clean.get("max_concurrent_adapters") == 1
        and clean.get("automatic_retry") is False,
        "clean-room policy drifted",
    )
    _require(
        inbox.get("default_disposition") == "unclassified"
        and inbox.get("automatic_filing") is False
        and inbox.get("automatic_classification_writes") == 0
        and inbox.get("taxonomy_mutations") == 0
        and inbox.get("ai_top_level_category_creation") is False
        and inbox.get("existing_owner_classification_preserved") is True,
        "conservative Inbox policy drifted",
    )
    _require(
        identity.get("content_key") == "platform_plus_stable_content_id"
        and identity.get("relation_key") == "account_plus_content_plus_liked"
        and identity.get("liked_and_favorited_may_coexist") is True
        and identity.get("duplicate_content_rows_allowed") == 0
        and identity.get("source_collection_for_liked") is None,
        "Content/relation identity drifted",
    )
    _require(
        checkpoint.get("canonical_store") == "sqlite"
        and checkpoint.get("resume_compatibility_version") == "xhs-likes-1.0.0"
        and checkpoint.get("unknown_or_partial_advances_cursor") is False
        and checkpoint.get("bounded_canary_is_full_scan") is False
        and checkpoint.get("full_scan_requires_authoritative_visible_end") is True
        and checkpoint.get("false_full_scan_allowed") == 0,
        "checkpoint policy drifted",
    )
    _require(
        len(deletion.get("non_authoritative_outcomes", [])) == 5
        and deletion.get("removed_count") == 0
        and deletion.get("physical_delete_count") == 0
        and deletion.get("automatic_content_delete_count") == 0
        and deletion.get("unlike_automation_count") == 0
        and deletion.get("relation_reconciliation_owner_task") == "TSK.x2n.adapters.005",
        "deletion policy drifted",
    )
    _require(
        canary.get("item_limit") == 20
        and canary.get("tooling_available") is True
        and canary.get("execution") == "NOT_RUN"
        and canary.get("private_gold_manifest_in_repository") is False,
        "Canary boundary drifted",
    )

    extension = EXTENSION_SOURCE.read_text(encoding="utf-8")
    companion = COMPANION_SOURCE.read_text(encoding="utf-8")
    cli = CLI_SOURCE.read_text(encoding="utf-8")
    runner = EXTENSION_RUNNER.read_text(encoding="utf-8")
    for token in (
        "extractXhsLikesVisibleBatch",
        "validateXhsLikesBatch",
        "const maxItems = 20",
        "automatic_scroll: false",
        "explicit_owner_action: true",
        'disposition: "unclassified"',
        "taxonomy_mutation: false",
        "bounded_limit_reached",
        "authoritative_end",
    ):
        _require(token in extension, f"Extension implementation missing: {token}")
    for forbidden in (
        "fetch(",
        "XMLHttpRequest",
        "document.cookie",
        "chrome.cookies",
        "scrollIntoView(",
        "scrollTo(",
        "scrollBy(",
    ):
        _require(forbidden not in extension, f"forbidden Extension surface entered: {forbidden}")
    for token in (
        "class XhsLikesAdapter",
        "class XhsLikesBatchCoordinator",
        'RESUME_COMPATIBILITY_VERSION = "xhs-likes-1.0.0"',
        'inbox_disposition: Literal["unclassified"]',
        "RelationType.LIKED",
        "source_collection_id=None",
        'automatic_classification_writes": 0',
        'taxonomy_mutations": 0',
        "full_scan_id = None",
    ):
        _require(token in companion, f"Companion implementation missing: {token}")
    for forbidden in ("requests.get(", "urllib.request", "httpx.", "selenium", "playwright"):
        _require(forbidden not in companion, f"forbidden Companion transport entered: {forbidden}")
    _require(
        'subparsers.add_parser("xhs-likes")' in cli
        and 'likes_actions.add_parser("canary-plan")' in cli
        and "build_xhs_likes_canary_plan" in cli,
        "non-executing Canary CLI is missing",
    )
    _require(
        "page.route" in runner
        and "unexpectedRequests.length === 0" in runner
        and "network_calls: unexpectedRequests.length" in runner,
        "DOM runner isolation is missing",
    )
    package = _load_json(EXTENSION_PACKAGE)
    _require(
        package.get("scripts", {}).get("test:xhs-likes-fixtures") == "node scripts/xhs-likes-fixture-e2e.mjs",
        "Extension fixture script is not registered",
    )
    for path in UNCHANGED_SECURITY_SURFACES:
        _require(path.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, path), f"security surface changed: {path.name}")
    artifact = _load_json(ARTIFACT_POLICY)
    enforcement = artifact.get("enforcement", [])
    for required in (
        "apps/extension/scripts/xhs-likes-fixture-e2e.mjs",
        "scripts/run_adapters_003_acceptance.py",
        "scripts/verify_adapters_003.py",
    ):
        _require(required in enforcement, f"Adapters003 enforcement is not registered: {required}")
    return Check(
        "clean_room_inbox_policy_and_implementation",
        "PASS",
        {
            "automatic_classification_writes": 0,
            "automatic_pagination": 0,
            "automatic_scrolls": 0,
            "canary_item_limit": 20,
            "host_permissions": 0,
            "network_transports": 0,
            "owner_canary": "NOT_RUN",
            "production_enabled": False,
            "sqlite_migrations": 0,
            "taxonomy_mutations": 0,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json(FIXTURE)
    dom = _load_json(DOM_FIXTURE)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S03.A003.001"
        and fixture.get("synthetic") is True
        and dom.get("fixture_id") == "FIXTURE.X2N.S03.A003.DOM.001"
        and dom.get("synthetic") is True,
        "Adapters003 fixture identity drifted",
    )
    for field in (
        "contains_accounts",
        "contains_cookies",
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
    ):
        _require(fixture.get(field) is False and dom.get(field) is False, f"fixture privacy drifted: {field}")
    chaos = fixture.get("chaos", {})
    _require(
        chaos.get("item_count") == 100
        and chaos.get("batch_size") == 20
        and chaos.get("owner_actions") == 5
        and chaos.get("kill_runs") == 50
        and chaos.get("favorite_overlap_items") == 20
        and chaos.get("expected_content_rows") == 100
        and chaos.get("expected_liked_relations") == 100
        and chaos.get("expected_favorited_relations") == 20
        and chaos.get("expected_total_relations") == 120
        and chaos.get("automatic_scrolls") == 0
        and chaos.get("expected_lost_ids") == 0
        and chaos.get("expected_duplicate_content_rows") == 0
        and chaos.get("expected_duplicate_side_effects") == 0
        and chaos.get("expected_infinite_loops") == 0,
        "chaos fixture drifted",
    )
    inbox = fixture.get("inbox_policy", {})
    _require(
        inbox.get("disposition") == "unclassified"
        and inbox.get("automatic_filing") is False
        and inbox.get("automatic_classification_writes") == 0
        and inbox.get("taxonomy_mutations") == 0,
        "Inbox fixture drifted",
    )
    non_authoritative = fixture.get("non_authoritative_cases", [])
    _require(
        len(non_authoritative) == 5 and all(row.get("removed") == 0 for row in non_authoritative),
        "deletion fixture drifted",
    )
    cases = dom.get("cases", [])
    _require(len(cases) == 7 and len({row.get("id") for row in cases}) == 7, "DOM fixture cases drifted")
    _require(sum(row.get("expected", {}).get("status") == "ready" for row in cases) == 2, "DOM ready cases drifted")
    for row in cases:
        path = DOM_FIXTURE.parent / str(row.get("file"))
        _require(path.is_file(), "DOM fixture file is missing")
        rendered = path.read_text(encoding="utf-8")
        _require("http://" not in rendered, "DOM fixture contains an insecure URL")
    global_rows = _load_json(GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S03.A003.001",
            "path": "packages/test-fixtures/adapters/v1/xhs_likes/fixture_manifest.json",
            "case_count": 107,
            "purpose": "Xiaohongshu visible likes DOM, conservative unclassified Inbox, 20 favorite overlaps, 100-item durable checkpoint and 50 process-kill recovery",
        }
        in global_rows,
        "Adapters003 fixture is not globally registered",
    )
    return Check(
        "synthetic_dom_identity_inbox_checkpoint_and_deletion_fixtures",
        "PASS",
        {
            "automatic_scrolls": 0,
            "chaos_items": 100,
            "dom_cases": 7,
            "favorite_overlap_items": 20,
            "kill_runs": 50,
            "non_authoritative_cases": 5,
            "removed_relations": 0,
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a003-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        output = _json_line(
            _run_external(
                "adapters_003_acceptance",
                (sys.executable, "-B", str(ACCEPTANCE_RUNNER)),
                env=_isolated_env(home),
                timeout=900,
            ),
            "Adapters003 acceptance",
        )
    expected = {
        "acceptance_scope": "ADAPTERS_003_XHS_LIKES_CI_SYNTH",
        "automatic_scrolls": 0,
        "canary_item_limit": 20,
        "canary_tooling": "PASS_NONEXECUTING",
        "identified_item_success_percent": 100,
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
        _require(output.get(field) == value, f"Adapters003 acceptance metric drifted: {field}")
    chaos = output.get("chaos", {})
    _require(
        chaos.get("kill_runs") == 50
        and chaos.get("final_id_set_exact") is True
        and chaos.get("lost_ids") == 0
        and chaos.get("duplicate_content_rows") == 0
        and chaos.get("duplicate_side_effects") == 0
        and chaos.get("infinite_loops") == 0
        and chaos.get("resume_from_durable_checkpoint") is True
        and chaos.get("content_count") == 100
        and chaos.get("liked_relation_count") == 100
        and chaos.get("favorited_relation_count") == 20
        and chaos.get("relation_count") == 120
        and chaos.get("likes_observation_count") == 100
        and chaos.get("observation_count") == 120
        and chaos.get("automatic_classification_writes") == 0
        and chaos.get("taxonomy_mutations") == 0
        and chaos.get("removed_relations") == 0
        and chaos.get("tombstone_candidates") == 0
        and chaos.get("physical_deletes") == 0
        and chaos.get("content_auto_deletes") == 0,
        "Adapters003 chaos acceptance failed",
    )
    dom = output.get("dom", {})
    _require(
        dom.get("status") == "PASS"
        and dom.get("fixture_cases") == 7
        and dom.get("identified_items") == 8
        and dom.get("error_evidence") == 5
        and dom.get("network_calls") == 0
        and dom.get("platform_calls") == 0,
        "Adapters003 DOM acceptance failed",
    )
    unit = output.get("unit_suite", {})
    _require(
        unit.get("tests") == 14 and unit.get("errors") == 0 and unit.get("failures") == 0 and unit.get("skips") == 0,
        "Adapters003 unit acceptance failed",
    )
    return Check(
        "xhs_likes_acceptance",
        "PASS",
        {
            "automatic_classification_writes": 0,
            "automatic_scrolls": 0,
            "canary_item_limit": 20,
            "chaos_items": 100,
            "content_count": 100,
            "dom_cases": 7,
            "duplicate_content_rows": 0,
            "duplicate_side_effects": 0,
            "favorited_relations": 20,
            "kill_runs": 50,
            "liked_relations": 100,
            "lost_ids": 0,
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "removed_relations": 0,
            "taxonomy_mutations": 0,
            "unit_tests": 14,
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
        DOM_FIXTURE,
        EXTENSION_SOURCE,
        EXTENSION_RUNNER,
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
    acceptance = details.get("xhs_likes_acceptance", {})
    lane = details.get("full_lane_replay", {})
    _require(acceptance and lane, "final evidence requires acceptance and full lane")
    payload = {
        "acceptance_ids": ["ACC.x2n.xhs.002", "ACC.x2n.xhs.003", "ACC.x2n.batch.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.batch.001": "PASS_CI_SYNTH_NON_AUTHORITATIVE_REMOVED_0_RECONCILIATION_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.xhs.002": "PASS_CI_SYNTH_DOM_UNCLASSIFIED_INBOX_OWNER_ALPHA_NOT_RUN",
            "ACC.x2n.xhs.003": "PASS_CI_SYNTH_100_ITEMS_50_PROCESS_KILLS_EXACT_RESUME",
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
            "automatic_classification_writes": acceptance.get("automatic_classification_writes"),
            "automatic_scrolls": acceptance.get("automatic_scrolls"),
            "blocking_executions": lane.get("blocking_executions"),
            "canary_item_limit": acceptance.get("canary_item_limit"),
            "chaos_items": acceptance.get("chaos_items"),
            "content_count": acceptance.get("content_count"),
            "coverage_percent": lane.get("coverage_percent"),
            "dom_cases": acceptance.get("dom_cases"),
            "duplicate_content_rows": acceptance.get("duplicate_content_rows"),
            "favorited_relations": acceptance.get("favorited_relations"),
            "kill_runs": acceptance.get("kill_runs"),
            "liked_relations": acceptance.get("liked_relations"),
            "lost_ids": acceptance.get("lost_ids"),
            "removed_relations": acceptance.get("removed_relations"),
            "taxonomy_mutations": acceptance.get("taxonomy_mutations"),
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
    _require(
        all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check"
    )
    metrics = evidence.get("task_metrics", {})
    _require(
        metrics.get("automatic_classification_writes") == 0
        and metrics.get("automatic_scrolls") == 0
        and metrics.get("canary_item_limit") == 20
        and metrics.get("chaos_items") == 100
        and metrics.get("content_count") == 100
        and metrics.get("dom_cases") == 7
        and metrics.get("duplicate_content_rows") == 0
        and metrics.get("favorited_relations") == 20
        and metrics.get("kill_runs") == 50
        and metrics.get("liked_relations") == 100
        and metrics.get("lost_ids") == 0
        and metrics.get("removed_relations") == 0
        and metrics.get("taxonomy_mutations") == 0
        and metrics.get("unit_tests") == 14
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
    _require(all(check.status == "PASS" for check in checks), "an Adapters003 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.003")
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
            file=os.sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
