#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.adapters.004."""

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
    "verify_adapters_003_for_adapters_004",
    PROJECT_ROOT / "scripts/verify_adapters_003.py",
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

TASK_ID = "TSK.x2n.adapters.004"
RUN_ID = "RUN-X2N-S03-A004"
PHASE = "PH.X2N.3.4"
BRANCH = "codex/xhs-douyin-2notion-v0001-s03-adapters004"
TASK_BASE_COMMIT = "0939d78303f5e96ddedf9c8ef8a01a8dce03574a"
FINAL_COMMIT = "37ec58cb51d5720bdbe16a67a6e4ea82107c3eb0"
ORIGIN_CUTOFF = PREVIOUS.ORIGIN_CUTOFF
UPSTREAM_COMMIT = "ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7"
UPSTREAM_TREE = "ff7774b618f269fcdc750e17dc63612f159b6b46"
UPSTREAM_VERSION = "2.0.0"
INTEGRATION_CONTRACT_SHA256 = "aee925e0064b02492580e7c2c3ab68f6f30f5d8b4e283c63f681d5764149a606"

TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
ACCEPTANCE = PROJECT_ROOT / "docs/product_design/v0.0.0.1/04_ACCEPTANCE_CONTRACT_TRACEABILITY.md"
RUN_CONTRACT = PROJECT_ROOT / "docs/governance/RUN_CONTRACT_S03_ADAPTERS_004.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
ARCHITECTURE_FACT = PROJECT_ROOT / "machine/facts/architecture_decisions.json"
UPSTREAM_REGISTRY = PROJECT_ROOT / "machine/facts/upstream_registry.json"
UPSTREAM_HASHES = PROJECT_ROOT / "machine/facts/upstream_file_hashes.json"
INTEGRATION_LOCK = PROJECT_ROOT / "machine/facts/douyin_upstream_integration_lock.json"
POLICY = PROJECT_ROOT / "machine/policy/douyin_upstream_policy.json"
FIXTURE = PROJECT_ROOT / "packages/test-fixtures/adapters/v1/douyin_upstream/fixture_manifest.json"
SYNTHETIC_LOCK = FIXTURE.parent / "resolved-lock.json"
SYNTHETIC_LICENSES = FIXTURE.parent / "transitive-licenses.json"
SYNTHETIC_SBOM = FIXTURE.parent / "sbom.cdx.json"
GLOBAL_FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
ARTIFACT_POLICY = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
NOTICE = PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
UPSTREAM_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/douyin_upstream.py"
ADAPTER_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/douyin_adapter.py"
COMPANION_TEST = PROJECT_ROOT / "apps/companion/tests/test_douyin_adapter.py"
CLI_SOURCE = PROJECT_ROOT / "apps/companion/src/x2n_companion/runtime_cli.py"
FIXTURE_WORKER = PROJECT_ROOT / "scripts/douyin_sidecar_fixture_worker.py"
SHADOW_RUNNER = PROJECT_ROOT / "scripts/run_douyin_shadow_upgrade.py"
ACCEPTANCE_RUNNER = PROJECT_ROOT / "scripts/run_adapters_004_acceptance.py"
EVIDENCE = PROJECT_ROOT / "evidence/adapters/TSK.x2n.adapters.004.json"

UNCHANGED_SECURITY_SURFACES = (
    PROJECT_ROOT / "apps/extension/manifest.json",
    PROJECT_ROOT / "apps/extension/src/service-worker.js",
    PROJECT_ROOT / "apps/companion/native-host/policy.json",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/canonical_store.py",
    PROJECT_ROOT / "apps/companion/src/x2n_companion/migrations.py",
    PROJECT_ROOT / "packages/contracts/src/x2n_contracts/models.py",
    PROJECT_ROOT / "package-lock.json",
    PROJECT_ROOT / "uv.lock",
    NOTICE,
    UPSTREAM_REGISTRY,
    UPSTREAM_HASHES,
    PROJECT_ROOT / "machine/policy/upstream_integration_policy.json",
)

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "apps/companion/src/x2n_companion/douyin_adapter.py",
    "apps/companion/src/x2n_companion/douyin_upstream.py",
    "apps/companion/src/x2n_companion/runtime_cli.py",
    "apps/companion/tests/test_douyin_adapter.py",
    "docs/governance/RUN_CONTRACT_S03_ADAPTERS_004.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "evidence/adapters/TSK.x2n.adapters.004.json",
    "machine/facts/architecture_decisions.json",
    "machine/facts/douyin_upstream_integration_lock.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/douyin_upstream_policy.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "scripts/douyin_sidecar_fixture_worker.py",
    "scripts/run_adapters_004_acceptance.py",
    "scripts/run_douyin_shadow_upgrade.py",
    "scripts/verify_adapters_003.py",
    "scripts/verify_adapters_004.py",
    "tests/test_adapters_003.py",
    "tests/test_adapters_004.py",
    "功能清单.md",
    "开发记录.md",
}
ALLOWED_CHANGED_PREFIXES = ("packages/test-fixtures/adapters/v1/douyin_upstream/",)


def _sha256_at(commit: str, path: Path) -> str:
    return hashlib.sha256(_read_blob_at(commit, path)).hexdigest()


def validate_scope() -> Check:
    _git(["cat-file", "-e", f"{FINAL_COMMIT}^{{commit}}"])
    _git(["cat-file", "-e", f"{TASK_BASE_COMMIT}^{{commit}}"])
    committed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    relative_changes: list[str] = []
    for path in sorted(set(committed)):
        relative = _project_relative(path)
        _require(relative is not None, "Adapters004 changed scope escaped x2n")
        _require(
            relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES),
            f"unregistered Adapters004 change: {relative}",
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
    _require(current_branch not in {"", "main"}, "Adapters004 regression requires a non-main worktree")
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
        "Adapters004 final commit no longer descends from Adapters003",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "current worktree no longer descends from Adapters004",
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
            "historical_branch": BRANCH,
            "current_branch": current_branch,
            "external_main_dirty_paths": len(main_paths),
            "origin_drift_commits": int(_git(["rev-list", "--count", f"{ORIGIN_CUTOFF}..{live_origin}"])),
            "origin_project_overlap": origin_overlap,
            "project_overlap_paths": main_overlap,
        },
    )


def validate_predecessor() -> Check:
    _require(PREVIOUS.FINAL_COMMIT == TASK_BASE_COMMIT, "Adapters003 final pin differs from Adapters004 base")
    _require(
        PREVIOUS.EVIDENCE.read_bytes() == _read_blob_at(TASK_BASE_COMMIT, PREVIOUS.EVIDENCE),
        "Adapters003 evidence was rewritten",
    )
    checks = PREVIOUS.run_checks(
        verify_worktree=False,
        allow_external_main_dirty=False,
        run_external=False,
    )
    _require(all(item.status == "PASS" for item in checks), "Adapters003 historical regression failed")
    PREVIOUS.verify_evidence()
    return Check(
        "adapters_003_fixed_predecessor",
        "PASS",
        {"evidence_mutations": 0, "historical_checks": len(checks) + 1, "predecessor_commit": TASK_BASE_COMMIT},
    )


def validate_task_and_state() -> Check:
    taskpack_text = _read_blob_at(FINAL_COMMIT, TASKPACK).decode("utf-8")
    base_taskpack = _read_blob_at(TASK_BASE_COMMIT, TASKPACK).decode("utf-8")
    task = _task_block(taskpack_text, TASK_ID)
    base_task = _task_block(base_taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "Adapters004 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.3" and _field(task, "phase") == PHASE, "Task routing drifted")
    _require(
        _list_field(task, "depends_on")
        == ["TSK.x2n.discovery.004", "TSK.x2n.foundation.002", "TSK.x2n.skeleton.002", "TSK.x2n.skeleton.004"],
        "Adapters004 dependency drifted",
    )
    _require(
        _list_field(task, "acceptance_ids")
        == ["ACC.x2n.dy.001", "ACC.x2n.dy.002", "ACC.x2n.dy.003", "ACC.x2n.batch.001"],
        "Adapters004 Acceptance drifted",
    )
    _require(task == base_task.replace("  status: planned\n", "  status: completed\n", 1), "Task changed beyond status")
    for future in ("TSK.x2n.adapters.006", "TSK.x2n.adapters.005"):
        _require(
            _task_block(taskpack_text, future) == _task_block(base_taskpack, future),
            f"{future} was entered by this Run",
        )
    taskpack = yaml.safe_load(taskpack_text)
    _require(isinstance(taskpack, dict), "Task Pack root must be an object")
    _require(
        taskpack.get("project", {}).get("status") == "STAGE_3_ADAPTERS_004_PASS_G3_NOT_RUN", "Task Pack status drifted"
    )
    authorization = taskpack.get("authorization", {})
    _require(
        authorization.get("stage_3_task_start") is True
        and authorization.get("real_account_execution") is False
        and authorization.get("public_release") is False,
        "Task Pack authorization drifted",
    )
    state = _load_json_at(FINAL_COMMIT, TASK_STATE)
    _require(state.get("schema_version") == "1.22", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.3" and state.get("last_completed_phase") == PHASE, "phase drifted")
    _require(state.get("run_id") == RUN_ID and state.get("run_kind") == "single_dag_task", "Run drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "Adapters004 state is not pass")
    _require("TSK.x2n.adapters.006" not in state.get("tasks", {}), "Adapters006 state was entered")
    _require("TSK.x2n.adapters.005" not in state.get("tasks", {}), "Adapters005 state was entered")
    _require(
        state.get("next_phase") == "PH.X2N.3.5" and state.get("next_run") == "TSK.x2n.adapters.006",
        "next Task routing drifted",
    )
    _require(
        state.get("current_stage_gate") == "not_run"
        and state.get("current_stage_remote_upload") == "forbidden_until_g3_pass",
        "G3/upload state overstated",
    )
    acceptance = state.get("acceptance_status", {})
    for acceptance_id in ("ACC.x2n.dy.001", "ACC.x2n.dy.002", "ACC.x2n.dy.003"):
        _require(str(acceptance.get(acceptance_id, "")).startswith("pass_ci_synth_"), f"{acceptance_id} is overstated")
        _require(
            "owner_alpha_not_run" in str(acceptance.get(acceptance_id, "")) or acceptance_id == "ACC.x2n.dy.003",
            f"{acceptance_id} Owner boundary drifted",
        )
    _require(
        acceptance.get("ACC.x2n.batch.001")
        == "pass_ci_synth_5_non_authoritative_removed_0_adapter004_physical_content_delete_0_second_complete_candidate_only_reconciliation_downstream_not_run",
        "batch Acceptance drifted",
    )
    _require(
        state.get("douyin_upstream_execution")
        == "pass_ci_synth_contract_worker_only_exact_commit_tree_version_license_protocol_build_attestation_18_negative_cases_upstream_executed_false_owner_private_build_not_installed",
        "Douyin execution boundary drifted",
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
        _load_json_at(FINAL_COMMIT, PROJECT_FACT).get("status") == "stage_3_adapters_004_pass_g3_not_run",
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
        UPSTREAM_COMMIT,
        UPSTREAM_TREE,
        "PASS_CI_SYNTH_SCOPED",
        "NOT_RUN",
    ):
        _require(value in contract, f"Run Contract identity missing: {value}")
    return Check(
        "task_and_acceptance_contract",
        "PASS",
        {
            "acceptance_ids": 4,
            "next_task": "TSK.x2n.adapters.006",
            "owner_canary": "NOT_RUN",
            "phase": PHASE,
            "single_task": True,
            "stage_gate": "G3_NOT_RUN",
        },
    )


def validate_pin_policy_and_implementation() -> Check:
    registry = _load_json_at(FINAL_COMMIT, UPSTREAM_REGISTRY)
    rows = {row["id"]: row for row in registry.get("repositories", [])}
    upstream = rows.get("douyin-downloader", {})
    _require(
        upstream.get("selected_commit") == UPSTREAM_COMMIT
        and upstream.get("tree") == UPSTREAM_TREE
        and upstream.get("declared_version") == UPSTREAM_VERSION
        and upstream.get("license", {}).get("spdx") == "MIT"
        and upstream.get("integration", {}).get("enabled") is False
        and upstream.get("integration", {}).get("runtime_dependency") is False,
        "Stage0 upstream registry drifted",
    )
    lock = _load_json_at(FINAL_COMMIT, INTEGRATION_LOCK)
    _require(
        lock.get("lock_id") == "LOCK.X2N.DOUYIN-DOWNLOADER.001"
        and lock.get("task_id") == TASK_ID
        and lock.get("upstream", {}).get("commit") == UPSTREAM_COMMIT
        and lock.get("upstream", {}).get("tree") == UPSTREAM_TREE
        and lock.get("upstream", {}).get("declared_version") == UPSTREAM_VERSION
        and lock.get("upstream", {}).get("license") == "MIT"
        and lock.get("integration_contract", {}).get("sha256") == INTEGRATION_CONTRACT_SHA256,
        "Douyin integration lock drifted",
    )
    runtime = lock.get("runtime_integration", {})
    _require(
        runtime.get("enabled") is False
        and runtime.get("bundled") is False
        and runtime.get("source_copied") is False
        and runtime.get("runtime_dependency") is False
        and runtime.get("raw_cli_allowed") is False
        and runtime.get("raw_rest_allowed") is False
        and runtime.get("owner_private_sidecar_installed") is False,
        "Douyin Runtime integration was enabled",
    )
    owner_gate = lock.get("owner_private_build_gate", {})
    _require(
        owner_gate.get("resolved_lock") == "NOT_RUN_NO_OWNER_PRIVATE_BUILD"
        and owner_gate.get("transitive_license_scan") == "NOT_RUN_NO_OWNER_PRIVATE_BUILD"
        and owner_gate.get("sbom") == "NOT_RUN_NO_OWNER_PRIVATE_BUILD"
        and owner_gate.get("real_execution") == "NOT_RUN",
        "Owner private build scope was overstated",
    )
    synthetic = lock.get("ci_synthetic_attestation", {})
    expected_digests = {
        "executable_sha256": _sha256_at(FINAL_COMMIT, FIXTURE_WORKER),
        "resolved_lock_sha256": _sha256_at(FINAL_COMMIT, SYNTHETIC_LOCK),
        "transitive_license_report_sha256": _sha256_at(FINAL_COMMIT, SYNTHETIC_LICENSES),
        "sbom_sha256": _sha256_at(FINAL_COMMIT, SYNTHETIC_SBOM),
    }
    _require(
        synthetic.get("scope") == "ci_synthetic" and synthetic.get("production_accepted") is False,
        "synthetic attestation scope drifted",
    )
    for field, expected in expected_digests.items():
        _require(synthetic.get(field) == expected, f"synthetic attestation digest drifted: {field}")
    policy = _load_json_at(FINAL_COMMIT, POLICY)
    flags = policy.get("feature_gate", {})
    _require(
        policy.get("policy_id") == "POLICY.X2N.DOUYIN-UPSTREAM.001"
        and policy.get("task_id") == TASK_ID
        and policy.get("default") == "deny"
        and flags.get("owner_canary_enabled") is False
        and flags.get("production_enabled") is False
        and flags.get("official_personal_likes_api") == "unknown_disabled"
        and flags.get("official_personal_favorites_api") == "unknown_disabled",
        "Douyin policy identity or feature gate drifted",
    )
    research = policy.get("official_research", {})
    _require(
        research.get("inference_not_claim_of_nonexistence") is True
        and len(research.get("sources", [])) == 3
        and all(str(url).startswith("https://open.douyin.com/") for url in research.get("sources", [])),
        "official research boundary drifted",
    )
    owner_action = policy.get("owner_action", {})
    _require(
        owner_action.get("max_items") == 20
        and owner_action.get("automatic_pagination") is False
        and owner_action.get("automatic_scroll") is False
        and owner_action.get("automatic_retry") is False
        and owner_action.get("account_state_change") is False
        and owner_action.get("one_transport_exchange_per_action") is True,
        "Owner batch boundary drifted",
    )
    canonical = policy.get("canonical", {})
    _require(
        canonical.get("truth_source") == "sqlite"
        and canonical.get("full_scan_completion_in_this_task") is False
        and canonical.get("removed_writes") == 0
        and canonical.get("tombstone_candidate_writes") == 0
        and canonical.get("physical_deletes") == 0
        and canonical.get("content_auto_deletes") == 0,
        "Canonical containment drifted",
    )
    upstream_source = _read_blob_at(FINAL_COMMIT, UPSTREAM_SOURCE).decode("utf-8")
    adapter_source = _read_blob_at(FINAL_COMMIT, ADAPTER_SOURCE).decode("utf-8")
    cli = _read_blob_at(FINAL_COMMIT, CLI_SOURCE).decode("utf-8")
    worker = _read_blob_at(FINAL_COMMIT, FIXTURE_WORKER).decode("utf-8")
    for token in (
        "class SubprocessDouyinTransport",
        "shell=False",
        "class LoopbackRestDouyinTransport",
        'HTTPConnection("127.0.0.1"',
        "class PinnedDouyinClient",
        "parse_health",
        "parse_batch",
        "evaluate_shadow_candidate",
        "INTEGRATION_CONTRACT_SHA256",
    ):
        _require(token in upstream_source, f"upstream containment implementation missing: {token}")
    for token in (
        "class DouyinAdapter",
        "class DouyinBatchCoordinator",
        'RESUME_COMPATIBILITY_VERSION = "douyin-upstream-1.0.0"',
        "Platform.DOUYIN",
        "RelationType.FAVORITED",
        "RelationType.LIKED",
        "SourceMethod.SELECTED_COLLECTION",
        "full_scan_id = NULL",
    ):
        _require(token in adapter_source, f"Douyin Adapter implementation missing: {token}")
    _require(
        'subparsers.add_parser("douyin")' in cli
        and 'douyin_actions.add_parser("canary-plan")' in cli
        and "build_douyin_canary_plan" in cli,
        "non-executing Douyin Canary CLI is missing",
    )
    _require(
        "urllib.request" not in upstream_source and "requests." not in upstream_source,
        "arbitrary network client entered wrapper",
    )
    _require("UPSTREAM_COMMIT" in worker and "ci_synthetic" in worker, "synthetic worker identity is missing")
    for path in UNCHANGED_SECURITY_SURFACES:
        _require(
            _read_blob_at(FINAL_COMMIT, path) == _read_blob_at(TASK_BASE_COMMIT, path),
            f"security surface changed: {path.name}",
        )
    notice = _read_blob_at(FINAL_COMMIT, NOTICE).decode("utf-8")
    for value in ("jiji262/douyin-downloader", UPSTREAM_COMMIT, "MIT", "Copyright (c) 2026 jiji262"):
        _require(value in notice, f"NOTICE identity missing: {value}")
    artifact = _load_json_at(FINAL_COMMIT, ARTIFACT_POLICY)
    enforcement = artifact.get("enforcement", [])
    for required in (
        "scripts/douyin_sidecar_fixture_worker.py",
        "scripts/run_douyin_shadow_upgrade.py",
        "scripts/run_adapters_004_acceptance.py",
        "scripts/verify_adapters_004.py",
    ):
        _require(required in enforcement, f"Adapters004 enforcement is not registered: {required}")
    return Check(
        "pin_policy_license_build_and_transport_containment",
        "PASS",
        {
            "actual_upstream_runtime_dependencies": 0,
            "automatic_pagination": 0,
            "build_attestation_digests": 4,
            "integration_contract_sha256": INTEGRATION_CONTRACT_SHA256,
            "owner_private_build": "NOT_RUN",
            "pin_commit": UPSTREAM_COMMIT,
            "pin_tree": UPSTREAM_TREE,
            "production_enabled": False,
            "raw_upstream_cli_rest_allowed": False,
            "transports": 2,
            "upstream_executions": 0,
        },
    )


def validate_fixtures() -> Check:
    fixture = _load_json_at(FINAL_COMMIT, FIXTURE)
    _require(
        fixture.get("fixture_id") == "FIXTURE.X2N.S03.A004.001" and fixture.get("synthetic") is True,
        "Adapters004 fixture identity drifted",
    )
    for field in (
        "contains_accounts",
        "contains_cookies",
        "contains_credentials",
        "contains_local_absolute_paths",
        "contains_media_urls",
        "contains_private_content",
    ):
        _require(fixture.get(field) is False, f"fixture privacy drifted: {field}")
    _require(
        fixture.get("upstream_executed") is False and fixture.get("platform_calls") == 0, "fixture execution overstated"
    )
    pin = fixture.get("pin", {})
    _require(
        pin.get("commit") == UPSTREAM_COMMIT
        and pin.get("tree") == UPSTREAM_TREE
        and pin.get("version") == UPSTREAM_VERSION
        and pin.get("license") == "MIT"
        and pin.get("integration_contract_sha256") == INTEGRATION_CONTRACT_SHA256,
        "fixture pin drifted",
    )
    mapping = fixture.get("mapping", {})
    _require(
        mapping.get("favorites_items") == 20
        and mapping.get("likes_items") == 20
        and mapping.get("favorite_collections") == 2
        and mapping.get("expected_content_rows") == 40
        and mapping.get("expected_favorited_relations") == 20
        and mapping.get("expected_liked_relations") == 20
        and mapping.get("expected_removed_relations") == 0
        and mapping.get("expected_tombstone_candidates") == 0
        and mapping.get("expected_upstream_paths_in_canonical") == 0
        and mapping.get("expected_upstream_database_primary_keys_in_canonical") == 0,
        "fixture mapping drifted",
    )
    cases = fixture.get("cases", [])
    _require(len(cases) == 38 and len(set(cases)) == 38, "contract fixture cases drifted")
    for path in (SYNTHETIC_LOCK, SYNTHETIC_LICENSES, SYNTHETIC_SBOM):
        _read_blob_at(FINAL_COMMIT, path)
    _require(
        _load_json_at(FINAL_COMMIT, SYNTHETIC_LOCK).get("upstream_runtime_installed") is False,
        "synthetic lock overstated",
    )
    _require(
        _load_json_at(FINAL_COMMIT, SYNTHETIC_LICENSES).get("upstream_runtime_installed") is False,
        "synthetic licenses overstated",
    )
    _require(
        len(_load_json_at(FINAL_COMMIT, SYNTHETIC_SBOM).get("components", [])) == 0,
        "synthetic SBOM contains runtime packages",
    )
    global_rows = _load_json_at(FINAL_COMMIT, GLOBAL_FIXTURE_MANIFEST).get("fixtures", [])
    _require(
        {
            "id": "FIXTURE.X2N.S03.A004.001",
            "path": "packages/test-fixtures/adapters/v1/douyin_upstream/fixture_manifest.json",
            "case_count": 38,
            "purpose": "Pinned Douyin owner-managed sidecar subprocess and loopback REST contract, strict schema/error/pin/build containment, 20 favorites plus 20 likes Canonical mapping and offline shadow blocking",
        }
        in global_rows,
        "Adapters004 fixture is not globally registered",
    )
    return Check(
        "synthetic_upstream_contract_mapping_and_deletion_fixtures",
        "PASS",
        {
            "contract_cases": 38,
            "favorite_collections": 2,
            "favorites_items": 20,
            "likes_items": 20,
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "synthetic_only": True,
        },
    )


def validate_execution() -> Check:
    with tempfile.TemporaryDirectory(prefix="x2n-a004-verify-") as value:
        home = Path(value) / "home"
        home.mkdir(mode=0o700)
        output = _json_line(
            _run_external(
                "adapters_004_acceptance",
                (sys.executable, "-B", str(ACCEPTANCE_RUNNER)),
                env=_isolated_env(home),
                timeout=900,
            ),
            "Adapters004 acceptance",
        )
    expected = {
        "acceptance_scope": "ADAPTERS_004_DOUYIN_PINNED_SIDECAR_CI_SYNTH",
        "automatic_pagination": 0,
        "canary_item_limit": 20,
        "canary_tooling": "PASS_NONEXECUTING",
        "favorite_canary_execution": "NOT_RUN",
        "identified_item_success_percent": 100,
        "like_canary_execution": "NOT_RUN",
        "network_calls_external": 0,
        "owner_canary": "NOT_RUN",
        "owner_private_sidecar": "NOT_INSTALLED",
        "owner_profile_login": "NOT_RUN",
        "phase": PHASE,
        "platform_calls": 0,
        "real_account_execution": "NOT_RUN",
        "status": "PASS_CI_SYNTH_SCOPED",
        "task_id": TASK_ID,
        "upstream_executed": False,
        "upstream_runtime_dependencies": 0,
    }
    for field, value in expected.items():
        _require(output.get(field) == value, f"Adapters004 acceptance metric drifted: {field}")
    contract = output.get("contract", {})
    _require(
        contract.get("exact_health") is True
        and contract.get("integration_contract_sha256") == INTEGRATION_CONTRACT_SHA256
        and contract.get("negative_cases") == 18
        and contract.get("normal_modes") == 2
        and contract.get("persistence_writes") == 0
        and contract.get("subprocess_shell") is False,
        "Adapters004 upstream contract acceptance failed",
    )
    canonical = output.get("canonical", {})
    _require(
        canonical.get("content_count") == 40
        and canonical.get("favorited_relations") == 20
        and canonical.get("liked_relations") == 20
        and canonical.get("collection_count") == 2
        and canonical.get("observations") == 40
        and canonical.get("exact_replays") == 2
        and canonical.get("full_scan_completions") == 0
        and canonical.get("removed_relations") == 0
        and canonical.get("tombstone_candidates") == 0
        and canonical.get("physical_deletes") == 0
        and canonical.get("content_auto_deletes") == 0
        and canonical.get("classification_writes") == 0
        and canonical.get("taxonomy_mutations") == 0
        and canonical.get("upstream_paths") == 0
        and canonical.get("upstream_database_primary_keys") == 0,
        "Adapters004 Canonical acceptance failed",
    )
    deletion = output.get("deletion", {})
    _require(
        deletion.get("non_authoritative_cases") == 5
        and deletion.get("non_authoritative_removed") == 0
        and deletion.get("second_complete_candidate_only") == 1
        and deletion.get("physical_deletes") == 0
        and deletion.get("content_auto_deletes") == 0,
        "Adapters004 deletion acceptance failed",
    )
    shadow = output.get("shadow", {})
    _require(
        shadow.get("approved_pin_status") == "PASS_PIN_UNCHANGED"
        and shadow.get("observed_candidate_status") == "BLOCKED_SHADOW"
        and shadow.get("promotions") == 0
        and shadow.get("network_calls") == 0,
        "Adapters004 shadow acceptance failed",
    )
    unit = output.get("unit_suite", {})
    _require(
        unit.get("tests") == 17 and unit.get("errors") == 0 and unit.get("failures") == 0 and unit.get("skips") == 0,
        "Adapters004 unit acceptance failed",
    )
    return Check(
        "douyin_pinned_sidecar_acceptance",
        "PASS",
        {
            "automatic_pagination": 0,
            "blocking_negative_contract_cases": 18,
            "content_count": 40,
            "favorite_collections": 2,
            "favorited_relations": 20,
            "liked_relations": 20,
            "owner_canary": "NOT_RUN",
            "platform_calls": 0,
            "removed_relations": 0,
            "shadow_promotions": 0,
            "unit_tests": 17,
            "upstream_executions": 0,
            "upstream_paths_or_database_primary_keys": 0,
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
        INTEGRATION_LOCK,
        FIXTURE,
        SYNTHETIC_LOCK,
        SYNTHETIC_LICENSES,
        SYNTHETIC_SBOM,
        NOTICE,
        UPSTREAM_SOURCE,
        ADAPTER_SOURCE,
        COMPANION_TEST,
        CLI_SOURCE,
        FIXTURE_WORKER,
        SHADOW_RUNNER,
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
    acceptance = details.get("douyin_pinned_sidecar_acceptance", {})
    lane = details.get("full_lane_replay", {})
    _require(acceptance and lane, "final evidence requires acceptance and full lane")
    payload = {
        "acceptance_ids": ["ACC.x2n.dy.001", "ACC.x2n.dy.002", "ACC.x2n.dy.003", "ACC.x2n.batch.001"],
        "acceptance_input_sha256": _acceptance_input_receipt(),
        "acceptance_status": {
            "ACC.x2n.batch.001": "PASS_CI_SYNTH_NON_AUTHORITATIVE_REMOVED_0_SECOND_COMPLETE_CANDIDATE_ONLY_RECONCILIATION_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.dy.001": "PASS_CI_SYNTH_20_FAVORITES_TWO_COLLECTIONS_OWNER_ALPHA_NOT_RUN",
            "ACC.x2n.dy.002": "PASS_CI_SYNTH_20_LIKES_OWNER_ALPHA_NOT_RUN",
            "ACC.x2n.dy.003": "PASS_CI_SYNTH_EXACT_PIN_BUILD_SCHEMA_ERROR_TIMEOUT_AND_SHADOW_CONTRACT",
        },
        "checks": [{"name": item.name, "status": item.status, "details": item.details} for item in checks],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "owner_canary": "NOT_RUN",
        "owner_private_sidecar": "NOT_INSTALLED",
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
            "blocking_executions": lane.get("blocking_executions"),
            "blocking_negative_contract_cases": acceptance.get("blocking_negative_contract_cases"),
            "content_count": acceptance.get("content_count"),
            "coverage_percent": lane.get("coverage_percent"),
            "favorite_collections": acceptance.get("favorite_collections"),
            "favorited_relations": acceptance.get("favorited_relations"),
            "liked_relations": acceptance.get("liked_relations"),
            "removed_relations": acceptance.get("removed_relations"),
            "shadow_promotions": acceptance.get("shadow_promotions"),
            "unit_tests": acceptance.get("unit_tests"),
            "upstream_executions": acceptance.get("upstream_executions"),
            "upstream_paths_or_database_primary_keys": acceptance.get("upstream_paths_or_database_primary_keys"),
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
        and evidence.get("owner_private_sidecar") == "NOT_INSTALLED"
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
        metrics.get("automatic_pagination") == 0
        and metrics.get("blocking_negative_contract_cases") == 18
        and metrics.get("content_count") == 40
        and metrics.get("favorite_collections") == 2
        and metrics.get("favorited_relations") == 20
        and metrics.get("liked_relations") == 20
        and metrics.get("removed_relations") == 0
        and metrics.get("shadow_promotions") == 0
        and metrics.get("unit_tests") == 17
        and metrics.get("upstream_executions") == 0
        and metrics.get("upstream_paths_or_database_primary_keys") == 0
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
        validate_pin_policy_and_implementation(),
        validate_fixtures(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_execution())
    if lane_report is not None:
        checks.append(validate_full_lane_report(lane_report))
    _require(all(check.status == "PASS" for check in checks), "an Adapters004 check failed")
    return checks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.adapters.004")
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
