#!/usr/bin/env python3
"""Generate and validate the fixed-source evidence for TaskPack task CB-000."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


SOURCE_IDENTITIES: dict[str, dict[str, Any]] = {
    "cyberboss": {
        "historical_source": "WenXiaoWendy/cyberboss",
        "commit": "373ab17d283f1e3b304a6a36e17e9e8d44f1acfc",
        "git_tree": "d175d890153fc753895a0ebcf11b5eb65d83a5ad",
        "commit_date": "2026-06-05T07:09:36+08:00",
        "package_name": "cyberboss",
        "package_version": "0.1.0",
        "node_engine": ">=22",
        "lockfile": "package-lock.json",
        "upstream_lockfile_sha256": (
            "a33cf82a6e117bf5284f0c805494d22ed9dcbc87d73e108b325c84c3b4395c00"
        ),
        "bundle_path": "app",
        "license_declared": "AGPL-3.0-only",
        "license_file_concluded": "AGPL-3.0-only",
        "compliance_expression": "AGPL-3.0-only",
        "license_sha256": (
            "526520455b0c01e09c1a23f6322a11d9e867de44dc833de8a94af6766dced64b"
        ),
    },
    "timeline-for-agent": {
        "historical_source": "WenXiaoWendy/timeline-for-agent",
        "commit": "62e1fa8db26f7a9147ad96579fc4077a39b94c8b",
        "git_tree": "cd1fbe0e5fac50ca3b446afc04d3656f871c9b4b",
        "commit_date": "2026-06-05T07:08:07+08:00",
        "package_name": "timeline-for-agent",
        "package_version": "0.1.0",
        "node_engine": ">=22",
        "lockfile": "package-lock.json",
        "upstream_lockfile_sha256": (
            "13b247c63c0a985ea32412d6c9b3d0051336e558b120ec6184574c5c589fb13a"
        ),
        "bundle_path": "vendor/timeline-for-agent",
        "license_declared": "AGPL-3.0-only",
        "license_file_concluded": "AGPL-3.0-only",
        "compliance_expression": "AGPL-3.0-only",
        "license_sha256": (
            "526520455b0c01e09c1a23f6322a11d9e867de44dc833de8a94af6766dced64b"
        ),
    },
    "whereabouts-mcp": {
        "historical_source": "WenXiaoWendy/whereabouts-mcp",
        "commit": "e36cb307f082f747327fd3a5d406fd9718a1428d",
        "git_tree": "cc22811b03ab4d411379421894e3408eb1964c14",
        "commit_date": "2026-04-22T22:52:00+08:00",
        "package_name": "whereabouts-mcp",
        "package_version": "0.1.0",
        "node_engine": ">=22",
        "lockfile": None,
        "upstream_lockfile_sha256": None,
        "bundle_path": "vendor/whereabouts-mcp",
        "license_declared": "AGPL-3.0-only",
        "license_file_concluded": "GPL-3.0-only",
        "compliance_expression": "GPL-3.0-only AND AGPL-3.0-only",
        "license_sha256": (
            "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
        ),
    },
}

EXPECTED_APP_MODIFICATIONS = {
    ".npmrc",
    ".gitignore",
    "package-lock.json",
    "package.json",
    "src/adapters/runtime/codex/rpc-client.js",
    "test/codex-rpc-client.test.js",
    "test/sticker-service.test.js",
}

REQUIRED_CLIENT_REQUESTS = {
    "initialize",
    "thread/start",
    "thread/resume",
    "thread/compact/start",
    "thread/list",
    "turn/start",
    "turn/interrupt",
    "model/list",
}
REQUIRED_CLIENT_NOTIFICATIONS = {"initialized"}
REQUIRED_SERVER_REQUESTS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
    "mcpServer/elicitation/request",
}

MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  \./(.+)$")
FORBIDDEN_DEPENDENCY = re.compile(
    r"(?:git\+|git@github|github:[^\"'\s]+|#[Mm][Aa][Ii][Nn]\b|#[Mm][Aa][Ss][Tt][Ee][Rr]\b)"
)
RUNTIME_SOURCE_FETCH = re.compile(
    r"(?:\bgit\s+(?:clone|fetch|pull)\b|\bcurl\b[^\n]*(?:github\.com|raw\.githubusercontent\.com)|"
    r"\bwget\b[^\n]*(?:github\.com|raw\.githubusercontent\.com))",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def git_ignored_paths(repo: Path, paths: list[Path]) -> list[str]:
    relative_paths = [path.relative_to(repo).as_posix() for path in paths]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        cwd=repo,
        input="\n".join(relative_paths) + "\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError(f"git_check_ignore_failed:{result.stderr.strip()}")
    return sorted(line for line in result.stdout.splitlines() if line)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def included_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in {".git", "node_modules"} for part in relative.parts):
            continue
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def manifest_entries(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in included_files(root)
    }


def write_manifest(path: Path, root: Path) -> dict[str, str]:
    entries = manifest_entries(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(f"{digest}  ./{relative}\n" for relative, digest in entries.items()),
        encoding="utf-8",
    )
    return entries


def read_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = MANIFEST_LINE.fullmatch(raw)
        if not match:
            raise ValueError(f"manifest_invalid_line:{path}:{number}")
        digest, relative = match.groups()
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts or relative in entries:
            raise ValueError(f"manifest_unsafe_or_duplicate:{path}:{number}")
        entries[relative] = digest
    return entries


def compare_manifests(
    upstream: dict[str, str], bundle: dict[str, str]
) -> dict[str, list[str]]:
    upstream_paths = set(upstream)
    bundle_paths = set(bundle)
    return {
        "added": sorted(bundle_paths - upstream_paths),
        "modified": sorted(
            path
            for path in upstream_paths & bundle_paths
            if upstream[path] != bundle[path]
        ),
        "removed": sorted(upstream_paths - bundle_paths),
    }


def package_name_from_lock_path(lock_path: str, value: dict[str, Any]) -> str:
    if not lock_path:
        return str(value.get("name") or "cyberboss")
    return lock_path.rsplit("node_modules/", 1)[-1]


def build_dependency_inventory(project: Path) -> dict[str, Any]:
    lock = load_json(project / "app/package-lock.json")
    packages: list[dict[str, Any]] = []
    for lock_path, raw_value in sorted((lock.get("packages") or {}).items()):
        value = raw_value if isinstance(raw_value, dict) else {}
        name = package_name_from_lock_path(lock_path, value)
        declared = value.get("license")
        concluded = declared
        license_evidence = "package-lock.json:license"
        conflict = False
        upstream_clarification = None

        if name == "qrcode-terminal":
            declared = "Apache-2.0 (legacy package.json licenses field)"
            concluded = "Apache-2.0 AND MIT"
            license_evidence = (
                "docs/evidence/CB-000/licenses/qrcode-terminal-0.12.0-LICENSE"
            )
        elif name == "whereabouts-mcp":
            declared = "AGPL-3.0-only"
            concluded = "GPL-3.0-only AND AGPL-3.0-only"
            license_evidence = "vendor/whereabouts-mcp/LICENSE + package.json"
            conflict = True
            upstream_clarification = False

        packages.append(
            {
                "lock_path": lock_path or ".",
                "name": name,
                "version": value.get("version") or lock.get("version"),
                "resolved": value.get("resolved") or "project-root",
                "integrity": value.get("integrity"),
                "license_declared": declared,
                "license_concluded": concluded,
                "license_evidence": license_evidence,
                "license_conflict_recorded": conflict,
                "upstream_clarification_received": upstream_clarification,
            }
        )

    unresolved = [
        item["name"]
        for item in packages
        if not item.get("license_concluded")
        or "UNKNOWN" in str(item.get("license_concluded")).upper()
    ]
    return {
        "schema_version": 1,
        "lockfile": "app/package-lock.json",
        "lockfile_version": lock.get("lockfileVersion"),
        "package_count_including_root": len(packages),
        "unresolved_licenses": unresolved,
        "whereabouts_compliance_policy": {
            "owner_decision": "strict_dual_obligation",
            "license_declared": "AGPL-3.0-only",
            "license_file_concluded": "GPL-3.0-only",
            "compliance_expression": "GPL-3.0-only AND AGPL-3.0-only",
            "preserve_both_license_indicators": True,
            "upstream_clarification_received": False,
            "must_not_claim_upstream_clarification": True,
        },
        "packages": packages,
    }


def collect_methods(value: Any) -> set[str]:
    methods: set[str] = set()
    if isinstance(value, dict):
        properties = value.get("properties")
        if isinstance(properties, dict):
            method = properties.get("method")
            if isinstance(method, dict):
                constant = method.get("const")
                if isinstance(constant, str):
                    methods.add(constant)
                enum = method.get("enum")
                if isinstance(enum, list):
                    methods.update(item for item in enum if isinstance(item, str))
        for child in value.values():
            methods.update(collect_methods(child))
    elif isinstance(value, list):
        for child in value:
            methods.update(collect_methods(child))
    return methods


def build_codex_protocol_evidence(schema_root: Path) -> dict[str, Any]:
    files = {
        "client_requests": schema_root / "ClientRequest.json",
        "client_notifications": schema_root / "ClientNotification.json",
        "server_requests": schema_root / "ServerRequest.json",
        "combined": schema_root / "codex_app_server_protocol.schemas.json",
    }
    for path in files.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    method_sets = {
        key: collect_methods(load_json(path))
        for key, path in files.items()
        if key != "combined"
    }
    missing = {
        "client_requests": sorted(
            REQUIRED_CLIENT_REQUESTS - method_sets["client_requests"]
        ),
        "client_notifications": sorted(
            REQUIRED_CLIENT_NOTIFICATIONS - method_sets["client_notifications"]
        ),
        "server_requests": sorted(
            REQUIRED_SERVER_REQUESTS - method_sets["server_requests"]
        ),
    }
    version_output = subprocess.run(
        ["codex", "--version"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
    version = version_output.removeprefix("codex-cli ").strip()
    return {
        "schema_version": 1,
        "codex_cli_output": version_output,
        "exact_tested_version": version,
        "minimum_verified_version": version,
        "older_versions_accepted": False,
        "schema_generation_command": (
            "codex app-server generate-json-schema --experimental --out <temp-dir>"
        ),
        "schema_file_count": len(list(schema_root.rglob("*.json"))),
        "schema_hashes": {
            key: sha256(path) for key, path in sorted(files.items())
        },
        "required_methods": {
            "client_requests": sorted(REQUIRED_CLIENT_REQUESTS),
            "client_notifications": sorted(REQUIRED_CLIENT_NOTIFICATIONS),
            "server_requests": sorted(REQUIRED_SERVER_REQUESTS),
        },
        "missing_methods": missing,
        "compatible": not any(missing.values()),
        "verification_scope": (
            "Generated experimental App Server schemas plus local adapter unit tests; "
            "no live authenticated turn was executed in CB-000."
        ),
    }


def build_source_lock(
    project: Path,
    upstream_manifests: dict[str, dict[str, str]],
    bundle_manifests: dict[str, dict[str, str]],
    diffs: dict[str, dict[str, list[str]]],
    codex_evidence: dict[str, Any],
) -> dict[str, Any]:
    sources = []
    for source_id, identity in SOURCE_IDENTITIES.items():
        upstream_manifest_path = (
            project
            / f"docs/evidence/CB-000/manifests/upstream-{source_id}.sha256"
        )
        bundle_manifest_path = (
            project / f"docs/evidence/CB-000/manifests/bundle-{source_id}.sha256"
        )
        sources.append(
            {
                "id": source_id,
                **identity,
                "tag": None,
                "upstream_manifest": upstream_manifest_path.relative_to(
                    project
                ).as_posix(),
                "upstream_manifest_sha256": sha256(upstream_manifest_path),
                "upstream_file_count": len(upstream_manifests[source_id]),
                "bundle_manifest": bundle_manifest_path.relative_to(
                    project
                ).as_posix(),
                "bundle_manifest_sha256": sha256(bundle_manifest_path),
                "bundle_file_count": len(bundle_manifests[source_id]),
                "bundle_changes_from_locked_source": diffs[source_id],
                "current_lockfile_path": (
                    f"{identity['bundle_path']}/{identity['lockfile']}"
                    if identity["lockfile"]
                    else None
                ),
                "current_lockfile_sha256": (
                    bundle_manifests[source_id].get(identity["lockfile"])
                    if identity["lockfile"]
                    else None
                ),
                "lockfile_changed_from_locked_source": (
                    bundle_manifests[source_id].get(identity["lockfile"])
                    != identity["upstream_lockfile_sha256"]
                    if identity["lockfile"]
                    else False
                ),
                "license_file": f"{identity['bundle_path']}/LICENSE",
                "fetched_by_exact_sha_once": True,
                "temporary_fetch_repository_remote_count": 0,
                "copyright_record": (
                    "No standalone author/copyright metadata was present at the locked "
                    "commit; historical repository identity and all source/license files "
                    "are preserved without inventing an author."
                ),
            }
        )

    return {
        "schema_version": 1,
        "generated_on": "2026-07-26",
        "task_id": "CB-000",
        "repository": "LinzeColin/MetaDatabase",
        "project_subpath": "CyberBoss/",
        "bundle_hash_definition": (
            "SHA-256 of the deterministic, relative-path, per-file SHA-256 manifest"
        ),
        "upstream_relationship": {
            "remote_allowed": False,
            "submodule_allowed": False,
            "git_url_dependency_allowed": False,
            "automatic_sync_allowed": False,
            "runtime_source_fetch_allowed": False,
            "periodic_rebase_allowed": False,
        },
        "sources": sources,
        "codex_cli": {
            "minimum_verified_version": codex_evidence["minimum_verified_version"],
            "exact_tested_version": codex_evidence["exact_tested_version"],
            "older_versions_accepted": False,
            "protocol_evidence": (
                "docs/evidence/CB-000/codex-protocol-methods.json"
            ),
        },
        "whereabouts_license_conflict": {
            "license_declared": "AGPL-3.0-only",
            "license_file_concluded": "GPL-3.0-only",
            "compliance_expression": "GPL-3.0-only AND AGPL-3.0-only",
            "owner_decision": "strict_dual_obligation",
            "preserve_original_license_and_source": True,
            "upstream_clarification_received": False,
            "must_not_claim_upstream_clarification": True,
        },
    }


def write_evidence(project: Path, audit_root: Path, schema_root: Path) -> None:
    evidence = project / "docs/evidence/CB-000"
    manifest_root = evidence / "manifests"
    upstream_manifests: dict[str, dict[str, str]] = {}
    bundle_manifests: dict[str, dict[str, str]] = {}
    diffs: dict[str, dict[str, list[str]]] = {}

    for source_id, identity in SOURCE_IDENTITIES.items():
        upstream_root = audit_root / "trees" / source_id
        bundle_root = project / identity["bundle_path"]
        if not upstream_root.is_dir() or not bundle_root.is_dir():
            raise FileNotFoundError(f"source_root_missing:{source_id}")
        upstream = write_manifest(
            manifest_root / f"upstream-{source_id}.sha256", upstream_root
        )
        bundle = write_manifest(
            manifest_root / f"bundle-{source_id}.sha256", bundle_root
        )
        upstream_manifests[source_id] = upstream
        bundle_manifests[source_id] = bundle
        diffs[source_id] = compare_manifests(upstream, bundle)

    write_json(
        evidence / "source-bundle-diff.json",
        {"schema_version": 1, "sources": diffs},
    )
    write_json(
        evidence / "dependency-license-inventory.json",
        build_dependency_inventory(project),
    )
    codex_evidence = build_codex_protocol_evidence(schema_root)
    write_json(evidence / "codex-protocol-methods.json", codex_evidence)
    write_json(
        project / "machine/source-lock.json",
        build_source_lock(
            project,
            upstream_manifests,
            bundle_manifests,
            diffs,
            codex_evidence,
        ),
    )


def validate(project: Path) -> list[str]:
    errors: list[str] = []
    repo = project.parent
    evidence = project / "docs/evidence/CB-000"
    required = [
        project / "app/package.json",
        project / "app/package-lock.json",
        project / "vendor/timeline-for-agent/package.json",
        project / "vendor/whereabouts-mcp/package.json",
        project / "machine/source-lock.json",
        project / "machine/facts/owner_decisions.json",
        evidence / "baseline-source.md",
        evidence / "REUSE_CHANGE_MAP.md",
        evidence / "CODEX_PROTOCOL_COMPATIBILITY.md",
        evidence / "LICENSE_COMPLIANCE.md",
        evidence / "VALIDATION_REPORT.md",
        evidence / "dependency-license-inventory.json",
        evidence / "source-bundle-diff.json",
        evidence / "codex-protocol-methods.json",
        evidence / "licenses/qrcode-terminal-0.12.0-LICENSE",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"required_file_missing:{path.relative_to(project)}")
    if errors:
        return errors

    source_lock = load_json(project / "machine/source-lock.json")
    locked_sources = {
        item.get("id"): item for item in source_lock.get("sources") or []
    }
    if set(locked_sources) != set(SOURCE_IDENTITIES):
        errors.append("source_lock_identity_set")

    for source_id, identity in SOURCE_IDENTITIES.items():
        item = locked_sources.get(source_id) or {}
        for field in (
            "historical_source",
            "commit",
            "git_tree",
            "commit_date",
            "package_name",
            "package_version",
            "node_engine",
            "lockfile",
            "upstream_lockfile_sha256",
            "bundle_path",
            "license_declared",
            "license_file_concluded",
            "compliance_expression",
            "license_sha256",
        ):
            if item.get(field) != identity[field]:
                errors.append(f"source_lock_mismatch:{source_id}:{field}")

        bundle_root = project / identity["bundle_path"]
        if not bundle_root.is_dir():
            errors.append(f"bundle_missing:{source_id}")
            continue
        source_paths = [
            path
            for path in bundle_root.rglob("*")
            if "node_modules" not in path.relative_to(bundle_root).parts
        ]
        if any(path.name in {".git", ".gitmodules"} for path in source_paths):
            errors.append(f"git_metadata_present:{source_id}")
        if any(path.is_symlink() for path in source_paths):
            errors.append(f"bundle_symlink_present:{source_id}")
        try:
            ignored = git_ignored_paths(repo, included_files(bundle_root))
        except RuntimeError as error:
            errors.append(str(error))
        else:
            for path in ignored:
                errors.append(f"bundle_source_ignored:{source_id}:{path}")
        package = load_json(bundle_root / "package.json")
        if package.get("name") != identity["package_name"]:
            errors.append(f"package_name:{source_id}")
        if package.get("version") != identity["package_version"]:
            errors.append(f"package_version:{source_id}")
        if (package.get("engines") or {}).get("node") != identity["node_engine"]:
            errors.append(f"node_engine:{source_id}")
        if sha256(bundle_root / "LICENSE") != identity["license_sha256"]:
            errors.append(f"license_hash:{source_id}")
        expected_current_lockfile_sha256 = (
            sha256(bundle_root / identity["lockfile"])
            if identity["lockfile"]
            else None
        )
        if item.get("current_lockfile_sha256") != expected_current_lockfile_sha256:
            errors.append(f"current_lockfile_hash:{source_id}")
        expected_current_lockfile_path = (
            f"{identity['bundle_path']}/{identity['lockfile']}"
            if identity["lockfile"]
            else None
        )
        if item.get("current_lockfile_path") != expected_current_lockfile_path:
            errors.append(f"current_lockfile_path:{source_id}")
        expected_lockfile_changed = (
            expected_current_lockfile_sha256
            != identity["upstream_lockfile_sha256"]
            if identity["lockfile"]
            else False
        )
        if item.get("lockfile_changed_from_locked_source") != expected_lockfile_changed:
            errors.append(f"lockfile_change_record:{source_id}")

        upstream_manifest = project / str(item.get("upstream_manifest") or "")
        bundle_manifest = project / str(item.get("bundle_manifest") or "")
        try:
            upstream_entries = read_manifest(upstream_manifest)
            bundle_entries = read_manifest(bundle_manifest)
        except (OSError, ValueError) as error:
            errors.append(str(error))
            continue
        actual_entries = manifest_entries(bundle_root)
        if bundle_entries != actual_entries:
            errors.append(f"bundle_manifest_content:{source_id}")
        if sha256(upstream_manifest) != item.get("upstream_manifest_sha256"):
            errors.append(f"upstream_manifest_hash:{source_id}")
        if sha256(bundle_manifest) != item.get("bundle_manifest_sha256"):
            errors.append(f"bundle_manifest_hash:{source_id}")
        actual_diff = compare_manifests(upstream_entries, bundle_entries)
        if actual_diff != item.get("bundle_changes_from_locked_source"):
            errors.append(f"bundle_diff_record:{source_id}")
        changed = set(actual_diff["added"] + actual_diff["modified"] + actual_diff["removed"])
        expected_changed = EXPECTED_APP_MODIFICATIONS if source_id == "cyberboss" else set()
        if changed != expected_changed:
            errors.append(f"unexpected_bundle_changes:{source_id}:{sorted(changed)}")

    package = load_json(project / "app/package.json")
    dependencies = package.get("dependencies") or {}
    if dependencies.get("timeline-for-agent") != "file:../vendor/timeline-for-agent":
        errors.append("timeline_dependency_not_local")
    if dependencies.get("whereabouts-mcp") != "file:../vendor/whereabouts-mcp":
        errors.append("whereabouts_dependency_not_local")
    if package.get("scripts", {}).get("test") != "node --test":
        errors.append("app_test_script")

    for relative in ("app/package.json", "app/package-lock.json"):
        text = (project / relative).read_text(encoding="utf-8")
        if FORBIDDEN_DEPENDENCY.search(text):
            errors.append(f"moving_dependency:{relative}")

    for root_name in ("app/src", "app/scripts", "vendor"):
        root = project / root_name
        for path in root.rglob("*"):
            if path.is_file() and path.suffix in {".js", ".mjs", ".cjs", ".sh"}:
                text = path.read_text(encoding="utf-8", errors="replace")
                if RUNTIME_SOURCE_FETCH.search(text):
                    errors.append(f"runtime_source_fetch:{path.relative_to(project)}")

    inventory = load_json(evidence / "dependency-license-inventory.json")
    lock = load_json(project / "app/package-lock.json")
    if inventory.get("package_count_including_root") != len(lock.get("packages") or {}):
        errors.append("dependency_inventory_count")
    if inventory.get("unresolved_licenses"):
        errors.append("dependency_license_unresolved")
    inventory_names = {
        (item.get("lock_path"), item.get("name"), item.get("version"))
        for item in inventory.get("packages") or []
    }
    lock_names = {
        (
            lock_path or ".",
            package_name_from_lock_path(lock_path, value),
            value.get("version") or lock.get("version"),
        )
        for lock_path, value in (lock.get("packages") or {}).items()
    }
    if inventory_names != lock_names:
        errors.append("dependency_inventory_lock_mismatch")

    conflict = source_lock.get("whereabouts_license_conflict") or {}
    expected_conflict = {
        "license_declared": "AGPL-3.0-only",
        "license_file_concluded": "GPL-3.0-only",
        "compliance_expression": "GPL-3.0-only AND AGPL-3.0-only",
        "owner_decision": "strict_dual_obligation",
        "preserve_original_license_and_source": True,
        "upstream_clarification_received": False,
        "must_not_claim_upstream_clarification": True,
    }
    if conflict != expected_conflict:
        errors.append("whereabouts_license_policy")

    owner = load_json(project / "machine/facts/owner_decisions.json")
    owner_conflict = (
        (owner.get("license") or {})
        .get("required_dependency_conflicts", {})
        .get("whereabouts-mcp")
    )
    expected_owner_conflict = {
        "locked_commit": "e36cb307f082f747327fd3a5d406fd9718a1428d",
        "package_declared": "AGPL-3.0-only",
        "license_file_concluded": "GPL-3.0-only",
        "compliance_expression": "GPL-3.0-only AND AGPL-3.0-only",
        "preserve_original_license_and_source": True,
        "preserve_conflict_record": True,
        "upstream_clarification_received": False,
        "must_not_claim_upstream_clarification": True,
    }
    if owner_conflict != expected_owner_conflict:
        errors.append("owner_whereabouts_license_policy")

    protocol = load_json(evidence / "codex-protocol-methods.json")
    if protocol.get("exact_tested_version") != "0.146.0-alpha.3.1":
        errors.append("codex_exact_tested_version")
    if protocol.get("minimum_verified_version") != "0.146.0-alpha.3.1":
        errors.append("codex_minimum_verified_version")
    if protocol.get("older_versions_accepted") is not False:
        errors.append("codex_older_version_policy")
    if protocol.get("compatible") is not True:
        errors.append("codex_protocol_compatibility")
    if any((protocol.get("missing_methods") or {}).values()):
        errors.append("codex_protocol_missing_methods")

    state = load_json(project / "machine/facts/task_state.json")
    if state.get("current_run") != {
        "run_id": "P0.1",
        "task_id": "CB-000",
        "scope": "fixed_source_dependency_license_and_codex_baseline",
        "status": "passed",
    }:
        errors.append("task_state_current_run")
    state_tasks = {item.get("id"): item.get("status") for item in state.get("tasks") or []}
    if state_tasks.get("CB-000") != "passed":
        errors.append("task_state_cb000")
    downstream = {key: value for key, value in state_tasks.items() if key != "CB-000"}
    if not downstream or any(value != "not_started" for value in downstream.values()):
        errors.append("downstream_task_started")
    if any(value != "not_started" for value in (state.get("pass_gates") or {}).values()):
        errors.append("pass_gate_advanced")

    readme = (project / "README.md").read_text(encoding="utf-8")
    handoff = (project / "HANDOFF.md").read_text(encoding="utf-8")
    notices = (project / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    provenance = (project / "UPSTREAM_PROVENANCE.md").read_text(encoding="utf-8")
    for marker, text in (
        ("P0.1 / CB-000", readme),
        ("P0.1 / CB-000", handoff),
        ("GPL-3.0-only AND AGPL-3.0-only", notices),
        ("no upstream clarification", notices.lower()),
        ("frozen source", provenance.lower()),
    ):
        if marker not in text:
            errors.append(f"documentation_marker:{marker}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--audit-root", type=Path)
    parser.add_argument("--codex-schema", type=Path)
    args = parser.parse_args()

    project = Path(__file__).resolve().parents[1]
    if args.write_evidence:
        if args.audit_root is None or args.codex_schema is None:
            parser.error("--write-evidence requires --audit-root and --codex-schema")
        write_evidence(project, args.audit_root.resolve(), args.codex_schema.resolve())
        print("CB000_EVIDENCE_WRITE=PASS")
        return 0

    errors = validate(project)
    for error in sorted(set(errors)):
        print(f"ERROR={error}")
    if errors:
        print("CB000_VALIDATION=FAIL")
        return 1
    print("CB000_VALIDATION=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
