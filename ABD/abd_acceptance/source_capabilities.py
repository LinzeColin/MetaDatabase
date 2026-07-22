from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .market_ontology import verify_existing_phase_evidence as verify_market_ontology_evidence


CONTRACT_ID = "AC-S05-P02"
REQUIREMENT_ID = "REQ-S05-P02"
STAGE_ID = "S05"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-23T12:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

PROVIDER_CONTRACTS_PATH = Path("provider_contracts.json")
SOURCE_CAPABILITIES_PATH = Path("source_capabilities.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S05_P02.json")
TEST_PATH = Path("tests/S05/P02_test.py")
JUNIT_PATH = Path("machine/evidence/S05/P02/pytest.xml")
AFFECTED_JUNIT_PATH = Path("machine/evidence/S05/P02/signed_state_regression.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S05/P02/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

EXPECTED_MODES = [
    "PUBLIC_BROWSER",
    "FILE_OR_STATIC_DATA",
    "FREE_ENDPOINT",
    "AUTHENTICATED_OBSERVER",
    "OWNER_DEVICE_OVERLAY",
]
EXPECTED_PROVIDERS = ["TAB", "SPORTSBET", "OTHER_OBSERVABLE_PROVIDER"]
EXPECTED_TASK_IDS = ["T-S05-P02-01", "T-S05-P02-02", "T-S05-P02-03"]
EXPECTED_TEST_IDS = ["TEST-S05-P02", "TEST-S05-P02-BOUNDARY", "TEST-S05-P02-REPLAY"]
EXPECTED_ARTIFACTS = {
    "ART-S05-P02-01": PROVIDER_CONTRACTS_PATH.as_posix(),
    "ART-S05-P02-02": SOURCE_CAPABILITIES_PATH.as_posix(),
}
EXPECTED_NUMERIC_DELTAS = ["-0.0001", "0", "0.0001"]

STRUCTURAL_SELF_NORMALIZED_SHA256 = "4d5fa6d6173fafcf165ee8c27348386b934f3f70bc0442bcb9bdd9b280a40e05"
PHASE_COMMIT = "8c0d0ec526e0bbbe571cc4f8dbf603bc7d4899c2"
PINNED_PHASE_CODE_HASH = "a5942113d4018639dbaa718c97dd0a8b1d76635057da12177df9d56bebbf8b6a"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/__init__.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/advice_card.py",
    "abd_acceptance/market_ontology.py",
    "abd_acceptance/reason_next_action.py",
    "abd_acceptance/source_capabilities.py",
    "abd_acceptance/stage3_review.py",
    "abd_acceptance/stage4_review.py",
    "abd_acceptance/usability_accessibility.py",
    "tests/S04/stage_review_test.py",
    "tests/S05/P02_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "README.md": "cdeb85233247f078f9b8d7380e182a6eb905bde133ac05246231a559c2cbe8ef",
    "abd_acceptance/__init__.py": "dd43b55546ecbb245bc4b97a201563454f20766666bbaf37a3741f89375e594b",
    "abd_acceptance/__main__.py": "6f1d82c21751c665a8b33b93178fc98db8a7545a095141c9c63811be1871d2f9",
    "abd_acceptance/advice_card.py": "c1961b3a6f4abc623aa6f4c2bfa83588b6d44c5e5adf5d276982c93460df1ff4",
    "abd_acceptance/market_ontology.py": "19993c503b05f3424ddfd3237b8ac8baa5799d133e545ee838d5c3b43743070c",
    "abd_acceptance/reason_next_action.py": "41e24f5487db85648fe19d2893fd29a3283db101f04b66a1ea8afd5321c717cd",
    "abd_acceptance/stage3_review.py": "5002d1027ebbd603aab6ae49d5ad3d190b7534065191d5feb8c21eab7096109d",
    "abd_acceptance/stage4_review.py": "9c7307f3437600f034520070ba085d66ac2f6c9335338e07d9282729af315646",
    "abd_acceptance/usability_accessibility.py": "91909f739040669de90cda1975bc4678c10909e8a838f85ae6637fdd42a41394",
    "tests/S04/stage_review_test.py": "eeb679801de3c73049cd64859bc3e46a31aae0954e6bde02674bffded1731206",
    "tests/S05/P02_test.py": "da9cacf2f864cb60bf0866c072da34685c4d57ff2180acced4b79f1567819cd2",
}
PINNED_PHASE_HASHES: Dict[str, str] = {
    PROVIDER_CONTRACTS_PATH.as_posix(): "1b45c2991e7c91b497a01003237ad883ba6a2831f25d83caa4cb4a1dac9fd8b6",
    SOURCE_CAPABILITIES_PATH.as_posix(): "fe248aeb82cfd10410287114fb822c327d1463b3ea68359c31c82549a90b9539",
    FIXTURE_PATH.as_posix(): "26b5f58830ff9add93bf8466383122eb5945ea2fd827ad1d2f11c7bb9ff256b2",
    TEST_PATH.as_posix(): "4e41ce1aedde1b8cb39fc9326041468224c4b0ca5e4aea23a5fbf0e21801c115",
}
PINNED_BASELINE_HASHES: Dict[str, str] = {
    "machine/facts/provider_contracts.json": "a9d0fd864fad7ac4c14ec6a324d447abbc8497b256a232f9ca04b3115b15364a",
    "provider_facts_snapshot.json": "a76b514469243d7b0a5c7c4ed3e2b388452d5fd5ded7fdc42aad48d5ebb17b06",
    "sources.json": "a00d0bf733c2fb6c14ef0f5d56012a4d632bab982f9d5744fbea5b3eef487966",
    "regulatory_matrix.json": "5022031f18d910d040221d4e526b87c1b05b118bed4c1da9e655bc7b9d08227f",
    "machine/facts/authorization_matrix.json": "f7cf34a3d60e37365c3090fac75f40e0b390ec211976393e7148d597a2f4affe",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/model_system_card.json": "73ec49595eeb93a50a85ffd92d52b79da8262563c1e4bae2f959f8900052a8f4",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
    "machine/evidence/EVD-S05-P01.json": "a5f2014009c92b50e49be7ad6260979ad8bb546d25b1d2f606ba745006fb8239",
    "machine/evidence/EVD-S05-P01_rollback.json": "9b88961d0fec3cb9409706cc879c80506c909894eba28e61ed98714b12b702f9",
}
PINNED_REPO_HASHES = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "provider_account_api_or_page_accessed": False,
    "provider_permission_or_api_grant_obtained": False,
    "real_market_data_collected": False,
    "source_terms_or_external_state_changed": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "model_or_strategy_executed": False,
    "recommendation_generated": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
}

ROLLBACK_ARTIFACTS = [
    PROVIDER_CONTRACTS_PATH,
    SOURCE_CAPABILITIES_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    Path("abd_acceptance/source_capabilities.py"),
    Path("abd_acceptance/market_ontology.py"),
    Path("tests/S05/P01_test.py"),
    Path("abd_acceptance/stage4_review.py"),
    Path("tests/S04/stage_review_test.py"),
    Path("abd_acceptance/advice_card.py"),
    Path("abd_acceptance/reason_next_action.py"),
    Path("abd_acceptance/usability_accessibility.py"),
    Path("abd_acceptance/stage3_review.py"),
    Path("abd_acceptance/__main__.py"),
    Path("abd_acceptance/__init__.py"),
    Path("README.md"),
]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bghp" + r"_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    re.compile(r"(?i)\b(?:api[_-]?token|client[_-]?secret|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+\-=]{12,}"),
]
LOCAL_PATH_FRAGMENTS = ["/" + "Users/", "/private/" + "var/", "file" + "://", "C:" + "\\Users\\"]
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class SourceCapabilityContractError(ValueError):
    """Raised when S05/P02 cannot be evaluated without weakening a source gate."""


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
    text = (root / "abd_acceptance/source_capabilities.py").read_text(encoding="utf-8")
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
    if relative == "abd_acceptance/source_capabilities.py":
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
        if line:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise SourceCapabilityContractError("evidence index rows must be objects")
            rows.append(value)
    return rows


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _parse_date(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def resolve_capability_request(capability: Mapping[str, Any], request: Mapping[str, Any]) -> Dict[str, Any]:
    """Resolve one read-only collection request without performing collection."""
    required_request_fields = {
        "provider_id",
        "mode",
        "provider_contract_version",
        "source_version_sha256",
        "evaluation_date",
        "incremental_cash_aud",
        "passed_gate_ids",
        "requested_action",
        "execution_environment",
    }
    missing = sorted(required_request_fields - set(request)) if isinstance(request, Mapping) else sorted(required_request_fields)

    def deny(reason: str, detail: Any = None) -> Dict[str, Any]:
        return {
            "decision": "DENY_COLLECTION",
            "reason_code": reason,
            "detail": detail,
            "advice_enabled": False,
            "order_enabled": False,
            "external_action_performed": False,
        }

    if missing:
        return deny("MALFORMED_REQUEST", {"missing": missing})
    if request.get("provider_id") != capability.get("provider_id") or request.get("mode") != capability.get("mode"):
        return deny("CAPABILITY_IDENTITY_MISMATCH")
    if request.get("provider_contract_version") != capability.get("provider_contract_version"):
        return deny("CONTRACT_VERSION_MISMATCH")
    expected_source_hash = capability.get("source_version_sha256")
    actual_source_hash = request.get("source_version_sha256")
    if not isinstance(actual_source_hash, str) or not SHA256_RE.fullmatch(actual_source_hash) or (
        isinstance(expected_source_hash, str) and actual_source_hash != expected_source_hash
    ):
        return deny("SOURCE_VERSION_MISMATCH")
    evaluation_date = _parse_date(request.get("evaluation_date"))
    review_by = _parse_date(capability.get("review_by"))
    if evaluation_date is None:
        return deny("MALFORMED_REQUEST", {"field": "evaluation_date"})
    if review_by is not None and evaluation_date > review_by:
        return deny("SOURCE_REVIEW_EXPIRED", {"evaluation_date": evaluation_date.isoformat(), "review_by": review_by.isoformat()})
    if request.get("incremental_cash_aud") != "0.00":
        return deny("INCREMENTAL_CASH_NOT_ZERO")
    if request.get("requested_action") != "COLLECT_READ_ONLY":
        return deny("ORDER_ACTION_PROHIBITED")
    if capability.get("test_fixture_only") is True and request.get("execution_environment") != "FROZEN_TEST":
        return deny("TEST_FIXTURE_PROHIBITED_IN_PRODUCTION")
    required_gates = capability.get("required_gate_ids")
    passed_gates = request.get("passed_gate_ids")
    if not isinstance(required_gates, list) or not isinstance(passed_gates, list) or any(not isinstance(row, str) for row in passed_gates):
        return deny("MALFORMED_REQUEST", {"field": "passed_gate_ids"})
    undeclared = sorted(set(passed_gates) - set(required_gates))
    if undeclared:
        return deny("UNDECLARED_GATE_PRESENT", undeclared)
    missing_gates = sorted(set(required_gates) - set(passed_gates))
    if missing_gates:
        return deny("REQUIRED_GATES_MISSING", missing_gates)
    if capability.get("production_collection_enabled") is not True:
        return deny("CAPABILITY_DISABLED", capability.get("state", "UNKNOWN"))
    if capability.get("test_fixture_only") is not True:
        return deny("RUNTIME_CAPABILITY_NOT_PROVEN")
    return {
        "decision": "ALLOW_FROZEN_TEST_READ_ONLY",
        "reason_code": "SOURCE_CONTRACT_PASS_TEST_ONLY",
        "detail": {"provider_id": capability.get("provider_id"), "mode": capability.get("mode")},
        "advice_enabled": False,
        "order_enabled": False,
        "external_action_performed": False,
    }


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in sorted(PINNED_PHASE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(checks, "S05P02-PHASE-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor), {"path": relative, "expected": expected, "successor": successor, "actual": actual})
        hashes[relative] = actual
    for relative, expected in sorted(PINNED_BASELINE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        _add(checks, "S05P02-BASELINE-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"path": relative, "expected": expected, "actual": actual})
        hashes[relative] = actual
    for relative, expected in sorted(PINNED_REPO_HASHES.items()):
        actual = sha256_file(root.parent / relative) if (root.parent / relative).is_file() else "MISSING"
        _add(checks, "S05P02-REPO-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"path": relative, "expected": expected, "actual": actual})
        hashes[relative] = actual
    _add(checks, "S05P02-ORACLE-STRUCTURAL-HASH", _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": _structural_self_hash(root)})


def _select_id(rows: Any, identifier: str) -> Mapping[str, Any]:
    if not isinstance(rows, list):
        return {}
    matching = [row for row in rows if isinstance(row, Mapping) and row.get("id") == identifier]
    return matching[0] if len(matching) == 1 else {}


def _check_taskpack(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirement = _select_id(strict_json_load(root / "machine/facts/requirements.json"), REQUIREMENT_ID)
    acceptance = _select_id(strict_json_load(root / "machine/facts/acceptance_contracts.json"), CONTRACT_ID)
    task_rows = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    tasks = [row for row in task_rows if isinstance(row, Mapping) and row.get("id") in EXPECTED_TASK_IDS]
    trace_rows = strict_json_load(root / "machine/facts/traceability_matrix.json")
    trace = [row for row in trace_rows if isinstance(row, Mapping) and row.get("acceptance_criteria_id") == CONTRACT_ID]
    _add(checks, "S05P02-TASKPACK-REQUIREMENT", requirement.get("scope") == list(EXPECTED_ARTIFACTS.values()) and requirement.get("target") == "任何采集能力必须先通过来源合同。", requirement)
    _add(checks, "S05P02-TASKPACK-ACCEPTANCE", acceptance.get("requirement_id") == REQUIREMENT_ID and acceptance.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S05-P02 --evidence machine/evidence" and [row.get("id") for row in acceptance.get("tests", [])] == EXPECTED_TEST_IDS, acceptance)
    _add(checks, "S05P02-TASKPACK-TASKS", [row.get("id") for row in tasks] == EXPECTED_TASK_IDS and tasks[0].get("depends_on") == ["T-S05-P01-03"] and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks), [row.get("id") for row in tasks])
    _add(checks, "S05P02-TASKPACK-TRACE", len(trace) == 1 and trace[0].get("requirement_id") == REQUIREMENT_ID and trace[0].get("task_ids") == EXPECTED_TASK_IDS and trace[0].get("test_ids") == EXPECTED_TEST_IDS and trace[0].get("artifact_ids") == list(EXPECTED_ARTIFACTS), trace)
    _add(checks, "S05P02-FIXTURE-TASKPACK-BINDING", fixture.get("expected_task_ids") == EXPECTED_TASK_IDS and fixture.get("expected_test_ids") == EXPECTED_TEST_IDS and fixture.get("expected_artifacts") == EXPECTED_ARTIFACTS, fixture.get("expected_artifacts"))


def _check_artifacts(
    root: Path,
    provider_contracts: Mapping[str, Any],
    source_capabilities: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    identity_ok = (
        provider_contracts.get("artifact_id") == "ART-S05-P02-01"
        and source_capabilities.get("artifact_id") == "ART-S05-P02-02"
        and provider_contracts.get("acceptance_contract_id") == source_capabilities.get("acceptance_contract_id") == CONTRACT_ID
        and provider_contracts.get("contract_version") == source_capabilities.get("contract_version") == "0.0.0.1-S05P02"
    )
    _add(checks, "S05P02-ARTIFACT-IDENTITY", identity_ok, {"provider": provider_contracts.get("artifact_id"), "capabilities": source_capabilities.get("artifact_id")})
    authority = provider_contracts.get("authority", {})
    authority_paths = {
        row.get("path"): row.get("sha256")
        for row in authority.values()
        if isinstance(row, Mapping) and isinstance(row.get("path"), str)
    }
    authority_ok = all(relative in PINNED_BASELINE_HASHES and expected == PINNED_BASELINE_HASHES[relative] for relative, expected in authority_paths.items()) and len(authority_paths) == 6
    _add(checks, "S05P02-AUTHORITY-HASH-BINDING", authority_ok, authority_paths)
    semantics = provider_contracts.get("semantics", {})
    _add(checks, "S05P02-UNKNOWN-FAILS-CLOSED", semantics.get("unknown_or_stale_default") == "DENY_COLLECTION_AND_SURFACE_GAP" and semantics.get("contract_pass_is_required_before_collection") is True and semantics.get("contract_pass_does_not_enable_advice_or_order") is True, semantics)
    review = provider_contracts.get("review_policy", {})
    _add(checks, "S05P02-REVIEW-POLICY", review.get("source_snapshot_retrieved_on") == "2026-07-20" and review.get("latest_review_by") == "2026-08-20" and review.get("live_revalidation_required_before_enablement") is True, review)
    modes = provider_contracts.get("mode_contracts", [])
    _add(checks, "S05P02-MODE-ORDER-EXACT", [row.get("mode") for row in modes] == EXPECTED_MODES, [row.get("mode") for row in modes])
    for mode in EXPECTED_MODES:
        rows = [row for row in modes if row.get("mode") == mode]
        row = rows[0] if len(rows) == 1 else {}
        ok = bool(row.get("required_gate_ids")) and len(row.get("required_gate_ids", [])) == len(set(row.get("required_gate_ids", []))) and bool(row.get("minimum_fields")) and isinstance(row.get("frequency_budget"), str) and isinstance(row.get("failure_action"), str)
        _add(checks, "S05P02-MODE-CONTRACT-%s" % mode, ok, row)
    providers = provider_contracts.get("provider_contracts", [])
    _add(checks, "S05P02-PROVIDER-ORDER-EXACT", [row.get("provider_id") for row in providers] == EXPECTED_PROVIDERS, [row.get("provider_id") for row in providers])
    for provider_id in EXPECTED_PROVIDERS:
        rows = [row for row in providers if row.get("provider_id") == provider_id]
        row = rows[0] if len(rows) == 1 else {}
        dated_source_ok = (
            row.get("source_facts_retrieved_on") == "2026-07-20" and row.get("review_by") == "2026-08-20"
            if provider_id != "OTHER_OBSERVABLE_PROVIDER"
            else row.get("source_facts_retrieved_on") == "NOT_APPLICABLE_UNBOUND" and row.get("review_by") == "SOURCE_BINDING_REQUIRED_BEFORE_REVIEW_DATE_EXISTS"
        )
        ok = dated_source_ok and row.get("production_collection_enabled") is False and row.get("rate_budget", {}).get("enabled_requests_per_period") == 0 and bool(row.get("stop_conditions")) and isinstance(row.get("backoff"), str) and "ORDER_SUBMISSION_CONFIRMATION_OR_RETRY" in row.get("prohibited_access_methods", [])
        _add(checks, "S05P02-PROVIDER-CONTRACT-%s" % provider_id, ok, row)
    tab = next((row for row in providers if row.get("provider_id") == "TAB"), {})
    sportsbet = next((row for row in providers if row.get("provider_id") == "SPORTSBET"), {})
    other = next((row for row in providers if row.get("provider_id") == "OTHER_OBSERVABLE_PROVIDER"), {})
    _add(checks, "S05P02-TAB-HARD-BOUNDARY", "SCREEN_SCRAPING" in tab.get("prohibited_access_methods", []) and "THIRD_PARTY_CREDENTIAL_ACCESS" in tab.get("prohibited_access_methods", []) and tab.get("realtime_truth") == "NOT_FROM_EMAIL_OR_ACTIVITY_STATEMENT", tab)
    _add(checks, "S05P02-SPORTSBET-HARD-BOUNDARY", "UNPROVEN_SCRAPING_AUTOMATION_OR_API" in sportsbet.get("prohibited_access_methods", []) and "PF-SPORTSBET-003" in sportsbet.get("source_fact_ids", []), sportsbet)
    _add(checks, "S05P02-UNBOUND-SOURCE-HARD-BOUNDARY", other.get("allowed_access_methods") == [] and other.get("applicable_licensed_entity") == "UNBOUND_UNKNOWN", other)
    adjacent = provider_contracts.get("adjacent_systems_out_of_scope", [])
    _add(checks, "S05P02-ADJACENT-SYSTEMS-EXCLUDED", [row.get("system_id") for row in adjacent] == ["GMAIL", "CLOUDFLARE", "OVH"], adjacent)
    hard = provider_contracts.get("hard_boundaries", {})
    _add(checks, "S05P02-A300-A0-NO-ORDER-NO-GUARANTEE", hard.get("initial_bankroll_aud") == "300.00" and hard.get("incremental_cash_budget_aud") == "0.00" and hard.get("paid_data_or_api_dependency_allowed") is False and hard.get("real_order_submission_confirmation_or_retry_present") is False and hard.get("target_30pct_guaranteed") is False and hard.get("target_shortfall_may_relax_source_gate") is False, hard)
    _add(checks, "S05P02-PROVIDER-CLAIM-BOUNDARY", bool(provider_contracts.get("claim_boundary")) and set(provider_contracts.get("claim_boundary", {}).values()) == {False}, provider_contracts.get("claim_boundary"))
    _add(checks, "S05P02-CAPABILITY-PARENT-HASH", source_capabilities.get("provider_contracts_sha256") == sha256_file(root / PROVIDER_CONTRACTS_PATH), source_capabilities.get("provider_contracts_sha256"))
    capabilities = source_capabilities.get("capabilities", [])
    expected_pairs = {(provider, mode) for provider in EXPECTED_PROVIDERS for mode in EXPECTED_MODES}
    actual_pairs = [(row.get("provider_id"), row.get("mode")) for row in capabilities]
    _add(checks, "S05P02-CAPABILITY-MATRIX-COMPLETE", len(capabilities) == 15 and len(set(actual_pairs)) == 15 and set(actual_pairs) == expected_pairs, actual_pairs)
    for provider_id in EXPECTED_PROVIDERS:
        rows = [row for row in capabilities if row.get("provider_id") == provider_id]
        ok = [row.get("mode") for row in rows] == EXPECTED_MODES and all(row.get("production_collection_enabled") is False and row.get("runtime_verified") is False and row.get("max_requests_per_period") == 0 and not row.get("passed_gate_ids") for row in rows)
        _add(checks, "S05P02-CAPABILITY-DISABLED-%s" % provider_id, ok, rows)
    summary = source_capabilities.get("matrix_summary", {})
    _add(checks, "S05P02-CAPABILITY-SUMMARY", summary == {"provider_count": 3, "mode_count": 5, "capability_record_count": 15, "production_collection_enabled_count": 0, "runtime_verified_count": 0, "real_market_coverage_count": 0}, summary)
    defaults = source_capabilities.get("fail_closed_defaults", {})
    _add(checks, "S05P02-FAIL-CLOSED-DEFAULTS", len(defaults) == 9 and all(isinstance(value, str) and value.startswith(("DENY", "STOP")) for value in defaults.values()), defaults)
    _add(checks, "S05P02-CAPABILITY-CLAIM-BOUNDARY", bool(source_capabilities.get("claim_boundary")) and set(source_capabilities.get("claim_boundary", {}).values()) == {False}, source_capabilities.get("claim_boundary"))
    synthetic = fixture.get("frozen_test_only_positive_contract", {})
    request = fixture.get("frozen_test_only_positive_request", {})
    decision = resolve_capability_request(synthetic, request)
    _add(checks, "S05P02-SYNTHETIC-POSITIVE-PASS", decision.get("decision") == "ALLOW_FROZEN_TEST_READ_ONLY" and decision.get("external_action_performed") is False and decision.get("advice_enabled") is False and decision.get("order_enabled") is False, decision)
    failure_log: List[Dict[str, Any]] = []
    for mutation in fixture.get("negative_mutations", []):
        mutated = deepcopy(request)
        path = mutation.get("path", [])
        if len(path) != 1:
            result = {"reason_code": "INVALID_FIXTURE_MUTATION"}
        elif mutation.get("delete") is True:
            mutated.pop(path[0], None)
            result = resolve_capability_request(synthetic, mutated)
        else:
            mutated[path[0]] = mutation.get("value")
            result = resolve_capability_request(synthetic, mutated)
        passed = result.get("decision") == "DENY_COLLECTION" and result.get("reason_code") == mutation.get("expected_reason")
        failure_log.append({"id": mutation.get("id"), "passed": passed, "expected_reason": mutation.get("expected_reason"), "actual_reason": result.get("reason_code")})
    _add(checks, "S05P02-NEGATIVE-FAULT-CATALOG", bool(failure_log) and all(row["passed"] for row in failure_log), failure_log)
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        perturbed = deepcopy(request)
        perturbed["numeric_probe"] = delta
        perturbed["adverse_odds_tick"] = True
        result = resolve_capability_request(synthetic, perturbed)
        _add(checks, "S05P02-STABILITY-%s" % str(delta).replace("-", "NEG").replace(".", "_"), result.get("decision") == decision.get("decision") and result.get("reason_code") == decision.get("reason_code"), {"delta": delta, "adverse_odds_tick": "NOT_APPLICABLE_TO_SOURCE_CONTRACT", "decision": result})
    replay_a = resolve_capability_request(deepcopy(synthetic), deepcopy(request))
    replay_b = resolve_capability_request(deepcopy(synthetic), deepcopy(request))
    _add(checks, "S05P02-DETERMINISTIC-REPLAY", replay_a == replay_b and _sha256_bytes(_json_bytes(replay_a)) == _sha256_bytes(_json_bytes(replay_b)), replay_a)
    _add(checks, "S05P02-NO-BINARY-FLOAT", not _contains_float(provider_contracts) and not _contains_float(source_capabilities) and not _contains_float(fixture), "all values are integers, booleans or decimal strings")


def _check_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("scheduler.py"),
        Path("cadence_tests.json"),
        Path("rate_budget.json"),
        Path("tests/S05/P03_test.py"),
        Path("machine/tests/fixtures/S05_P03.json"),
        Path("abd_acceptance/source_scheduler.py"),
    ]
    signed_paths = [Path("machine/evidence/EVD-S05-P03.json"), Path("machine/evidence/EVD-S05-P03_rollback.json")]
    candidate_present = [path.as_posix() for path in candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in signed_paths if (root / path).exists()]
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P03"]

    def planned(row: Mapping[str, Any]) -> bool:
        return row.get("status") == "PLANNED" and "actual_artifact" not in row and "artifact_sha256" not in row

    successor: Dict[str, Any] = {}
    mode = "INVALID_PARTIAL_S05_P03"
    if not candidate_present and not signed_present and len(rows) == 1 and planned(rows[0]):
        ok = True
        mode = "S05_P03_NOT_STARTED"
    elif len(candidate_present) == len(candidate_paths) and not signed_present and len(rows) == 1 and planned(rows[0]):
        try:
            from .source_scheduler import validate_candidate_preflight as validate_s05_p03_candidate

            successor = validate_s05_p03_candidate(root)
            ok = successor.get("status") == "PASS" and successor.get("next") == "S05/P04_READY_NOT_STARTED"
            mode = "VERIFIED_S05_P03_CANDIDATE" if ok else "INVALID_S05_P03_CANDIDATE"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif (
        len(candidate_present) == len(candidate_paths)
        and len(signed_present) == len(signed_paths)
        and len(rows) == 1
        and rows[0].get("status") == "PASS"
        and rows[0].get("actual_artifact") == "machine/evidence/EVD-S05-P03.json"
        and isinstance(rows[0].get("artifact_sha256"), str)
    ):
        try:
            from .source_scheduler import validate_signed_receipt_preflight as validate_s05_p03_signed

            successor = validate_s05_p03_signed(root)
            ok = successor.get("status") == "PASS" and successor.get("next") == "S05/P04_READY_NOT_STARTED"
            mode = "VERIFIED_S05_P03_SIGNED" if ok else "INVALID_S05_P03_SIGNED"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        ok = False
    _add(checks, "S05P02-P03-PROGRESSION", ok, {"mode": mode, "candidate_present": candidate_present, "signed_present": signed_present, "index": rows, "successor_summary": successor.get("summary") if isinstance(successor, Mapping) else successor})


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = [PROVIDER_CONTRACTS_PATH, SOURCE_CAPABILITIES_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/source_capabilities.py")]
    leaks: List[Dict[str, str]] = []
    for relative in paths:
        path = root / relative
        if not path.is_file():
            leaks.append({"path": relative.as_posix(), "kind": "missing"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            leaks.append({"path": relative.as_posix(), "kind": "secret-pattern"})
        if any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS):
            leaks.append({"path": relative.as_posix(), "kind": "absolute-local-path"})
    _add(checks, "S05P02-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


def _junit_summary(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {key: sum(int(suite.attrib.get(key, "0")) for suite in suites) for key in ("tests", "failures", "errors", "skipped")}


def _junit_is_normalized(path: Path) -> bool:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return all(suite.attrib.get("timestamp") == JUNIT_FIXED_CLOCK and suite.attrib.get("time") == "0.000" for suite in suites)


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for check_id, relative, minimum_key in [
        ("S05P02-TARGETED-PYTEST", JUNIT_PATH, "minimum_targeted_pytest_cases"),
        ("S05P02-AFFECTED-REGRESSION", AFFECTED_JUNIT_PATH, "minimum_affected_pytest_cases"),
        ("S05P02-FULL-REGRESSION", FULL_JUNIT_PATH, "minimum_full_pytest_cases"),
    ]:
        try:
            summary = _junit_summary(root / relative)
            minimum = int(fixture.get(minimum_key, 0))
            ok = summary["tests"] >= minimum and summary["failures"] == 0 and summary["errors"] == 0 and _junit_is_normalized(root / relative)
            _add(checks, check_id, ok, summary)
            hashes[relative.as_posix()] = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, check_id, False, "%s: %s" % (type(exc).__name__, exc))
    try:
        report = strict_json_load(root / PACK_REPORT_PATH)
        summary = report.get("summary", {})
        ok = report.get("status") == "PASS" and summary.get("checks") == 49 and summary.get("passed") == 49 and summary.get("failed") == 0
        _add(checks, "S05P02-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S05P02-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
        _add(checks, "S05P02-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S05P02-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    provider_contracts = _safe_load(root / PROVIDER_CONTRACTS_PATH, checks, "S05P02-PROVIDER-CONTRACTS-STRICT-JSON")
    source_capabilities = _safe_load(root / SOURCE_CAPABILITIES_PATH, checks, "S05P02-SOURCE-CAPABILITIES-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S05P02-FIXTURE-STRICT-JSON")
    _check_pins(root, checks, hashes)
    if isinstance(provider_contracts, Mapping) and isinstance(source_capabilities, Mapping) and isinstance(fixture, Mapping):
        try:
            _check_taskpack(root, fixture, checks)
            _check_artifacts(root, provider_contracts, source_capabilities, fixture, checks)
            _check_progression(root, checks)
            _check_no_leaks(root, checks)
        except Exception as exc:
            _add(checks, "S05P02-CANDIDATE-PREFLIGHT", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S05P02-CANDIDATE-INPUTS-AVAILABLE", False, "provider contracts, source capabilities or fixture unavailable")
    minimum = int(fixture.get("minimum_oracle_checks", 0)) if isinstance(fixture, Mapping) else 0
    if len(checks) < minimum:
        _add(checks, "S05P02-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    ids = [row["id"] for row in checks]
    if len(ids) != len(set(ids)):
        _add(checks, "S05P02-CHECK-IDS-UNIQUE", False, "duplicate check ids")
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_P02_CANDIDATE_VALID" if not failed else "S05_P02_CANDIDATE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "next": "S05/P03_READY_NOT_STARTED" if not failed else "S05/P02_REMEDIATION_REQUIRED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    preflight = validate_candidate_preflight(root)
    checks = list(preflight.get("checks", []))
    hashes = dict(preflight.get("hashes", {}))
    try:
        predecessor = verify_market_ontology_evidence(root, verify_git_history=_verify_git_history)
        ok = predecessor.get("status") == "PASS" and predecessor.get("decision") == "S05_P01_EVIDENCE_VERIFIED" and predecessor.get("next") == "S05/P02_READY_NOT_STARTED"
        _add(checks, "S05P02-P01-SIGNED-PREREQUISITE", ok, predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05P02-P01-SIGNED-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    product = canonical.get("product", {})
    boundary_ok = product.get("initial_bankroll_aud") == "300.00" and product.get("incremental_cash_budget_aud") == "0.00" and product.get("monthly_target_return") == "0.30" and canonical.get("scope", {}).get("order_submission_module_present") is False and parameters.get("target_30pct", {}).get("guaranteed") is False and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION" and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
    _add(checks, "S05P02-CANONICAL-BOUNDARY", boundary_ok, {"product": product, "target": parameters.get("target_30pct")})
    if require_external_reports:
        fixture = strict_json_load(root / FIXTURE_PATH)
        _check_external_reports(root, fixture, checks, hashes)
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
        "decision": "SOURCE_CAPABILITY_CONTRACTS_FROZEN_FAIL_CLOSED" if status == "PASS" else "SOURCE_CAPABILITY_CONTRACTS_BLOCKED_FAIL_CLOSED",
        "phase_status": "S05_P02_PASS" if status == "PASS" else "S05_P02_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "pass_gate_interpretation": "EVERY_COLLECTION_CAPABILITY_REQUIRES_A_VERSIONED_SOURCE_CONTRACT; CURRENT_REAL_PROVIDER_COLLECTION_REMAINS_DISABLED",
        "production_collection_status": "ALL_15_PROVIDER_MODE_CAPABILITIES_DISABLED_PENDING_SOURCE_SPECIFIC_RUNTIME_PROOF",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "NOT_READY_S05_P03_TO_P04_AND_WHOLE_STAGE_REVIEW_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S05/P03_READY_NOT_STARTED" if status == "PASS" else "S05/P02_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s05-p02-rollback-") as directory:
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
            results[relative.as_posix()] = {"status": "PASS" if corrupted != expected and restored == expected else "FAIL", "signed_sha256": expected, "corrupted_sha256": corrupted, "restored_sha256": restored}
    status = "PASS" if len(results) == len(ROLLBACK_ARTIFACTS) and all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_SOURCE_CONTRACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
        "provider_account_api_or_page_accessed": False,
        "real_market_data_collected": False,
        "recommendation_or_order_generated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _structured_failure_log(fixture: Mapping[str, Any]) -> List[Dict[str, Any]]:
    capability = fixture["frozen_test_only_positive_contract"]
    request = fixture["frozen_test_only_positive_request"]
    rows: List[Dict[str, Any]] = []
    for mutation in fixture.get("negative_mutations", []):
        mutated = deepcopy(request)
        key = mutation["path"][0]
        if mutation.get("delete") is True:
            mutated.pop(key, None)
        else:
            mutated[key] = mutation.get("value")
        result = resolve_capability_request(capability, mutated)
        rows.append({"case_id": mutation["id"], "decision": result["decision"], "reason_code": result["reason_code"], "expected_reason": mutation["expected_reason"], "matched": result["reason_code"] == mutation["expected_reason"]})
    return rows


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = sorted({
        *PINNED_PHASE_HASHES,
        *PINNED_BASELINE_HASHES,
        "abd_acceptance/source_capabilities.py",
        "abd_acceptance/market_ontology.py",
        "tests/S05/P01_test.py",
        "abd_acceptance/stage4_review.py",
        "tests/S04/stage_review_test.py",
        "abd_acceptance/advice_card.py",
        "abd_acceptance/reason_next_action.py",
        "abd_acceptance/usability_accessibility.py",
        "abd_acceptance/stage3_review.py",
        "abd_acceptance/__main__.py",
        "abd_acceptance/__init__.py",
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
        rollback = {"schema_version": "1.0.0", "evidence_id": "EVD-S05-P02-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc), "production_state_changed": False, "external_state_changed": False, "provider_account_api_or_page_accessed": False, "real_market_data_collected": False, "recommendation_or_order_generated": False, "incremental_cash_spent_aud": "0.00"}
    if rollback.get("status") != "PASS":
        validation = deepcopy(validation)
        validation.update({"status": "FAIL", "decision": "SOURCE_CAPABILITY_CONTRACTS_BLOCKED_FAIL_CLOSED", "phase_status": "S05_P02_FAIL", "next": "S05/P02_REMEDIATION_REQUIRED"})
    fixture = strict_json_load(root / FIXTURE_PATH)
    capabilities = strict_json_load(root / SOURCE_CAPABILITIES_PATH)
    failure_log = _structured_failure_log(fixture)
    inputs = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P02",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "phase_status": validation["phase_status"],
        "artifacts": EXPECTED_ARTIFACTS,
        "validation": validation,
        "contract_matrix_proof": {
            "provider_count": 3,
            "mode_count": 5,
            "capability_record_count": len(capabilities.get("capabilities", [])),
            "production_collection_enabled_count": sum(row.get("production_collection_enabled") is True for row in capabilities.get("capabilities", [])),
            "runtime_verified_count": sum(row.get("runtime_verified") is True for row in capabilities.get("capabilities", [])),
            "all_real_capabilities_fail_closed": all(row.get("production_collection_enabled") is False for row in capabilities.get("capabilities", [])),
            "synthetic_positive_case_external_action_performed": False,
        },
        "structured_failure_log": failure_log,
        "scope_boundary": {
            "p02_versions_source_capabilities_only": True,
            "real_provider_collection_not_enabled": True,
            "source_snapshot_is_not_current_runtime_proof": True,
            "synthetic_fixture_is_not_provider_permission_or_market_evidence": True,
            "gmail_is_adjacent_s06_scope_and_not_realtime_market_truth": True,
            "p03_scheduler_and_rate_budget_not_started": True,
            "p04_silent_gap_oracle_not_started": True,
            "advice_order_and_deployment_not_performed": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": inputs["machine/facts/parameters.json"],
            "model": inputs["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S05/P02 validates offline source contracts and frozen synthetic decisions only; it accesses no provider, account, page, endpoint, market, Gmail, host, model, recommendation, order or return.",
            "code": _current_code_hash(root),
            "output_provider_contracts": sha256_file(root / PROVIDER_CONTRACTS_PATH),
            "output_source_capabilities": sha256_file(root / SOURCE_CAPABILITIES_PATH),
            "structured_failure_log": _sha256_bytes(_json_bytes(failure_log)),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S05/P02_test.py --junitxml=machine/evidence/S05/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py --junitxml=machine/evidence/S05/P02/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P02/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P02/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "pass_gate_interpretation": validation["pass_gate_interpretation"],
        "production_collection_status": validation["production_collection_status"],
        "production_status": validation["production_status"],
        "release_status": validation["release_status"],
        "financial_target_status": validation["financial_target_status"],
        "next": validation["next"],
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S05-P02"]
    if len(matching) != 1:
        raise SourceCapabilityContractError("expected exactly one INDEX-AC-S05-P02 row")
    matching[0].update({"status": status, "actual_artifact": EVIDENCE_PATH.as_posix(), "artifact_sha256": evidence_hash, "verified_at": FIXED_CLOCK, "next": "S05/P03_READY_NOT_STARTED" if status == "PASS" else "S05/P02_REMEDIATION_REQUIRED"})
    _atomic_write(root / EVIDENCE_INDEX_PATH, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise SourceCapabilityContractError("evidence directory must be inside the ABD project root") from exc
    evidence, rollback = build_evidence(root, require_external_reports=True)
    evidence_path = evidence_dir / EVIDENCE_PATH.name
    rollback_path = evidence_dir / ROLLBACK_EVIDENCE_PATH.name
    _atomic_write(rollback_path, _json_bytes(rollback))
    _atomic_write(evidence_path, _json_bytes(evidence))
    evidence_hash = sha256_file(evidence_path)
    _update_evidence_index(root, evidence["status"], evidence_hash)
    return {"contract_id": CONTRACT_ID, "status": evidence["status"], "evidence_path": evidence_path.relative_to(root).as_posix(), "evidence_sha256": evidence_hash, "next": evidence["next"]}


def _decision_hash_matches(evidence: Mapping[str, Any]) -> bool:
    unsigned = deepcopy(dict(evidence))
    expected = unsigned.pop("decision_sha256", None)
    return isinstance(expected, str) and expected == _sha256_bytes(_json_bytes(unsigned))


def validate_signed_receipt_preflight(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    candidate = validate_candidate_preflight(root)
    _add(checks, "S05P02-SIGNED-CANDIDATE", candidate.get("status") == "PASS", candidate.get("summary"))
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S05P02-SIGNED-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S05P02-SIGNED-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S05-P02" and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID and evidence.get("stage_id") == STAGE_ID and evidence.get("phase_id") == PHASE_ID and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS" and evidence.get("decision") == "SOURCE_CAPABILITY_CONTRACTS_FROZEN_FAIL_CLOSED" and evidence.get("phase_status") == "S05_P02_PASS" and evidence.get("next") == "S05/P03_READY_NOT_STARTED" and _decision_hash_matches(evidence)
        _add(checks, "S05P02-SIGNED-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S05P02-SIGNED-VALIDATION", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate_path = Path(relative)
            if candidate_path.is_absolute() or ".." in candidate_path.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate_path if relative.startswith(".github/") else root / candidate_path
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected and not _historical_file_matches(root, relative, str(expected), verify_git_history):
                input_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S05P02-SIGNED-INPUT-HASHES", not input_errors, input_errors or "all inputs match current files or the exact signed P02 commit")
        current_code = _current_code_hash(root)
        expected_code = evidence.get("hashes", {}).get("code")
        historical_code = _historical_code_hash(root, verify_git_history) if expected_code != current_code else current_code
        code_ok = expected_code == current_code or (expected_code == PINNED_PHASE_CODE_HASH and historical_code in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"})
        _add(checks, "S05P02-SIGNED-CODE-HASH", code_ok, {"expected": expected_code, "actual": current_code, "historical": historical_code})
        report_errors: List[Dict[str, str]] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [JUNIT_PATH, AFFECTED_JUNIT_PATH, FULL_JUNIT_PATH, PACK_REPORT_PATH, SCAN_REPORT_PATH]:
            expected = validation_hashes.get(relative.as_posix())
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if not isinstance(expected, str) or actual != expected:
                report_errors.append({"path": relative.as_posix(), "expected": str(expected), "actual": actual})
        _add(checks, "S05P02-SIGNED-REPORT-HASHES", not report_errors, report_errors or "all reports match")
        _add(checks, "S05P02-SIGNED-ROLLBACK-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        proof = evidence.get("contract_matrix_proof", {})
        proof_ok = proof.get("provider_count") == 3 and proof.get("mode_count") == 5 and proof.get("capability_record_count") == 15 and proof.get("production_collection_enabled_count") == 0 and proof.get("runtime_verified_count") == 0 and proof.get("all_real_capabilities_fail_closed") is True and proof.get("synthetic_positive_case_external_action_performed") is False
        _add(checks, "S05P02-SIGNED-MATRIX-PROOF", proof_ok, proof)
        failures = evidence.get("structured_failure_log", [])
        _add(checks, "S05P02-SIGNED-FAILURE-LOG", len(failures) == len(strict_json_load(root / FIXTURE_PATH).get("negative_mutations", [])) and all(row.get("decision") == "DENY_COLLECTION" and row.get("matched") is True for row in failures), failures)
        boundary_ok = evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_collection_status") == "ALL_15_PROVIDER_MODE_CAPABILITIES_DISABLED_PENDING_SOURCE_SPECIFIC_RUNTIME_PROOF" and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        _add(checks, "S05P02-SIGNED-BOUNDARY", boundary_ok, evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S05P02-SIGNED-INTEGRITY", "S05P02-SIGNED-VALIDATION", "S05P02-SIGNED-INPUT-HASHES", "S05P02-SIGNED-CODE-HASH", "S05P02-SIGNED-REPORT-HASHES", "S05P02-SIGNED-ROLLBACK-BINDING", "S05P02-SIGNED-MATRIX-PROOF", "S05P02-SIGNED-FAILURE-LOG", "S05P02-SIGNED-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, Mapping) and rollback.get("evidence_id") == "EVD-S05-P02-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and rollback.get("provider_account_api_or_page_accessed") is False and rollback.get("real_market_data_collected") is False and rollback.get("recommendation_or_order_generated") is False and rollback.get("incremental_cash_spent_aud") == "0.00" and set(rollback.get("artifacts", {})) == {path.as_posix() for path in ROLLBACK_ARTIFACTS} and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S05P02-SIGNED-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P02"]
    index_ok = len(rows) == 1 and rows[0].get("status") == "PASS" and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and rows[0].get("artifact_sha256") == evidence_hash and rows[0].get("next") == "S05/P03_READY_NOT_STARTED"
    _add(checks, "S05P02-SIGNED-INDEX", index_ok, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S05_P02_SIGNED_PREFLIGHT_VALID" if not failed else "S05_P02_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "next": "S05/P03_READY_NOT_STARTED" if not failed else "S05/P02_REMEDIATION_REQUIRED"}


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    preflight = validate_signed_receipt_preflight(root, verify_git_history=verify_git_history)
    _add(checks, "S05P02-RECEIPT-PREFLIGHT", preflight.get("status") == "PASS", preflight.get("summary"))
    try:
        predecessor = verify_market_ontology_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S05P02-RECEIPT-P01-PREREQUISITE", predecessor.get("status") == "PASS", predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05P02-RECEIPT-P01-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S05_P02_EVIDENCE_VERIFIED" if not failed else "S05_P02_EVIDENCE_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": preflight.get("evidence_sha256"), "rollback_sha256": preflight.get("rollback_sha256"), "next": "S05/P03_READY_NOT_STARTED" if not failed else "S05/P02_REMEDIATION_REQUIRED"}
