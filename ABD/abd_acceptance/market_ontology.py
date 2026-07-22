from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from jsonschema import Draft202012Validator, FormatChecker

from .canonical_facts import sha256_file, strict_json_load
from .stage2_delivery import verify_stage2_delivery
from .stage4_delivery import (
    PINNED_RECEIPT_SHA256 as STAGE4_DELIVERY_RECEIPT_SHA256,
    RECEIPT_PATH as STAGE4_DELIVERY_RECEIPT_PATH,
    verify_stage4_delivery,
)


CONTRACT_ID = "AC-S05-P01"
REQUIREMENT_ID = "REQ-S05-P01"
STAGE_ID = "S05"
PHASE_ID = "P01"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-23T01:02:53+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

ONTOLOGY_PATH = Path("market_ontology.json")
SCHEMA_PATH = Path("coverage_manifest.schema.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S05_P01.json")
TEST_PATH = Path("tests/S05/P01_test.py")
JUNIT_PATH = Path("machine/evidence/S05/P01/pytest.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S05/P01/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P01.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P01_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

STRUCTURAL_SELF_NORMALIZED_SHA256 = "6bbb7d6cdade75bae68b9cd51832363870ab1676738960a8a9779223e210241c"
PHASE_COMMIT = "6ddbf8a36b4b089ab0511bd26f7d0c0fa2662bcc"
PINNED_PHASE_CODE_HASH = "e5ebba41d7a5943b5302cf0d5813a165aae77cb99fc84d8de72c5f358cf9bc1e"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/__init__.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/market_ontology.py",
    "abd_acceptance/stage4_review.py",
    "tests/S04/stage_review_test.py",
    "tests/S05/P01_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "README.md": "ff1c4f4d9146496772a66c527bc7c5aba36cb3bc7ce2bd99700f33b115853d47",
    "abd_acceptance/__init__.py": "a99a38901124e8e9cab0e4b3402ff6d809989e438d9226b6bc30f793336d1af5",
    "abd_acceptance/__main__.py": "cd49b1652dc98a812d03fbbf7cfaaa345e676fbab28132d8263134a6f6ea027e",
    "abd_acceptance/stage4_review.py": "d011f699cd792f4fffd00d81e967e17f35741cc7bcbbb2d241838f40ae6cff35",
    "tests/S04/stage_review_test.py": "5bbdbd6ddfb0bc65358fb14c29eeac6f42d41f7804a8746bb2489b912d7809d5",
    "tests/S05/P01_test.py": "44f2132acd1a9f04ef1b3297300f22e2cbcb86e0db10ec8cf5ca90fa48cab8f7",
}
PINNED_PHASE_HASHES: Dict[str, str] = {
    ONTOLOGY_PATH.as_posix(): "f87d5433a69d7605a63d76200eb0813ded681a23af5eaafc5d7c613d10187efe",
    SCHEMA_PATH.as_posix(): "b87e741b552704f969260cbf31bd2c076d1dce092a208b81cd1b46a94928c3f2",
    FIXTURE_PATH.as_posix(): "bd8dc5ae5616fa4815ecae5dc23a8b86eb2940a817b63cdd54078e5e10f46557",
    TEST_PATH.as_posix(): "b42a0af4c57b70684911403c68df8df5d76ad90f36e041be076ab7660d9a5d6b",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/evidence/S02/STAGE_REVIEW/github_delivery_receipt.json": "80a0a58f98ebea48d7b6ed80d57cef7f1d8410fccb89b25588d74b4a204bc6e4",
    "machine/evidence/EVD-S02-STAGE-REVIEW.json": "7164544cf192a5ce45b093eccc4d310e9fce811900a1cef3b277834e01292569",
    "machine/evidence/EVD-S02-STAGE-REVIEW_rollback.json": "d0f9815ee7c483df7a8d5a3747fe5c5e6c0506062e6be4751580c876a195f867",
    "abd_acceptance/stage2_delivery.py": "d031952a2a1e756a53ca9d572ed4226a572c371ae0850d306de1645468620650",
    STAGE4_DELIVERY_RECEIPT_PATH.as_posix(): STAGE4_DELIVERY_RECEIPT_SHA256,
    "machine/evidence/EVD-S04-STAGE-REVIEW.json": "1dc45c997a4544370e724b9828459ac8ba8e0d3990aec9b380528818a15bf708",
    "machine/evidence/EVD-S04-STAGE-REVIEW_rollback.json": "0cb65c9b4c37a0d20cd98d732bf4d8bc4aab8739080f3604de587ce2a787be79",
    "abd_acceptance/stage4_delivery.py": "1688b6042cb0d4e21c305fef05dfc0dee720abda57106bb9f0a4d5e2b3fca732",
}
PINNED_REPO_HASHES: Dict[str, str] = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

KNOWN_KINDS = (
    "SPORT",
    "COMPETITION",
    "EVENT",
    "PERIOD",
    "MARKET",
    "SELECTION",
    "LINE",
    "SETTLEMENT_RULE",
)
ALL_KINDS = (*KNOWN_KINDS, "UNKNOWN")
UNKNOWN_REASON_CODES = {
    "AMBIGUOUS_TYPE",
    "DUPLICATE_SOURCE_REFERENCE",
    "INVALID_PARENT_RELATION",
    "MALFORMED_IDENTIFIER",
    "MALFORMED_INPUT",
    "MISSING_REQUIRED_RELATION",
    "UNRECOGNIZED_TYPE",
    "UNSUPPORTED_SEMANTICS",
}
OBJECT_ID_RE = re.compile(
    r"^(SPORT|COMPETITION|EVENT|PERIOD|MARKET|SELECTION|LINE|SETTLEMENT_RULE|UNKNOWN):[a-z0-9][a-z0-9._~-]{0,127}$"
)
SOURCE_ID_RE = re.compile(r"^[A-Z][A-Z0-9._-]{2,63}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed_for_market_discovery": False,
    "provider_account_or_page_accessed": False,
    "source_terms_or_capabilities_changed": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "model_or_strategy_executed": False,
    "recommendation_generated": False,
    "order_submitted_or_retried": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
}

ROLLBACK_ARTIFACTS = [
    ONTOLOGY_PATH,
    SCHEMA_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    Path("tests/S05/__init__.py"),
    Path("abd_acceptance/market_ontology.py"),
    Path("abd_acceptance/stage4_delivery.py"),
    STAGE4_DELIVERY_RECEIPT_PATH,
    Path("abd_acceptance/stage4_review.py"),
    Path("tests/S04/stage_review_test.py"),
    Path("abd_acceptance/__main__.py"),
    Path("abd_acceptance/__init__.py"),
    Path("README.md"),
]


class MarketOntologyError(ValueError):
    """Raised when observed objects cannot be represented without silent loss."""


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], check_id: str, passed: bool, detail: Any) -> None:
    checks.append({"id": check_id, "passed": bool(passed), "detail": detail})


def _safe_load(path: Path, checks: List[Dict[str, Any]], check_id: str) -> Any:
    try:
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, check_id, True, path.name)
    return value


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, Mapping):
        return any(_contains_float(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_float(item) for item in value)
    return False


def _current_code_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "abd_acceptance").glob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/market_ontology.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(root: Path, relative: str, expected_sha256: str, verify_git_history: bool) -> bool:
    if relative not in SUCCESSOR_EVOLVABLE_SIGNED_INPUTS:
        return False
    if verify_git_history:
        if not _phase_commit_is_ancestor(root):
            return False
        result = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:ABD/%s" % (PHASE_COMMIT, relative)],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0 and _sha256_bytes(result.stdout) == expected_sha256
    if relative == "abd_acceptance/market_ontology.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return successor not in {None, "TO_BE_FILLED"} and (root / relative).is_file() and sha256_file(root / relative) == successor


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _phase_commit_is_ancestor(root):
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        ["git", "-C", str(root.parent), "ls-tree", "-r", "--name-only", PHASE_COMMIT, "--", "ABD/abd_acceptance"],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(row for row in listing.stdout.splitlines() if row.startswith("ABD/abd_acceptance/") and row.endswith(".py")):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        digest.update(repo_path.removeprefix("ABD/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _load_index(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if not line:
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise MarketOntologyError("evidence index rows must be objects")
        rows.append(value)
    return rows


def _kind_map(ontology: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {
        str(row.get("id")): row
        for row in ontology.get("known_object_kinds", [])
        if isinstance(row, Mapping) and isinstance(row.get("id"), str)
    }


def validate_ontology(ontology: Mapping[str, Any]) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    rows = ontology.get("known_object_kinds", [])
    kind_map = _kind_map(ontology)
    ids = [row.get("id") for row in rows if isinstance(row, Mapping)]
    if ids != list(KNOWN_KINDS) or len(set(ids)) != len(KNOWN_KINDS):
        errors.append({"path": "known_object_kinds", "message": "known kind order/set must be exact and unique"})
    if ontology.get("schema_version") != "1.0.0" or ontology.get("ontology_id") != "ABD-MARKET-ONTOLOGY":
        errors.append({"path": "$", "message": "ontology identity mismatch"})
    if ontology.get("ontology_version") != "0.0.0.1-S05P01":
        errors.append({"path": "ontology_version", "message": "unexpected ontology version"})
    contract = ontology.get("classification_contract", {})
    if contract.get("drop_unclassified_input_allowed") is not False or contract.get("implicit_default_kind_allowed") is not False:
        errors.append({"path": "classification_contract", "message": "silent drop/default must be forbidden"})
    if contract.get("unknown_advice_eligible") is not False:
        errors.append({"path": "classification_contract.unknown_advice_eligible", "message": "unknown must block advice"})
    for kind, row in kind_map.items():
        allowed = row.get("allowed_parent_kinds", [])
        required = row.get("required_parent_counts", {})
        maximum = row.get("maximum_parent_counts", {})
        if len(allowed) != len(set(allowed)) or any(parent not in KNOWN_KINDS for parent in allowed):
            errors.append({"path": "known_object_kinds.%s.allowed_parent_kinds" % kind, "message": "invalid parent set"})
        if any(parent not in allowed or not isinstance(count, int) or count < 0 for parent, count in required.items()):
            errors.append({"path": "known_object_kinds.%s.required_parent_counts" % kind, "message": "invalid required parent counts"})
        if any(parent not in allowed or not isinstance(count, int) or count < required.get(parent, 0) for parent, count in maximum.items()):
            errors.append({"path": "known_object_kinds.%s.maximum_parent_counts" % kind, "message": "invalid maximum parent counts"})
    unknown = ontology.get("unknown_contract", {})
    if set(unknown.get("required_reason_codes", [])) != UNKNOWN_REASON_CODES:
        errors.append({"path": "unknown_contract.required_reason_codes", "message": "unknown reasons mismatch"})
    if unknown.get("routing_action") != "QUARANTINE_AND_SURFACE_COVERAGE_GAP" or unknown.get("advice_eligible") is not False:
        errors.append({"path": "unknown_contract", "message": "unknown routing must fail closed"})
    if ontology.get("line_contract", {}).get("binary_float_allowed") is not False:
        errors.append({"path": "line_contract.binary_float_allowed", "message": "binary float must be forbidden"})
    if ontology.get("settlement_contract", {}).get("implicit_rule_allowed") is not False:
        errors.append({"path": "settlement_contract.implicit_rule_allowed", "message": "implicit settlement rule must be forbidden"})
    claim = ontology.get("claim_boundary", {})
    if not claim or any(value is not False for value in claim.values()):
        errors.append({"path": "claim_boundary", "message": "all P01 runtime/coverage claims must remain false"})
    if _contains_float(ontology):
        errors.append({"path": "$", "message": "binary float found"})
    return errors


def _record_id(source_id: str, source_ref: str) -> str:
    digest = _sha256_bytes((source_id + "\0" + source_ref).encode("utf-8"))
    return "REC-" + digest[:24]


def _unknown_object_id(source_id: str, source_ref: str) -> str:
    digest = _sha256_bytes((source_id + "\0" + source_ref + "\0UNKNOWN").encode("utf-8"))
    return "UNKNOWN:" + digest[:24]


def _source_refs_digest(raw_objects: Sequence[Mapping[str, Any]]) -> str:
    pairs = sorted("%s\0%s" % (row["source_id"], row["source_object_ref"]) for row in raw_objects)
    return _sha256_bytes(("\n".join(pairs) + "\n").encode("utf-8"))


def _validate_raw_identity(raw: Mapping[str, Any]) -> Tuple[str, str, str, str, str]:
    source_id = raw.get("source_id")
    source_ref = raw.get("source_object_ref")
    payload_hash = raw.get("source_payload_sha256")
    observed_at = raw.get("observed_at")
    raw_label = raw.get("raw_type_label")
    if not isinstance(source_id, str) or SOURCE_ID_RE.fullmatch(source_id) is None:
        raise MarketOntologyError("source_id is missing or malformed")
    if not isinstance(source_ref, str) or not source_ref or len(source_ref) > 256 or "\n" in source_ref or "\r" in source_ref:
        raise MarketOntologyError("source_object_ref is missing or malformed")
    if not isinstance(payload_hash, str) or SHA256_RE.fullmatch(payload_hash) is None:
        raise MarketOntologyError("source_payload_sha256 is missing or malformed")
    if not isinstance(observed_at, str) or not observed_at:
        raise MarketOntologyError("observed_at is missing")
    if not isinstance(raw_label, str) or not raw_label or len(raw_label) > 128:
        raise MarketOntologyError("raw_type_label is missing or malformed")
    return source_id, source_ref, payload_hash, observed_at, raw_label


def _unknown_record(raw: Mapping[str, Any], reason: str) -> Dict[str, Any]:
    source_id, source_ref, payload_hash, observed_at, raw_label = _validate_raw_identity(raw)
    if reason not in UNKNOWN_REASON_CODES:
        raise MarketOntologyError("unsupported unknown reason: %s" % reason)
    return {
        "record_id": _record_id(source_id, source_ref),
        "classification_status": "UNKNOWN",
        "object_kind": "UNKNOWN",
        "object_id": _unknown_object_id(source_id, source_ref),
        "source_id": source_id,
        "source_object_ref": source_ref,
        "source_payload_sha256": payload_hash,
        "observed_at": observed_at,
        "parent_refs": [],
        "advice_eligible": False,
        "unknown_reason_code": reason,
        "raw_type_label": raw_label,
        "routing_action": "QUARANTINE_AND_SURFACE_COVERAGE_GAP",
    }


def classify_discovery_object(raw: Mapping[str, Any], ontology: Mapping[str, Any]) -> Dict[str, Any]:
    source_id, source_ref, payload_hash, observed_at, _ = _validate_raw_identity(raw)
    known = set(_kind_map(ontology))
    candidates = raw.get("candidate_kinds")
    if not isinstance(candidates, list) or not candidates:
        return _unknown_record(raw, "UNRECOGNIZED_TYPE")
    if len(candidates) != 1 or len(set(str(item) for item in candidates)) != 1:
        return _unknown_record(raw, "AMBIGUOUS_TYPE")
    kind = candidates[0]
    if not isinstance(kind, str) or kind not in known:
        return _unknown_record(raw, "UNRECOGNIZED_TYPE")
    object_id = raw.get("proposed_object_id")
    if not isinstance(object_id, str) or OBJECT_ID_RE.fullmatch(object_id) is None or not object_id.startswith(kind + ":"):
        return _unknown_record(raw, "MALFORMED_IDENTIFIER")
    return {
        "record_id": _record_id(source_id, source_ref),
        "classification_status": "KNOWN",
        "object_kind": kind,
        "object_id": object_id,
        "source_id": source_id,
        "source_object_ref": source_ref,
        "source_payload_sha256": payload_hash,
        "observed_at": observed_at,
        "parent_refs": [],
        "advice_eligible": False,
    }


def _parent_policy_error(record: Mapping[str, Any], records_by_ref: Mapping[Tuple[str, str], Mapping[str, Any]], raw: Mapping[str, Any], ontology: Mapping[str, Any]) -> str | None:
    if record.get("classification_status") != "KNOWN":
        return None
    kind = str(record.get("object_kind"))
    policy = _kind_map(ontology).get(kind, {})
    parent_refs = raw.get("parent_source_refs")
    if not isinstance(parent_refs, list) or any(not isinstance(item, str) or not item for item in parent_refs):
        return "MISSING_REQUIRED_RELATION"
    resolved: List[Mapping[str, Any]] = []
    for source_ref in parent_refs:
        parent = records_by_ref.get((str(record.get("source_id")), source_ref))
        if parent is None or parent.get("classification_status") != "KNOWN":
            return "MISSING_REQUIRED_RELATION"
        resolved.append(parent)
    parent_kinds = Counter(str(parent.get("object_kind")) for parent in resolved)
    allowed = set(policy.get("allowed_parent_kinds", []))
    if any(parent_kind not in allowed for parent_kind in parent_kinds):
        return "INVALID_PARENT_RELATION"
    for parent_kind, required in policy.get("required_parent_counts", {}).items():
        if parent_kinds.get(parent_kind, 0) != required:
            return "MISSING_REQUIRED_RELATION"
    for parent_kind, maximum in policy.get("maximum_parent_counts", {}).items():
        if parent_kinds.get(parent_kind, 0) > maximum:
            return "INVALID_PARENT_RELATION"
    if sum(parent_kinds.values()) != len(parent_refs) or len(parent_refs) != len(set(parent_refs)):
        return "INVALID_PARENT_RELATION"
    return None


def build_coverage_manifest(
    raw_objects: Sequence[Mapping[str, Any]],
    ontology: Mapping[str, Any],
    *,
    generated_at: str = FIXED_CLOCK,
    input_mode: str = "FROZEN_SYNTHETIC_FIXTURE",
) -> Dict[str, Any]:
    if validate_ontology(ontology):
        raise MarketOntologyError("ontology is invalid")
    if not isinstance(raw_objects, Sequence) or isinstance(raw_objects, (str, bytes, bytearray)) or not raw_objects:
        raise MarketOntologyError("at least one observed object is required")
    materialized = [dict(row) if isinstance(row, Mapping) else None for row in raw_objects]
    if any(row is None for row in materialized):
        raise MarketOntologyError("every observed object must be a mapping")
    typed_rows: List[Dict[str, Any]] = [classify_discovery_object(row, ontology) for row in materialized if row is not None]
    keys = [(row["source_id"], row["source_object_ref"]) for row in typed_rows]
    if len(keys) != len(set(keys)):
        raise MarketOntologyError("duplicate source object reference")
    records_by_ref: Dict[Tuple[str, str], Dict[str, Any]] = {key: row for key, row in zip(keys, typed_rows)}
    raw_by_ref: Dict[Tuple[str, str], Mapping[str, Any]] = {key: raw for key, raw in zip(keys, materialized) if raw is not None}

    changed = True
    while changed:
        changed = False
        for key in sorted(records_by_ref):
            record = records_by_ref[key]
            raw = raw_by_ref[key]
            reason = _parent_policy_error(record, records_by_ref, raw, ontology)
            if reason is not None:
                records_by_ref[key] = _unknown_record(raw, reason)
                changed = True

    known_object_ids = [
        str(record["object_id"])
        for record in records_by_ref.values()
        if record["classification_status"] == "KNOWN"
    ]
    if len(known_object_ids) != len(set(known_object_ids)):
        raise MarketOntologyError("duplicate proposed object_id")

    for key, record in records_by_ref.items():
        if record["classification_status"] != "KNOWN":
            continue
        raw = raw_by_ref[key]
        parent_ids = [records_by_ref[(record["source_id"], source_ref)]["object_id"] for source_ref in raw.get("parent_source_refs", [])]
        record["parent_refs"] = sorted(parent_ids)

    records = sorted(records_by_ref.values(), key=lambda row: (row["source_id"], row["source_object_ref"]))
    counts = Counter(str(row["object_kind"]) for row in records)
    counts_by_kind = {kind: counts.get(kind, 0) for kind in ALL_KINDS}
    input_digest = _source_refs_digest([row for row in materialized if row is not None])
    manifest_id = "COV-" + _sha256_bytes((input_digest + "\0" + generated_at + "\0" + input_mode).encode("utf-8"))[:24].upper()
    return {
        "schema_version": "1.0.0",
        "manifest_id": manifest_id,
        "ontology_id": ontology["ontology_id"],
        "ontology_version": ontology["ontology_version"],
        "generated_at": generated_at,
        "input_mode": input_mode,
        "declared_discovery_scope": "ALL_OBSERVABLE_MARKETS",
        "input_set": {
            "observed_object_count": len(materialized),
            "source_object_refs_sha256": input_digest,
        },
        "records": records,
        "summary": {
            "total_records": len(records),
            "known_count": len(records) - counts_by_kind["UNKNOWN"],
            "unknown_count": counts_by_kind["UNKNOWN"],
            "counts_by_kind": counts_by_kind,
        },
        "manifest_status": "COMPLETE_FOR_OBSERVED_INPUT",
        "claim_boundary": {
            "all_observable_markets_verified": False,
            "cross_source_identity_resolved": False,
            "source_capabilities_verified": False,
            "market_data_freshness_verified": False,
            "recommendation_or_order_enabled": False,
        },
    }


def safe_build_coverage_manifest(raw_objects: Sequence[Mapping[str, Any]], ontology: Mapping[str, Any]) -> Dict[str, Any]:
    try:
        manifest = build_coverage_manifest(raw_objects, ontology)
        return {"status": "PASS", "manifest": manifest, "error": None}
    except Exception as exc:
        return {
            "status": "BLOCKED_INVALID_INPUT",
            "manifest": None,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def validate_coverage_manifest(schema: Mapping[str, Any], ontology: Mapping[str, Any], manifest: Mapping[str, Any]) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for error in sorted(validator.iter_errors(manifest), key=lambda item: list(item.absolute_path)):
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        errors.append({"path": path, "message": error.message})
    if errors:
        return errors
    records = list(manifest.get("records", []))
    object_ids = [row.get("object_id") for row in records]
    record_ids = [row.get("record_id") for row in records]
    source_keys = [(row.get("source_id"), row.get("source_object_ref")) for row in records]
    for label, values in [("object_id", object_ids), ("record_id", record_ids), ("source_object_ref", source_keys)]:
        if len(values) != len(set(values)):
            errors.append({"path": "records", "message": "%s values must be unique" % label})
    by_id = {str(row.get("object_id")): row for row in records}
    kind_map = _kind_map(ontology)
    for index, row in enumerate(records):
        kind = str(row.get("object_kind"))
        object_id = str(row.get("object_id"))
        if not object_id.startswith(kind + ":"):
            errors.append({"path": "records.%d.object_id" % index, "message": "object id prefix does not match kind"})
        if kind == "UNKNOWN":
            if row.get("parent_refs") != [] or row.get("advice_eligible") is not False:
                errors.append({"path": "records.%d" % index, "message": "unknown record must be parentless and advice-ineligible"})
            continue
        parents = [by_id.get(str(parent_id)) for parent_id in row.get("parent_refs", [])]
        if any(parent is None or parent.get("object_kind") == "UNKNOWN" for parent in parents):
            errors.append({"path": "records.%d.parent_refs" % index, "message": "all parents must resolve to known records"})
            continue
        counts = Counter(str(parent.get("object_kind")) for parent in parents if parent is not None)
        policy = kind_map.get(kind, {})
        allowed = set(policy.get("allowed_parent_kinds", []))
        if any(parent_kind not in allowed for parent_kind in counts):
            errors.append({"path": "records.%d.parent_refs" % index, "message": "parent kind is not allowed"})
        for parent_kind, required in policy.get("required_parent_counts", {}).items():
            if counts.get(parent_kind, 0) != required:
                errors.append({"path": "records.%d.parent_refs" % index, "message": "required parent count mismatch for %s" % parent_kind})
        for parent_kind, maximum in policy.get("maximum_parent_counts", {}).items():
            if counts.get(parent_kind, 0) > maximum:
                errors.append({"path": "records.%d.parent_refs" % index, "message": "maximum parent count exceeded for %s" % parent_kind})

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(object_id: str) -> bool:
        if object_id in visiting:
            return False
        if object_id in visited:
            return True
        visiting.add(object_id)
        record = by_id.get(object_id, {})
        if any(not visit(str(parent_id)) for parent_id in record.get("parent_refs", [])):
            return False
        visiting.remove(object_id)
        visited.add(object_id)
        return True

    if any(not visit(object_id) for object_id in list(by_id)):
        errors.append({"path": "records", "message": "parent graph must be acyclic"})

    markets = [row for row in records if row.get("object_kind") == "MARKET"]
    for market in markets:
        market_id = market.get("object_id")
        selections = [row for row in records if row.get("object_kind") == "SELECTION" and market_id in row.get("parent_refs", [])]
        rules = [row for row in records if row.get("object_kind") == "SETTLEMENT_RULE" and market_id in row.get("parent_refs", [])]
        if not selections:
            errors.append({"path": "records", "message": "each market requires at least one selection"})
        if len(rules) != 1:
            errors.append({"path": "records", "message": "each market requires exactly one settlement rule"})

    actual_counts = Counter(str(row.get("object_kind")) for row in records)
    expected_summary = {
        "total_records": len(records),
        "known_count": len(records) - actual_counts.get("UNKNOWN", 0),
        "unknown_count": actual_counts.get("UNKNOWN", 0),
        "counts_by_kind": {kind: actual_counts.get(kind, 0) for kind in ALL_KINDS},
    }
    if manifest.get("summary") != expected_summary:
        errors.append({"path": "summary", "message": "summary does not match records"})
    input_set = manifest.get("input_set", {})
    if input_set.get("observed_object_count") != len(records):
        errors.append({"path": "input_set.observed_object_count", "message": "every observed input must produce exactly one record"})
    digest_rows = [
        {"source_id": row.get("source_id"), "source_object_ref": row.get("source_object_ref")}
        for row in records
    ]
    if input_set.get("source_object_refs_sha256") != _source_refs_digest(digest_rows):
        errors.append({"path": "input_set.source_object_refs_sha256", "message": "input reference digest mismatch"})
    if manifest.get("manifest_status") != "COMPLETE_FOR_OBSERVED_INPUT":
        errors.append({"path": "manifest_status", "message": "positive manifest must be complete for observed input"})
    if any(value is not False for value in manifest.get("claim_boundary", {}).values()):
        errors.append({"path": "claim_boundary", "message": "P01 cannot claim runtime coverage, identity, freshness, advice or order"})
    if _contains_float(manifest):
        errors.append({"path": "$", "message": "binary float found"})
    return errors


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in PINNED_PHASE_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(checks, "S05P01-PIN-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor), {"expected": expected, "successor": successor, "actual": actual})
    structural = _structural_self_hash(root)
    hashes["abd_acceptance/market_ontology.py"] = sha256_file(root / "abd_acceptance/market_ontology.py")
    _add(checks, "S05P01-ORACLE-SELF-INTEGRITY", structural == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": structural})
    for relative, expected in PINNED_BASELINE_HASHES.items():
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S05P01-BASELINE-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in PINNED_REPO_HASHES.items():
        path = root.parent / relative
        actual = sha256_file(path) if path.is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S05P01-REPO-%s" % relative.upper().replace("/", "-").replace(".", "-"), actual == expected, {"expected": expected, "actual": actual})


def _row(rows: Sequence[Mapping[str, Any]], item_id: str, key: str = "id") -> Mapping[str, Any]:
    found = [row for row in rows if row.get(key) == item_id]
    return found[0] if len(found) == 1 else {}


def _check_taskpack_trace(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = strict_json_load(root / "machine/facts/requirements.json")
    acceptance = strict_json_load(root / "machine/facts/acceptance_contracts.json")
    tasks = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    traces = strict_json_load(root / "machine/facts/traceability_matrix.json")
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    req = _row(requirements, REQUIREMENT_ID)
    ac = _row(acceptance, CONTRACT_ID)
    phase_tasks = [row for row in tasks if row.get("stage_id") == STAGE_ID and row.get("phase_id") == PHASE_ID]
    trace = _row(traces, REQUIREMENT_ID, "requirement_id")
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID]
    expected_tasks = ["T-S05-P01-01", "T-S05-P01-02", "T-S05-P01-03"]
    expected_tests = ["TEST-S05-P01", "TEST-S05-P01-BOUNDARY", "TEST-S05-P01-REPLAY"]
    ok = (
        req.get("stage_id") == STAGE_ID
        and req.get("phase_id") == PHASE_ID
        and req.get("scope") == [ONTOLOGY_PATH.as_posix(), SCHEMA_PATH.as_posix()]
        and req.get("target") == "所有发现对象都有唯一类型或明确未知状态。"
        and ac.get("requirement_id") == REQUIREMENT_ID
        and ac.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S05-P01 --evidence machine/evidence"
        and [row.get("id") for row in ac.get("tests", [])] == expected_tests
        and [row.get("id") for row in phase_tasks] == expected_tasks
        and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in phase_tasks)
        and trace.get("acceptance_criteria_id") == CONTRACT_ID
        and trace.get("task_ids") == expected_tasks
        and trace.get("test_ids") == expected_tests
        and trace.get("evidence_id") == "EVD-S05-P01"
        and len(stages) == 1
        and stages[0].get("depends_on") == ["S02", "S04"]
        and stages[0].get("phases", [])[0].get("outputs") == [ONTOLOGY_PATH.as_posix(), SCHEMA_PATH.as_posix()]
    )
    _add(checks, "S05P01-TASKPACK-TRACE-EXACT", ok, {"requirement": req.get("id"), "contract": ac.get("id"), "tasks": expected_tasks})


def _check_ontology_schema_fixture(ontology: Mapping[str, Any], schema: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    ontology_errors = validate_ontology(ontology)
    _add(checks, "S05P01-ONTOLOGY-VALID", not ontology_errors, ontology_errors or "valid")
    try:
        Draft202012Validator.check_schema(schema)
        _add(checks, "S05P01-COVERAGE-SCHEMA-META-VALID", True, schema.get("$id"))
    except Exception as exc:
        _add(checks, "S05P01-COVERAGE-SCHEMA-META-VALID", False, "%s: %s" % (type(exc).__name__, exc))
    fixture_shape = (
        fixture.get("schema_version") == "1.0.0"
        and fixture.get("fixture_id") == "FIX-S05-P01"
        and fixture.get("contract_id") == CONTRACT_ID
        and fixture.get("requirement_id") == REQUIREMENT_ID
        and fixture.get("fixed_clock") == FIXED_CLOCK
        and fixture.get("expected_known_kinds") == list(KNOWN_KINDS)
        and fixture.get("allowed_numeric_boundary_deltas") == ["-0.0001", "0", "0.0001"]
        and fixture.get("adverse_odds_tick_action") == "NOT_APPLICABLE_NO_ODDS_OR_ACTION_DECISION_IN_S05_P01"
        and not _contains_float(fixture)
    )
    _add(checks, "S05P01-FIXTURE-SHAPE", fixture_shape, fixture.get("fixture_id"))
    try:
        manifest = build_coverage_manifest(fixture.get("raw_discovery_objects", []), ontology)
    except Exception as exc:
        _add(checks, "S05P01-FROZEN-MANIFEST-BUILD", False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, "S05P01-FROZEN-MANIFEST-BUILD", True, manifest.get("manifest_id"))
    errors = validate_coverage_manifest(schema, ontology, manifest)
    _add(checks, "S05P01-FROZEN-MANIFEST-VALID", not errors, errors or "valid")
    _add(checks, "S05P01-FROZEN-MANIFEST-SUMMARY", manifest.get("summary") == fixture.get("expected_summary"), manifest.get("summary"))
    unknowns = [row for row in manifest.get("records", []) if row.get("object_kind") == "UNKNOWN"]
    unknown_ok = (
        len(unknowns) == 1
        and unknowns[0].get("unknown_reason_code") == fixture.get("expected_unknown_reason_code")
        and unknowns[0].get("routing_action") == "QUARANTINE_AND_SURFACE_COVERAGE_GAP"
        and unknowns[0].get("advice_eligible") is False
        and unknowns[0].get("parent_refs") == []
    )
    _add(checks, "S05P01-EXPLICIT-UNKNOWN-FAIL-CLOSED", unknown_ok, unknowns)
    _add(checks, "S05P01-CLAIM-BOUNDARY", manifest.get("claim_boundary") == fixture.get("expected_claim_boundary"), manifest.get("claim_boundary"))
    _add(checks, "S05P01-DETERMINISTIC-REPLAY", manifest == build_coverage_manifest(deepcopy(fixture.get("raw_discovery_objects", [])), ontology), manifest.get("manifest_id"))
    return manifest


def _check_negative_and_fault_paths(ontology: Mapping[str, Any], schema: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    raw_rows = fixture.get("raw_discovery_objects", [])
    for reason, mutation in [
        ("AMBIGUOUS_TYPE", ["SPORT", "EVENT"]),
        ("UNRECOGNIZED_TYPE", ["SOURCE_PRIVATE_KIND"]),
    ]:
        candidate = deepcopy(raw_rows[0])
        candidate["candidate_kinds"] = mutation
        record = classify_discovery_object(candidate, ontology)
        _add(checks, "S05P01-CLASSIFY-%s" % reason, record.get("object_kind") == "UNKNOWN" and record.get("unknown_reason_code") == reason and record.get("advice_eligible") is False, record)
    malformed = deepcopy(raw_rows[0])
    malformed["proposed_object_id"] = "EVENT:wrong-prefix"
    malformed_record = classify_discovery_object(malformed, ontology)
    _add(checks, "S05P01-CLASSIFY-MALFORMED-IDENTIFIER", malformed_record.get("unknown_reason_code") == "MALFORMED_IDENTIFIER", malformed_record)
    missing_parent = deepcopy(raw_rows)
    missing_parent[4]["parent_source_refs"] = ["event/1", "period/missing"]
    missing_manifest = build_coverage_manifest(missing_parent, ontology)
    missing_market = next(row for row in missing_manifest["records"] if row["source_object_ref"] == "market/1")
    _add(checks, "S05P01-MISSING-PARENT-BECOMES-UNKNOWN", missing_market.get("unknown_reason_code") == "MISSING_REQUIRED_RELATION" and missing_market.get("advice_eligible") is False, missing_market)
    wrong_parent = deepcopy(raw_rows)
    wrong_parent[5]["parent_source_refs"] = ["event/1"]
    wrong_manifest = build_coverage_manifest(wrong_parent, ontology)
    wrong_selection = next(row for row in wrong_manifest["records"] if row["source_object_ref"] == "selection/1")
    _add(checks, "S05P01-WRONG-PARENT-BECOMES-UNKNOWN", wrong_selection.get("unknown_reason_code") == "INVALID_PARENT_RELATION", wrong_selection)
    duplicate = deepcopy(raw_rows)
    duplicate.append(deepcopy(raw_rows[0]))
    blocked = safe_build_coverage_manifest(duplicate, ontology)
    _add(checks, "S05P01-DUPLICATE-SOURCE-REF-BLOCKED", blocked.get("status") == "BLOCKED_INVALID_INPUT" and blocked.get("manifest") is None, blocked)
    malformed_raw = deepcopy(raw_rows)
    malformed_raw[0].pop("source_payload_sha256")
    blocked = safe_build_coverage_manifest(malformed_raw, ontology)
    _add(checks, "S05P01-MALFORMED-RAW-BLOCKED", blocked.get("status") == "BLOCKED_INVALID_INPUT" and blocked.get("manifest") is None, blocked)
    valid = build_coverage_manifest(raw_rows, ontology)
    missing_record = deepcopy(valid)
    missing_record["records"] = missing_record["records"][:-1]
    errors = validate_coverage_manifest(schema, ontology, missing_record)
    _add(checks, "S05P01-SILENT-DROP-DETECTED", any("every observed input" in row["message"] or "summary" in row["path"] for row in errors), errors)
    enabled = deepcopy(valid)
    enabled["claim_boundary"]["recommendation_or_order_enabled"] = True
    errors = validate_coverage_manifest(schema, ontology, enabled)
    _add(checks, "S05P01-ADVICE-CLAIM-FAILS-CLOSED", bool(errors), errors)


def _check_numeric_stability(ontology: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    baseline = build_coverage_manifest(fixture.get("raw_discovery_objects", []), ontology)
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        candidate = deepcopy(fixture.get("raw_discovery_objects", []))
        for row in candidate:
            row["numeric_probe"] = delta
            row["adverse_odds_tick"] = True
        replay = build_coverage_manifest(candidate, ontology)
        same_actions = [row["classification_status"] for row in replay["records"]] == [row["classification_status"] for row in baseline["records"]]
        same_kinds = [row["object_kind"] for row in replay["records"]] == [row["object_kind"] for row in baseline["records"]]
        _add(checks, "S05P01-NUMERIC-STABILITY-%s" % delta.replace("-", "NEG").replace(".", "_"), same_actions and same_kinds, {"delta": delta, "adverse_odds_tick": "NOT_APPLICABLE", "actions_stable": same_actions})


def _check_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("provider_contracts.json"),
        Path("source_capabilities.json"),
        Path("tests/S05/P02_test.py"),
        Path("machine/tests/fixtures/S05_P02.json"),
        Path("abd_acceptance/source_capabilities.py"),
    ]
    signed_paths = [Path("machine/evidence/EVD-S05-P02.json"), Path("machine/evidence/EVD-S05-P02_rollback.json")]
    candidate_present = [path.as_posix() for path in candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in signed_paths if (root / path).exists()]
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P02"]

    def planned(row: Mapping[str, Any]) -> bool:
        return row.get("status") == "PLANNED" and "actual_artifact" not in row and "artifact_sha256" not in row

    successor: Dict[str, Any] = {}
    mode = "INVALID_PARTIAL_S05_P02"
    if not candidate_present and not signed_present and len(rows) == 1 and planned(rows[0]):
        ok = True
        mode = "S05_P02_NOT_STARTED"
    elif len(candidate_present) == len(candidate_paths) and not signed_present and len(rows) == 1 and planned(rows[0]):
        try:
            from .source_capabilities import validate_candidate_preflight as validate_s05_p02_candidate

            successor = validate_s05_p02_candidate(root)
            ok = successor.get("status") == "PASS" and successor.get("next") == "S05/P03_READY_NOT_STARTED"
            mode = "VERIFIED_S05_P02_CANDIDATE" if ok else "INVALID_S05_P02_CANDIDATE"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif (
        len(candidate_present) == len(candidate_paths)
        and len(signed_present) == len(signed_paths)
        and len(rows) == 1
        and rows[0].get("status") == "PASS"
        and rows[0].get("actual_artifact") == "machine/evidence/EVD-S05-P02.json"
        and isinstance(rows[0].get("artifact_sha256"), str)
    ):
        try:
            from .source_capabilities import validate_signed_receipt_preflight as validate_s05_p02_signed

            successor = validate_s05_p02_signed(root)
            ok = successor.get("status") == "PASS" and successor.get("next") == "S05/P03_READY_NOT_STARTED"
            mode = "VERIFIED_S05_P02_SIGNED" if ok else "INVALID_S05_P02_SIGNED"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        ok = False
    _add(checks, "S05P01-P02-PROGRESSION", ok, {"mode": mode, "candidate_present": candidate_present, "signed_present": signed_present, "index": rows, "successor_summary": successor.get("summary") if isinstance(successor, Mapping) else successor})


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for check_id, relative, minimum in [
        ("S05P01-TARGETED-PYTEST", JUNIT_PATH, int(fixture.get("minimum_targeted_pytest_cases", 0))),
        ("S05P01-FULL-REGRESSION", FULL_JUNIT_PATH, int(fixture.get("minimum_full_pytest_cases", 0))),
    ]:
        try:
            summary = _junit_summary(root / relative)
            ok = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, check_id, ok, summary)
            hashes[relative.as_posix()] = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary", {})
        ok = report.get("status") == "PASS" and summary.get("checks") == 49 and summary.get("passed") == 49 and summary.get("failed") == 0
        _add(checks, "S05P01-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S05P01-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {
            "STATUS: PASS",
            "MAX_INCREMENTAL_CASH_AUD: 0.00",
            "PAID_OR_UNKNOWN_DEPENDENCIES: 0",
            "EXTERNAL_NETWORK_ACCESS_PERFORMED: false",
            "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false",
        }
        _add(checks, "S05P01-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S05P01-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    ontology = _safe_load(root / ONTOLOGY_PATH, checks, "S05P01-ONTOLOGY-STRICT-JSON")
    schema = _safe_load(root / SCHEMA_PATH, checks, "S05P01-SCHEMA-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S05P01-FIXTURE-STRICT-JSON")
    _check_pins(root, checks, hashes)
    if isinstance(ontology, Mapping) and isinstance(schema, Mapping) and isinstance(fixture, Mapping):
        try:
            _check_taskpack_trace(root, checks)
            _check_ontology_schema_fixture(ontology, schema, fixture, checks)
            _check_negative_and_fault_paths(ontology, schema, fixture, checks)
            _check_numeric_stability(ontology, fixture, checks)
            _check_progression(root, checks)
        except Exception as exc:
            _add(checks, "S05P01-CANDIDATE-PREFLIGHT", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S05P01-CANDIDATE-INPUTS-AVAILABLE", False, "ontology, schema or fixture unavailable")
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_P01_CANDIDATE_VALID" if not failed else "S05_P01_CANDIDATE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "next": "S05/P02_READY_NOT_STARTED" if not failed else "S05/P01_REMEDIATION_REQUIRED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    preflight = validate_candidate_preflight(root)
    checks = list(preflight.get("checks", []))
    hashes = dict(preflight.get("hashes", {}))
    try:
        s02 = verify_stage2_delivery(root, verify_git_history=_verify_git_history)
        _add(checks, "S05P01-S02-DELIVERY-PREREQUISITE", s02.get("status") == "PASS" and s02.get("decision") == "S02_DELIVERED_S03_MAY_START", s02.get("summary"))
    except Exception as exc:
        _add(checks, "S05P01-S02-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        s04 = verify_stage4_delivery(root, verify_git_history=_verify_git_history)
        _add(checks, "S05P01-S04-DELIVERY-PREREQUISITE", s04.get("status") == "PASS" and s04.get("decision") == "S04_DELIVERED_S05_MAY_START" and s04.get("next") == "S05/P01_READY_NOT_STARTED", s04.get("summary"))
    except Exception as exc:
        _add(checks, "S05P01-S04-DELIVERY-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    safety = (
        canonical.get("product", {}).get("initial_bankroll_aud") == "300.00"
        and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00"
        and canonical.get("scope", {}).get("discovery_scope") == "ALL_OBSERVABLE_MARKETS"
        and canonical.get("scope", {}).get("order_submission_module_present") is False
        and parameters.get("target_30pct", {}).get("guaranteed") is False
        and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION"
        and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
    )
    _add(checks, "S05P01-A300-A0-NO-ORDER-NO-GUARANTEE", safety, {"product": canonical.get("product"), "scope": canonical.get("scope")})
    if require_external_reports:
        fixture = strict_json_load(root / FIXTURE_PATH)
        _check_external_reports(root, fixture, checks, hashes)
    minimum = int(strict_json_load(root / FIXTURE_PATH).get("expected_oracle_check_minimum", 0))
    if len(checks) < minimum:
        _add(checks, "S05P01-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    ids = [row["id"] for row in checks]
    if len(ids) != len(set(ids)):
        _add(checks, "S05P01-CHECK-IDS-UNIQUE", False, "duplicate check ids")
    failed = [row["id"] for row in checks if not row["passed"]]
    status = "PASS" if not failed else "FAIL"
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "MARKET_ONTOLOGY_AND_COVERAGE_SCHEMA_FROZEN" if status == "PASS" else "MARKET_ONTOLOGY_BLOCKED_FAIL_CLOSED",
        "phase_status": "S05_P01_PASS" if status == "PASS" else "S05_P01_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "NOT_READY_S05_P02_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "next": "S05/P02_READY_NOT_STARTED" if status == "PASS" else "S05/P01_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s05-p01-rollback-") as directory:
        temporary = Path(directory)
        for index, relative in enumerate(ROLLBACK_ARTIFACTS):
            source = root / relative
            expected = sha256_file(source)
            signed = temporary / ("signed-%02d" % index)
            active = temporary / ("active-%02d" % index)
            shutil.copyfile(str(source), str(signed))
            shutil.copyfile(str(signed), str(active))
            active.write_bytes(active.read_bytes() + b"\nCORRUPTED")
            corrupted = sha256_file(active)
            shutil.copyfile(str(signed), str(active))
            restored = sha256_file(active)
            results[relative.as_posix()] = {
                "status": "PASS" if corrupted != expected and restored == expected else "FAIL",
                "signed_sha256": expected,
                "corrupted_sha256": corrupted,
                "restored_sha256": restored,
            }
    status = "PASS" if len(results) == len(ROLLBACK_ARTIFACTS) and all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P01-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_PHASE_ARTIFACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
        "provider_or_market_accessed": False,
        "recommendation_or_order_generated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = sorted({
        *PINNED_PHASE_HASHES,
        *PINNED_BASELINE_HASHES,
        "abd_acceptance/market_ontology.py",
        "abd_acceptance/__main__.py",
        "abd_acceptance/__init__.py",
        "abd_acceptance/stage4_review.py",
        "tests/S04/stage_review_test.py",
        "README.md",
    })
    result = {relative: sha256_file(root / relative) for relative in paths}
    for relative in PINNED_REPO_HASHES:
        result[relative] = sha256_file(root.parent / relative)
    return result


def build_evidence(root: Path, require_external_reports: bool = True, *, _verify_git_history: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports, _verify_git_history=_verify_git_history)
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {
            "schema_version": "1.0.0",
            "evidence_id": "EVD-S05-P01-ROLLBACK",
            "contract_id": CONTRACT_ID,
            "fixed_clock": FIXED_CLOCK,
            "status": "FAIL",
            "error": "%s: %s" % (type(exc).__name__, exc),
            "production_state_changed": False,
            "external_state_changed": False,
            "provider_or_market_accessed": False,
            "recommendation_or_order_generated": False,
            "incremental_cash_spent_aud": "0.00",
        }
    if rollback.get("status") != "PASS":
        validation = deepcopy(validation)
        validation["status"] = "FAIL"
        validation["decision"] = "MARKET_ONTOLOGY_BLOCKED_FAIL_CLOSED"
        validation["phase_status"] = "S05_P01_FAIL"
        validation["next"] = "S05/P01_REMEDIATION_REQUIRED"
    ontology = strict_json_load(root / ONTOLOGY_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    manifest = build_coverage_manifest(fixture["raw_discovery_objects"], ontology)
    inputs = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P01",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "phase_status": validation["phase_status"],
        "artifacts": [ONTOLOGY_PATH.as_posix(), SCHEMA_PATH.as_posix()],
        "validation": validation,
        "frozen_manifest_proof": {
            "manifest_id": manifest["manifest_id"],
            "manifest_sha256": _sha256_bytes(_json_bytes(manifest)),
            "summary": manifest["summary"],
            "all_observed_inputs_represented": manifest["input_set"]["observed_object_count"] == manifest["summary"]["total_records"],
            "unknown_is_explicit_and_advice_ineligible": all(row["advice_eligible"] is False for row in manifest["records"] if row["object_kind"] == "UNKNOWN"),
        },
        "prerequisite_delivery": {
            "s02_status": "VERIFIED_MERGED_AND_MAIN_CI_PASS",
            "s04_status": "VERIFIED_MERGED_AND_MAIN_CI_PASS",
            "s04_receipt": STAGE4_DELIVERY_RECEIPT_PATH.as_posix(),
            "s04_receipt_sha256": STAGE4_DELIVERY_RECEIPT_SHA256,
        },
        "scope_boundary": {
            "p01_defines_types_and_manifest_schema_only": True,
            "actual_market_universe_enumerated_or_verified": False,
            "cross_source_identity_resolution_not_started": True,
            "p02_source_capability_contract_not_started": True,
            "p03_scheduler_not_started": True,
            "p04_silent_gap_oracle_not_started": True,
            "fixture_is_synthetic_and_not_market_evidence": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": inputs["machine/facts/parameters.json"],
            "model": inputs["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S05/P01 classifies frozen synthetic discovery objects and validates an offline schema; it accesses no provider, account, market, host, model, recommendation, order or return.",
            "code": _current_code_hash(root),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S05/P01_test.py --junitxml=machine/evidence/S05/P01/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P01/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P01/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P01 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "NOT_READY_S05_P02_TO_S19_AND_RUNTIME_VALIDATION_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "next": validation["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S05-P01"]
    if len(matching) != 1:
        raise MarketOntologyError("expected exactly one INDEX-AC-S05-P01 row")
    matching[0].update({
        "status": status,
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "verified_at": FIXED_CLOCK,
        "next": "S05/P02_READY_NOT_STARTED" if status == "PASS" else "S05/P01_REMEDIATION_REQUIRED",
    })
    payload = b"".join((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8") for row in rows)
    _atomic_write(root / EVIDENCE_INDEX_PATH, payload)


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise MarketOntologyError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {
        "contract_id": CONTRACT_ID,
        "status": evidence["status"],
        "evidence_path": evidence_path.relative_to(root).as_posix(),
        "evidence_sha256": evidence_hash,
        "next": evidence["next"],
    }


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def validate_signed_receipt_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    candidate = validate_candidate_preflight(root)
    _add(checks, "S05P01-SIGNED-CANDIDATE", candidate.get("status") == "PASS", candidate.get("summary"))
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S05P01-SIGNED-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S05P01-SIGNED-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = (
            evidence.get("schema_version") == "1.0.0"
            and evidence.get("evidence_id") == "EVD-S05-P01"
            and evidence.get("contract_id") == CONTRACT_ID
            and evidence.get("requirement_id") == REQUIREMENT_ID
            and evidence.get("stage_id") == STAGE_ID
            and evidence.get("phase_id") == PHASE_ID
            and evidence.get("fixed_clock") == FIXED_CLOCK
            and evidence.get("status") == "PASS"
            and evidence.get("decision") == "MARKET_ONTOLOGY_AND_COVERAGE_SCHEMA_FROZEN"
            and evidence.get("phase_status") == "S05_P01_PASS"
            and evidence.get("next") == "S05/P02_READY_NOT_STARTED"
            and _decision_hash_matches(evidence)
        )
        _add(checks, "S05P01-SIGNED-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S05P01-SIGNED-VALIDATION", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate_path = Path(relative)
            if candidate_path.is_absolute() or ".." in candidate_path.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate_path if relative.startswith(".github/") else root / candidate_path
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected and not _historical_file_matches(root, relative, expected, verify_git_history):
                input_errors.append({"path": relative, "expected": expected, "actual": actual})
        _add(checks, "S05P01-SIGNED-INPUT-HASHES", not input_errors, input_errors or "all inputs match current files or the exact signed P01 commit")
        current_code = _current_code_hash(root)
        expected_code = evidence.get("hashes", {}).get("code")
        historical_code = _historical_code_hash(root, verify_git_history) if expected_code != current_code else current_code
        code_ok = expected_code == current_code or (expected_code == PINNED_PHASE_CODE_HASH and historical_code in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"})
        _add(checks, "S05P01-SIGNED-CODE-HASH", code_ok, {"expected": expected_code, "actual": current_code, "historical": historical_code})
        report_errors: List[Dict[str, str]] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [JUNIT_PATH, FULL_JUNIT_PATH, PACK_REPORT_PATH, SCAN_REPORT_PATH]:
            expected = validation_hashes.get(relative.as_posix())
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if not isinstance(expected, str) or actual != expected:
                report_errors.append({"path": relative.as_posix(), "expected": str(expected), "actual": actual})
        _add(checks, "S05P01-SIGNED-REPORT-HASHES", not report_errors, report_errors or "all validation reports match")
        _add(checks, "S05P01-SIGNED-ROLLBACK-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        _add(checks, "S05P01-SIGNED-BOUNDARY", evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED", evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S05P01-SIGNED-INTEGRITY", "S05P01-SIGNED-VALIDATION", "S05P01-SIGNED-INPUT-HASHES", "S05P01-SIGNED-CODE-HASH", "S05P01-SIGNED-REPORT-HASHES", "S05P01-SIGNED-ROLLBACK-BINDING", "S05P01-SIGNED-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = (
        isinstance(rollback, Mapping)
        and rollback.get("evidence_id") == "EVD-S05-P01-ROLLBACK"
        and rollback.get("contract_id") == CONTRACT_ID
        and rollback.get("fixed_clock") == FIXED_CLOCK
        and rollback.get("status") == "PASS"
        and rollback.get("production_state_changed") is False
        and rollback.get("external_state_changed") is False
        and rollback.get("provider_or_market_accessed") is False
        and rollback.get("recommendation_or_order_generated") is False
        and rollback.get("incremental_cash_spent_aud") == "0.00"
        and len(rollback.get("artifacts", {})) == len(ROLLBACK_ARTIFACTS)
        and set(rollback.get("artifacts", {})) == {path.as_posix() for path in ROLLBACK_ARTIFACTS}
        and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    )
    _add(checks, "S05P01-SIGNED-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P01"]
    index_ok = len(rows) == 1 and rows[0].get("status") == "PASS" and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and rows[0].get("artifact_sha256") == evidence_hash and rows[0].get("next") == "S05/P02_READY_NOT_STARTED"
    _add(checks, "S05P01-SIGNED-INDEX", index_ok, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_P01_SIGNED_PREFLIGHT_VALID" if not failed else "S05_P01_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_sha256": evidence_hash,
        "rollback_sha256": rollback_hash,
        "next": "S05/P02_READY_NOT_STARTED" if not failed else "S05/P01_REMEDIATION_REQUIRED",
    }


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    preflight = validate_signed_receipt_preflight(root, verify_git_history=verify_git_history)
    _add(checks, "S05P01-RECEIPT-PREFLIGHT", preflight.get("status") == "PASS", preflight.get("summary"))
    try:
        s02 = verify_stage2_delivery(root, verify_git_history=verify_git_history)
        _add(checks, "S05P01-RECEIPT-S02-DELIVERY", s02.get("status") == "PASS", s02.get("summary"))
    except Exception as exc:
        _add(checks, "S05P01-RECEIPT-S02-DELIVERY", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        s04 = verify_stage4_delivery(root, verify_git_history=verify_git_history)
        _add(checks, "S05P01-RECEIPT-S04-DELIVERY", s04.get("status") == "PASS", s04.get("summary"))
    except Exception as exc:
        _add(checks, "S05P01-RECEIPT-S04-DELIVERY", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_P01_EVIDENCE_VERIFIED" if not failed else "S05_P01_EVIDENCE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": preflight.get("evidence_sha256"),
        "rollback_sha256": preflight.get("rollback_sha256"),
        "next": "S05/P02_READY_NOT_STARTED" if not failed else "S05/P01_REMEDIATION_REQUIRED",
    }
