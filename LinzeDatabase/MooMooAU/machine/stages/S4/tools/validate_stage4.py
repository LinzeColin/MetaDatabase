#!/usr/bin/env python3
"""Fail-closed, read-only cumulative validator for MooMooAU Stage 4."""

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
STAGE3_TOOLS = PROJECT_ROOT / "machine/stages/S3/tools"
TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
STAGE4_WORKFLOW = REPOSITORY_ROOT / ".github/workflows/moomooau-stage4-ci.yml"
BASELINE_COMMIT = "b15ccdbe0e4ed16e3a01e17431360f844621b852"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
STAGE4_LOCK_SHA256 = "c65f0de4923708e274befde827b2f7f32aae513e158830ababdb7304107de2f5"
STAGE4_SBOM_SHA256 = "c10d9b5193195c2d0e90b9f072a38bbbb112da680a4d897da3dbff07efee3d2e"
STAGE4_TASKS = [f"T040{i}" for i in range(1, 8)]
STAGE4_ACCEPTANCES = [f"S4AC-00{i}" for i in range(1, 8)]
IGNORED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}
PINNED_ACTION = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?@[0-9a-f]{40}$")

for import_path in (STAGE3_TOOLS, TOOLS, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from validate_publication import (  # noqa: E402
    EMAIL,
    LOCAL_PATH,
    REPOSITORY_TOKEN,
    SECRET_PATTERNS,
    scan_tree,
)
from validate_stage3 import evaluate_stage3  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_workflow,
)

from moomooau_archive.document_parser import ParserActivation, ParserProfileRegistry  # noqa: E402
from moomooau_archive.github_guard import (  # noqa: E402
    CONTENT_APPEND_MESSAGE,
    CONTENT_POINTER_MESSAGE,
    GitHubBoundaryError,
    GitHubEndpointGuard,
    RepositoryLocator,
    TargetRepositoryConfig,
    content_url,
)
from moomooau_archive.http_boundary import HttpRequest, HttpResponse  # noqa: E402
from moomooau_archive.processed_models import (  # noqa: E402
    ClassificationActivation,
    ClassificationRegistry,
    DocumentClass,
)


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
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage3-ci.yml",
        STAGE4_WORKFLOW,
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


def _validate_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S4"}
    local = _load(root / "machine/stages/S4/contracts/stage4_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE4_ACCEPTANCES:
        errors.append("Stage 4 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE4_TASKS:
        errors.append("Stage 4 acceptance to task mapping must be one-to-one")
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
            errors.append("Stage 4 final acceptance links drift from the frozen task graph")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 4 acceptance contract is incomplete")
    expected_dependencies = {
        "T0401": ["T0307"],
        "T0402": ["T0401"],
        "T0403": ["T0402"],
        "T0404": ["T0403"],
        "T0405": ["T0404"],
        "T0406": ["T0405"],
        "T0407": ["T0406"],
    }
    if len(graph_tasks) != 7 or any(
        graph_tasks[task_id].get("dependencies") != dependencies
        for task_id, dependencies in expected_dependencies.items()
    ):
        errors.append("Stage 4 dependency chain drifts from the frozen task graph")

    run_contract = _load(root / "machine/stages/S4/contracts/run_contract.json")
    prohibitions = run_contract.get("prohibitions", {})
    if (
        run_contract.get("stage_id") != "S4"
        or run_contract.get("baseline_commit") != BASELINE_COMMIT
        or run_contract.get("baseline_manifest_sha256") != BASELINE_MANIFEST_SHA256
        or not run_contract.get("protected_oracles")
        or not isinstance(prohibitions, dict)
        or any(value != 0 for value in prohibitions.values())
        or "Stage 5 or later tasks" not in run_contract.get("non_goals", [])
        or "Moomoo Portal access, download, scraping or automation"
        not in run_contract.get("non_goals", [])
    ):
        errors.append("Stage 4 run contract is incomplete or grants production authority")
    return errors


def _validate_registries_and_schemas(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    class_path = root / "machine/stages/S4/registry/document-classification.v1.json"
    parser_path = root / "machine/stages/S4/registry/parser-profiles.v1.json"
    try:
        class_registry = ClassificationRegistry.from_json(class_path.read_bytes())
        parser_registry = ParserProfileRegistry.from_json(parser_path.read_bytes())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"production Stage 4 registry is invalid: {type(exc).__name__}"]
    if (
        class_registry.activation is not ClassificationActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
        or class_registry.rules
        or parser_registry.activation is not ParserActivation.EMPTY_PROTECTED_EVIDENCE_REQUIRED
        or parser_registry.profiles
    ):
        errors.append("production classification and parser registries must remain empty")

    schemas = sorted((root / "machine/stages/S4/public-schemas").glob("*.schema.json"))
    if len(schemas) < 3:
        errors.append("Stage 4 public schema set is incomplete")
        return errors
    for schema_path in schemas:
        try:
            Draft202012Validator.check_schema(_load(schema_path))
        except Exception as exc:
            errors.append(f"invalid public schema {schema_path.name}: {type(exc).__name__}")
    pairs = (
        ("classification-registry-v1.schema.json", class_path),
        ("parser-profile-registry-v1.schema.json", parser_path),
    )
    for schema_name, value_path in pairs:
        try:
            validator = Draft202012Validator(
                _load(root / "machine/stages/S4/public-schemas" / schema_name),
                format_checker=FormatChecker(),
            )
            if list(validator.iter_errors(_load(value_path))):
                errors.append(f"committed registry does not match {schema_name}")
        except Exception as exc:
            errors.append(f"registry schema validation failed: {type(exc).__name__}")
    if tuple(value.value for value in DocumentClass) != (
        "DAILY_STATEMENT",
        "MONTHLY_STATEMENT",
        "FINANCIAL_YEAR_SUMMARY",
        "CONTRACT_NOTE",
        "TRADE_NOTICE",
        "CASH_NOTICE",
        "FX_NOTICE",
        "DIVIDEND_NOTICE",
        "TAX_NOTICE",
        "CORPORATE_ACTION",
        "TRANSFER_CUSTODY",
        "SECURITY_ALERT",
        "KYC_COMPLIANCE",
        "SUPPORT",
        "FEE_NOTICE",
        "PROMOTION_REWARD",
        "RESEARCH_MARKETING",
        "VERIFIED_UNKNOWN",
    ):
        errors.append("frozen document class enumeration drifted")
    return errors


def _validate_source_boundaries(root: Path) -> list[str]:
    errors: list[str] = []
    models = (root / "src/moomooau_archive/processed_models.py").read_text(encoding="utf-8")
    parser = (root / "src/moomooau_archive/document_parser.py").read_text(encoding="utf-8")
    product = (root / "src/moomooau_archive/processed_product.py").read_text(encoding="utf-8")
    commit = (root / "src/moomooau_archive/processed_commit.py").read_text(encoding="utf-8")
    public = (root / "src/moomooau_archive/public_inventory.py").read_text(encoding="utf-8")
    source = "\n".join((models, parser, product, commit, public))

    required_models = (
        "VERIFIED_UNKNOWN",
        "EMPTY_PROTECTED_EVIDENCE_REQUIRED",
        "DocumentEnvelopeFactory",
        "raw_ciphertext_digest",
        'ZoneInfo("Australia/Sydney")',
    )
    required_parser = (
        "attempt_recovery=False",
        "WAITING_FOR_PDF_PASSWORD",
        "read_only=True",
        "keep_links=False",
        "XLSX formula is prohibited",
        "field observations conflict",
        "PROTECTED_PARSER_PROFILE_NOT_AVAILABLE",
    )
    required_product = (
        "pyarrow.parquet",
        "write_table",
        "read_table",
        "Canonical JSONL",
        "business_root",
        "snapshot_root",
    )
    required_commit = (
        "OfficialAgeStream",
        "minimum_observation_days = 14",
        "PROTECTED_APPROVAL_REQUIRED",
        "CONTENT_POINTER_MESSAGE",
        "compare_and_swap_current",
        "remote_recovery_verified=False",
        "public_publish_eligible=False",
        "m3_eligible=False",
    )
    required_public = (
        'ONE_HUNDRED_PLUS = "100+"',
        'UNDER_24_HOURS = "<24h"',
        "moomooau-public-inventory-root",
        "public inventory contains a forbidden private field",
    )
    if any(token not in models for token in required_models):
        errors.append("Document classification or Envelope invariant is missing")
    if any(token not in parser for token in required_parser):
        errors.append("bounded parser or password invariant is missing")
    if any(token not in product for token in required_product):
        errors.append("deterministic JSONL or Parquet invariant is missing")
    if any(token not in commit for token in required_commit):
        errors.append("Processed age, version or blue-green invariant is missing")
    if any(token not in public for token in required_public):
        errors.append("public bucket or opaque-root invariant is missing")
    forbidden_runtime = (
        "moomoo.com",
        "openapi.moomoo.com",
        "import requests",
        "import httpx",
        "import socket",
        "import tempfile",
        "extractall(",
        "eval(",
        "exec(",
    )
    if any(token in source.casefold() for token in forbidden_runtime):
        errors.append("Stage 4 runtime contains Portal, network, extraction or execution scope")
    return errors


class _RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[HttpRequest] = []

    def send(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        return HttpResponse(200, b"{}")


def _validate_github_cas_boundary() -> list[str]:
    errors: list[str] = []
    transport = _RecordingTransport()
    config = TargetRepositoryConfig(repository_id=7_400_001, installation_id=8_400_001)
    guard = GitHubEndpointGuard(transport, config)
    locator = RepositoryLocator(config.repository_id, "synthetic-owner", "synthetic-target")
    guard.bind_repository(locator)
    synthetic_plaintext = b"synthetic plaintext"
    bodies = (
        {
            "content": base64.b64encode(synthetic_plaintext).decode("ascii"),
            "message": CONTENT_APPEND_MESSAGE,
        },
        {
            "content": base64.b64encode(synthetic_plaintext).decode("ascii"),
            "message": CONTENT_POINTER_MESSAGE,
            "sha": "a" * 40,
        },
    )
    paths = (
        "MooMooAU/Processed/statements/v1/parser/1.0.0/" + "a" * 64 + ".jsonl.age",
        "MooMooAU/State/processed-current/" + "a" * 64 + ".json.age",
    )
    for path, payload in zip(paths, bodies, strict=True):
        try:
            guard.send(
                HttpRequest(
                    "PUT",
                    content_url(locator, path),
                    body=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
                )
            )
        except GitHubBoundaryError:
            pass
        else:
            errors.append("plaintext escaped a Processed GitHub pre-network guard")
    if transport.requests or guard.metrics.cross_repository_network_calls != 0:
        errors.append("rejected Processed plaintext reached the transport")
    return errors


def _validate_lock(root: Path) -> list[str]:
    errors: list[str] = []
    lock = root / "requirements/stage4.lock"
    if not lock.is_file() or _sha256(lock) != STAGE4_LOCK_SHA256:
        return ["Stage 4 lock digest is missing or drifted"]
    text = lock.read_text(encoding="utf-8")
    required = (
        "openpyxl==3.1.5",
        "pikepdf==10.10.0",
        "pyarrow==25.0.0",
        "pypdf==6.14.2",
        "pip-tools==7.6.0",
        "--hash=sha256:",
    )
    if any(token not in text for token in required):
        errors.append("Stage 4 lock is missing an exact dependency or hashes")
    if "--index-url" in text or "--extra-index-url" in text or "file://" in text:
        errors.append("Stage 4 lock contains a non-default or local package source")
    sbom_path = root / "machine/stages/S4/supply-chain/sbom.cdx.json"
    if not sbom_path.is_file() or _sha256(sbom_path) != STAGE4_SBOM_SHA256:
        errors.append("Stage 4 reproducible SBOM is missing or drifted")
    else:
        sbom = _load(sbom_path)
        components = {
            item.get("name"): item.get("version")
            for item in sbom.get("components", [])
            if isinstance(item, dict)
        }
        expected_components = {
            "openpyxl": "3.1.5",
            "pikepdf": "10.10.0",
            "pyarrow": "25.0.0",
            "pypdf": "6.14.2",
        }
        if any(components.get(name) != version for name, version in expected_components.items()):
            errors.append("Stage 4 SBOM does not bind the exact parser dependencies")
        if '"purl"' in sbom_path.read_text(encoding="utf-8"):
            errors.append("Stage 4 public-safe SBOM still contains package URL locators")
    return errors


def _validate_workflow(root: Path) -> list[str]:
    errors: list[str] = []
    if not STAGE4_WORKFLOW.is_file():
        return ["Stage 4 CI workflow is missing"]
    workflow = STAGE4_WORKFLOW.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*-?\s*uses:\s*([^\s]+)\s*$", workflow, flags=re.MULTILINE)
    if len(uses) != 8 or any(PINNED_ACTION.fullmatch(item) is None for item in uses):
        errors.append("all eight Stage 4 Action uses must be immutable commit SHAs")
    pins = _load(root / "machine/stages/S2/supply-chain/pins.json")
    for action, metadata in pins.get("actions", {}).items():
        expected = metadata.get("commit_sha") if isinstance(metadata, dict) else None
        if not any(
            item.rsplit("@", 1)[1] == expected
            and (
                item.rsplit("@", 1)[0] == action or item.rsplit("@", 1)[0].startswith(action + "/")
            )
            for item in uses
        ):
            errors.append("Stage 4 workflow drifts from the immutable Action pin catalog")
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
        errors.append("Stage 4 workflow contains a persistence, schedule or authority surface")
    required = (
        "--require-hashes",
        "--cumulative-final",
        "requirements/stage4.lock",
        "test_t04*.py",
        "validate_stage4.py",
        "pip_audit",
        "detect-secrets",
        "dependency-review-action",
        "codeql-action/init",
        "codeql-action/analyze",
        "docker build --no-cache",
        "--network none",
        "--read-only",
        "python -m build",
        "machine/stages/S4/supply-chain/sbom.cdx.json",
        "--exclude-files 'machine/stages/S4/supply-chain/sbom\\.cdx\\.json'",
    )
    if any(token not in workflow for token in required):
        errors.append("Stage 4 workflow is missing a required local or security gate")
    errors.extend(
        validate_governance_dependency_workflow(
            STAGE4_WORKFLOW,
            repository_root=REPOSITORY_ROOT,
        )
    )
    age_digest = pins.get("age", {}).get("linux_amd64_archive_sha256")
    if not isinstance(age_digest, str) or age_digest not in workflow:
        errors.append("Stage 4 workflow does not pin the official age archive")
    dockerfile = (root / "container/Dockerfile.stage4-ci").read_text(encoding="utf-8")
    container_digest = pins.get("container", {}).get("oci_index_digest")
    if (
        not isinstance(container_digest, str)
        or "@" + container_digest not in dockerfile
        or "--require-hashes" not in dockerfile
        or "requirements/stage4.lock" not in dockerfile
        or "not a production runtime image" not in dockerfile
    ):
        errors.append("Stage 4 validation container is mutable or overstated")
    return errors


def _validate_public_surfaces(root: Path) -> list[str]:
    errors: list[str] = []
    publication = scan_tree(root)
    if publication["status"] != "PASS":
        errors.append("project publication scan found forbidden values")
    workflow = STAGE4_WORKFLOW.read_text(encoding="utf-8") if STAGE4_WORKFLOW.is_file() else ""
    if (
        EMAIL.search(workflow)
        or LOCAL_PATH.search(workflow)
        or any(pattern.search(workflow) for pattern in SECRET_PATTERNS)
    ):
        errors.append("Stage 4 workflow contains a forbidden sensitive pattern")
    contract = _load(root / "machine/contracts/publication_safety.json")
    forbidden_hashes = set(contract["forbidden_locator_sha256_casefold"])
    if any(
        hashlib.sha256(token.casefold().encode()).hexdigest() in forbidden_hashes
        for token in REPOSITORY_TOKEN.findall(workflow)
    ):
        errors.append("Stage 4 workflow contains a forbidden private locator")
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S4/schemas/stage4-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    graph = _load(root / "machine/contracts/task_graph.json")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S4"}
    for index, task_id in enumerate(STAGE4_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        if list(validator.iter_errors(record)):
            errors.append(f"invalid evidence schema for {task_id}")
            continue
        if record["stage_acceptance_id"] != f"S4AC-00{index}" or record["record_status"] != "PASS":
            errors.append(f"evidence identity or status mismatch for {task_id}")
        if any(item["status"] != "PASS" for item in record["checks"]):
            errors.append(f"non-passing Stage 4 check for {task_id}")
        linked = record["linked_final_acceptance"]
        if [item["id"] for item in linked] != graph_tasks[task_id]["acceptance_ids"] or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"} for item in linked
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")
        if any(item["status"] != "NOT_RUN" for item in record["production_oracles"]):
            errors.append(f"production oracle is overstated for {task_id}")
        if any(record["prohibition_counters"].values()):
            errors.append(f"prohibition counter is nonzero for {task_id}")

    task_status = _load(root / "machine/stages/S4/contracts/task_status.json")
    if (
        [item.get("id") for item in task_status.get("tasks", [])] != STAGE4_TASKS
        or any(item.get("status") != "completed" for item in task_status.get("tasks", []))
        or task_status.get("baseline_commit") != BASELINE_COMMIT
        or task_status.get("later_stage_status") != "planned_unchanged"
        or task_status.get("delivery_status") != "LOCAL_ONLY_NOT_PUBLISHED"
    ):
        errors.append("Stage 4 task status overlay is incomplete")

    latest = _load(root / "evidence/stage4/latest.json")
    observation = latest.get("stage4_observation", {})
    if (
        latest.get("stage_id") != "S4"
        or latest.get("status") != "PASS"
        or latest.get("scope") != "LOCAL_SYNTHETIC_ONLY"
        or latest.get("task_pass_count") != 7
        or latest.get("task_total") != 7
        or latest.get("cumulative_task_tests_passed") != 95
        or latest.get("final_acceptance_policy") != "NOT_FINAL"
        or latest.get("final_acceptances_passed") != 0
        or latest.get("protected_oracles_executed") != 0
        or any(latest.get("prohibition_counters", {}).values())
        or observation.get("production_classification_rules") != 0
        or observation.get("production_parser_profiles") != 0
        or observation.get("synthetic_document_classes_covered") != 18
        or observation.get("synthetic_trusted_wrong_password_outputs") != 0
        or observation.get("persistent_plaintext_objects") != 0
        or observation.get("processed_overwrites") != 0
        or observation.get("public_forbidden_fields") != 0
        or observation.get("dependency_advisory_scan") != "PASS"
        or observation.get("known_vulnerabilities_observed") != 0
        or observation.get("local_secret_scan_findings") != 0
        or observation.get("package_build_smoke") != "PASS"
        or observation.get("taskpack_validation") != "PASS"
        or observation.get("governance_validation") != "PASS"
        or observation.get("digest_pinned_container_build") != "PASS"
        or observation.get("network_none_read_only_container_smoke") != "PASS"
        or observation.get("real_fourteen_day_parser_observation") != "NOT_RUN"
        or observation.get("private_remote_recovery") != "NOT_RUN"
        or observation.get("remote_stage4_ci") != "NOT_RUN"
    ):
        errors.append("Stage 4 aggregate evidence is not a fail-closed local PASS record")

    semantic = _load(root / "machine/stages/S4/contracts/semantic_gate.json")
    statuses = {item.get("status") for item in semantic.get("resolutions", [])}
    if (
        semantic.get("stage_id") != "S4"
        or semantic.get("status") != "PASS"
        or semantic.get("baseline_commit") != BASELINE_COMMIT
        or not semantic.get("resolutions")
        or not statuses.issubset({"RESOLVED", "CONTROLLED_NOT_RUN"})
        or "CONTROLLED_NOT_RUN" not in statuses
    ):
        errors.append("Stage 4 semantic gate is incomplete or overstates protected oracles")
    return errors


def evaluate_stage4(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
    *,
    include_delivery_records: bool = True,
    allow_stage5: bool = False,
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
    stage3 = evaluate_stage3(root, governance_root, allow_stage4=True)
    checks.append(
        _check(
            "baseline.cumulative_stage3",
            stage3["status"] == "PASS",
            f"Stage 3 failed checks {len(stage3['failed_check_ids'])}",
        )
    )
    contract_errors = _validate_contracts(root)
    checks.append(
        _check(
            "contracts.stage4_overlay",
            not contract_errors,
            f"Stage 4 contract errors {len(contract_errors)}",
        )
    )
    required = [
        root / "src/moomooau_archive/processed_models.py",
        root / "src/moomooau_archive/document_parser.py",
        root / "src/moomooau_archive/processed_product.py",
        root / "src/moomooau_archive/processed_commit.py",
        root / "src/moomooau_archive/public_inventory.py",
        root / "tests/stage4_support.py",
        root / "requirements/stage4.lock",
        root / "container/Dockerfile.stage4-ci",
        root / "machine/stages/S4/supply-chain/sbom.cdx.json",
        STAGE4_WORKFLOW,
    ] + [root / "tests/tasks" / f"test_{task_id.casefold()}.py" for task_id in STAGE4_TASKS]
    checks.append(
        _check(
            "package.stage4_structure",
            all(path.is_file() for path in required),
            f"required Stage 4 paths {len(required)}",
        )
    )
    registry_errors = _validate_registries_and_schemas(root)
    checks.append(
        _check(
            "classification.production_profiles_fail_closed",
            not registry_errors,
            f"registry or schema errors {len(registry_errors)}; active production profiles 0",
        )
    )
    source_errors = _validate_source_boundaries(root)
    checks.append(
        _check(
            "security.stage4_source_boundaries",
            not source_errors,
            f"source boundary errors {len(source_errors)}",
        )
    )
    cas_errors = _validate_github_cas_boundary()
    checks.append(
        _check(
            "security.processed_plaintext_and_cas_guards",
            not cas_errors,
            f"Processed persistence boundary errors {len(cas_errors)}",
        )
    )
    lock_errors = _validate_lock(root)
    checks.append(
        _check(
            "security.stage4_hash_lock",
            not lock_errors,
            f"Stage 4 lock errors {len(lock_errors)}",
        )
    )
    workflow_errors = _validate_workflow(root)
    checks.append(
        _check(
            "security.no_secret_stage4_ci",
            not workflow_errors,
            f"Stage 4 workflow errors {len(workflow_errors)}",
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
    stage5_paths = (
        root / "machine/stages/S5",
        root / "tests/tasks/test_t0501.py",
        REPOSITORY_ROOT / ".github/workflows/moomooau-stage5-ci.yml",
    )
    checks.append(
        _check(
            "scope.no_stage5_or_production_authority",
            allow_stage5 or not any(path.exists() for path in stage5_paths),
            (
                "Stage 5 paths explicitly allowed only by the cumulative Stage 5 validator; "
                "production authority counters 0"
                if allow_stage5
                else "Stage 5 implementation paths 0; production authority counters 0"
            ),
        )
    )
    if include_delivery_records:
        evidence_errors = _validate_evidence(root)
        checks.append(
            _check(
                "evidence.stage4_records",
                not evidence_errors,
                f"Stage 4 evidence errors {len(evidence_errors)}",
            )
        )
    after = _tree_digest(root)
    checks.append(_check("validator.read_only", before == after, "tree digest unchanged"))
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "moomooau.stage4-verification.v1",
        "stage_id": "S4",
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_check_ids": failed,
        "signals": {
            "stage4_tasks": 7,
            "stage4_local_acceptances": 7,
            "production_classification_rules": 0,
            "production_parser_profiles": 0,
            "real_gmail_calls": 0,
            "gmail_mutations": 0,
            "private_repository_calls": 0,
            "real_secrets_read": 0,
            "protected_key_deliveries": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "moomoo_portal_calls": 0,
            "persistent_plaintext_objects": 0,
            "protected_approvals_executed": 0,
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
    result = evaluate_stage4(
        args.root,
        args.governance_root,
        allow_stage5=args.cumulative_final,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
