"""Fail-closed, local-only acceptance oracle for ABD S14/P04.

The P04 SHA-256 value is a replayable local attestation, not a key-backed
production signature. A passing result proves only the available local
source/dependency/build trace and never asserts deployment, account access,
real orders, a production host, or a financial return.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import platform
import re
import sys
import tomllib
from typing import Any, Dict, List, Mapping, MutableMapping
import xml.etree.ElementTree as ElementTree

from .canonical_facts import sha256_file, strict_json_load
from .component_governance import (
    EXTERNAL_EFFECT_BOUNDARY as P03_EXTERNAL_EFFECT_BOUNDARY,
    verify_existing_phase_evidence as verify_component_governance_phase_evidence,
)


CONTRACT_ID = "AC-S14-P04"
REQUIREMENT_ID = "REQ-S14-P04"
STAGE_ID = "S14"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

PROVENANCE_PATH = Path("provenance.json")
SIGNING_PATH = Path("artifact_signing.md")
ROLLBACK_POLICY_PATH = Path("security_rollback.md")
ORACLE_PATH = Path("abd_acceptance/artifact_provenance.py")
TEST_PATH = Path("tests/S14/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S14_P04.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S14/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S14/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")

REQUIREMENTS_PATH = Path("machine/facts/requirements.json")
CONTRACTS_PATH = Path("machine/facts/acceptance_contracts.json")
TASK_GRAPH_PATH = Path("machine/facts/task_graph.json")
TRACEABILITY_PATH = Path("machine/facts/traceability_matrix.json")
DEPENDENCY_BUDGET_PATH = Path("machine/facts/dependency_budget.lock")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S14-P03.json")
P03_ROLLBACK_PATH = Path("machine/evidence/EVD-S14-P03_rollback.json")

P03_EVIDENCE_SHA256 = "5d0644b143115c6cdd99eb8774b8f8cbc68a618ba86b82772ff6797e7293708c"
P03_ROLLBACK_SHA256 = "39437e5a68e6cb86bc6a4122bcda763b501be4196d2973a64c0d2a2b2c8d64b2"
SOURCE_BASE_REVISION = "4e340376392d6bde2a39f31511fe4a4e4e22eb30"
SOURCE_BASE_TREE = "a36d8788c172942d3c4b81ba2ba37d448a90ff2d"

SOURCE_INPUT_PATHS = (
    "../LICENSE",
    "PURSUE_GOAL_PROMPT.txt",
    "VERSION",
    "machine/facts/canonical_facts.json",
    "machine/facts/parameters.json",
    "machine/facts/requirements.json",
    "machine/facts/acceptance_contracts.json",
    "machine/facts/task_graph.json",
    "machine/facts/traceability_matrix.json",
    "sbom.json",
    "component_governance.json",
    "patch_sla.json",
    ORACLE_PATH.as_posix(),
    TEST_PATH.as_posix(),
    FIXTURE_PATH.as_posix(),
)
SNAPSHOT_CASE_IDS = (
    "PASS",
    "P03_PREDECESSOR_FAIL",
    "PROVENANCE_FAIL",
    "SIGNING_POLICY_FAIL",
    "ROLLBACK_POLICY_FAIL",
    "SOURCE_TRACE_FAIL",
    "DEPENDENCY_TRACE_FAIL",
    "BUILD_ENVIRONMENT_FAIL",
    "ATTESTATION_FAIL",
    "EXTERNAL_BOUNDARY_FAIL",
    "POINT_0001_COVERAGE_LOW",
    "POINT_0001_COVERAGE_HIGH",
    "FOREIGN_ODDS_INPUT_FAIL",
)
EXTERNAL_EFFECT_BOUNDARY = dict(P03_EXTERNAL_EFFECT_BOUNDARY)


class ArtifactProvenanceError(ValueError):
    """Raised when S14/P04 cannot remain deterministic and fail closed."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_float(item) for item in value)
    return False


def _portable(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(isinstance(key, str) and _portable(item) for key, item in value.items())
    if isinstance(value, list):
        return all(_portable(item) for item in value)
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return not normalized.startswith("/") and "/Users/" not in normalized and "file://" not in normalized
    return True


def _strict_jsonl(path: Path) -> List[Mapping[str, Any]]:
    rows: List[Mapping[str, Any]] = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise ArtifactProvenanceError("blank evidence-index row %d" % number)
        row = json.loads(line)
        if not isinstance(row, Mapping):
            raise ArtifactProvenanceError("evidence-index row %d is not an object" % number)
        rows.append(row)
    if not rows:
        raise ArtifactProvenanceError("evidence index is empty")
    return rows


def _row(rows: Any, identifier: str, *, key: str = "id") -> Mapping[str, Any]:
    if not isinstance(rows, list):
        raise ArtifactProvenanceError("rows must be a list")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == identifier]
    if len(matches) != 1:
        raise ArtifactProvenanceError("expected exactly one %s=%s" % (key, identifier))
    return matches[0]


def _safe_load(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        value = strict_json_load(root / relative)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _safe_text(root: Path, relative: Path, checks: List[Dict[str, Any]], identifier: str) -> str | None:
    try:
        value = (root / relative).read_text(encoding="utf-8")
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, relative.as_posix())
    return value


def _coverage_decimal(value: Any) -> Decimal:
    if not isinstance(value, str) or re.fullmatch(r"\d+\.\d{4}", value) is None:
        raise ArtifactProvenanceError("coverage_score must be four-place decimal text")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ArtifactProvenanceError("coverage_score is not decimal") from exc


def _expected_source_base() -> Dict[str, str]:
    return {
        "repository_remote": "git@github.com:LinzeColin/MetaDatabase.git",
        "repository_subdirectory": "ABD",
        "predecessor_source_revision": SOURCE_BASE_REVISION,
        "predecessor_source_tree": SOURCE_BASE_TREE,
        "revision_role": "S14_P03_SIGNED_PREDECESSOR_BASE_NOT_A_P04_RELEASE_COMMIT",
        "current_p04_commit_status": "NOT_CREATED_AT_LOCAL_ATTESTATION_TIME",
    }


def _expected_build_environment() -> Dict[str, Any]:
    return {
        "command": "uv run --frozen --python 3.12",
        "python": {
            "implementation": sys.implementation.name,
            "version": ".".join(str(part) for part in sys.version_info[:3]),
        },
        "uv_version_observed": "0.11.28 (ebf0f43d7 2026-07-07 aarch64-apple-darwin)",
        "host": {
            "system": platform.system(),
            "machine": platform.machine(),
            "classification": "LOCAL_DEVELOPMENT_ENVIRONMENT_NOT_CI_OR_PRODUCTION",
        },
        "reproducibility_scope": "LOCAL_FROZEN_PHASE_EXECUTION_ONLY",
        "production_host_or_image_verified": False,
        "external_network_accessed": False,
    }


def _source_input_hashes(root: Path) -> Dict[str, str]:
    # The shared CLI dispatcher is owned by stage orchestration.  It is
    # deliberately outside P04's phase-owned provenance closure so a later
    # stage-review entrypoint cannot silently invalidate this signed Phase.
    return {relative: sha256_file(root / relative) for relative in SOURCE_INPUT_PATHS}


def _expected_dependency_provenance(root: Path) -> Dict[str, Any]:
    try:
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8")).get("project")
        budget = strict_json_load(root / DEPENDENCY_BUDGET_PATH)
    except Exception as exc:
        raise ArtifactProvenanceError("dependency provenance sources are unreadable") from exc
    environment = budget.get("python_environment") if isinstance(budget, Mapping) else None
    if (
        not isinstance(project, Mapping)
        or not isinstance(environment, Mapping)
        or project.get("name") != "abd"
        or project.get("version") != VERSION
        or project.get("dependencies") != []
        or environment.get("runtime_direct_dependencies") != []
        or environment.get("dev_direct_dependencies") != ["jsonschema==4.25.1", "pytest==8.4.2"]
    ):
        raise ArtifactProvenanceError("frozen zero-runtime-dependency boundary is not established")
    return {
        "runtime_direct_dependencies": [],
        "development_direct_dependencies": ["jsonschema==4.25.1", "pytest==8.4.2"],
        "locked_files": {
            "pyproject.toml": sha256_file(root / "pyproject.toml"),
            "uv.lock": sha256_file(root / "uv.lock"),
            DEPENDENCY_BUDGET_PATH.as_posix(): sha256_file(root / DEPENDENCY_BUDGET_PATH),
        },
        "component_inventory": {
            "path": "sbom.json",
            "sha256": sha256_file(root / "sbom.json"),
            "production_component_count": 1,
            "unadmitted_runtime_prerequisites": [
                "UNADMITTED-ABD-IMAGE",
                "UNADMITTED-CLOUDFLARED-BINARY",
                "UNADMITTED-CLOUDFLARE-OVH-RUNTIME",
            ],
        },
        "runtime_status": "NO_DECLARED_RUNTIME_DIRECT_DEPENDENCIES",
    }


def _expected_artifact_hashes(root: Path) -> Dict[str, str]:
    return {
        SIGNING_PATH.as_posix(): sha256_file(root / SIGNING_PATH),
        ROLLBACK_POLICY_PATH.as_posix(): sha256_file(root / ROLLBACK_POLICY_PATH),
    }


def compute_local_attestation(provenance: Mapping[str, Any]) -> str:
    """Return the self-excluding local SHA-256 attestation."""

    payload = dict(provenance)
    attestation = payload.get("local_attestation")
    if isinstance(attestation, Mapping):
        normalized = dict(attestation)
        normalized.pop("value", None)
        payload["local_attestation"] = normalized
    return _sha256_bytes(_json_bytes(payload))


def _require_header(value: Mapping[str, Any]) -> None:
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("evidence_kind") != "ABD_LOCAL_PRE_RELEASE_PROVENANCE"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("execution_mode") != "FROZEN_LOCAL_DETERMINISTIC_NO_NETWORK"
    ):
        raise ArtifactProvenanceError("provenance header is not frozen")


def validate_provenance(value: Any, root: Path) -> Dict[str, Any]:
    fields = {
        "schema_version", "evidence_kind", "contract_id", "requirement_id", "stage_id", "phase_id",
        "product_version", "fixed_clock", "execution_mode", "provenance_status", "source_base",
        "source_inputs", "dependency_provenance", "build_environment", "local_attestation",
        "artifact_hashes", "predecessor", "external_effect_boundary", "release_boundary",
        "not_production_evidence",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value) or not _portable(value):
        raise ArtifactProvenanceError("provenance fields are not closed or portable")
    _require_header(value)
    attestation = value.get("local_attestation")
    expected_attestation = {
        "algorithm": "SHA-256",
        "scope": "CANONICAL_PROVENANCE_EXCLUDING_ATTESTATION_VALUE_LOCAL_REPLAY_ONLY",
        "keyed_or_identity_signature": False,
        "verification": "LOCAL_CANONICAL_JSON_REPLAY_ONLY_NOT_A_RELEASE_SIGNATURE",
    }
    predecessor = {
        "contract_id": "AC-S14-P03",
        "receipt": P03_EVIDENCE_PATH.as_posix(),
        "receipt_sha256": P03_EVIDENCE_SHA256,
        "rollback_receipt": P03_ROLLBACK_PATH.as_posix(),
        "rollback_receipt_sha256": P03_ROLLBACK_SHA256,
        "status": "PASS",
    }
    release_boundary = {
        "actual_release_signed": False,
        "approval_evidence_present": False,
        "deployment_or_activation_performed": False,
        "stage_review_required_before_any_release": True,
        "real_orders_or_accounts_accessed": False,
        "incremental_cash_spent_aud": "0.00",
    }
    if (
        value.get("provenance_status") != "LOCAL_PRE_RELEASE_PROVENANCE_COMPLETE_NOT_DEPLOYED"
        or value.get("source_base") != _expected_source_base()
        or value.get("source_inputs") != _source_input_hashes(root)
        or value.get("dependency_provenance") != _expected_dependency_provenance(root)
        or value.get("build_environment") != _expected_build_environment()
        or not isinstance(attestation, Mapping)
        or {key: attestation.get(key) for key in expected_attestation} != expected_attestation
        or not isinstance(attestation.get("value"), str)
        or re.fullmatch(r"[a-f0-9]{64}", attestation["value"]) is None
        or attestation["value"] != compute_local_attestation(value)
        or value.get("artifact_hashes") != _expected_artifact_hashes(root)
        or value.get("predecessor") != predecessor
        or value.get("external_effect_boundary") != EXTERNAL_EFFECT_BOUNDARY
        or value.get("release_boundary") != release_boundary
        or value.get("not_production_evidence") is not True
    ):
        raise ArtifactProvenanceError("provenance contract is not exact")
    return {
        "source_input_count": len(value["source_inputs"]),
        "dependency_lock_count": len(value["dependency_provenance"]["locked_files"]),
        "artifact_document_count": len(value["artifact_hashes"]),
        "attestation_is_keyed_signature": False,
    }


SIGNING_REQUIRED_MARKERS = (
    "# ABD Artifact Signing Boundary",
    "Local SHA-256 attestation only",
    "not a GPG, Sigstore, key-backed, identity-backed, or production release signature",
    "AC-S14-P04",
    "provenance.json",
    "stage review and explicit approval evidence are required before any real release",
    "No signing key, account credential, deployment target, or external service is accessed by this Phase.",
)
ROLLBACK_REQUIRED_MARKERS = (
    "# ABD Security Rollback Boundary",
    "DISABLE_S14_P04_LOCAL_RELEASE_CANDIDATE",
    "restore the last signed S14/P03 evidence baseline",
    "preserve immutable local evidence and deterministic replay inputs",
    "source hash mismatch",
    "dependency lock mismatch",
    "malformed local attestation",
    "critical or high security finding",
    "No shell, host, Cloudflare, OVH, account, order, or deployment mutation is performed by this Phase.",
    "A real production rollback requires its own authorized release and operations gate.",
)


def validate_artifact_signing(value: Any) -> Dict[str, Any]:
    if not isinstance(value, str) or not value.endswith("\n") or "\r" in value:
        raise ArtifactProvenanceError("artifact signing policy must be normalized UTF-8 text")
    if any(marker not in value for marker in SIGNING_REQUIRED_MARKERS):
        raise ArtifactProvenanceError("artifact signing policy is missing required boundaries")
    return {"sha256": _sha256_bytes(value.encode("utf-8")), "actual_release_signature_created": False}


def validate_security_rollback(value: Any) -> Dict[str, Any]:
    if not isinstance(value, str) or not value.endswith("\n") or "\r" in value:
        raise ArtifactProvenanceError("security rollback policy must be normalized UTF-8 text")
    if any(marker not in value for marker in ROLLBACK_REQUIRED_MARKERS):
        raise ArtifactProvenanceError("security rollback policy is missing required boundaries")
    return {"sha256": _sha256_bytes(value.encode("utf-8")), "external_mutation_performed": False}


def evaluate_provenance_snapshot(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    required = {
        "p03_receipt_current", "provenance_closed", "signing_policy_closed", "rollback_policy_closed",
        "source_trace_closed", "dependency_trace_closed", "build_environment_trace_closed",
        "attestation_valid", "external_effect_boundary_preserved", "coverage_score",
        "foreign_odds_input_present",
    }
    if not isinstance(snapshot, Mapping) or set(snapshot) != required:
        raise ArtifactProvenanceError("provenance snapshot shape is invalid")
    for field in required - {"coverage_score"}:
        if type(snapshot.get(field)) is not bool:
            raise ArtifactProvenanceError("%s must be boolean" % field)
    coverage = _coverage_decimal(snapshot.get("coverage_score"))
    reason_map = (
        ("p03_receipt_current", "P03_RECEIPT_NOT_CURRENT"),
        ("provenance_closed", "PROVENANCE_NOT_CLOSED"),
        ("signing_policy_closed", "SIGNING_POLICY_NOT_CLOSED"),
        ("rollback_policy_closed", "ROLLBACK_POLICY_NOT_CLOSED"),
        ("source_trace_closed", "SOURCE_TRACE_NOT_CLOSED"),
        ("dependency_trace_closed", "DEPENDENCY_TRACE_NOT_CLOSED"),
        ("build_environment_trace_closed", "BUILD_ENVIRONMENT_TRACE_NOT_CLOSED"),
        ("attestation_valid", "LOCAL_ATTESTATION_INVALID"),
        ("external_effect_boundary_preserved", "EXTERNAL_ACTION_BOUNDARY_RELAXED"),
    )
    reasons = [reason for key, reason in reason_map if snapshot[key] is not True]
    if coverage != Decimal("1.0000"):
        reasons.append("PROVENANCE_COVERAGE_NOT_EXACT")
    if snapshot["foreign_odds_input_present"] is True:
        reasons.append("FOREIGN_ODDS_INPUT_REJECTED")
    result: Dict[str, Any] = {
        "status": "S14P04_PROVENANCE_VERIFIED_NO_ACTION"
        if not reasons else "S14P04_PROVENANCE_REJECTED_NO_ACTION",
        "reason_codes": reasons,
        "release_enabled": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "external_network_used": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }
    result["output_sha256"] = _sha256_bytes(_json_bytes(result))
    return result


def validate_provenance_fixture(value: Any) -> Dict[str, Any]:
    fields = {
        "schema_version", "fixture_id", "contract_id", "requirement_id", "stage_id", "phase_id",
        "product_version", "fixed_clock", "minimum_targeted_pytest_cases", "expected_decision",
        "expected_next", "snapshot_case_count", "snapshot_cases",
    }
    if not isinstance(value, Mapping) or set(value) != fields or _contains_float(value):
        raise ArtifactProvenanceError("provenance fixture fields are not closed")
    if (
        value.get("schema_version") != "1.0.0"
        or value.get("fixture_id") != "FIX-S14-P04-ARTIFACT-PROVENANCE"
        or value.get("contract_id") != CONTRACT_ID
        or value.get("requirement_id") != REQUIREMENT_ID
        or value.get("stage_id") != STAGE_ID
        or value.get("phase_id") != PHASE_ID
        or value.get("product_version") != VERSION
        or value.get("fixed_clock") != FIXED_CLOCK
        or value.get("minimum_targeted_pytest_cases") != 37
        or value.get("expected_decision") != "LOCAL_PRE_RELEASE_PROVENANCE_COMPLETE_STAGE_REVIEW_REQUIRED"
        or value.get("expected_next") != "S14/STAGE_REVIEW_READY_NOT_STARTED"
        or value.get("snapshot_case_count") != len(SNAPSHOT_CASE_IDS)
    ):
        raise ArtifactProvenanceError("provenance fixture header is not frozen")
    rows = value.get("snapshot_cases")
    if not isinstance(rows, list) or [row.get("case_id") for row in rows if isinstance(row, Mapping)] != list(SNAPSHOT_CASE_IDS):
        raise ArtifactProvenanceError("provenance fixture snapshots are not exact")
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != {"case_id", "snapshot", "expected"}:
            raise ArtifactProvenanceError("provenance fixture snapshot shape is invalid")
        actual = evaluate_provenance_snapshot(row["snapshot"])
        expected = row.get("expected")
        if (
            not isinstance(expected, Mapping)
            or set(expected) != {"status", "reason_codes"}
            or actual["status"] != expected["status"]
            or actual["reason_codes"] != expected["reason_codes"]
        ):
            raise ArtifactProvenanceError("provenance fixture expected result is invalid")
    return dict(value)


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> bool:
    try:
        verified = verify_component_governance_phase_evidence(root)
        receipt = strict_json_load(root / P03_EVIDENCE_PATH)
        rollback = strict_json_load(root / P03_ROLLBACK_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-AC-S14-P03")
        passed = (
            verified.get("status") == "PASS"
            and isinstance(receipt, Mapping)
            and receipt.get("next") == "S14/P04_READY_NOT_STARTED"
            and sha256_file(root / P03_EVIDENCE_PATH) == P03_EVIDENCE_SHA256
            and isinstance(rollback, Mapping)
            and rollback.get("status") == "PASS"
            and sha256_file(root / P03_ROLLBACK_PATH) == P03_ROLLBACK_SHA256
            and index.get("artifact_sha256") == P03_EVIDENCE_SHA256
        )
        detail: Any = {"predecessor_verifier": verified.get("status"), "index": index.get("status")}
        hashes[P03_EVIDENCE_PATH.as_posix()] = sha256_file(root / P03_EVIDENCE_PATH)
        hashes[P03_ROLLBACK_PATH.as_posix()] = sha256_file(root / P03_ROLLBACK_PATH)
    except Exception as exc:
        passed = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P04-P03-SIGNED-DEPENDENCY-EXACT", passed, detail)
    return passed


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> bool:
    requirements = _safe_load(root, REQUIREMENTS_PATH, checks, "S14P04-REQUIREMENTS-PARSE")
    contracts = _safe_load(root, CONTRACTS_PATH, checks, "S14P04-CONTRACTS-PARSE")
    graph = _safe_load(root, TASK_GRAPH_PATH, checks, "S14P04-TASK-GRAPH-PARSE")
    traceability = _safe_load(root, TRACEABILITY_PATH, checks, "S14P04-TRACEABILITY-PARSE")
    try:
        index = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        _add(checks, "S14P04-EVIDENCE-INDEX-PARSE", True, EVIDENCE_INDEX_PATH.as_posix())
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        trace = _row(traceability, REQUIREMENT_ID, key="requirement_id")
        task_rows = [
            row for row in graph["tasks"]
            if isinstance(row, Mapping) and row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID
        ]
        task_map = {row.get("id"): row for row in task_rows}
        index_row = _row(index, "INDEX-" + CONTRACT_ID)
        task_ids = ["T-S14-P04-01", "T-S14-P04-02", "T-S14-P04-03"]
        signed_index = (
            index_row.get("kind") == "PHASE_EVIDENCE"
            and index_row.get("contract_id") == CONTRACT_ID
            and index_row.get("status") == "PASS"
            and index_row.get("actual_artifact") == EVIDENCE_PATH.as_posix()
            and index_row.get("next") == "S14/STAGE_REVIEW_READY_NOT_STARTED"
            and isinstance(index_row.get("artifact_sha256"), str)
        )
        planned_index = (
            index_row.get("kind") == "ACCEPTANCE_EVIDENCE"
            and index_row.get("acceptance_contract_id") == CONTRACT_ID
            and index_row.get("status") == "PLANNED"
            and index_row.get("expected_artifact") == EVIDENCE_PATH.as_posix()
        )
        exact = (
            requirement.get("scope") == [PROVENANCE_PATH.as_posix(), SIGNING_PATH.as_posix(), ROLLBACK_POLICY_PATH.as_posix()]
            and requirement.get("target") == "发布制品可追溯到源代码、依赖和构建环境。"
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S14-P04 --evidence machine/evidence"
            and [item.get("id") for item in contract.get("tests", [])]
            == ["TEST-S14-P04", "TEST-S14-P04-BOUNDARY", "TEST-S14-P04-REPLAY"]
            and [row.get("id") for row in task_rows] == task_ids
            and task_map[task_ids[0]].get("outputs") == [PROVENANCE_PATH.as_posix(), SIGNING_PATH.as_posix(), ROLLBACK_POLICY_PATH.as_posix()]
            and task_map[task_ids[0]].get("depends_on") == ["T-S14-P03-03"]
            and task_map[task_ids[1]].get("outputs") == [TEST_PATH.as_posix(), FIXTURE_PATH.as_posix()]
            and task_map[task_ids[2]].get("outputs") == [EVIDENCE_PATH.as_posix(), ROLLBACK_EVIDENCE_PATH.as_posix()]
            and trace.get("acceptance_criteria_id") == CONTRACT_ID
            and trace.get("task_ids") == task_ids
            and trace.get("evidence_id") == "EVD-S14-P04"
            and trace.get("artifact_ids") == ["ART-S14-P04-01", "ART-S14-P04-02", "ART-S14-P04-03"]
            and (planned_index or signed_index)
        )
        detail: Any = {"task_ids": task_ids, "index_status": index_row.get("status")}
    except Exception as exc:
        exact = False
        detail = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S14P04-REQUIREMENT-ACCEPTANCE-TASK-TRACE-EXACT", exact, detail)
    return exact


def _check_artifacts(provenance: Any, signing: Any, rollback_policy: Any, fixture: Any, root: Path, checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    validators = (
        ("provenance", "S14P04-PROVENANCE-EXACT", lambda: validate_provenance(provenance, root)),
        ("signing", "S14P04-SIGNING-POLICY-EXACT", lambda: validate_artifact_signing(signing)),
        ("rollback", "S14P04-ROLLBACK-POLICY-EXACT", lambda: validate_security_rollback(rollback_policy)),
        ("fixture", "S14P04-FIXTURE-EXACT", lambda: validate_provenance_fixture(fixture)),
    )
    for name, identifier, validator in validators:
        try:
            results[name] = validator()
            _add(checks, identifier, True, results[name])
            results[name + "_ok"] = True
        except Exception as exc:
            _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
            results[name + "_ok"] = False
    return results


def _check_snapshot_cases(fixture: Any, checks: List[Dict[str, Any]]) -> bool:
    rows = fixture.get("snapshot_cases") if isinstance(fixture, Mapping) else None
    if not isinstance(rows, list):
        _add(checks, "S14P04-SNAPSHOT-CASES", False, "cases unavailable")
        return False
    passed = True
    for row in rows:
        try:
            actual = evaluate_provenance_snapshot(row["snapshot"])
            current = actual["status"] == row["expected"]["status"] and actual["reason_codes"] == row["expected"]["reason_codes"]
        except Exception as exc:
            actual = "%s: %s" % (type(exc).__name__, exc)
            current = False
        case_id = row.get("case_id") if isinstance(row, Mapping) else "MALFORMED"
        _add(checks, "S14P04-CASE-%s" % case_id, current, actual)
        passed = passed and current
    return passed


def _check_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], *, require_test_reports: bool) -> bool:
    if not require_test_reports:
        return True
    try:
        document = ElementTree.parse(root / JUNIT_PATH).getroot()
        suites = [document] if document.tag == "testsuite" else list(document.findall("testsuite"))
        summary = {field: sum(int(suite.attrib.get(field, "0")) for suite in suites) for field in ("tests", "failures", "errors", "skipped")}
        junit_ok = (
            bool(suites)
            and summary["tests"] >= fixture.get("minimum_targeted_pytest_cases")
            and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0
            and all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK for suite in suites)
        )
    except Exception as exc:
        summary = "%s: %s" % (type(exc).__name__, exc)
        junit_ok = False
    _add(checks, "S14P04-TARGETED-PYTEST-REPORT", junit_ok, summary)
    try:
        scan = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = all(
            marker in scan for marker in (
                "STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
                "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
            )
        )
    except Exception as exc:
        scan = "%s: %s" % (type(exc).__name__, exc)
        scan_ok = False
    _add(checks, "S14P04-PAID-DEPENDENCY-SCAN-PASS", scan_ok, SCAN_REPORT_PATH.as_posix() if scan_ok else scan)
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary_value = report.get("summary") if isinstance(report, Mapping) else None
        pack_ok = (
            isinstance(report, Mapping) and report.get("status") == "PASS" and isinstance(summary_value, Mapping)
            and summary_value.get("failed") == 0 and summary_value.get("passed") == summary_value.get("checks")
        )
    except Exception as exc:
        summary_value = "%s: %s" % (type(exc).__name__, exc)
        pack_ok = False
    _add(checks, "S14P04-TASKPACK-STATIC-VALIDATION-PASS", pack_ok, summary_value)
    return junit_ok and scan_ok and pack_ok


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str], snapshot: Mapping[str, Any], analysis: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "contract_id": CONTRACT_ID, "requirement_id": REQUIREMENT_ID, "stage_id": STAGE_ID, "phase_id": PHASE_ID,
        "status": status,
        "decision": "LOCAL_PRE_RELEASE_PROVENANCE_COMPLETE_STAGE_REVIEW_REQUIRED" if status == "PASS" else "ARTIFACT_PROVENANCE_REMEDIATION_REQUIRED",
        "next": "S14/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S14/P04_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_ids": failed},
        "checks": checks, "snapshot": dict(snapshot), "analysis": dict(analysis), "hashes": dict(sorted(hashes.items())),
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    predecessor_ok = _check_predecessor(root, checks, hashes)
    _check_taskpack(root, checks)
    provenance = _safe_load(root, PROVENANCE_PATH, checks, "S14P04-PROVENANCE-PARSE")
    signing = _safe_text(root, SIGNING_PATH, checks, "S14P04-SIGNING-POLICY-PARSE")
    rollback_policy = _safe_text(root, ROLLBACK_POLICY_PATH, checks, "S14P04-ROLLBACK-POLICY-PARSE")
    fixture = _safe_load(root, FIXTURE_PATH, checks, "S14P04-FIXTURE-PARSE")
    artifacts = _check_artifacts(provenance, signing, rollback_policy, fixture, root, checks)
    provenance_ok = artifacts["provenance_ok"]
    snapshot = evaluate_provenance_snapshot({
        "p03_receipt_current": predecessor_ok,
        "provenance_closed": provenance_ok,
        "signing_policy_closed": artifacts["signing_ok"],
        "rollback_policy_closed": artifacts["rollback_ok"],
        "source_trace_closed": provenance_ok,
        "dependency_trace_closed": provenance_ok,
        "build_environment_trace_closed": provenance_ok,
        "attestation_valid": provenance_ok,
        "external_effect_boundary_preserved": EXTERNAL_EFFECT_BOUNDARY == {
            "external_network_accessed": False, "gmail_account_or_api_accessed": False,
            "ovh_or_cloudflare_runtime_accessed": False, "real_account_balance_read_or_written": False,
            "recommendation_generated_or_enabled": False, "order_submitted_confirmed_or_retried": False,
            "production_deployed_or_activated": False, "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        },
        "coverage_score": "1.0000" if all(artifacts[key] for key in ("provenance_ok", "signing_ok", "rollback_ok", "fixture_ok")) else "0.0000",
        "foreign_odds_input_present": False,
    })
    _add(checks, "S14P04-ACTUAL-PROVENANCE-SNAPSHOT-PASS", snapshot["status"] == "S14P04_PROVENANCE_VERIFIED_NO_ACTION", snapshot)
    _check_snapshot_cases(fixture, checks)
    if isinstance(fixture, Mapping):
        _check_reports(root, fixture, checks, require_test_reports=require_test_reports)
    elif require_test_reports:
        _add(checks, "S14P04-TEST-REPORTS-UNAVAILABLE", False, "fixture unavailable")
    try:
        hashes.update(_source_input_hashes(root))
        hashes.update(_expected_artifact_hashes(root))
    except Exception:
        pass
    analysis = {
        "source_input_count": len(SOURCE_INPUT_PATHS) if provenance_ok else 0,
        "dependency_trace_current": provenance_ok,
        "source_trace_current": provenance_ok,
        "build_environment_trace_current": provenance_ok,
        "local_attestation_is_keyed_signature": False,
        "production_artifact_or_host_verified": False,
        "external_network_used": False,
        "external_account_or_runtime_used": False,
    }
    return _result(checks, hashes, snapshot, analysis)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {
            "status": "PASS" if (root / relative).is_file() else "FAIL",
            "sha256": sha256_file(root / relative) if (root / relative).is_file() else "MISSING",
        }
        for relative in (
            PROVENANCE_PATH, SIGNING_PATH, ROLLBACK_POLICY_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH,
            P03_EVIDENCE_PATH, P03_ROLLBACK_PATH,
        )
    }
    return {
        "schema_version": "1.0.0", "evidence_id": "EVD-S14-P04-ROLLBACK", "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S14_P04_LOCAL_RELEASE_CANDIDATE_PRESERVE_P03_AND_SIGNED_EVIDENCE_NO_EXTERNAL_MUTATION",
        "artifacts": artifacts, "external_state_changed": False, "production_state_changed": False,
        "recommendation_generated": False, "order_submission_enabled": False, "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = {
        PROVENANCE_PATH.as_posix(), SIGNING_PATH.as_posix(), ROLLBACK_POLICY_PATH.as_posix(),
        ORACLE_PATH.as_posix(), TEST_PATH.as_posix(), FIXTURE_PATH.as_posix(),
        P03_EVIDENCE_PATH.as_posix(), P03_ROLLBACK_PATH.as_posix(),
    }
    paths.update(SOURCE_INPUT_PATHS)
    paths.update({"pyproject.toml", "uv.lock", DEPENDENCY_BUDGET_PATH.as_posix()})
    if require_test_reports:
        paths.update({JUNIT_PATH.as_posix(), SCAN_REPORT_PATH.as_posix(), PACK_REPORT_PATH.as_posix()})
    return {relative: sha256_file(root / relative) for relative in sorted(paths)}


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = dict(evidence)
    payload.pop("decision_sha256", None)
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0", "evidence_id": "EVD-S14-P04", "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID, "stage_id": STAGE_ID, "phase_id": PHASE_ID, "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK, "status": validation["status"], "decision": validation["decision"], "next": validation["next"],
        "release_status": "S14_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED" if validation["status"] == "PASS" else "S14_P04_REMEDIATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED", "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "deterministic_replay": {
            "source_input_count": len(SOURCE_INPUT_PATHS), "snapshot_case_count": len(SNAPSHOT_CASE_IDS),
            "real_time_wait_performed": False, "external_network_accessed": False,
        },
        "local_attestation_boundary": {
            "keyed_or_identity_signature_created": False, "actual_release_signature_created": False,
            "production_approval_evidence_present": False,
        },
        "structured_failure_evidence": {
            "fixture": FIXTURE_PATH.as_posix(),
            "rejected_case_ids": [case_id for case_id in SNAPSHOT_CASE_IDS if case_id != "PASS"],
            "format": "DETERMINISTIC_JSON_FIXTURE_AND_JUNIT_REPORT",
        },
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "local_attestation": strict_json_load(root / PROVENANCE_PATH)["local_attestation"]["value"],
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "validation": validation,
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback["status"]},
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    path = root / EVIDENCE_INDEX_PATH
    raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
    rows = _strict_jsonl(path)
    replacement = {
        "id": "INDEX-" + CONTRACT_ID, "kind": "PHASE_EVIDENCE", "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID, "requirement_id": REQUIREMENT_ID, "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(), "artifact_sha256": evidence_hash,
        "next": "S14/STAGE_REVIEW_READY_NOT_STARTED", "verified_at": FIXED_CLOCK,
    }
    positions = [number for number, row in enumerate(rows) if row.get("id") == replacement["id"]]
    if len(positions) != 1:
        raise ArtifactProvenanceError("S14/P04 evidence-index row must exist exactly once")
    existing = rows[positions[0]]
    is_current = existing.get("kind") == "PHASE_EVIDENCE" and existing.get("contract_id") == CONTRACT_ID and existing.get("status") == "PASS"
    is_planned = existing.get("kind") == "ACCEPTANCE_EVIDENCE" and existing.get("acceptance_contract_id") == CONTRACT_ID and existing.get("status") == "PLANNED"
    if not (is_current or is_planned):
        raise ArtifactProvenanceError("S14/P04 evidence-index row is not the planned or current phase record")
    output = [
        _jsonl_bytes(replacement) if number == positions[0] else (line + "\n").encode("utf-8")
        for number, line in enumerate(raw_lines)
    ]
    _atomic_write(path, b"".join(output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    if evidence_dir.resolve() != (root / "machine/evidence").resolve():
        raise ArtifactProvenanceError("evidence directory must be canonical machine/evidence")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ArtifactProvenanceError("cannot write evidence for a failed S14/P04 phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S14/STAGE_REVIEW_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    try:
        evidence = strict_json_load(root / EVIDENCE_PATH)
        rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
        index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-" + CONTRACT_ID)
    except Exception as exc:
        raise ArtifactProvenanceError("existing S14/P04 evidence is unavailable") from exc
    validation = evaluate_contract(root, require_test_reports=True)
    valid = (
        isinstance(evidence, Mapping) and isinstance(rollback, Mapping)
        and evidence.get("evidence_id") == "EVD-S14-P04" and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("status") == "PASS"
        and evidence.get("decision") == "LOCAL_PRE_RELEASE_PROVENANCE_COMPLETE_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S14/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY
        and evidence.get("financial_target_status") == "UNVERIFIED_NOT_GUARANTEED"
        and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        and evidence.get("hashes", {}).get("code") == sha256_file(root / ORACLE_PATH)
        and evidence.get("hashes", {}).get("inputs") == _input_hashes(root, require_test_reports=True)
        and evidence.get("hashes", {}).get("local_attestation") == strict_json_load(root / PROVENANCE_PATH)["local_attestation"]["value"]
        and evidence.get("hashes", {}).get("rollback_evidence") == _sha256_bytes(_json_bytes(rollback))
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and rollback.get("status") == "PASS" and rollback.get("external_state_changed") is False
        and rollback.get("production_state_changed") is False and rollback.get("real_time_soak_waited") is False
        and index.get("kind") == "PHASE_EVIDENCE" and index.get("artifact_sha256") == sha256_file(root / EVIDENCE_PATH)
        and index.get("next") == "S14/STAGE_REVIEW_READY_NOT_STARTED" and validation.get("status") == "PASS"
        and validation.get("analysis", {}).get("source_trace_current") is True
        and validation.get("analysis", {}).get("dependency_trace_current") is True
        and validation.get("analysis", {}).get("build_environment_trace_current") is True
    )
    if not valid:
        raise ArtifactProvenanceError("existing S14/P04 evidence does not replay exactly")
    return {
        "contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S14/STAGE_REVIEW_READY_NOT_STARTED",
    }
