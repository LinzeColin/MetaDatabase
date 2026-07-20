#!/usr/bin/env python3
"""Fail-closed verifier for TSK.x2n.foundation.002."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
TASK_ID = "TSK.x2n.foundation.002"
RUN_ID = "RUN-X2N-S01-F002"
BRANCH = "codex/xhs-douyin-2notion-v0001-s01-foundation001"
TASK_BASE_COMMIT = "69130c1db9946850b23e1c78f771129eb094eea2"
FINAL_COMMIT = "ae17e377090ef3bc1123d2512cda0daef9efe1cb"
ORIGIN_CUTOFF = "f1e5016a4e1bba10c86d8dd017868d5d64835f42"
TASKPACK = PROJECT_ROOT / "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml"
TASK_STATE = PROJECT_ROOT / "machine/facts/task_state.json"
PROJECT_FACT = PROJECT_ROOT / "machine/facts/project.json"
CONTRACT_ROOT = PROJECT_ROOT / "packages/contracts"
FIXTURE_ROOT = PROJECT_ROOT / "packages/test-fixtures/contracts/v1"
FIXTURE_MANIFEST = PROJECT_ROOT / "machine/policy/synthetic_fixture_manifest.json"
SBOM = PROJECT_ROOT / "machine/sbom/stage_1_foundation_002.cdx.json"
EVIDENCE = PROJECT_ROOT / "evidence/contracts/TSK.x2n.foundation.002.json"

EXPECTED_CONTRACTS = (
    "native_message_request",
    "native_message_response",
    "native_host_policy",
    "canonical_content",
    "user_relation",
    "source_observation",
    "artifact",
    "taxonomy_category",
    "classification",
    "sink_receipt",
    "health_report",
    "error",
    "provenance_chain",
    "compatibility_policy",
)
PYTHON_DEPENDENCIES = {
    "annotated-types": "0.7.0",
    "pydantic": "2.13.4",
    "pydantic-core": "2.46.4",
    "typing-extensions": "4.16.0",
    "typing-inspection": "0.4.2",
}
ERROR_CLASSES = {
    "user_action_required",
    "platform_changed",
    "rate_limited",
    "network",
    "dependency_missing",
    "provider",
    "invalid_input",
    "security_blocked",
    "storage",
    "data_integrity",
    "policy",
    "unknown",
}

ALLOWED_CHANGED_EXACT = {
    "CHANGELOG.md",
    "HANDOFF.md",
    "README.md",
    "SKILL.md",
    "THIRD_PARTY_NOTICES.md",
    "package.json",
    "package-lock.json",
    "pyproject.toml",
    "uv.lock",
    "功能清单.md",
    "开发记录.md",
    "模型参数文件.md",
    "docs/governance/RUN_CONTRACT_S01_FOUNDATION_002.md",
    "docs/product_design/v0.0.0.1/05_TASK_DAG_CODEX_TASKPACK.yaml",
    "machine/facts/architecture_decisions.json",
    "machine/facts/project.json",
    "machine/facts/task_state.json",
    "machine/policy/artifact_allowlist.json",
    "machine/policy/synthetic_fixture_manifest.json",
    "machine/sbom/stage_1_foundation_002.cdx.json",
    "scripts/generate_foundation_002_sbom.py",
    "scripts/verify_foundation_001.py",
    "scripts/verify_foundation_002.py",
    "scripts/verify_phase_0_2.py",
    "scripts/verify_phase_0_5.py",
    "scripts/verify_stage_0_review.py",
    "tests/test_foundation_001.py",
    "tests/test_foundation_002.py",
}
ALLOWED_CHANGED_PREFIXES = (
    "packages/contracts/",
    "packages/test-fixtures/contracts/",
    "evidence/contracts/",
)


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
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    _require(isinstance(value, dict), f"JSON object required: {path.name}")
    return value


def _git(args: Sequence[str], cwd: Path = REPOSITORY_ROOT) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, "Git scope check failed")
    return result.stdout.rstrip()


def _porcelain_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if not line:
            continue
        value = line[3:]
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        paths.append(value)
    return paths


def _project_relative(path: str) -> Optional[str]:
    prefix = "xhs-douyin-2notion/"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return "" if path == "xhs-douyin-2notion" else None


def _allowed_change(relative: str) -> bool:
    return relative in ALLOWED_CHANGED_EXACT or relative.startswith(ALLOWED_CHANGED_PREFIXES)


def _task_block(text: str, task_id: str) -> str:
    match = re.search(
        rf"(?ms)^- id: {re.escape(task_id)}\n(?P<body>.*?)(?=^- id: TSK\.x2n\.|\Z)",
        text,
    )
    _require(match is not None, f"Task block missing: {task_id}")
    return match.group(0)


def _field(block: str, name: str) -> str:
    match = re.search(rf"(?m)^  {re.escape(name)}: ([^\n]+)$", block)
    _require(match is not None, f"Task field missing: {name}")
    return match.group(1).strip().strip("'\"")


def _list_field(block: str, name: str) -> list[str]:
    match = re.search(rf"(?ms)^  {re.escape(name)}:\n(?P<items>(?:  - [^\n]+\n)*)", block)
    _require(match is not None, f"Task list field missing: {name}")
    return [line.removeprefix("  - ") for line in match.group("items").splitlines()]


def _iter_files() -> Iterable[Path]:
    ignored = {".git", "node_modules", "__pycache__", ".pytest_cache", ".venv", "dist", "build"}
    for path in PROJECT_ROOT.rglob("*"):
        if path.is_file() and not any(part in ignored for part in path.parts):
            yield path


def validate_scope() -> Check:
    # Scope is historical: later DAG Tasks are verified independently and
    # must not be charged to the completed foundation.002 Run.
    changed = _git(
        ["-c", "core.quotePath=false", "diff", "--name-only", f"{TASK_BASE_COMMIT}..{FINAL_COMMIT}"]
    ).splitlines()
    relative_changes: list[str] = []
    for path in changed:
        relative = _project_relative(path)
        _require(relative is not None, "foundation.002 changed scope escaped x2n")
        _require(_allowed_change(relative), f"unregistered foundation.002 change: {relative}")
        relative_changes.append(relative)

    forbidden_tokens = (
        "Agent" + "Database",
        "OpenAI" + "Database",
        "/" + "Users/",
        "github" + "_pat_",
        "Bearer" + " ",
    )
    legacy_cdn_pattern = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp)",
        flags=re.IGNORECASE,
    )
    expanded_cdn_pattern = re.compile(
        r"https?://[^\s'\"]*(?:xhscdn|douyinvod|byteimg|pstatp|bilivideo|hdslb|kscdn|yximgs|sinaimg|alicdn|tbcdn)",
        flags=re.IGNORECASE,
    )
    changed_relative = set(relative_changes)
    scanned = 0
    for path in _iter_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="replace")
        _require(not any(token in text for token in forbidden_tokens), "forbidden repository, path or credential-shaped token entered x2n")
        relative = str(path.relative_to(PROJECT_ROOT))
        pattern = expanded_cdn_pattern if relative in changed_relative else legacy_cdn_pattern
        _require(pattern.search(text) is None, "platform media CDN URL entered x2n changed scope")
    forbidden_suffixes = {".sqlite", ".sqlite3", ".db", ".mp4", ".mov", ".m4a", ".mp3", ".wav", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".pem", ".p12", ".pfx"}
    _require(not any(path.suffix.lower() in forbidden_suffixes for path in _iter_files()), "private/runtime file type entered x2n")
    return Check(
        "scope_and_privacy",
        "PASS",
        {
            "changed_files": len(relative_changes),
            "out_of_scope_writes": 0,
            "sensitive_or_media_url_hits": 0,
            "text_files_scanned": scanned,
        },
    )


def validate_worktree(allow_external_main_dirty: bool) -> Check:
    _require(Path(_git(["rev-parse", "--show-toplevel"])).resolve() == REPOSITORY_ROOT.resolve(), "wrong Git root")
    _require(_git(["branch", "--show-current"]) == BRANCH, "wrong Stage 1 worktree branch")
    persisted_remote = _git(["config", "--local", "--get", "remote.origin.url"])
    _require(
        re.fullmatch(r"(?:https://github\.com/|git@github\.com:)LinzeColin/MetaDatabase(?:\.git)?", persisted_remote) is not None,
        "wrong or authenticated persisted origin",
    )
    for commit in (TASK_BASE_COMMIT, FINAL_COMMIT):
        _git(["cat-file", "-e", f"{commit}^{{commit}}"])
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, FINAL_COMMIT],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "foundation.002 final commit no longer descends from its Task base",
    )
    _require(
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", FINAL_COMMIT, "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=False,
        ).returncode
        == 0,
        "foundation branch no longer contains the verified foundation.002 commit",
    )
    _git(["cat-file", "-e", f"{ORIGIN_CUTOFF}^{{commit}}"])
    _require(
        subprocess.run(["git", "merge-base", "--is-ancestor", TASK_BASE_COMMIT, "HEAD"], cwd=REPOSITORY_ROOT, check=False).returncode == 0,
        "foundation.002 branch no longer descends from its Task base",
    )
    live_origin = _git(["rev-parse", "origin/main"])
    _require(
        subprocess.run(["git", "merge-base", "--is-ancestor", ORIGIN_CUTOFF, live_origin], cwd=REPOSITORY_ROOT, check=False).returncode == 0,
        "origin/main no longer descends from the review cutoff",
    )
    origin_paths = _git(["-c", "core.quotePath=false", "diff", "--name-only", f"{ORIGIN_CUTOFF}..{live_origin}"]).splitlines()
    origin_overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in origin_paths)
    _require(origin_overlap == 0, "origin/main changed x2n after the review cutoff")

    main_path: Optional[Path] = None
    for block in _git(["worktree", "list", "--porcelain"]).split("\n\n"):
        lines = block.splitlines()
        worktree = next((line.removeprefix("worktree ") for line in lines if line.startswith("worktree ")), None)
        branch = next((line for line in lines if line.startswith("branch ")), None)
        if worktree and branch == "branch refs/heads/main":
            main_path = Path(worktree)
            break
    _require(main_path is not None and _git(["branch", "--show-current"], main_path) == "main", "MetaDatabase main worktree is unavailable or off main")
    main_paths = _porcelain_paths(
        _git(["-c", "core.quotePath=false", "status", "--porcelain=v1", "--untracked-files=all"], main_path)
    )
    main_overlap = sum(path == "xhs-douyin-2notion" or path.startswith("xhs-douyin-2notion/") for path in main_paths)
    _require(main_overlap == 0, "MetaDatabase main worktree dirty state overlaps x2n")
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


def validate_task_and_state() -> Check:
    taskpack = TASKPACK.read_text(encoding="utf-8")
    task = _task_block(taskpack, TASK_ID)
    _require(_field(task, "status") == "completed", "foundation.002 Task is not completed")
    _require(_field(task, "stage") == "STG.X2N.1" and _field(task, "phase") == "PH.X2N.1.2", "foundation.002 routing drifted")
    _require(_list_field(task, "depends_on") == ["TSK.x2n.foundation.001", "TSK.x2n.discovery.005"], "foundation.002 dependency drifted")
    _require(_list_field(task, "acceptance_ids") == ["ACC.x2n.ext.003", "ACC.x2n.data.001", "ACC.x2n.data.003"], "foundation.002 Acceptance drifted")
    _require("  status: STAGE_1_FOUNDATION_004_COMPLETE_G1_NOT_RUN\n" in taskpack, "Taskpack current status drifted")

    state = _load_json(TASK_STATE)
    _require(state.get("schema_version") == "1.6", "task state schema drifted")
    _require(state.get("stage") == "STG.X2N.1" and state.get("last_completed_phase") == "PH.X2N.1.4", "current Stage routing drifted")
    _require(state.get("run_id") == "RUN-X2N-S01-F004" and state.get("run_kind") == "single_dag_task", "current Run identity drifted")
    _require(state.get("tasks", {}).get(TASK_ID) == "pass", "foundation.002 Task state is not pass")
    _require(state.get("tasks", {}).get("TSK.x2n.foundation.003") == "pass", "foundation.003 Task state is not pass")
    _require(state.get("tasks", {}).get("TSK.x2n.foundation.004") == "pass", "foundation.004 Task state is not pass")
    _require(state.get("next_phase") == "PH.X2N.1.5" and state.get("next_run") == "TSK.x2n.foundation.005", "next Task routing drifted")
    _require(state.get("current_stage_gate") == "not_run" and state.get("current_stage_remote_upload") == "forbidden_until_g1_pass", "G1/upload overstated")
    acceptance = state.get("acceptance_status", {})
    _require(acceptance.get("ACC.x2n.ext.003") == "pass_temp_native_host_contract_idempotency_injection", "Native Acceptance did not advance through foundation.004")
    _require(acceptance.get("ACC.x2n.data.001") == "pass_sqlite_store_scope_schema_fk_unique_integrity", "data schema Acceptance did not advance through foundation.003")
    _require(acceptance.get("ACC.x2n.data.003") == "pass_synthetic_contract_scope_real_sinks_downstream_not_run", "provenance Acceptance overstated")
    project = _load_json(PROJECT_FACT)
    _require(project.get("status") == "stage_1_foundation_004_complete_g1_not_run", "project state drifted")
    return Check(
        "task_state",
        "PASS",
        {
            "acceptance_scope": "CURRENT_CONTRACT_AND_SYNTHETIC_ONLY",
            "downstream": "REAL_SINKS_NOT_RUN",
            "next_task": "TSK.x2n.foundation.005",
            "task": TASK_ID,
        },
    )


def _visit_schema(value: Any, *, object_count: list[int], properties: set[str]) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object":
            object_count[0] += 1
            _require(value.get("additionalProperties") is False, "generated object schema accepts unknown fields")
        node_properties = value.get("properties")
        if isinstance(node_properties, dict):
            properties.update(node_properties)
        for item in value.values():
            _visit_schema(item, object_count=object_count, properties=properties)
    elif isinstance(value, list):
        for item in value:
            _visit_schema(item, object_count=object_count, properties=properties)


def validate_contract_artifacts() -> Check:
    schema_paths = sorted((CONTRACT_ROOT / "schemas/v1").glob("*.schema.json"))
    _require([path.stem.removesuffix(".schema") for path in schema_paths] == sorted(EXPECTED_CONTRACTS), "JSON Schema set drifted")
    manifest = _load_json(CONTRACT_ROOT / "registry/contracts.v1.json")
    rows = manifest.get("contracts", [])
    _require([item.get("name") for item in rows] == list(EXPECTED_CONTRACTS), "contract registry order/set drifted")
    _require(manifest.get("contract_version") == "1.0" and manifest.get("unknown_fields") == "reject" and manifest.get("unknown_versions") == "reject", "compatibility policy weakened")
    _require(manifest.get("payload_hash") == {
        "algorithm": "sha256",
        "canonicalization": "utf8_json_sorted_keys_compact_safe_integer_v1",
        "typescript_helpers": ["canonicalPayloadJson", "computePayloadHash"],
    }, "payload-hash cross-language contract drifted")
    object_count = [0]
    properties: set[str] = set()
    for path in schema_paths:
        schema = _load_json(path)
        _require(schema.get("$id") == f"urn:x2n:contract:1.0:{path.stem.removesuffix('.schema')}", "Schema ID drifted")
        _require(schema.get("x-x2n-contract-version") == "1.0" and schema.get("x-x2n-compatibility") == "exact_match_fail_closed", "Schema version metadata drifted")
        _visit_schema(schema, object_count=object_count, properties=properties)
    forbidden = {"argv", "authorization", "command", "cookie", "cookies", "download_url", "executable", "file_path", "headers", "local_path", "media_url", "path", "proxy_url", "shell", "token"}
    _require(not properties.intersection(forbidden), "dangerous persistent property entered Contract")
    _require("page_url" in properties and "ephemeral_media_ref_ids" in properties, "canonical page/opaque media representation is incomplete")
    _require("private_payload_ref" in properties and "private_payload_hash" in properties, "private artifact indirection is incomplete")
    typescript = (CONTRACT_ROOT / "types/contracts.ts").read_text(encoding="utf-8")
    _require(all(f'"{name}"' in typescript for name in ERROR_CLASSES), "TypeScript error-class parity drifted")
    _require("created_by: \"owner\"" in typescript and "append_only: true" in typescript, "TypeScript governance constraints drifted")
    _require("canonicalPayloadJson" in typescript and "computePayloadHash" in typescript, "TypeScript payload-hash helpers missing")
    return Check(
        "contract_artifacts",
        "PASS",
        {
            "contract_version": "1.0",
            "contracts": len(EXPECTED_CONTRACTS),
            "dangerous_persistent_properties": 0,
            "object_schemas_default_deny": object_count[0],
            "typescript_single_generated_surface": True,
        },
    )


def validate_error_registry() -> Check:
    registry = _load_json(CONTRACT_ROOT / "registry/error_codes.v1.json")
    _require(set(registry.get("classes", [])) == ERROR_CLASSES, "error class registry is incomplete")
    rows = registry.get("errors", [])
    codes = [item.get("code") for item in rows]
    _require(len(codes) == len(set(codes)) == 24, "error code registry set/uniqueness drifted")
    _require({item.get("class") for item in rows} == ERROR_CLASSES, "not every error class has a stable code")
    _require(all(isinstance(item.get("retryable"), bool) for item in rows), "error retryability is ambiguous")
    rendered = json.dumps(registry, ensure_ascii=False)
    _require(re.search(r"https?://|/" + "Users/", rendered) is None, "error registry contains unsafe diagnostic data")
    return Check("error_taxonomy", "PASS", {"classes": len(ERROR_CLASSES), "codes": len(codes), "unknown_code_policy": "reject"})


def validate_fixtures() -> Check:
    main = _load_json(FIXTURE_MANIFEST)
    rows = main.get("fixtures", [])
    _require(len(rows) == 5, "synthetic fixture registration must preserve foundation.002 and append later Task fixtures")
    _require(rows[2] == {
        "id": "FIXTURE.X2N.S01.F002.001",
        "path": "packages/test-fixtures/contracts/v1/fixture_manifest.json",
        "case_count": 144,
        "purpose": "strict v1 contract round-trip, compatibility, provenance and Native security fuzz",
    }, "foundation.002 fixture registration drifted")
    suite = _load_json(FIXTURE_ROOT / "fixture_manifest.json")
    invalid = _load_json(FIXTURE_ROOT / "invalid_cases.json")
    _require(suite.get("valid_case_count") == 16 and len(suite.get("valid_cases", [])) == 16, "valid fixture count drifted")
    _require(suite.get("invalid_case_count") == 22 and len(invalid.get("cases", [])) == 22, "invalid fixture count drifted")
    _require(suite.get("generated_fuzz_case_count") == 106 and suite.get("case_count") == 144, "fuzz/total fixture count drifted")
    _require([item.get("id") for item in suite["valid_cases"]] == [f"F002-VALID-{index:03d}" for index in range(1, 17)], "valid fixture IDs drifted")
    _require([item.get("id") for item in invalid["cases"]] == [f"F002-INVALID-{index:03d}" for index in range(1, 23)], "invalid fixture IDs drifted")
    _require(all((FIXTURE_ROOT / item["path"]).is_file() for item in suite["valid_cases"]), "registered valid fixture missing")
    for key in ("real_accounts", "contains_credentials", "contains_private_content", "contains_media_urls", "contains_local_absolute_paths"):
        _require(suite.get(key) is False, f"fixture public boundary weakened: {key}")
    return Check(
        "contract_fixtures",
        "PASS",
        {
            "declared_invalid": 22,
            "generated_native_fuzz": 106,
            "public_sensitive_inputs": 0,
            "total_cases": 144,
            "valid_round_trip": 16,
        },
    )


def validate_dependencies() -> Check:
    package = _load_json(PROJECT_ROOT / "package.json")
    lock = _load_json(PROJECT_ROOT / "package-lock.json")
    _require(package.get("scripts", {}).get("check:contracts:types") == "npm run check:types --workspace @x2n/contracts", "root TypeScript check script drifted")
    contract_package = _load_json(CONTRACT_ROOT / "package.json")
    _require(contract_package.get("devDependencies") == {"typescript": "7.0.2"}, "TypeScript direct pin drifted")
    registry_npm: dict[str, dict[str, Any]] = {}
    for path, metadata in lock.get("packages", {}).items():
        if path.startswith("node_modules/") and metadata.get("link") is not True:
            name = path.removeprefix("node_modules/")
            if name == "typescript" or name.startswith("@typescript/typescript-"):
                registry_npm[name] = metadata
    _require(len(registry_npm) == 21 and "typescript" in registry_npm, "npm registry dependency set drifted")
    _require(all(name == "typescript" or name.startswith("@typescript/typescript-") for name in registry_npm), "unexpected npm dependency entered lock")
    _require(all(item.get("version") == "7.0.2" and item.get("license") == "Apache-2.0" for item in registry_npm.values()), "TypeScript version/license drifted")
    _require(all("hasInstallScript" not in item for item in registry_npm.values()), "npm install script entered historical Contract dependency set")

    registry_python: dict[str, str] = {}
    for block in (PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8").split("[[package]]")[1:]:
        name = re.search(r'(?m)^name = "([^"]+)"$', block)
        version = re.search(r'(?m)^version = "([^"]+)"$', block)
        source = re.search(r"(?m)^source = (.+)$", block)
        if name and version and source and "registry" in source.group(1):
            registry_python[name.group(1)] = version.group(1)
    _require(registry_python == PYTHON_DEPENDENCIES, "Python registry dependency set/version drifted")
    contract_pyproject = (CONTRACT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    _require(re.findall(r'(?m)^\s*"([^"]+)",?$', contract_pyproject) == ["pydantic==2.13.4"], "Pydantic direct pin drifted")

    sbom = _load_json(SBOM)
    _require(sbom.get("bomFormat") == "CycloneDX" and sbom.get("specVersion") == "1.5", "foundation.002 SBOM format drifted")
    _require(len(sbom.get("components", [])) == 26, "foundation.002 SBOM component count drifted")
    notices = (PROJECT_ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    for token in ("pydantic", "2.13.4", "pydantic-core", "2.46.4", "typing-extensions", "PSF-2.0", "typescript", "7.0.2", "Apache-2.0"):
        _require(token in notices, "dependency NOTICE is incomplete")
    return Check(
        "dependency_supply_chain",
        "PASS",
        {
            "build_registry_packages": len(registry_npm),
            "install_scripts": 0,
            "runtime_registry_packages": len(registry_python),
            "sbom_components": len(sbom["components"]),
        },
    )


def _isolated_env(home: Path, *, pythonpath: bool) -> dict[str, str]:
    env = {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "UV_CACHE_DIR": str(home / "uv-cache"),
        "UV_INDEX_URL": "https://pypi.org/simple",
        "UV_KEYRING_PROVIDER": "disabled",
        "UV_NO_CONFIG": "1",
    }
    if pythonpath:
        env["PYTHONPATH"] = "packages/contracts/src"
    return env


def _run_external(label: str, command: Sequence[str], cwd: Path, env: dict[str, str]) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, check=False, capture_output=True, text=True)
    _require(result.returncode == 0, f"external contract verification failed: {label}")
    combined = result.stdout + result.stderr
    _require("/" + "Users/" not in combined and "github" + "_pat_" not in combined, f"external verification exposed private data: {label}")
    return combined


def validate_external_contracts() -> Check:
    _require(shutil.which("uv") is not None and shutil.which("npm") is not None and shutil.which("node") is not None, "uv, npm and node are required for contract verification")
    with tempfile.TemporaryDirectory(prefix="x2n-f002-verify-") as temporary:
        root = Path(temporary)
        home = root / "home"
        home.mkdir(mode=0o700)
        env = _isolated_env(home, pythonpath=True)
        uv_prefix = ("uv", "run", "--isolated", "--frozen", "--package", "x2n-contracts", "python", "-B")
        _run_external("generator_check", (*uv_prefix, "-m", "x2n_contracts.generate", "--check"), PROJECT_ROOT, env)
        tests = _run_external(
            "python_contract_tests",
            (*uv_prefix, "-m", "unittest", "discover", "-s", "packages/contracts/tests", "-p", "test_*.py"),
            PROJECT_ROOT,
            env,
        )
        match = re.search(r"Ran (\d+) tests", tests)
        _require(match is not None and int(match.group(1)) == 12, "Python contract test count drifted")
        _run_external("sbom_check", (sys.executable, "-B", "scripts/generate_foundation_002_sbom.py", "--check"), PROJECT_ROOT, env)

        fresh = root / "project"
        fresh.mkdir()
        shutil.copy2(PROJECT_ROOT / "package.json", fresh / "package.json")
        shutil.copy2(PROJECT_ROOT / "package-lock.json", fresh / "package-lock.json")
        (fresh / "packages").mkdir()
        (fresh / "apps").mkdir()
        shutil.copytree(PROJECT_ROOT / "packages/contracts", fresh / "packages/contracts")
        shutil.copytree(PROJECT_ROOT / "packages/test-fixtures", fresh / "packages/test-fixtures")
        shutil.copytree(PROJECT_ROOT / "apps/extension", fresh / "apps/extension")
        npm_env = {
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.environ.get("PATH", ""),
            "NPM_CONFIG_AUDIT": "false",
            "NPM_CONFIG_FUND": "false",
            "NPM_CONFIG_IGNORE_SCRIPTS": "true",
            "NPM_CONFIG_REGISTRY": "https://registry.npmjs.org/",
            "NPM_CONFIG_USERCONFIG": str(home / "npmrc"),
        }
        (home / "npmrc").write_text("", encoding="utf-8")
        _run_external("npm_frozen_install", ("npm", "ci", "--ignore-scripts", "--audit=false", "--fund=false"), fresh, npm_env)
        _run_external("typescript_strict_compile", ("npm", "run", "check:contracts:types"), fresh, npm_env)
        _run_external(
            "typescript_hash_helper_emit",
            (
                str(fresh / "node_modules/.bin/tsc"),
                "packages/contracts/types/contracts.ts",
                "--target",
                "ES2022",
                "--module",
                "ESNext",
                "--lib",
                "ES2022,DOM",
                "--outDir",
                "emitted",
                "--strict",
            ),
            fresh,
            npm_env,
        )
        hash_vector = fresh / "verify-hash.mjs"
        hash_vector.write_text(
            """import { readFile } from "node:fs/promises";
import { computePayloadHash } from "./emitted/contracts.js";
const request = JSON.parse(await readFile("./packages/test-fixtures/contracts/v1/valid/native_capture.json", "utf8"));
const actual = await computePayloadHash(request.payload);
if (actual !== request.payload_hash) process.exit(1);
process.stdout.write(JSON.stringify({ status: "PASS", vectors: 1 }));
""",
            encoding="utf-8",
        )
        _run_external("cross_language_payload_hash", ("node", "verify-hash.mjs"), fresh, npm_env)
    return Check(
        "contract_execution",
        "PASS",
        {
            "fixture_cases": 144,
            "generator_drift": 0,
            "network_or_process_product_calls": 0,
            "python_contract_tests": 12,
            "python_typescript_payload_hash_vectors": 1,
            "typescript_strict_compile": True,
        },
    )


def run_checks(*, verify_worktree: bool, allow_external_main_dirty: bool, run_external: bool) -> list[Check]:
    checks = [
        validate_scope(),
        validate_task_and_state(),
        validate_contract_artifacts(),
        validate_error_registry(),
        validate_fixtures(),
        validate_dependencies(),
    ]
    if verify_worktree:
        checks.insert(1, validate_worktree(allow_external_main_dirty))
    if run_external:
        checks.append(validate_external_contracts())
    _require(all(check.status == "PASS" for check in checks), "a foundation.002 check failed")
    return checks


def _safe_evidence(payload: dict[str, Any]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    _require("/" + "Users/" not in rendered, "evidence contains a local absolute path")
    _require(re.search(r"https?://", rendered) is None, "evidence contains a URL")
    _require("github" + "_pat_" not in rendered, "evidence contains credential-shaped material")


def write_evidence(checks: list[Check]) -> None:
    _require(any(check.name == "contract_execution" for check in checks), "evidence requires external contract execution")
    payload = {
        "acceptance_ids": ["ACC.x2n.ext.003", "ACC.x2n.data.001", "ACC.x2n.data.003"],
        "acceptance_status": {
            "ACC.x2n.ext.003": "PASS_CURRENT_CONTRACT_SCOPE_HOST_JOB_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.data.001": "PASS_CURRENT_CONTRACT_SCOPE_SQLITE_DOWNSTREAM_NOT_RUN",
            "ACC.x2n.data.003": "PASS_SYNTHETIC_CONTRACT_SCOPE_REAL_SINKS_DOWNSTREAM_NOT_RUN",
        },
        "checks": [{"details": check.details, "name": check.name, "status": check.status} for check in checks],
        "contract_version": "1.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "phase": "PH.X2N.1.2",
        "private_content_included": False,
        "product_lifecycle": "DOWNSTREAM_NOT_RUN",
        "real_account_execution": "NOT_RUN",
        "remote_upload": "FORBIDDEN_UNTIL_G1_PASS",
        "run_id": RUN_ID,
        "schema_version": "1.0",
        "stage": "STG.X2N.1",
        "stage_gate": "G1_NOT_RUN",
        "status": "PASS",
        "task_id": TASK_ID,
    }
    _safe_evidence(payload)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify_evidence() -> Check:
    evidence = _load_json(EVIDENCE)
    _safe_evidence(evidence)
    _require(evidence.get("task_id") == TASK_ID and evidence.get("run_id") == RUN_ID, "evidence identity drifted")
    _require(evidence.get("status") == "PASS" and evidence.get("stage_gate") == "G1_NOT_RUN", "evidence status overstated")
    _require(evidence.get("product_lifecycle") == "DOWNSTREAM_NOT_RUN", "evidence overstated product lifecycle")
    _require(all(item.get("status") == "PASS" for item in evidence.get("checks", [])), "evidence contains a failed check")
    return Check("evidence", "PASS", {"receipt_sha256": hashlib.sha256(EVIDENCE.read_bytes()).hexdigest(), "task": TASK_ID})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify TSK.x2n.foundation.002")
    parser.add_argument("--verify-worktree", action="store_true")
    parser.add_argument("--allow-external-main-dirty", action="store_true")
    parser.add_argument("--skip-external", action="store_true")
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        checks = run_checks(
            verify_worktree=args.verify_worktree,
            allow_external_main_dirty=args.allow_external_main_dirty,
            run_external=not args.skip_external,
        )
        if args.write_evidence:
            write_evidence(checks)
        if args.require_evidence:
            checks.append(verify_evidence())
        print(json.dumps({"checks": [{"name": item.name, "status": item.status} for item in checks], "status": "PASS", "task": TASK_ID}, ensure_ascii=False, sort_keys=True))
        return 0
    except VerificationError as error:
        print(json.dumps({"reason": str(error), "status": "FAIL_CLOSED", "task": TASK_ID}, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
