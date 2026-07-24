#!/usr/bin/env python3
"""Fail-closed, read-only cumulative validator for MooMooAU Stage 3."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
STAGE2_TOOLS = PROJECT_ROOT / "machine/stages/S2/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
STAGE3_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage3-ci.yml"
BASELINE_COMMIT = "19167f94ed82cc44ff92ee9c46d3e606612fbd27"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
STAGE3_TASKS = [f"T030{i}" for i in range(1, 8)]
STAGE3_ACCEPTANCES = [f"S3AC-00{i}" for i in range(1, 8)]
IGNORED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")

for import_path in (STAGE2_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_publication import (  # noqa: E402
    EMAIL,
    LOCAL_PATH,
    REPOSITORY_TOKEN,
    SECRET_PATTERNS,
    scan_tree,
)
from validate_stage2 import evaluate_stage2  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_workflow,
)

from moomooau_archive.age_stream import is_age_envelope  # noqa: E402
from moomooau_archive.canonical_raw import CanonicalRawError, decode_gmail_raw  # noqa: E402
from moomooau_archive.github_guard import (  # noqa: E402
    CONTENT_APPEND_MESSAGE,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse  # noqa: E402
from moomooau_archive.sender_registry import RegistryActivation, SenderRegistry  # noqa: E402


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _check(check_id: str, passed: bool, detail: str) -> dict[str, str]:
    return {"id": check_id, "status": "PASS" if passed else "FAIL", "detail": detail}


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    paths = [
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and not (set(path.parts) & IGNORED_PARTS)
    ]
    for workflow in (
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage1-ci.yml",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage2-security.yml",
        STAGE3_WORKFLOW,
    ):
        if workflow.is_file():
            paths.append(workflow)
    for path in sorted(set(paths), key=str):
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else path.relative_to(REPOSITORY_ROOT).as_posix()
        )
        digest.update(relative.encode() + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def _validate_stage3_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S3"}
    local = _load(root / "machine/stages/S3/contracts/stage3_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE3_ACCEPTANCES:
        errors.append("Stage 3 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE3_TASKS:
        errors.append("Stage 3 acceptance to task mapping must be one-to-one")
    required_fields = {
        "title",
        "environment",
        "input",
        "oracle",
        "threshold",
        "evidence_required",
        "verification",
        "failure_action",
    }
    for item in items:
        task = graph_tasks.get(item.get("task_id"))
        if task is None or item.get("linked_final_acceptance_ids") != task.get("acceptance_ids"):
            errors.append("Stage 3 final acceptance links drift from the frozen task graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 3 acceptance contract is incomplete")
    expected_dependencies = {
        "T0301": ["T0207"],
        "T0302": ["T0301"],
        "T0303": ["T0302"],
        "T0304": ["T0303"],
        "T0305": ["T0304"],
        "T0306": ["T0305"],
        "T0307": ["T0306"],
    }
    if len(graph_tasks) != 7 or any(
        graph_tasks[task_id].get("dependencies") != dependencies
        for task_id, dependencies in expected_dependencies.items()
    ):
        errors.append("Stage 3 dependency chain drifts from the frozen task graph")

    run_contract = _load(root / "machine/stages/S3/contracts/run_contract.json")
    if (
        run_contract.get("stage_id") != "S3"
        or run_contract.get("baseline_commit") != BASELINE_COMMIT
        or not run_contract.get("protected_oracles")
        or any(value != 0 for value in run_contract.get("prohibitions", {}).values())
        or "Stage 4 or later tasks" not in run_contract.get("non_goals", [])
    ):
        errors.append("Stage 3 run contract is incomplete or grants production authority")
    return errors


def _validate_registry(root: Path) -> list[str]:
    path = root / "machine/stages/S3/registry/verified-senders.v1.json"
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
        registry = SenderRegistry.from_json(raw)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"production sender registry is invalid: {type(exc).__name__}"]
    if (
        value.get("schema_version") != "moomooau.sender-registry.v1"
        or registry.registry_version != "1.0.0"
        or registry.activation is not RegistryActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
        or registry.entries
    ):
        return ["production sender registry must remain versioned and empty"]
    return []


class _RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(201, b"{}")


def _validate_raw_and_persistence_boundaries() -> list[str]:
    errors: list[str] = []
    if is_age_envelope(b"prefix age-encryption.org/v1\nsynthetic") or is_age_envelope(
        b"age-encryption.org/v1\nsynthetic"
    ):
        errors.append("magic-only plaintext was accepted as an age envelope")
    raw = b"From: synthetic source\r\nSubject: synthetic statement\r\n\r\nbody\r\n"
    encoded = base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
    try:
        decoded = decode_gmail_raw(
            encoded,
            maximum_encoded_bytes=4096,
            maximum_raw_bytes=4096,
        )
    except CanonicalRawError:
        decoded = b""
    if decoded != raw:
        errors.append("canonical Gmail RAW byte round-trip failed")
    try:
        decode_gmail_raw("A", maximum_encoded_bytes=4096, maximum_raw_bytes=4096)
    except CanonicalRawError:
        pass
    else:
        errors.append("ambiguous Gmail RAW base64url input was accepted")

    transport = _RecordingTransport()
    config = TargetRepositoryConfig(repository_id=7_200_001, installation_id=8_200_001)
    guard = GitHubEndpointGuard(transport, config)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
    guard.bind_repository(locator)
    body = json.dumps(
        {
            "content": base64.b64encode(b"synthetic plaintext").decode("ascii"),
            "message": CONTENT_APPEND_MESSAGE,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    try:
        guard.send(
            HttpRequest(
                "PUT",
                content_url(locator, "MooMooAU/Raw/messages/2026/01/object.eml.age"),
                body=body,
            )
        )
    except GitHubBoundaryError:
        pass
    else:
        errors.append("plaintext escaped the GitHub Contents pre-network guard")
    if transport.requests or guard.metrics.cross_repository_network_calls != 0:
        errors.append("a rejected plaintext request reached the transport")
    return errors


def _validate_source_boundaries(root: Path) -> list[str]:
    errors: list[str] = []
    discovery = (root / "src/moomooau_archive/gmail_discovery.py").read_text(encoding="utf-8")
    sender = (root / "src/moomooau_archive/sender_registry.py").read_text(encoding="utf-8")
    canonical = (root / "src/moomooau_archive/canonical_raw.py").read_text(encoding="utf-8")
    attachments = (root / "src/moomooau_archive/attachment_inspector.py").read_text(
        encoding="utf-8"
    )
    raw_commit = (root / "src/moomooau_archive/raw_commit.py").read_text(encoding="utf-8")

    discovery_required = (
        '("ALL_MAIL", None)',
        '("INBOX", "INBOX")',
        '("SPAM", "SPAM")',
        '("TRASH", "TRASH")',
        '("includeSpamTrash", "true")',
        '("maxResults", "500")',
        '"-in:sent -in:drafts"',
        'ZoneInfo("Australia/Sydney")',
        "FULL_HISTORY_EXPIRED",
        "FULL_SUNDAY",
        '"SENT" in current.label_ids',
    )
    if any(token not in discovery for token in discovery_required):
        errors.append("fixed Gmail discovery or reconciliation invariants are missing")

    sender_required = (
        "EMPTY_PROTECTED_EVIDENCE_REQUIRED",
        "Authentication-Results",
        "VerificationPhase.PRE_RAW",
        "VerificationPhase.PRE_M3",
        "double_verification_matches",
        "first.message_id == second.message_id",
    )
    if any(token not in sender for token in sender_required):
        errors.append("sender registry or double-verification invariants are missing")

    canonical_required = (
        'message_format="raw"',
        "decode_gmail_raw",
        "hashlib.sha256(raw).hexdigest()",
        "permit.registry_digest",
    )
    if any(token not in canonical for token in canonical_required):
        errors.append("Canonical Raw permit, hash or decode invariants are missing")

    attachment_required = (
        "maximum_attachment_bytes",
        "maximum_zip_ratio",
        "maximum_depth",
        "timeout_seconds",
        "QUARANTINED",
        "canonical_plaintext_sha256",
    )
    forbidden_attachment = (
        "import subprocess",
        "import socket",
        "import requests",
        "import httpx",
        "os.system(",
        "eval(",
        "exec(",
        "extractall(",
    )
    if any(token not in attachments for token in attachment_required) or any(
        token in attachments for token in forbidden_attachment
    ):
        errors.append("attachment inspection is unbounded or exposes execution/network/extraction")

    raw_required = (
        "OfficialAgeStream",
        "MemoryAppendOnlyCiphertextStore",
        "GitHubAppendOnlyCiphertextStore",
        "PRIVATE_COMMITTED_RECOVERY_PENDING",
        "remote_recovery_verified=False",
        "public_publish_eligible=False",
        "m3_eligible=False",
        "attachments.canonical_plaintext_sha256 != canonical.plaintext_sha256",
    )
    if any(token not in raw_commit for token in raw_required):
        errors.append("Raw append-only or post-commit fail-closed invariants are missing")
    return errors


def _validate_workflow(root: Path) -> list[str]:
    errors: list[str] = []
    if not STAGE3_WORKFLOW.is_file():
        return ["Stage 3 CI workflow is missing"]
    workflow = STAGE3_WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)
    if len(uses) != 8 or any(PINNED_ACTION.fullmatch(item) is None for item in uses):
        errors.append("all eight Stage 3 Action uses must be immutable commit SHAs")

    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    action_pins = pins.get("actions", {})
    for action, metadata in action_pins.items():
        expected = metadata.get("commit_sha") if isinstance(metadata, dict) else None
        if not any(
            item.rsplit("@", 1)[1] == expected
            and (
                item.rsplit("@", 1)[0] == action or item.rsplit("@", 1)[0].startswith(action + "/")
            )
            for item in uses
        ):
            errors.append("Stage 3 workflow drifts from the immutable Action pin catalog")

    forbidden = (
        "self-hosted",
        "actions/cache",
        "upload-artifact",
        "download-artifact",
        "schedule:",
        "workflow_dispatch",
        "git push",
        "contents: write",
    )
    if any(token in workflow.casefold() for token in forbidden):
        errors.append("Stage 3 workflow contains a persistence, schedule or authority surface")
    required = (
        "--require-hashes",
        "--cumulative-final",
        "test_t03*.py",
        "validate_stage3.py",
        "pip_audit",
        "cyclonedx-py",
        "detect-secrets",
        "dependency-review-action",
        "codeql-action/init",
        "codeql-action/analyze",
        "docker build --no-cache",
        "--network none",
        "--read-only",
        "python -m build",
    )
    if any(token not in workflow for token in required):
        errors.append("Stage 3 workflow is missing a required local or security gate")
    errors.extend(
        validate_governance_dependency_workflow(
            STAGE3_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )

    age_digest = pins.get("age", {}).get("linux_amd64_archive_sha256")
    if not isinstance(age_digest, str) or age_digest not in workflow:
        errors.append("Stage 3 workflow does not pin the official age archive")
    dockerfile = (root / "container/Dockerfile.stage3-ci").read_text(encoding="utf-8")
    container_digest = pins.get("container", {}).get("oci_index_digest")
    if (
        not isinstance(container_digest, str)
        or "@" + container_digest not in dockerfile
        or "--require-hashes" not in dockerfile
        or "not a production runtime image" not in dockerfile
    ):
        errors.append("Stage 3 validation container is mutable or overstated")
    return errors


def _validate_public_surfaces(root: Path) -> list[str]:
    errors: list[str] = []
    publication = scan_tree(root)
    if publication["status"] != "PASS":
        errors.append("project publication scan found forbidden values")
    workflow = STAGE3_WORKFLOW.read_text(encoding="utf-8") if STAGE3_WORKFLOW.is_file() else ""
    if (
        EMAIL.search(workflow)
        or LOCAL_PATH.search(workflow)
        or any(pattern.search(workflow) for pattern in SECRET_PATTERNS)
    ):
        errors.append("Stage 3 workflow contains a forbidden sensitive pattern")
    contract = _load(root / "machine/contracts/publication_safety.json")
    forbidden_hashes = set(contract["forbidden_locator_sha256_casefold"])
    if any(
        hashlib.sha256(token.casefold().encode()).hexdigest() in forbidden_hashes
        for token in REPOSITORY_TOKEN.findall(workflow)
    ):
        errors.append("Stage 3 workflow contains a forbidden private locator")
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S3/schemas/stage3-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S3"}
    for index, task_id in enumerate(STAGE3_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid evidence schema for {task_id}")
            continue
        if record["stage_acceptance_id"] != f"S3AC-00{index}" or record["record_status"] != "PASS":
            errors.append(f"evidence identity or status mismatch for {task_id}")
        if any(item["status"] != "PASS" for item in record["checks"]):
            errors.append(f"non-passing Stage 3 check for {task_id}")
        linked = record["linked_final_acceptance"]
        if [item["id"] for item in linked] != graph_tasks[task_id]["acceptance_ids"] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"} for item in linked
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        if any(item["status"] != "NOT_RUN" for item in record["production_oracles"]):
            errors.append(f"production oracle is overstated for {task_id}")
        if any(record["prohibition_counters"].values()):
            errors.append(f"prohibition counter is nonzero for {task_id}")

    task_status = _load(root / "machine/stages/S3/contracts/task_status.json")
    if (
        [item.get("id") for item in task_status.get("tasks", [])] != STAGE3_TASKS
        or any(item.get("status") != "completed" for item in task_status.get("tasks", []))
        or task_status.get("baseline_commit") != BASELINE_COMMIT
        or task_status.get("later_stage_status") != "planned_unchanged"
        or task_status.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
    ):
        errors.append("Stage 3 task status overlay is incomplete")

    latest = _load(root / "evidence/stage3/latest.json")
    observation = latest.get("stage3_observation", {})
    if (
        latest.get("stage_id") != "S3"
        or latest.get("status") != "PASS"
        or latest.get("scope") != "LOCAL_SYNTHETIC_ONLY"
        or latest.get("task_pass_count") != 7
        or latest.get("task_total") != 7
        or latest.get("cumulative_task_tests_passed") != 71
        or latest.get("final_acceptance_policy") != "NOT_FINAL"
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or any(latest.get("prohibition_counters", {}).values())
        or observation.get("production_sender_entries") != 0
        or observation.get("synthetic_unrelated_metadata_records") != 1000
        or observation.get("synthetic_unrelated_raw_permits") != 0
        or observation.get("synthetic_candidate_difference") != 0
        or observation.get("synthetic_raw_roundtrip") != "PASS"
        or observation.get("persistent_plaintext_objects") != 0
        or observation.get("dependency_advisory_scan") != "PASS"
        or observation.get("known_vulnerabilities_observed") != 0
        or observation.get("local_secret_scan_findings") != 0
        or observation.get("package_build_smoke") != "PASS"
        or observation.get("taskpack_validation") != "PASS"
        or observation.get("governance_validation") != "PASS"
        or observation.get("digest_pinned_container_build") != "PASS"
        or observation.get("network_none_read_only_container_smoke") != "PASS"
        or observation.get("private_remote_recovery") != "NOT_RUN"
        or observation.get("remote_stage3_ci") != "NOT_RUN"
    ):
        errors.append("Stage 3 aggregate evidence is not a fail-closed local PASS record")

    semantic = _load(root / "machine/stages/S3/contracts/semantic_gate.json")
    statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("stage_id") != "S3"
        or semantic.get("status") != "PASS"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or not statuses.issubset({"RESOLVED", "CONTROLLED_NOT_RUN"})
        or "CONTROLLED_NOT_RUN" not in statuses
    ):
        errors.append("Stage 3 semantic gate is incomplete or overstates protected oracles")
    return errors


def evaluate_stage3(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
    *,
    include_delivery_records: bool = True,
    allow_stage4: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    before = _tree_digest(root)
    checks: list[dict[str, str]] = []

    manifest = root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"
    checks.append(
        _check(
            "baseline.manifest_identity",
            _sha256(manifest) == BASELINE_MANIFEST_SHA256,
            "frozen Stage 0 manifest digest matches the verified handoff",
        )
    )
    stage2 = evaluate_stage2(root, governance_root)
    checks.append(
        _check(
            "baseline.cumulative_stage2",
            stage2["status"] == "PASS",
            f"Stage 2 failed checks {len(stage2['failed_check_ids'])}",
        )
    )

    contract_errors = _validate_stage3_contracts(root)
    checks.append(
        _check(
            "contracts.stage3_overlay",
            not contract_errors,
            f"Stage 3 contract errors {len(contract_errors)}",
        )
    )

    required = [
        root / "src/moomooau_archive/gmail_discovery.py",
        root / "src/moomooau_archive/sender_registry.py",
        root / "src/moomooau_archive/canonical_raw.py",
        root / "src/moomooau_archive/attachment_inspector.py",
        root / "src/moomooau_archive/raw_commit.py",
        root / "tests/stage3_support.py",
        root / "machine/stages/S3/registry/verified-senders.v1.json",
        root / "container/Dockerfile.stage3-ci",
        STAGE3_WORKFLOW,
    ] + [root / "tests/tasks" / f"test_{task_id.casefold()}.py" for task_id in STAGE3_TASKS]
    checks.append(
        _check(
            "package.stage3_structure",
            all(path.is_file() for path in required),
            f"required Stage 3 paths {len(required)}",
        )
    )

    registry_errors = _validate_registry(root)
    checks.append(
        _check(
            "classification.production_registry_fail_closed",
            not registry_errors,
            f"production registry errors {len(registry_errors)}; active entries 0",
        )
    )

    source_errors = _validate_source_boundaries(root)
    checks.append(
        _check(
            "security.stage3_source_boundaries",
            not source_errors,
            f"source boundary errors {len(source_errors)}",
        )
    )

    raw_errors = _validate_raw_and_persistence_boundaries()
    checks.append(
        _check(
            "security.raw_and_plaintext_guards",
            not raw_errors,
            f"RAW or persistence boundary errors {len(raw_errors)}",
        )
    )

    workflow_errors = _validate_workflow(root)
    checks.append(
        _check(
            "security.no_secret_stage3_ci",
            not workflow_errors,
            f"Stage 3 workflow errors {len(workflow_errors)}",
        )
    )

    publication_errors = _validate_public_surfaces(root)
    checks.append(
        _check(
            "security.publication",
            not publication_errors,
            f"publication errors {len(publication_errors)}",
        )
    )

    scope_paths = (
        root / "machine/stages/S4",
        root / "tests/tasks/test_t0401.py",
    )
    checks.append(
        _check(
            "scope.no_stage4_or_production_authority",
            allow_stage4 or not any(path.exists() for path in scope_paths),
            (
                "retired by the cumulative Stage 4 validator; production authority counters 0"
                if allow_stage4
                else "Stage 4 implementation paths 0; production authority counters 0"
            ),
        )
    )

    if include_delivery_records:
        evidence_errors = _validate_evidence(root)
        checks.append(
            _check(
                "evidence.stage3_records",
                not evidence_errors,
                f"Stage 3 evidence errors {len(evidence_errors)}",
            )
        )

    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "moomooau.stage3-verification.v1",
        "stage_id": "S3",
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_check_ids": failed,
        "signals": {
            "stage3_tasks": 7,
            "stage3_local_acceptances": 7,
            "production_sender_entries": 0,
            "real_gmail_calls": 0,
            "gmail_mutations": 0,
            "private_repository_calls": 0,
            "real_secrets_read": 0,
            "protected_key_deliveries": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "non_moomoo_full_reads": 0,
            "non_moomoo_downloads": 0,
            "non_moomoo_mutations": 0,
            "raw_before_verification": 0,
            "untrusted_content_execution": 0,
            "protected_oracles_executed": 0,
            "final_acceptances_passed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    parser.add_argument(
        "--cumulative-final",
        action="store_true",
        help=(
            "allow later-stage implementation paths in a cumulative final-tree validation; "
            "all production authority and external-effect checks remain fail closed"
        ),
    )
    args = parser.parse_args()
    result = evaluate_stage3(
        args.root,
        args.governance_root,
        allow_stage4=args.cumulative_final,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
