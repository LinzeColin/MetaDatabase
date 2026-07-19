#!/usr/bin/env python3
"""Fail-closed verifier for x2n Stage 0 / Phase 0.2.

This verifier audits evidence and pins; it never installs or executes upstream
product code. Adapter behavior acceptances remain downstream NOT_RUN.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
REGISTRY = PROJECT_ROOT / "machine/facts/upstream_registry.json"
HASH_MANIFEST = PROJECT_ROOT / "machine/facts/upstream_file_hashes.json"
POLICY = PROJECT_ROOT / "machine/policy/upstream_integration_policy.json"
ARTIFACT_ALLOWLIST = PROJECT_ROOT / "machine/policy/artifact_allowlist.json"
SBOM = PROJECT_ROOT / "machine/sbom/stage_0_phase_0_2.cdx.json"
NOTICE = PROJECT_ROOT / "THIRD_PARTY_NOTICES.md"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
EVIDENCE_DIR = PROJECT_ROOT / "machine/evidence/stage_0/phase_0_2"

PHASE_TASK = "TSK.x2n.discovery.004"
EXPECTED = {
    "xiaohongshu-exporter": {
        "remote": "https://github.com/zhulin025/xiaohongshu-exporter.git",
        "commit": "130b3ceb156278597c16f7e7e98d93ff42acaadf",
        "tree": "7e7d1861a3c5b0c3cd5afd66198b99bcc4e35ec8",
        "license": "missing",
    },
    "douyin-downloader": {
        "remote": "https://github.com/jiji262/douyin-downloader.git",
        "commit": "ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7",
        "tree": "ff7774b618f269fcdc750e17dc63612f159b6b46",
        "license": "MIT",
    },
    "MediaCrawler": {
        "remote": "https://github.com/NanmiCoder/MediaCrawler.git",
        "commit": "0625e01a6bc717a3fc9c96d3dac7fb8957043838",
        "tree": "68b28cbdd7b948911c1d61f8e584d042fced0504",
        "license": "restricted",
    },
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
    _require(path.is_file(), f"missing JSON: {path.name}")
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(args: list[str], cwd: Path, *, binary: bool = False) -> str | bytes:
    result = subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=not binary)
    _require(result.returncode == 0, f"command failed: {args[0]} {args[1] if len(args) > 1 else ''}")
    if binary:
        return result.stdout
    return result.stdout.rstrip()


def validate_registry() -> Check:
    registry = _load_json(REGISTRY)
    _require(registry.get("task_id") == PHASE_TASK, "registry task mismatch")
    _require(registry.get("phase") == "PH.X2N.0.2", "registry phase mismatch")
    _require(registry.get("actual_runtime_dependencies") == [], "runtime dependencies must remain empty")

    repositories = registry.get("repositories", [])
    _require(len(repositories) == 3, "exactly three candidates required")
    by_id = {item.get("id"): item for item in repositories}
    _require(set(by_id) == set(EXPECTED), "candidate registry mismatch")
    for repo_id, expected in EXPECTED.items():
        item = by_id[repo_id]
        _require(item.get("selected_commit") == expected["commit"], f"wrong pin: {repo_id}")
        _require(item.get("observed_main_commit") == expected["commit"], f"wrong observed ref: {repo_id}")
        _require(item.get("tree") == expected["tree"], f"wrong tree: {repo_id}")
        _require(item.get("pin_state") == "exact_commit", f"non-exact pin: {repo_id}")
        integration = item.get("integration", {})
        _require(integration.get("enabled") is False, f"candidate enabled: {repo_id}")
        _require(integration.get("bundled") is False, f"candidate bundled: {repo_id}")
        _require(integration.get("runtime_dependency") is False, f"candidate entered runtime: {repo_id}")

    xhs = by_id["xiaohongshu-exporter"]
    _require(xhs["license"]["verification"] == "unverified_missing_license_file", "xhs license must fail closed")
    _require(xhs["license"]["code_copy_allowed"] is False, "xhs code copy allowed")
    _require(xhs["integration"]["mode"] == "clean_room_reference_only", "xhs clean-room gate missing")

    douyin = by_id["douyin-downloader"]
    _require(douyin["license"]["spdx"] == "MIT", "douyin MIT missing")
    _require(douyin["dependency_state"]["lock_present"] is False, "douyin lock state must reflect tree")
    _require(douyin["dependency_state"]["reproducible_environment"] is False, "unlocked environment called reproducible")

    media = by_id["MediaCrawler"]
    _require(media["license"]["spdx"] == "LicenseRef-NON-COMMERCIAL-LEARNING-1.1", "MediaCrawler restriction missing")
    _require(media["integration"]["core_dependency"] is False, "MediaCrawler entered core")

    metrics = registry.get("metrics", {})
    _require(metrics.get("actual_runtime_dependency_count") == 0, "runtime dependency count is non-zero")
    _require(metrics.get("unknown_license_runtime_dependency_count") == 0, "unknown runtime license exists")
    _require(metrics.get("unpinned_runtime_upstream_count") == 0, "unpinned runtime upstream exists")
    _require(metrics.get("xiaohongshu_unverified_code_copies") == 0, "xhs code copy exists")
    _require(metrics.get("mediacrawler_bundled") is False, "MediaCrawler bundled")

    required = registry.get("required_personal_collection_capabilities", {})
    _require(required.get("xiaohongshu_likes_and_favorites_official_api") == "unknown_disabled", "xhs platform uncertainty weakened")
    _require(required.get("douyin_likes_and_favorites_official_api") == "unknown_disabled", "douyin platform uncertainty weakened")
    _require(required.get("upstream_implementation_is_authorization_evidence") is False, "upstream code treated as authorization")

    gates = registry.get("gates", {})
    _require(gates.get("product_code_started") is False, "product code started in discovery")
    _require(gates.get("real_account_execution") is False, "real account execution recorded")
    _require(gates.get("adapter_enablement") is False, "adapter enabled")
    _require(gates.get("stage_gate") == "not_run", "Stage gate changed")
    return Check("dependency_registry", "PASS", {"candidates": 3, "runtime_dependencies": 0, "all_disabled": True})


def validate_hash_manifest() -> Check:
    manifest = _load_json(HASH_MANIFEST)
    _require(manifest.get("algorithm") == "sha256", "wrong hash algorithm")
    files = manifest.get("files", [])
    _require(len(files) == 27, f"expected 27 hashed files, got {len(files)}")
    identities: set[tuple[str, str]] = set()
    counts = {repo_id: 0 for repo_id in EXPECTED}
    for item in files:
        repo_id = item.get("repository")
        _require(repo_id in EXPECTED, "hash references unknown repository")
        _require(item.get("commit") == EXPECTED[repo_id]["commit"], f"hash pin mismatch: {repo_id}")
        _require(re.fullmatch(r"[0-9a-f]{40}", item.get("git_blob", "")) is not None, "invalid Git blob")
        _require(re.fullmatch(r"[0-9a-f]{64}", item.get("sha256", "")) is not None, "invalid SHA-256")
        path = item.get("path", "")
        _require(path and not Path(path).is_absolute() and ".." not in Path(path).parts, "unsafe evidence path")
        identity = (repo_id, path)
        _require(identity not in identities, f"duplicate file evidence: {identity}")
        identities.add(identity)
        counts[repo_id] += 1
    _require(counts == {"xiaohongshu-exporter": 6, "douyin-downloader": 9, "MediaCrawler": 12}, "file evidence count drift")
    return Check("upstream_file_hashes", "PASS", {"files": len(files), "repositories": 3})


def validate_policy() -> Check:
    policy = _load_json(POLICY)
    _require(policy.get("default") == "deny", "upstream policy is not deny-by-default")
    _require(policy.get("actual_runtime_dependencies") == [], "policy runtime dependencies are non-empty")
    copies = policy.get("source_copy", {})
    _require(copies.get("xiaohongshu-exporter") == "forbidden", "xhs source copy not forbidden")
    _require(copies.get("MediaCrawler") == "forbidden", "MediaCrawler source copy not forbidden")
    wrapper = set(policy.get("future_douyin_wrapper_requirements", []))
    required = {
        "exact_commit_and_exact_integration_lock",
        "transitive_license_scan_and_sbom",
        "version_mismatch_blocks",
        "unknown_schema_blocks",
        "synthetic_normal_missing_unknown_error_timeout_schema_drift_fixtures",
        "all_output_paths_under_X2N_DATA_ROOT",
        "upstream_database_json_manifest_and_cookie_persistence_disabled",
        "cdn_urls_credentials_raw_media_and_upstream_paths_removed_before_canonical",
    }
    _require(required.issubset(wrapper), "douyin wrapper gates incomplete")
    constraints = set(policy.get("global_constraints", []))
    _require("no_automatic_scrolling" in constraints, "auto-scroll gate missing")
    _require("no_account_state_change" in constraints, "account-state gate missing")
    _require("feature_flags_default_off" in constraints, "feature flag gate missing")
    artifact_policy = _load_json(ARTIFACT_ALLOWLIST)
    _require("dependency_and_license_manifests" in artifact_policy.get("allowed_classes", []), "dependency evidence is not an allowed artifact class")
    enforcement = set(artifact_policy.get("enforcement", []))
    _require({"scripts/verify_phase_0_1.py", "scripts/verify_phase_0_2.py"}.issubset(enforcement), "artifact enforcement entrypoints incomplete")
    return Check("upstream_integration_policy", "PASS", {"default": "deny", "wrapper_gates": len(wrapper)})


def validate_notice() -> Check:
    _require(NOTICE.is_file(), "THIRD_PARTY_NOTICES missing")
    text = NOTICE.read_text(encoding="utf-8")
    required = (
        "ef3ad18c2b50e38e534f72aabe2b3fbb0b3fadd7",
        "License: MIT",
        "Copyright (c) 2026 jiji262",
        "UNVERIFIED_MISSING_LICENSE_FILE",
        "130b3ceb156278597c16f7e7e98d93ff42acaadf",
        "NON-COMMERCIAL LEARNING LICENSE 1.1",
        "0625e01a6bc717a3fc9c96d3dac7fb8957043838",
        "not bundled",
    )
    missing = [value for value in required if value not in text]
    _require(not missing, f"notice fields missing: {missing}")
    return Check("license_notice", "PASS", {"douyin_mit_notice": True, "excluded_candidates": 2})


def validate_sbom() -> Check:
    sbom = _load_json(SBOM)
    _require(sbom.get("bomFormat") == "CycloneDX", "SBOM format mismatch")
    _require(sbom.get("specVersion") == "1.5", "SBOM spec mismatch")
    component = sbom.get("metadata", {}).get("component", {})
    _require(component.get("name") == "xhs-douyin-2notion", "SBOM root component mismatch")
    components = sbom.get("components", [])
    _require(len(components) == 3, "SBOM candidate count mismatch")
    scopes = {item.get("name"): item.get("scope") for item in components}
    _require(scopes == {"xiaohongshu-exporter": "excluded", "douyin-downloader": "optional", "MediaCrawler": "excluded"}, "SBOM scope mismatch")
    for item in components:
        properties = {prop.get("name"): prop.get("value") for prop in item.get("properties", [])}
        _require(properties.get("x2n:actual-runtime") == "false", f"SBOM actual runtime mismatch: {item.get('name')}")
    dependencies = sbom.get("dependencies")
    _require(dependencies == [{"ref": "x2n@v0.0.0.1", "dependsOn": []}], "SBOM actual dependency graph is not empty")
    return Check("sbom_dry_run", "PASS", {"actual_runtime_dependencies": 0, "audited_candidates": 3})


def _text_files() -> Iterable[Path]:
    ignored = {"__pycache__", ".pytest_cache"}
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and not any(part in ignored for part in path.parts):
            if path.suffix.lower() in {"", ".md", ".json", ".yaml", ".yml", ".py", ".toml", ".txt"}:
                yield path


def validate_repository_boundary() -> Check:
    forbidden_directories = {"vendor", "third_party", "upstreams", "xiaohongshu-exporter", "douyin-downloader", "MediaCrawler"}
    directory_hits = [path.name for path in PROJECT_ROOT.rglob("*") if path.is_dir() and path.name in forbidden_directories]
    _require(not directory_hits, f"vendored upstream directory found: {directory_hits}")
    forbidden_files = [
        str(path.relative_to(PROJECT_ROOT))
        for path in PROJECT_ROOT.rglob("*")
        if path.is_file() and (path.suffix.lower() == ".zip" or path.name.endswith(".min.js"))
    ]
    _require(not forbidden_files, f"upstream binary/minified artifact found: {forbidden_files}")

    credential_prefix = "github" + "_pat_"
    credential_hits: list[str] = []
    authenticated_remote_hits: list[str] = []
    for path in _text_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(re.escape(credential_prefix) + r"[A-Za-z0-9]", text):
            credential_hits.append(str(path.relative_to(PROJECT_ROOT)))
        if re.search(r"https://[^\s/@]+@github\.com/", text):
            authenticated_remote_hits.append(str(path.relative_to(PROJECT_ROOT)))
    _require(not credential_hits, f"credential-shaped value entered repository: {credential_hits}")
    _require(not authenticated_remote_hits, f"authenticated remote entered repository: {authenticated_remote_hits}")
    return Check("repository_upstream_boundary", "PASS", {"vendored_directories": 0, "credential_hits": 0, "authenticated_remote_hits": 0})


def validate_task_state() -> Check:
    with TASKPACK.open("r", encoding="utf-8") as handle:
        taskpack = yaml.safe_load(handle)
    task = next((item for item in taskpack.get("tasks", []) if item.get("id") == PHASE_TASK), None)
    _require(task is not None, "Phase task missing")
    _require(task.get("phase") == "PH.X2N.0.2", "Phase task routing mismatch")
    _require(task.get("status") == "completed", "Phase task not completed")
    _require(task.get("depends_on") == ["TSK.x2n.discovery.001"], "Phase dependency drift")
    _require(task.get("acceptance_ids") == ["ACC.x2n.gov.003", "ACC.x2n.dy.003"], "Phase acceptances drift")

    state = _load_json(TASK_STATE)
    state_phase = state.get("phase")
    _require(state_phase in {"PH.X2N.0.2", "PH.X2N.0.5"}, "task_state no longer contains a valid Phase 0.2+ state")
    expected_run = "RUN-X2N-S00-P02" if state_phase == "PH.X2N.0.2" else "RUN-X2N-S00-P05"
    _require(state.get("run_id") == expected_run, "task_state run mismatch")
    _require(state.get("state") == "phase_pass", "Phase state is not pass")
    _require(state.get("tasks", {}).get(PHASE_TASK) == "pass", "Phase task state not pass")
    acceptances = state.get("acceptance_status", {})
    _require(acceptances.get("ACC.x2n.gov.003") == "pass_current_artifact_scope", "governance acceptance status mismatch")
    _require(acceptances.get("ACC.x2n.dy.003") == "baseline_pass_downstream_not_run", "douyin downstream status overstated")
    expected_next = "PH.X2N.0.5" if state_phase == "PH.X2N.0.2" else "STG.X2N.0.REVIEW"
    _require(state.get("next_phase") == expected_next, "next phase mismatch")
    _require(state.get("next_phase_authorized") is False, "next phase auto-authorized")
    _require(state.get("stage_gate") == "not_run", "Stage gate changed")
    _require(state.get("remote_upload") == "forbidden_until_stage_gate", "remote upload gate weakened")
    return Check("phase_task_state", "PASS", {"task": PHASE_TASK, "stage_gate": "NOT_RUN", "adapter_contract": "DOWNSTREAM_NOT_RUN"})


def validate_source_snapshots(source_root: Path) -> Check:
    _require(source_root.is_dir() and not source_root.is_symlink(), "source snapshot root missing or symlinked")
    manifest = _load_json(HASH_MANIFEST)
    hash_items = manifest["files"]
    verified_files = 0
    for repo_id, expected in EXPECTED.items():
        repo = source_root / repo_id
        _require(repo.is_dir() and not repo.is_symlink(), f"snapshot missing: {repo_id}")
        # Read the persisted local value. `git remote get-url` may expand an
        # owner-global insteadOf rule containing authentication material even
        # when the clone config itself is credential-free.
        remote = _run(["git", "config", "--local", "--get", "remote.origin.url"], repo)
        _require(remote == expected["remote"], f"persisted remote is not normalized: {repo_id}")
        git_config = (repo / ".git/config").read_text(encoding="utf-8", errors="replace")
        _require(("github" + "_pat_") not in git_config, f"credential remained in temp clone: {repo_id}")
        _require(re.search(r"https://[^\s/@]+@github\.com/", git_config) is None, f"authenticated remote remained: {repo_id}")
        _run(["git", "cat-file", "-e", f"{expected['commit']}^{{commit}}"], repo)
        tree = _run(["git", "rev-parse", f"{expected['commit']}^{{tree}}"], repo)
        _require(tree == expected["tree"], f"tree mismatch: {repo_id}")
        observed_ref = _run(["git", "rev-parse", "refs/remotes/origin/main"], repo)
        _require(observed_ref == expected["commit"], f"observed main mismatch: {repo_id}")

        names_text = _run(["git", "ls-tree", "-r", "--name-only", expected["commit"]], repo)
        names = names_text.splitlines()
        license_names = [name for name in names if Path(name).name.upper() in {"LICENSE", "COPYING", "NOTICE"}]
        if expected["license"] == "missing":
            _require(not license_names, "xhs repository unexpectedly has a license file; registry needs re-audit")
        else:
            _require("LICENSE" in names, f"repository LICENSE missing: {repo_id}")
            license_bytes = _run(["git", "show", f"{expected['commit']}:LICENSE"], repo, binary=True)
            _require(isinstance(license_bytes, bytes), "binary Git output expected")
            if expected["license"] == "MIT":
                _require(license_bytes.startswith(b"MIT License\n"), "douyin license is not MIT")
                _require(b"Copyright (c) 2026 jiji262" in license_bytes, "douyin copyright missing")
            else:
                _require(license_bytes.startswith(b"NON-COMMERCIAL LEARNING LICENSE 1.1\n"), "MediaCrawler restriction drifted")

        if repo_id == "douyin-downloader":
            lock_names = {name for name in names if Path(name).name in {"uv.lock", "poetry.lock", "Pipfile.lock", "requirements.lock"}}
            _require(not lock_names, "douyin lock appeared; registry needs re-audit")
        if repo_id == "MediaCrawler":
            _require("uv.lock" in names, "MediaCrawler lock missing")

        for item in (entry for entry in hash_items if entry["repository"] == repo_id):
            blob = _run(["git", "rev-parse", f"{expected['commit']}:{item['path']}"], repo)
            _require(blob == item["git_blob"], f"blob mismatch: {repo_id}/{item['path']}")
            content = _run(["git", "show", f"{expected['commit']}:{item['path']}"], repo, binary=True)
            _require(isinstance(content, bytes), "binary Git output expected")
            digest = hashlib.sha256(content).hexdigest()
            _require(digest == item["sha256"], f"SHA-256 mismatch: {repo_id}/{item['path']}")
            verified_files += 1
    _require(verified_files == 27, "not all upstream evidence files verified")
    return Check("official_source_snapshots", "PASS", {"repositories": 3, "files": verified_files, "credential_hits": 0})


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
    repo_root = Path(_run(["git", "rev-parse", "--show-toplevel"], PROJECT_ROOT)).resolve()
    _require(repo_root == REPOSITORY_ROOT.resolve(), "project is not in MetaDatabase worktree")
    branch = _run(["git", "branch", "--show-current"], repo_root)
    _require(
        branch in {
            "codex/xhs-douyin-2notion-v0001-s00-p02",
            "codex/xhs-douyin-2notion-v0001-s00-p05",
        },
        "wrong Phase 0.2-compatible branch",
    )
    status = _run(["git", "-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], repo_root)
    changed = _porcelain_paths(status)
    scope_allowed, legacy_deletions = _scope_status(status)
    _require(scope_allowed, "changed scope escaped project")
    if "README.md" in changed:
        _validate_parent_index_diff(_run(["git", "diff", "HEAD", "--unified=0", "--no-color", "--", "README.md"], repo_root))

    blocks = _run(["git", "worktree", "list", "--porcelain"], repo_root).split("\n\n")
    main_path: Path | None = None
    for block in blocks:
        fields = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in fields if line.startswith("worktree ")), None)
        branch_field = next((line for line in fields if line.startswith("branch ")), None)
        if worktree and branch_field == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None, "main worktree not found")
    _require(_run(["git", "branch", "--show-current"], main_path) == "main", "main worktree is not on main")
    main_status = _run(
        ["git", "-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"],
        main_path,
    )
    isolation = _evaluate_main_isolation(_porcelain_paths(main_status), allow_external_main_dirty)
    return Check(
        "worktree_scope",
        "PASS",
        {"branch": branch, "changed_paths": len(changed), "legacy_project_deletions": legacy_deletions, **isolation},
    )


def validate_temp_cleanup() -> Check:
    run_root = Path.home() / "Downloads" / "MediaCrawler" / "xhs-douyin-2notion" / "downloads" / "external_research" / "runs" / "RUN-X2N-S00-P02"
    _require(not run_root.exists(), "Phase 0.2 temporary source snapshot still exists")
    return Check("temporary_snapshot_cleanup", "PASS", {"run_id": "RUN-X2N-S00-P02", "remaining_entries": 0})


def validate_evidence() -> Check:
    required = {
        "verification.json",
        "TSK.x2n.discovery.004.json",
        "ACC.x2n.gov.003.json",
        "ACC.x2n.dy.003.json",
        "cleanup.json",
    }
    actual = {path.name for path in EVIDENCE_DIR.glob("*.json")}
    _require(required == actual, f"evidence file set mismatch: {sorted(actual)}")
    verification = _load_json(EVIDENCE_DIR / "verification.json")
    _require(verification.get("status") == "PASS", "verification receipt is not PASS")
    _require(verification.get("phase") == "PH.X2N.0.2", "verification phase mismatch")
    _require(verification.get("registry_sha256") == _sha256(REGISTRY), "registry evidence hash mismatch")
    _require(verification.get("hash_manifest_sha256") == _sha256(HASH_MANIFEST), "hash-manifest evidence hash mismatch")
    _require(verification.get("sbom_sha256") == _sha256(SBOM), "SBOM evidence hash mismatch")
    _require(verification.get("route_revalidated_by_run") == "RUN-X2N-S00-P05", "owner route revalidation run missing")
    _require(verification.get("route_change_event") == "CE-X2N-20260719-S00-P05", "owner route change event missing")
    _require(verification.get("route_revalidation_scope") == "owner_project_name_only_no_upstream_content_change", "Phase 0.2 route revalidation scope is ambiguous")
    _require(verification.get("source_snapshot_verification") == "PASS", "source snapshot evidence missing")
    _require(verification.get("adapter_contract_tests") == "DOWNSTREAM_NOT_RUN", "adapter acceptance overstated")
    _require(verification.get("stage_gate") == "NOT_RUN", "evidence changed Stage gate")
    _require(verification.get("remote_upload") == "FORBIDDEN_UNTIL_STAGE_GATE", "evidence weakened upload gate")

    task = _load_json(EVIDENCE_DIR / "TSK.x2n.discovery.004.json")
    _require(task.get("task_status") == "PASS", "task receipt is not PASS")
    gov = _load_json(EVIDENCE_DIR / "ACC.x2n.gov.003.json")
    _require(gov.get("status") == "PASS_CURRENT_ARTIFACT_SCOPE", "governance acceptance scope mismatch")
    dy = _load_json(EVIDENCE_DIR / "ACC.x2n.dy.003.json")
    _require(dy.get("status") == "BASELINE_PASS_DOWNSTREAM_NOT_RUN", "douyin acceptance overstated")
    cleanup = _load_json(EVIDENCE_DIR / "cleanup.json")
    _require(cleanup.get("status") == "PASS" and cleanup.get("remaining_entries") == 0, "cleanup receipt mismatch")
    return Check("evidence_receipts", "PASS", {"files": len(actual), "adapter_contract": "DOWNSTREAM_NOT_RUN"})


def run_core_checks() -> list[Check]:
    return [
        validate_registry(),
        validate_hash_manifest(),
        validate_policy(),
        validate_notice(),
        validate_sbom(),
        validate_repository_boundary(),
        validate_task_state(),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--verify-temp-cleanup", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        _require(not args.allow_external_main_dirty or args.verify_worktree, "--allow-external-main-dirty requires --verify-worktree")
        checks = run_core_checks()
        if args.source_root:
            checks.append(validate_source_snapshots(args.source_root))
        if args.verify_worktree:
            checks.append(validate_worktree_scope(args.allow_external_main_dirty))
        if args.verify_temp_cleanup:
            checks.append(validate_temp_cleanup())
        if args.require_evidence:
            checks.append(validate_evidence())
        result = {
            "status": "PASS",
            "phase": "PH.X2N.0.2",
            "checks": [check.__dict__ for check in checks],
            "adapter_contract_tests": "DOWNSTREAM_NOT_RUN",
            "stage_gate": "NOT_RUN",
            "remote_upload": "FORBIDDEN_UNTIL_STAGE_GATE",
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, ValueError, VerificationError, yaml.YAMLError) as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
