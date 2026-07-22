#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.001."""

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
    "verify_skeleton_009_for_adapters_001",
    PROJECT_ROOT / "scripts/verify_skeleton_009.py",
)
assert PREVIOUS_SPEC and PREVIOUS_SPEC.loader
PREVIOUS = importlib.util.module_from_spec(PREVIOUS_SPEC)
sys.modules[PREVIOUS_SPEC.name] = PREVIOUS
PREVIOUS_SPEC.loader.exec_module(PREVIOUS)

VerificationError = PREVIOUS.VerificationError
Check = PREVIOUS.Check
_require = PREVIOUS._require
_pairs = PREVIOUS._pairs
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
FULL_LANE_GATES = PREVIOUS.FULL_LANE_GATES

TASK_ID = "TSK.x2n.adapters.001"
RUN_ID = "RUN-X2N-S03-A001"
PHASE = "PH.X2N.3.1"
BRANCH = "codex/xhs-douyin-2notion-v0001-s03-adapters001"
TASK_BASE_COMMIT = "ee5d251ca30eab226c4df75c53965f312c2d9b05"
STAGE_2_REVIEW_FINAL_COMMIT = "bfea9f8d4fc0f6d691544c28a641624ed37122fa"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_001.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
REMOTE_MERGE_FACT = PROJECT_ROOT / "machine/facts/stage_2_remote_merge_state.json"
POLICY = PROJECT_ROOT / "machine/policy/adapter_profile_session_policy.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/profile_session/fixture_manifest.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
PROFILE_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/profile_session.py"
GUARD_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/adapter_guard.py"
RUNTIME_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_001_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.001.json"

HISTORICAL_STAGE_2_EVIDENCE = (
    PROJECT_ROOT / "machine/facts/stage_2_gate_state.json",
    PROJECT_ROOT / "machine/evidence/stage_2/review/G2.json",
    PROJECT_ROOT / "machine/evidence/stage_2/review/findings.json",
    PROJECT_ROOT / "machine/evidence/stage_2/review/verification.json",
)

UNCHANGED_SECURITY_SURFACES = (
    PROJECT_ROOT / "apps/extension/manifest.json",
    PROJECT_ROOT / "apps/companion/native-host/policy.json",
    PROJECT_ROOT / "packages/contracts/schemas/v1/health_report.schema.json",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/errors.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "package-lock.json",
    PROJECT_ROOT / "uv.lock",
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/src/x2n_companion/adapter_guard.py",
    "apps/companion/src/x2n_companion/profile_session.py",
    "apps/companion/src/x2n_companion/runtime.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_profile_session.py",
    "docs/governance/RUN_CONTRACT_S03_ADAPTERS_001.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.adapters.001.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/stage_2_remote_merge_state.json",
    "machine/facts/task_state.json",
    "machine/policy/adapter_profile_session_policy.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/run_adapters_001_acceptance.py",
    "scripts/verify_adapters_001.py",
    "scripts/verify_stage_2_review.py",
    "tests/test_adapters_001.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/adapters/v1/profile_session/",)


def _yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"YAML object required: {path.name}")
    return value


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    committed = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}...HEAD"]).splitlines()
    working = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"])
    )
    relative_changes: list[str] = []
    for path in sorted(set(committed + working)):
        relative = _project_relative(path)
        _require(relative is not None, "Adapters001 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Adapters001 change: {relative}",
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
        not any(path.suffix.lower() in forbidden_suffixes for path in files), "private Runtime artifact entered x2n"
    )
    profile_artifacts = [
        path
        for path in files
        if any(part in {"browser_profiles", "BrowserProfile"} for part in path.relative_to(PROJECT_ROOT).parts)
    ]
    _require(not profile_artifacts, "Browser Profile artifact entered x2n")
    return Check(
        "scope_and_public_private_boundary",
        "PASS",
        {
            "browser_profile_artifacts": 0,
            "changed_files": len(relative_changes),
            "local_path_findings": 0,
            "out_of_scope_writes": 0,
            "sensitive_or_media_url_hits": 0,
            "text_files_scanned": len(files),
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Adapters001 worktree branch")
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
        "Adapters001 branch no longer descends from the Stage 2 merge",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, live_origin],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "origin/main no longer descends from the Stage 2 merge",
    )
    origin_paths = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{live_origin}"]
    ).splitlines()
    origin_overlap = sum(
        path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in origin_paths
    )
    _require(origin_overlap == 0, "origin/main changed x2n during Adapters001")

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
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{TASK_BASE_COMMIT}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": main_overlap,
        },
    )


def validate_stage_2_transition() -> Check:
    parents = _git(["rev-list", "--parents", "-n", "1", TASK_BASE_COMMIT]).split()
    _require(len(parents) == 3, "Stage 2 base is not the expected merge commit")
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", STAGE_2_REVIEW_FINAL_COMMIT, TASK_BASE_COMMIT],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "Stage 2 review final commit is not in the merge ancestry",
    )
    for path in HISTORICAL_STAGE_2_EVIDENCE:
        _require(
            path.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, path),
            f"historical Stage 2 evidence changed: {path.name}",
        )
    fact = _load_json(REMOTE_MERGE_FACT)
    pull = fact.get("pull_request", {})
    checks = fact.get("remote_checks", [])
    _require(
        fact.get("source") == "public_github_pr_and_actions_metadata"
        and fact.get("repository") == "LinzeColin/MetaDatabase"
        and fact.get("stage_3_task_start_authorized") is True
        and fact.get("historical_stage_2_gate_evidence_mutated") is False
        and fact.get("external_auth_material_contact") is False,
        "Stage 2 remote transition fact drifted",
    )
    _require(
        pull.get("number") == 78
        and pull.get("state") == "merged"
        and pull.get("merge_commit") == TASK_BASE_COMMIT
        and pull.get("review_final_commit") == STAGE_2_REVIEW_FINAL_COMMIT,
        "Stage 2 PR merge fact drifted",
    )
    _require(
        [(item.get("run_id"), item.get("conclusion")) for item in checks]
        == [(29922576589, "success"), (29922576674, "success")],
        "Stage 2 remote CI facts drifted",
    )
    return Check(
        "stage_2_remote_transition",
        "PASS",
        {
            "historical_evidence_mutations": 0,
            "merge_commit": TASK_BASE_COMMIT,
            "pull_request": 78,
            "remote_successful_checks": 2,
        },
    )


def validate_task_and_state() -> Check:
    taskpack_text = TASKPACK.read_text(encoding="utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Adapters001 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.3" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on") == ["TSK.x2n.foundation.004", "TSK.x2n.discovery.005"],
        "Adapters001 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids") == ["ACC.x2n.batch.001", "ACC.x2n.ops.004", "ACC.x2n.gov.002"],
        "Adapters001 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    _require(
        _task_block(taskpack_text, "TSK.x2n.adapters.002") == _task_block(base_taskpack, "TSK.x2n.adapters.002"),
        "Adapters002 was entered by this Run",
    )
    taskpack = _yaml(TASKPACK)
    project = taskpack.get("project", {})
    authorization = taskpack.get("authorization", {})
    _require(project.get("status") == "STAGE_3_ADAPTERS_001_PASS_G3_NOT_RUN", "Task Pack status drifted")
    _require(
        authorization.get("stage_3_task_start") is True
        and authorization.get("real_account_execution") is False
        and authorization.get("public_release") is False,
        "Task Pack authorization drifted",
    )

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.19", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.3" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Adapters001 state is not pass")
    _require("TSK.x2n.adapters.002" not in state.get("tasks", {}), "Adapters002 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.3.2" and state.get("next_run") == "TSK.x2n.adapters.002",
        "next Task routing drifted",
    )
    _require(
        state.get("stage_3_authorized") is True
        and state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g3_pass",
        "G3/upload state overstated",
    )
    _require(
        state.get("completed_stage_gate", {}).get("gate_id") == "G2"
        and state.get("completed_stage_gate", {}).get("remote_upload") == "merged",
        "G2 remote merge was not reconciled",
    )
    acceptance = state.get("acceptance_status", {})
    _require(
        acceptance.get("ACC.x2n.batch.001")
        == "pass_ci_synth_5_non_authoritative_removed_0_two_complete_candidate_only_physical_and_content_delete_0_adapter_integration_downstream_not_run",
        "batch Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.ops.004")
        == "pass_ci_synth_8_components_missing_dependency_profile_and_db_busy_ok_degraded_blocked_path_sensitive_0_owner_alpha_not_run",
        "Doctor Acceptance drifted",
    )
    _require(
        acceptance.get("ACC.x2n.gov.002")
        == "pass_current_source_build_candidate_profile_path_browser_state_sensitive_private_content_0_owner_release_downstream_not_run",
        "public/private Acceptance drifted",
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
        _load_json(PROJECT_FACT).get("status") == "stage_3_adapters_001_pass_g3_not_run",
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
            "next_task": "TSK.x2n.adapters.002",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
            "stage_gate": "G3_NOT_RUN",
        },
    )


def validate_policy_and_implementation() -> Check:
    policy = _load_json(POLICY)
    _require(
        policy.get("policy_id") == "POLICY.X2N.ADAPTER-RUNTIME.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("default") == "deny",
        "Adapter runtime policy identity drifted",
    )
    runtime = policy.get("runtime", {})
    launcher = policy.get("profile_launcher", {})
    session = policy.get("session_health", {})
    doctor = policy.get("doctor", {})
    execution = policy.get("adapter_execution", {})
    deletion = policy.get("batch_deletion_protection", {})
    _require(
        runtime.get("root_ref") == "X2N_DATA_ROOT"
        and runtime.get("profile_mode") == "0700"
        and runtime.get("checkpoint_mode") == "0600"
        and runtime.get("repository_profile_files_allowed") == 0
        and runtime.get("ordinary_backup_includes_profiles") is False,
        "Private Profile policy drifted",
    )
    for field in (
        "caller_supplied_executable",
        "caller_supplied_profile_path",
        "caller_supplied_url",
        "automated_login",
        "remote_debugging",
        "cookie_or_credential_input",
        "cookie_or_credential_export",
        "verification_bypass",
    ):
        _require(launcher.get(field) is False, f"Profile launcher boundary weakened: {field}")
    _require(
        session.get("ttl_seconds") == 300
        and session.get("credential_or_cookie_read") is False
        and session.get("profile_path_emitted") is False
        and session.get("missing_or_stale") == "blocked_user_action",
        "session-health policy drifted",
    )
    _require(
        doctor.get("states") == ["ok", "degraded", "blocked"]
        and doctor.get("components")
        == ["extension", "native_host", "companion", "canonical_db", "ffmpeg", "provider", "notion", "adapter"]
        and doctor.get("noncore_missing_preserves_canonical") is True
        and doctor.get("sensitive_or_private_path_output") is False,
        "Doctor policy drifted",
    )
    _require(
        execution.get("max_concurrent_adapters") == 1
        and execution.get("mutex_wait") is False
        and execution.get("minimum_batch_start_interval_seconds") == 30
        and execution.get("minimum_item_observation_interval_seconds") == 3
        and execution.get("automatic_scroll") is False
        and execution.get("automatic_retry_on_auth_verification_or_platform_change") is False,
        "Adapter mutex/rate policy drifted",
    )
    _require(
        len(deletion.get("non_authoritative_outcomes", [])) == 5
        and deletion.get("removed_count_for_non_authoritative_outcome") == 0
        and deletion.get("complete_successes_required_for_candidate") == 2
        and deletion.get("maximum_automatic_state") == "tombstone_candidate"
        and deletion.get("owner_confirmation_required_for_physical_delete") is True
        and deletion.get("automatic_content_delete") is False,
        "batch deletion policy drifted",
    )

    profile_source = PROFILE_SOURCE.read_text(encoding="utf-8")
    guard_source = GUARD_SOURCE.read_text(encoding="utf-8")
    runtime_source = RUNTIME_SOURCE.read_text(encoding="utf-8")
    cli_source = CLI_SOURCE.read_text(encoding="utf-8")
    for token in (
        "PROFILE_LAUNCH_CONFIRMATION",
        "chrome://newtab/",
        "--user-data-dir=",
        "SessionHealthStore",
        "SESSION_TTL_SECONDS = 300",
        "build_doctor_report",
        "profile_path_emitted",
    ):
        _require(token in profile_source, f"Profile/session implementation missing: {token}")
    for forbidden in ("document.cookie", "Cookies.sqlite", "--remote-debugging", "requests.get(", "urllib.request"):
        _require(forbidden not in profile_source, f"forbidden Profile/session surface entered: {forbidden}")
    for token in (
        "LOCK_EX | fcntl.LOCK_NB",
        "MINIMUM_BATCH_START_INTERVAL_SECONDS = 30.0",
        "MINIMUM_ITEM_OBSERVATION_INTERVAL_SECONDS = 3.0",
        "BatchDeletionGuard",
        "tombstone_candidate_count",
    ):
        _require(token in guard_source, f"Adapter guard implementation missing: {token}")
    _require(
        "time.sleep" not in guard_source and "removed_count: Literal[0]" in guard_source, "guard auto-action drifted"
    )
    _require(
        "browser_profile_directory" in runtime_source
        and "Dedicated Browser Profile cannot contain symbolic links" in runtime_source,
        "Runtime Profile confinement missing",
    )
    _require(
        'subparsers.add_parser("doctor")' in cli_source
        and 'subparsers.add_parser("profile")' in cli_source
        and 'in {"doctor", "profile"}' in cli_source,
        "Profile/Doctor CLI missing",
    )
    for forbidden_option in ("--profile-path", "--executable", "--url"):
        _require(forbidden_option not in cli_source, f"arbitrary CLI input entered: {forbidden_option}")
    for path in UNCHANGED_SECURITY_SURFACES:
        _require(
            path.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, path),
            f"unapproved contract surface changed: {path.name}",
        )
    artifact = _load_json(ARTIFACT_POLICY)
    enforcement = artifact.get("enforcement", [])
    _require(
        "scripts/run_adapters_001_acceptance.py" in enforcement and "scripts/verify_adapters_001.py" in enforcement,
        "Adapters001 enforcement is not registered",
    )
    return Check(
        "profile_session_doctor_and_adapter_guard",
        "PASS",
        {
            "arbitrary_executable_path_or_url_inputs": 0,
            "automatic_login_or_verification_bypass": 0,
            "doctor_components": 8,
            "max_concurrent_adapters": 1,
            "minimum_batch_start_interval_seconds": 30,
            "minimum_item_observation_interval_seconds": 3,
            "native_contract_changes": 0,
            "profile_path_outputs": 0,
            "session_ttl_seconds": 300,
            "sqlite_migrations": 0,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json(FIXTURE)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S03.A001.001" and fixture.get("synthetic") is True,
        "Adapters001 fixture identity drifted",
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
        _require(fixture.get(field) is False, f"fixture privacy boundary weakened: {field}")
    sessions = fixture.get("session_cases", [])
    batches = fixture.get("batch_cases", [])
    _require(len(sessions) == 7 and len({item.get("id") for item in sessions}) == 7, "session fixture drifted")
    _require(len(batches) == 7 and len({item.get("id") for item in batches}) == 7, "batch fixture drifted")
    _require(sum(item.get("signal") == "expired" for item in sessions) == 1, "expired-session fixture missing")
    _require(
        sum(item.get("expected_state") == "ok" for item in sessions) == 1
        and sum(item.get("expected_state") == "blocked" for item in sessions) == 6,
        "session-health fixture oracle drifted",
    )
    _require(
        [item.get("outcome") for item in batches[:5]]
        == ["auth_expired", "http_error", "platform_changed", "empty_response", "partial_scan"],
        "non-authoritative batch matrix drifted",
    )
    _require(
        all(item.get("expected_removed") == 0 for item in batches)
        and [item.get("expected_tombstone_candidates") for item in batches[-2:]] == [0, 1]
        and fixture.get("physical_delete_cases") == 0,
        "batch deletion fixture oracle drifted",
    )
    global_rows = _load_json(GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S03.A001.001",
            "path": "packages/test-fixtures/adapters/v1/profile_session/fixture_manifest.json",
            "case_count": 14,
            "purpose": "credential-free Profile session health, expired-login user action and batch deletion protection",
        }
        in global_rows,
        "Adapters001 fixture is not globally registered",
    )
    return Check(
        "synthetic_session_and_deletion_fixtures",
        "PASS",
        {
            "batch_cases": 7,
            "expired_session_cases": 1,
            "non_authoritative_removed": 0,
            "physical_delete_cases": 0,
            "session_cases": 7,
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a001-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        output = _json_line(
            _run_external(
                "adapters_001_acceptance",
                (sys.executable, "-B", str(ACCEPTANCE_RUNNER)),
                env=_isolated_env(home),
                timeout=300,
            ),
            "Adapters001 acceptance",
        )
    expected = {
        "acceptance_scope": "ADAPTERS_001_PROFILE_SESSION_CI_SYNTH",
        "batch_cases": 7,
        "complete_successes_required_for_candidate": 2,
        "non_authoritative_batch_cases": 5,
        "owner_canary": "NOT_RUN",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "physical_delete_cases": 0,
        "platform_calls": 0,
        "profile_path_findings": 0,
        "real_account_execution": "NOT_RUN",
        "removed_relations": 0,
        "session_cases": 7,
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
    }
    for field, value in expected.items():
        _require(output.get(field) == value, f"Adapters001 acceptance metric drifted: {field}")
    unit = output.get("unit_suite", {})
    _require(
        unit.get("tests") == 16 and unit.get("errors") == 0 and unit.get("failures") == 0 and unit.get("skips") == 0,
        "Adapters001 unit acceptance failed",
    )
    return Check(
        "profile_session_acceptance",
        "PASS",
        {
            "batch_cases": 7,
            "complete_successes_required": 2,
            "owner_canary": "NOT_RUN",
            "owner_profile_login": "NOT_RUN",
            "physical_deletes": 0,
            "platform_calls": 0,
            "profile_path_findings": 0,
            "removed_relations": 0,
            "session_cases": 7,
            "unit_tests": 16,
        },
    )


def validate_full_lane_report(path: Path) -> Check:
    _require(path.is_file(), "full lane report is unavailable")
    report = _load_json(path)
    _require(report.get("status") == "PASS" and report.get("lane") == "full", "full lane did not pass")
    _require(
        report.get("blocking_commands") == 12
        and report.get("blocking_repetitions") == 2
        and report.get("blocking_executions") == 24,
        "full lane execution cardinality drifted",
    )
    _require(
        report.get("blocking_failures") == 0
        and report.get("flaky_blocking_tests") == 0
        and report.get("silent_blocking_skips") == 0,
        "full lane blocking quality gate failed",
    )
    _require(report.get("explicit_nonblocking_skips") == 6, "full lane optional skip allowlist drifted")
    expected_results = [
        {
            "blocking": True,
            "gate": gate,
            "label": f"{gate}_r{repetition}",
            "repetition": repetition,
            "status": "PASS",
        }
        for repetition in (1, 2)
        for gate in FULL_LANE_GATES
    ]
    _require(report.get("blocking_results") == expected_results, "full lane execution identity or result drifted")
    _require(
        report.get("platform_calls") == 0 and report.get("model_calls") == 0 and report.get("real_accounts") == 0,
        "full lane executed a forbidden external surface",
    )
    coverage = report.get("coverage", {})
    _require(
        coverage.get("status") == "PASS"
        and coverage.get("branch_mode") is True
        and float(coverage.get("overall_combined_percent", 0)) >= 70.0,
        "full lane coverage gate failed",
    )
    osv = report.get("osv", {})
    _require(
        osv.get("status") == "PASS"
        and osv.get("dependencies_queried") == 33
        and osv.get("vulnerabilities_reported") == 0
        and osv.get("critical_high_unresolved") == 0,
        "full lane OSV gate failed",
    )
    artifact = report.get("artifact_report", {})
    member_count = artifact.get("member_count")
    _require(
        report.get("artifact_deterministic") is True
        and artifact.get("status") == "PASS"
        and isinstance(member_count, int)
        and member_count >= 60
        and artifact.get("runtime_data_files") == 0
        and artifact.get("allowlist_findings") == 0,
        "full lane artifact gate failed",
    )
    return Check(
        "full_lane_replay",
        "PASS",
        {
            "artifact_members": member_count,
            "blocking_executions": 24,
            "blocking_failures": 0,
            "coverage_percent": coverage["overall_combined_percent"],
            "dependencies_queried": 33,
            "explicit_nonblocking_skips": 6,
            "flaky_blocking_tests": 0,
            "runtime_data_files": 0,
            "silent_blocking_skips": 0,
            "vulnerabilities_reported": 0,
        },
    )


def _acceptance_input_receipt() -> str:
    digest = hashlib.sha256()
    for path in (
        TASKPACK,
        ACCEPTANCE,
        RUN_CONTRACT,
        POLICY,
        FIXTURE,
        PROFILE_SOURCE,
        GUARD_SOURCE,
        RUNTIME_SOURCE,
        CLI_SOURCE,
    ):
        digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered and "github" + "_pat_" not in rendered, "evidence contains private data")
    _require(
        "Bearer" + " " not in rendered and "--user-data-dir=" not in rendered, "evidence contains secret/Profile data"
    )
    _require(re.search(r"/(?:Users|home)/[A-Za-z0-9._-]+/", rendered) is None, "evidence contains local path")


def write_evidence(checks: list[Check]) -> None:
    details = {item.name: item.details for item in checks}
    acceptance = details.get("profile_session_acceptance", {})
    lane = details.get("full_lane_replay", {})
    _require(acceptance and lane, "final evidence requires acceptance and full lane")
    payload = {
        "acceptance_ids": ["ACC.x2n.batch.001", "ACC.x2n.ops.004", "ACC.x2n.gov.002"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.batch.001": "PASS_CI_SYNTH_POLICY_PRIMITIVE_ADAPTER_INTEGRATION_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.gov.002": "PASS_CURRENT_SOURCE_BUILD_CANDIDATE_OWNER_RELEASE_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.ops.004": "PASS_CI_SYNTH_DOCTOR_OWNER_ALPHA_INSTALL_DOWNSTREAM_NOT_RUN",
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
            "blocking_executions": lane.get("blocking_executions"),
            "coverage_percent": lane.get("coverage_percent"),
            "doctor_components": details["profile_session_doctor_and_adapter_guard"].get("doctor_components"),
            "non_authoritative_removed": details["synthetic_session_and_deletion_fixtures"].get(
                "non_authoritative_removed"
            ),
            "physical_deletes": acceptance.get("physical_deletes"),
            "profile_path_findings": acceptance.get("profile_path_findings"),
            "session_cases": acceptance.get("session_cases"),
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
        metrics.get("doctor_components") == 8
        and metrics.get("session_cases") == 7
        and metrics.get("unit_tests") == 16
        and metrics.get("non_authoritative_removed") == 0
        and metrics.get("physical_deletes") == 0
        and metrics.get("profile_path_findings") == 0
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
        validate_stage_2_transition(),
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
    _require(all(check.status == "PASS" for check in checks), "an Adapters001 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.001")
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
