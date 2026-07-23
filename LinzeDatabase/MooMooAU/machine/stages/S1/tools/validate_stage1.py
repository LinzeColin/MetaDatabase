#!/usr/bin/env python3
"""Fail-closed, read-only cumulative validator for MooMooAU Stage 1."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

PROJECT_ROOT = Path(__file__).resolve().parents[4]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/moomooau-stage1-ci.yml"
BASELINE_COMMIT = "31a51114f8749b93b1da53f7bb11a7e2f7f916de"
BASELINE_MANIFEST_SHA256 = "c2783bd232062ca123a725a3db2cf26a36c4a99a9476c432c36c850f86675c7f"
STAGE1_TASKS = [f"T010{i}" for i in range(1, 8)]
STAGE1_ACCEPTANCES = [f"S1AC-00{i}" for i in range(1, 8)]
IGNORED_PARTS = {
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "build",
    "dist",
}

TOOLS = PROJECT_ROOT / "machine/tools"
SRC = PROJECT_ROOT / "src"
for import_path in (str(TOOLS), str(SRC)):
    if import_path not in sys.path:
        sys.path.insert(0, import_path)

from validate_publication import (  # noqa: E402
    EMAIL,
    LOCAL_PATH,
    REPOSITORY_TOKEN,
    SECRET_PATTERNS,
    scan_tree,
)
from validate_stage0 import evaluate_stage0  # noqa: E402
from validate_workflow_matrix import (  # noqa: E402
    validate_governance_dependency_workflow,
)

from moomooau_archive.adapters import (  # noqa: E402
    EphemeralAgeSession,
    MemoryCiphertextStore,
    TrackedSyntheticSource,
)
from moomooau_archive.contracts import schema_catalog, validate_json_contract  # noqa: E402
from moomooau_archive.fixtures import build_fixture_set  # noqa: E402
from moomooau_archive.models import VerificationDecision  # noqa: E402
from moomooau_archive.pipeline import archive_candidate  # noqa: E402
from moomooau_archive.verification import SyntheticVerifier  # noqa: E402


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
    if WORKFLOW_PATH.is_file():
        paths.append(WORKFLOW_PATH)
    for path in sorted(paths, key=lambda item: str(item)):
        relative = (
            path.relative_to(root).as_posix()
            if path.is_relative_to(root)
            else path.relative_to(REPOSITORY_ROOT).as_posix()
        )
        digest.update(relative.encode("utf-8") + b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


def validate_taskpack_structures(
    requirements: list[dict[str, Any]],
    acceptances: list[dict[str, Any]],
    graph: dict[str, Any],
    trace_rows: list[dict[str, str]],
) -> list[str]:
    errors: list[str] = []
    requirement_ids = [item.get("id") for item in requirements]
    acceptance_ids = [item.get("id") for item in acceptances]
    task_ids = [item.get("id") for item in graph.get("tasks", [])]
    if len(requirement_ids) != 34 or len(set(requirement_ids)) != 34:
        errors.append("requirements must contain 34 unique IDs")
    if len(acceptance_ids) != 34 or len(set(acceptance_ids)) != 34:
        errors.append("acceptances must contain 34 unique IDs")
    if len(task_ids) != 58 or len(set(task_ids)) != 58:
        errors.append("task graph must contain 58 unique task IDs")
    acceptance_by_requirement = {item.get("requirement_id"): item.get("id") for item in acceptances}
    if any(
        acceptance_by_requirement.get(item.get("id")) != item.get("acceptance_id")
        for item in requirements
    ):
        errors.append("requirement to acceptance mapping is incomplete")

    task_set = set(task_ids)
    indegree = {task_id: 0 for task_id in task_ids}
    edges: dict[str, list[str]] = defaultdict(list)
    for task in graph.get("tasks", []):
        for dependency in task.get("dependencies", []):
            if dependency not in task_set:
                errors.append("task dependency references an unknown task")
                continue
            edges[dependency].append(task["id"])
            indegree[task["id"]] += 1
    queue = deque(task_id for task_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        task_id = queue.popleft()
        visited += 1
        for child in edges[task_id]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(task_ids):
        errors.append("task graph is cyclic")

    if (
        len(trace_rows) != 34
        or {row.get("requirement_id") for row in trace_rows} != set(requirement_ids)
        or {row.get("acceptance_id") for row in trace_rows} != set(acceptance_ids)
        or any(not row.get("task_ids", "").strip() for row in trace_rows)
    ):
        errors.append("traceability matrix is incomplete")
    return errors


def _validate_stage1_contracts(root: Path) -> list[str]:
    errors: list[str] = []
    graph = _load(root / "machine/contracts/task_graph.json")
    final_acceptance_ids = {
        item["id"]
        for item in _load(root / "machine/contracts/acceptance_contract.json")[
            "acceptance_contracts"
        ]
    }
    local = _load(root / "machine/stages/S1/contracts/stage1_acceptance_contract.json")
    items = local.get("acceptance_contracts", [])
    if [item.get("id") for item in items] != STAGE1_ACCEPTANCES:
        errors.append("Stage 1 acceptance IDs must be ordered and unique")
    if [item.get("task_id") for item in items] != STAGE1_TASKS:
        errors.append("Stage 1 acceptance to task mapping must be one-to-one")
    graph_tasks = {item["id"]: item for item in graph["tasks"] if item["stage_id"] == "S1"}
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
        linked = item.get("linked_final_acceptance_ids", [])
        if task is None or linked != task.get("acceptance_ids"):
            errors.append("Stage 1 final acceptance links drift from frozen task graph")
        if not set(linked).issubset(final_acceptance_ids):
            errors.append("Stage 1 links an unknown final acceptance")
        if not required_fields.issubset(item) or any(
            not str(item.get(field, "")).strip() for field in required_fields
        ):
            errors.append("Stage 1 acceptance contract is incomplete")
    if len(graph_tasks) != 7:
        errors.append("Stage 1 must contain exactly seven frozen tasks")
    return errors


def _validate_schema_plane(root: Path) -> list[str]:
    errors: list[str] = []
    catalog = schema_catalog()
    if set(catalog) != {"message", "document", "transaction", "timeline", "lineage", "evidence"}:
        errors.append("runtime schema catalog must contain six named contracts")
    sync = {
        "message": "message-envelope-v1.schema.json",
        "document": "document-class-v1.schema.json",
        "timeline": "timeline-event-v1.schema.json",
        "lineage": "lineage-v1.schema.json",
        "evidence": "public-evidence-v1.schema.json",
    }
    for name, filename in sync.items():
        if catalog.get(name) != _load(root / "schemas" / filename):
            errors.append(f"runtime schema drift: {name}")
    for name, schema in catalog.items():
        try:
            validate_json_contract(name, _minimal_valid_instance(name, schema))
        except Exception as exc:  # fail closed with exception type only
            errors.append(f"schema self-check failed: {name}:{type(exc).__name__}")
    return errors


def _minimal_valid_instance(name: str, schema: dict[str, Any]) -> object:
    del schema
    lineage = {
        "source_id": "synthetic-source-000001",
        "parser_name": "synthetic-parser",
        "parser_version": "stage1-v1",
        "schema_version": "1.0.0",
        "imported_at_utc": "2026-01-01T00:00:00Z",
        "key_epoch": "synthetic-epoch",
    }
    values: dict[str, object] = {
        "document": "DAILY_STATEMENT",
        "lineage": lineage,
        "transaction": {
            "source_id": "synthetic-source-000001",
            "transaction_id": "synthetic-tx-001",
            "transaction_date_utc": None,
            "currency": "AUD",
            "amount": None,
            "quantity": None,
            "status": "UNKNOWN",
        },
        "message": {
            "schema_version": "1.0.0",
            "source_id": "synthetic-source-000001",
            "document_class": "DAILY_STATEMENT",
            "verification": {"decision": "VERIFIED", "verifier_version": "stage1-v1"},
            "gmail": {"internal_date_utc": "2026-01-01T00:00:00Z", "label_state": ["SYNTHETIC"]},
            "processing_state": "RAW_ONLY",
            "lineage": lineage,
        },
        "timeline": {
            "schema_version": "1.0.0",
            "source_id": "synthetic-source-000001",
            "document_class": "DAILY_STATEMENT",
            "email_internal_date_utc": "2026-01-01T00:00:00Z",
            "email_received_at_sydney": "2026-01-01T11:00:00+11:00",
            "expectation_state": "UNKNOWN",
            "m3_state": "NOT_ELIGIBLE",
        },
        "evidence": {
            "schema_version": "1.0.0",
            "run_status": "DEGRADED",
            "freshness_bucket": "UNKNOWN",
            "count_bucket": "ZERO",
            "code_version": "stage1-v1",
            "parser_versions": [],
            "opaque_evidence_root": "syntheticOpaqueRoot0001",
            "gates": {"production": "NOT_RUN"},
            "failure_code": "STAGE_1_SYNTHETIC_ONLY",
        },
    }
    return values[name]


def _validate_e2e() -> list[str]:
    errors: list[str] = []
    fixtures = build_fixture_set()
    source = TrackedSyntheticSource((fixtures.verified, fixtures.unrelated, fixtures.spoofed))
    verifier = SyntheticVerifier()
    remote = MemoryCiphertextStore()
    with EphemeralAgeSession() as cipher:
        for rejected in (fixtures.unrelated, fixtures.spoofed):
            result = archive_candidate(
                rejected.metadata,
                source=source,
                verifier=verifier,
                cipher=cipher,
                remote=remote,
            )
            if result.decision is not VerificationDecision.REJECTED or result.raw_fetched:
                errors.append("rejected candidate crossed the RAW boundary")
        verified = archive_candidate(
            fixtures.verified.metadata,
            source=source,
            verifier=verifier,
            cipher=cipher,
            remote=remote,
        )
    if source.raw_fetches != [fixtures.verified.metadata.source_id]:
        errors.append("RAW fetch set is not exactly the verified source")
    if not verified.remote_recovered or verified.plaintext_sha256 != verified.recovered_sha256:
        errors.append("official age remote recovery did not round-trip exactly")
    if remote.put_calls != 1 or remote.fetch_calls != 1 or len(remote.object_names()) != 1:
        errors.append("in-memory remote object cardinality mismatch")
    if any(fixtures.verified.raw in ciphertext for ciphertext in remote.ciphertexts()):
        errors.append("plaintext reached the in-memory remote")
    try:
        validate_json_contract("evidence", verified.public_evidence)
    except Exception as exc:
        errors.append(f"public evidence contract failed: {type(exc).__name__}")
    if verified.public_evidence.get("run_status") != "DEGRADED":
        errors.append("synthetic success must not claim production health")
    return errors


def _validate_workflow(root: Path) -> list[str]:
    errors: list[str] = []
    if not WORKFLOW_PATH.is_file():
        return ["MooMooAU Stage 1 workflow is missing"]
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    uses = re.findall(r"^\s*uses:\s*([^\s]+)\s*$", text, flags=re.MULTILINE)
    if len(uses) != 3 or any(
        re.fullmatch(r"actions/[A-Za-z0-9_-]+@[0-9a-f]{40}", value) is None for value in uses
    ):
        errors.append("all three first-party Actions must use immutable SHAs")
    forbidden = {
        "schedule:": "scheduled production trigger",
        "self-hosted": "self-hosted runner",
        "actions/cache": "dependency cache",
        "upload-artifact": "artifact upload",
        "download-artifact": "artifact download",
        "git push": "remote write",
    }
    for token, label in forbidden.items():
        if token.casefold() in text.casefold():
            errors.append(f"workflow contains forbidden {label}")
    if "permissions:\n  contents: read" not in text:
        errors.append("workflow permissions are not read-only")
    required_families = [
        "ruff",
        "mypy",
        "pytest",
        "validate_stage1.py",
        "build --no-isolation",
        "dual-plane",
        "publication",
    ]
    if any(token not in text for token in required_families):
        errors.append("workflow does not expose all seven Stage 1 gate families")
    errors.extend(
        validate_governance_dependency_workflow(
            WORKFLOW_PATH,
            repository_root=REPOSITORY_ROOT,
        )
    )

    dependency_lines = [
        line.strip()
        for line in (root / "requirements/stage1-ci.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    pin_pattern = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9_.+-]+$")
    if len(dependency_lines) != 10 or any(
        pin_pattern.fullmatch(line) is None for line in dependency_lines
    ):
        errors.append("Stage 1 direct dependency pins are incomplete")
    return errors


def _validate_public_surfaces(root: Path) -> list[str]:
    errors: list[str] = []
    publication = scan_tree(root)
    if publication["status"] != "PASS":
        errors.append("project publication scan found forbidden values")
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8") if WORKFLOW_PATH.is_file() else ""
    if (
        EMAIL.search(workflow)
        or LOCAL_PATH.search(workflow)
        or any(pattern.search(workflow) for pattern in SECRET_PATTERNS)
    ):
        errors.append("workflow contains a forbidden sensitive pattern")
    contract = _load(root / "machine/contracts/publication_safety.json")
    forbidden_hashes = set(contract["forbidden_locator_sha256_casefold"])
    if any(
        hashlib.sha256(token.casefold().encode("utf-8")).hexdigest() in forbidden_hashes
        for token in REPOSITORY_TOKEN.findall(workflow)
    ):
        errors.append("workflow contains a forbidden private locator")
    return errors


def _validate_evidence(root: Path) -> list[str]:
    from jsonschema import Draft202012Validator, FormatChecker

    errors: list[str] = []
    schema = _load(root / "machine/stages/S1/schemas/stage1-evidence-v1.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    contract_items = _load(root / "machine/stages/S1/contracts/stage1_acceptance_contract.json")[
        "acceptance_contracts"
    ]
    contract_by_task = {item["task_id"]: item for item in contract_items}
    for index, task_id in enumerate(STAGE1_TASKS, start=1):
        path = root / "evidence/tasks" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"missing evidence for {task_id}")
            continue
        record = _load(path)
        schema_errors = sorted(validator.iter_errors(record), key=lambda item: list(item.path))
        if schema_errors:
            errors.append(f"invalid evidence schema for {task_id}")
            continue
        if record["stage_acceptance_id"] != f"S1AC-00{index}" or record["record_status"] != "PASS":
            errors.append(f"evidence identity or status mismatch for {task_id}")
        if any(item["status"] != "PASS" for item in record["checks"]):
            errors.append(f"non-passing check in evidence for {task_id}")
        expected_links = contract_by_task[task_id]["linked_final_acceptance_ids"]
        actual_links = [item["id"] for item in record["linked_final_acceptance"]]
        if actual_links != expected_links or any(
            item["status"] not in {"PARTIAL", "NOT_RUN"}
            for item in record["linked_final_acceptance"]
        ):
            errors.append(f"final acceptance status is overstated for {task_id}")

    status_path = root / "machine/stages/S1/contracts/task_status.json"
    if not status_path.is_file():
        errors.append("Stage 1 task status overlay is missing")
    else:
        status = _load(status_path)
        items = status.get("tasks", [])
        if [item.get("id") for item in items] != STAGE1_TASKS or any(
            item.get("status") != "completed" for item in items
        ):
            errors.append("Stage 1 task status overlay is incomplete")
        if status.get("later_stage_status") != "planned_unchanged":
            errors.append("later-stage status boundary is missing")

    latest_path = root / "evidence/stage1/latest.json"
    if not latest_path.is_file():
        errors.append("Stage 1 aggregate evidence is missing")
    else:
        latest = _load(latest_path)
        if (
            latest.get("stage_id") != "S1"
            or latest.get("status") != "PASS"
            or latest.get("task_pass_count") != 7
            or latest.get("task_total") != 7
            or latest.get("final_acceptance_policy") != "NOT_FINAL"
            or any(value != 0 for value in latest.get("prohibition_counters", {}).values())
        ):
            errors.append("Stage 1 aggregate evidence is not a fail-closed PASS record")

    semantic_path = root / "machine/stages/S1/contracts/semantic_gate.json"
    if not semantic_path.is_file():
        errors.append("Stage 1 semantic gate is missing")
    else:
        semantic = _load(semantic_path)
        if (
            semantic.get("stage_id") != "S1"
            or semantic.get("status") != "PASS"
            or semantic.get("baseline_commit") != BASELINE_COMMIT
            or not semantic.get("resolutions")
            or any(item.get("status") != "RESOLVED" for item in semantic["resolutions"])
        ):
            errors.append("Stage 1 semantic gate is incomplete")
    return errors


def evaluate_stage1(
    root: Path = PROJECT_ROOT,
    governance_root: Path | None = None,
    *,
    include_delivery_records: bool = True,
) -> dict[str, Any]:
    root = root.resolve()
    before = _tree_digest(root)
    checks: list[dict[str, str]] = []

    baseline_manifest = root / "taskpack/PACKAGE_MANIFEST.v1.0.1.json"
    baseline_hash_ok = _sha256(baseline_manifest) == BASELINE_MANIFEST_SHA256
    checks.append(
        _check(
            "baseline.manifest_identity",
            baseline_hash_ok,
            "frozen manifest digest matches Stage 0 handoff",
        )
    )

    stage0 = evaluate_stage0(root, governance_root)
    expected_retired_gate = {"scope.no_stage1_or_deployment"}
    baseline_ok = set(stage0["failed_check_ids"]) == expected_retired_gate and all(
        check["status"] == "PASS"
        for check in stage0["checks"]
        if check["id"] not in expected_retired_gate
    )
    checks.append(
        _check(
            "baseline.cumulative_stage0",
            baseline_ok,
            "enduring Stage 0 checks pass; only its retired no-Stage-1 gate fails",
        )
    )

    requirements = _load(root / "machine/contracts/requirements.json")["requirements"]
    acceptances = _load(root / "machine/contracts/acceptance_contract.json")["acceptance_contracts"]
    graph = _load(root / "machine/contracts/task_graph.json")
    with (root / "machine/contracts/traceability_matrix.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        trace_rows = list(csv.DictReader(stream))
    taskpack_errors = validate_taskpack_structures(requirements, acceptances, graph, trace_rows)
    checks.append(
        _check(
            "contracts.frozen_taskpack",
            not taskpack_errors,
            f"taskpack structural errors {len(taskpack_errors)}",
        )
    )

    local_errors = _validate_stage1_contracts(root)
    checks.append(
        _check(
            "contracts.stage1_overlay",
            not local_errors,
            f"Stage 1 overlay errors {len(local_errors)}",
        )
    )

    required = [
        root / "pyproject.toml",
        root / "src/moomooau_archive/cli.py",
        root / "src/moomooau_archive/contracts.py",
        root / "requirements/stage1-ci.txt",
        root / "machine/stages/S1/tools/validate_stage1.py",
        WORKFLOW_PATH,
    ] + [root / "tests/tasks" / f"test_{task_id.casefold()}.py" for task_id in STAGE1_TASKS]
    missing = [path for path in required if not path.is_file()]
    checks.append(
        _check("package.public_structure", not missing, f"required file misses {len(missing)}")
    )

    schema_errors = _validate_schema_plane(root)
    checks.append(
        _check(
            "contracts.schema_plane", not schema_errors, f"schema plane errors {len(schema_errors)}"
        )
    )

    e2e_errors = _validate_e2e()
    checks.append(
        _check(
            "skeleton.official_age_roundtrip",
            not e2e_errors,
            f"synthetic pipeline errors {len(e2e_errors)}",
        )
    )

    workflow_errors = _validate_workflow(root)
    checks.append(
        _check("ci.no_secret_base", not workflow_errors, f"workflow errors {len(workflow_errors)}")
    )

    publication_errors = _validate_public_surfaces(root)
    checks.append(
        _check(
            "security.publication",
            not publication_errors,
            f"publication errors {len(publication_errors)}",
        )
    )

    run_contract = _load(root / "machine/stages/S1/contracts/run_contract.json")
    prohibition_values = run_contract.get("prohibitions", {})
    source_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((root / "src").rglob("*.py"))
    )
    prohibited_imports = [
        token
        for token in ("googleapiclient", "google.auth", "httpx", "requests")
        if token in source_text
    ]
    prohibitions_ok = (
        prohibition_values
        and all(value == 0 for value in prohibition_values.values())
        and not prohibited_imports
        and run_contract.get("baseline_commit") == BASELINE_COMMIT
    )
    checks.append(
        _check(
            "scope.zero_external_authority",
            prohibitions_ok,
            f"prohibited runtime imports {len(prohibited_imports)}",
        )
    )

    if include_delivery_records:
        evidence_errors = _validate_evidence(root)
        checks.append(
            _check(
                "evidence.stage1_records",
                not evidence_errors,
                f"Stage 1 evidence errors {len(evidence_errors)}",
            )
        )

    after = _tree_digest(root)
    checks.append(
        _check("validator.read_only", before == after, "tree digest unchanged during validation")
    )
    failed = [item["id"] for item in checks if item["status"] != "PASS"]
    return {
        "schema_version": "moomooau.stage1-verification.v1",
        "stage_id": "S1",
        "status": "PASS" if not failed else "BLOCKED",
        "checks": checks,
        "failed_check_ids": failed,
        "signals": {
            "stage1_tasks": 7,
            "stage1_local_acceptances": 7,
            "gmail_calls": 0,
            "gmail_mutations": 0,
            "secrets_read": 0,
            "external_writes": 0,
            "remote_publication": 0,
            "final_acceptances_passed": 0,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--governance-root", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_stage1(args.root, args.governance_root)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
