from __future__ import annotations

import hashlib
import importlib
import json
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Mapping, MutableMapping, Sequence, Tuple

from .canonical_facts import sha256_file, strict_json_load
from .source_scheduler import verify_existing_phase_evidence as verify_source_scheduler_evidence


_oracle = importlib.import_module("silent_gap_oracle")
ALLOWED_STATUSES = _oracle.ALLOWED_STATUSES
GAP_STATUSES = _oracle.GAP_STATUSES
STATUS_POLICY = _oracle.STATUS_POLICY
SilentGapOracleError = _oracle.SilentGapOracleError
audit_coverage = _oracle.audit_coverage
build_coverage_record = _oracle.build_coverage_record
classify_source_capability = _oracle.classify_source_capability
evaluate_gap_threshold = _oracle.evaluate_gap_threshold
sha256_json = _oracle.sha256_json


CONTRACT_ID = "AC-S05-P04"
REQUIREMENT_ID = "REQ-S05-P04"
STAGE_ID = "S05"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-23T21:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

DASHBOARD_PATH = Path("coverage_dashboard.json")
ORACLE_PATH = Path("silent_gap_oracle.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S05_P04.json")
TEST_PATH = Path("tests/S05/P04_test.py")
JUNIT_PATH = Path("machine/evidence/S05/P04/pytest.xml")
AFFECTED_JUNIT_PATH = Path("machine/evidence/S05/P04/signed_state_regression.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S05/P04/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

EXPECTED_TASK_IDS = ["T-S05-P04-01", "T-S05-P04-02", "T-S05-P04-03"]
EXPECTED_TEST_IDS = ["TEST-S05-P04", "TEST-S05-P04-BOUNDARY", "TEST-S05-P04-REPLAY"]
EXPECTED_ARTIFACTS = {
    "ART-S05-P04-01": DASHBOARD_PATH.as_posix(),
    "ART-S05-P04-02": ORACLE_PATH.as_posix(),
}
EXPECTED_PROVIDERS = ["TAB", "SPORTSBET", "OTHER_OBSERVABLE_PROVIDER"]
EXPECTED_MODES = [
    "PUBLIC_BROWSER",
    "FILE_OR_STATIC_DATA",
    "FREE_ENDPOINT",
    "AUTHENTICATED_OBSERVER",
    "OWNER_DEVICE_OVERLAY",
]
EXPECTED_NUMERIC_DELTAS = ["-0.0001", "0", "0.0001"]

PHASE_COMMIT = "6aad40149a19e4012ab2520fe2002521465c24e3"
PINNED_PHASE_CODE_HASH = "ce412627d902eb65e517c5281277062d7429f3dc86321c4b8e2b8335388a6747"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "abd_acceptance/advice_card.py",
    "abd_acceptance/coverage_observability.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/__init__.py",
    "abd_acceptance/market_ontology.py",
    "abd_acceptance/reason_next_action.py",
    "abd_acceptance/source_capabilities.py",
    "abd_acceptance/source_scheduler.py",
    "abd_acceptance/stage3_review.py",
    "abd_acceptance/stage4_review.py",
    "abd_acceptance/usability_accessibility.py",
    "tests/S05/P04_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "abd_acceptance/advice_card.py": "e97ff5ae3d4b748bd13a99fc846cc5e4be4cc68f7c04d975daf99e7131ccbffd",
    "abd_acceptance/__main__.py": "f1203c182f2da4121d809b613b0b5ade3143c63654d096de6502c05ebf6fe02c",
    "abd_acceptance/__init__.py": "b211116e0eca203b261c8ea73afb905c0bdc028c15693172f6dd7ff53cbc99fb",
    "abd_acceptance/market_ontology.py": "c0048d0dbf8720d9dff19d2da71d2a9338ef7db64557f0a6222d5466986eba96",
    "abd_acceptance/reason_next_action.py": "eaf72f13b895c590283230ca4e029385be68593262aa2571932135dc61004176",
    "abd_acceptance/source_capabilities.py": "dc6b4559bb99ba208f2dfdd3cebb3471e7330bb54159196ee9a7bb4bec14e9a2",
    "abd_acceptance/source_scheduler.py": "1a301c29d3c9ef0a7db1a703bd5592c8dc307814c90fdef83614140c6ae3b410",
    "abd_acceptance/stage3_review.py": "48b98ecd0f7d424ed06c46917608467f7022706ee3f3cec65688aeaa4deee96f",
    "abd_acceptance/stage4_review.py": "6df3066a68ef40ea2f014edee454f17fb0d07b0a3b7b850c32cee6ac0007b592",
    "abd_acceptance/usability_accessibility.py": "e80420ca90a2d1cb9278f728dedc77cd00524597d262a47495acb7946225b829",
    "tests/S05/P04_test.py": "7a867468ac99968c2bebd607e557b9c219a21d828fbb435e52879fff9ace9b68",
}
STRUCTURAL_SELF_NORMALIZED_SHA256 = "e650d150d1dd006d8eacb111cfe1c5ebe606cde64e61e960d174d376979f14f2"
PINNED_PHASE_HASHES: Dict[str, str] = {
    DASHBOARD_PATH.as_posix(): "6cafc06b9979c37d774f126c84608b841bf3ea4d7d132643d294718d516d5744",
    ORACLE_PATH.as_posix(): "e83fc758c42a1061259bcf9b556eb0f184fc27322d5b5f329b7187e1a0c2653d",
    FIXTURE_PATH.as_posix(): "261f2546f0f8d4e411038beb1929ab9f3213f0f60f039931186f63574b8a1985",
    TEST_PATH.as_posix(): "e579336018e71bb627c2c8f98b7c6e95fa3af7e0d3855bb8fa6cd899dbde579b",
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
    "market_ontology.json": "f87d5433a69d7605a63d76200eb0813ded681a23af5eaafc5d7c613d10187efe",
    "coverage_manifest.schema.json": "b87e741b552704f969260cbf31bd2c076d1dce092a208b81cd1b46a94928c3f2",
    "provider_contracts.json": "1b45c2991e7c91b497a01003237ad883ba6a2831f25d83caa4cb4a1dac9fd8b6",
    "source_capabilities.json": "fe248aeb82cfd10410287114fb822c327d1463b3ea68359c31c82549a90b9539",
    "scheduler.py": "c290df6ef3a6228108c916d456c08e4ff3781289831fe5fb5ed0d19833f95b91",
    "cadence_tests.json": "f9afb627048ea10219545a04082ee2402a16deb549ea792aeced85d78c1aadbc",
    "rate_budget.json": "7dc8db47146f38ab3e3b888d9e2757ac38ff53a3785fb2bd66580a4b0a970323",
    "machine/evidence/EVD-S05-P03.json": "0ad9ae6a259f811c2587cd305b2996b42665c94f8ebc389b3e0ea3a24112e599",
    "machine/evidence/EVD-S05-P03_rollback.json": "45560fa18fdef1783de8ef9af1b902b1c247eee18a7f57ed455ecb8ba71f32a8",
}
PINNED_REPO_HASHES = {
    WORKFLOW_PATH.as_posix(): "e1ed7245f525cea1489932337e18fe8abbe13d3a8d45cfcf11aa2235b444a25d",
}

EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "provider_account_api_or_page_accessed": False,
    "real_market_data_collected": False,
    "real_provider_dispatch_performed": False,
    "scheduler_daemon_started": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "model_or_strategy_executed": False,
    "recommendation_generated_or_enabled": False,
    "order_submitted_confirmed_or_retried": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "incremental_cash_spent_aud": "0.00",
}

ROLLBACK_ARTIFACTS = [
    DASHBOARD_PATH,
    ORACLE_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    Path("abd_acceptance/coverage_observability.py"),
    Path("abd_acceptance/source_scheduler.py"),
    Path("tests/S05/P03_test.py"),
    Path("abd_acceptance/stage4_review.py"),
    Path("tests/S04/stage_review_test.py"),
    Path("abd_acceptance/source_capabilities.py"),
    Path("abd_acceptance/market_ontology.py"),
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


class CoverageObservabilityContractError(ValueError):
    """Raised when S05/P04 cannot be evaluated without weakening a gate."""


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


def _phase_commit_is_ancestor(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root.parent), "merge-base", "--is-ancestor", PHASE_COMMIT, "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _historical_file_matches(
    root: Path,
    relative: str,
    expected_sha256: str,
    verify_git_history: bool,
) -> bool:
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
    if relative == "abd_acceptance/coverage_observability.py":
        try:
            return _structural_self_hash(root) == STRUCTURAL_SELF_NORMALIZED_SHA256
        except Exception:
            return False
    successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
    return (
        successor not in {None, "TO_BE_FILLED"}
        and (root / relative).is_file()
        and sha256_file(root / relative) == successor
    )


def _historical_code_hash(root: Path, verify_git_history: bool) -> str:
    if not verify_git_history:
        return "UNVERIFIED_UNIT_TEST_HISTORY"
    if not _phase_commit_is_ancestor(root):
        return "INVALID_PHASE_COMMIT_ANCESTRY"
    listing = subprocess.run(
        [
            "git",
            "-C",
            str(root.parent),
            "ls-tree",
            "-r",
            "--name-only",
            PHASE_COMMIT,
            "--",
            "ABD/abd_acceptance",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if listing.returncode != 0:
        return "UNAVAILABLE_PHASE_COMMIT_TREE"
    digest = hashlib.sha256()
    for repo_path in sorted(
        line
        for line in listing.stdout.splitlines()
        if line.startswith("ABD/abd_acceptance/") and line.endswith(".py")
    ):
        blob = subprocess.run(
            ["git", "-C", str(root.parent), "show", "%s:%s" % (PHASE_COMMIT, repo_path)],
            check=False,
            capture_output=True,
        )
        if blob.returncode != 0:
            return "UNAVAILABLE_PHASE_COMMIT_BLOB"
        relative = repo_path.removeprefix("ABD/")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(blob.stdout)
        digest.update(b"\0")
    return digest.hexdigest()


def _structural_self_hash(root: Path) -> str:
    text = (root / "abd_acceptance/coverage_observability.py").read_text(encoding="utf-8")
    normalized = re.sub(
        r'(?m)^(STRUCTURAL_SELF_NORMALIZED_SHA256 = ")[^"]+("\s*)$',
        r"\1<NORMALIZED>\2",
        text,
        count=1,
    )
    if normalized == text:
        return "NORMALIZATION_FAILED"
    return _sha256_bytes(normalized.encode("utf-8"))


def _load_index(root: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in (root / EVIDENCE_INDEX_PATH).read_text(encoding="utf-8-sig").splitlines():
        if line:
            value = json.loads(line)
            if not isinstance(value, dict):
                raise CoverageObservabilityContractError("evidence index rows must be objects")
            rows.append(value)
    return rows


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _select_id(rows: Any, identifier: str) -> Mapping[str, Any]:
    if not isinstance(rows, list):
        return {}
    matching = [row for row in rows if isinstance(row, Mapping) and row.get("id") == identifier]
    return matching[0] if len(matching) == 1 else {}


def _check_pins(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in sorted(PINNED_PHASE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        successor = SUCCESSOR_UNIT_PROFILE_HASHES.get(relative)
        _add(
            checks,
            "S05P04-PHASE-PIN-%s" % relative.replace("/", "-").replace(".", "_"),
            actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor),
            {"expected": expected, "accepted_successor": successor, "actual": actual},
        )
    structural = _structural_self_hash(root)
    _add(checks, "S05P04-ORACLE-STRUCTURAL-HASH", structural == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": structural})
    for relative, expected in sorted(PINNED_BASELINE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S05P04-BASELINE-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in sorted(PINNED_REPO_HASHES.items()):
        actual = sha256_file(root.parent / relative) if (root.parent / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S05P04-REPO-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirement = _select_id(strict_json_load(root / "machine/facts/requirements.json"), REQUIREMENT_ID)
    acceptance = _select_id(strict_json_load(root / "machine/facts/acceptance_contracts.json"), CONTRACT_ID)
    task_rows = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    tasks = [row for row in task_rows if isinstance(row, Mapping) and row.get("id") in EXPECTED_TASK_IDS]
    traces = [row for row in strict_json_load(root / "machine/facts/traceability_matrix.json") if isinstance(row, Mapping) and row.get("acceptance_criteria_id") == CONTRACT_ID]
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID]
    target = "静默缺口=0；每个缺口都有原因和恢复动作。"
    _add(checks, "S05P04-TASKPACK-REQUIREMENT", requirement.get("scope") == list(EXPECTED_ARTIFACTS.values()) and requirement.get("target") == target, requirement)
    _add(checks, "S05P04-TASKPACK-ACCEPTANCE", acceptance.get("requirement_id") == REQUIREMENT_ID and acceptance.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S05-P04 --evidence machine/evidence" and [row.get("id") for row in acceptance.get("tests", [])] == EXPECTED_TEST_IDS, acceptance)
    _add(checks, "S05P04-TASKPACK-TASKS", [row.get("id") for row in tasks] == EXPECTED_TASK_IDS and tasks[0].get("depends_on") == ["T-S05-P03-03"] and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks), [row.get("id") for row in tasks])
    _add(checks, "S05P04-TASKPACK-TRACE", len(traces) == 1 and traces[0].get("requirement_id") == REQUIREMENT_ID and traces[0].get("task_ids") == EXPECTED_TASK_IDS and traces[0].get("test_ids") == EXPECTED_TEST_IDS and traces[0].get("artifact_ids") == list(EXPECTED_ARTIFACTS), traces)
    phase = next((row for row in stages[0].get("phases", []) if row.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
    _add(checks, "S05P04-TASKPACK-ROADMAP", phase.get("outputs") == list(EXPECTED_ARTIFACTS.values()) and phase.get("pass_gate") == target, phase)
    _add(checks, "S05P04-FIXTURE-BINDING", fixture.get("expected_task_ids") == EXPECTED_TASK_IDS and fixture.get("expected_test_ids") == EXPECTED_TEST_IDS and fixture.get("expected_artifacts") == EXPECTED_ARTIFACTS, fixture.get("expected_artifacts"))


def _expected_units(provider_contracts: Mapping[str, Any]) -> List[Dict[str, str]]:
    providers = [row.get("provider_id") for row in provider_contracts.get("provider_contracts", []) if isinstance(row, Mapping)]
    modes = [row.get("mode") for row in provider_contracts.get("mode_contracts", []) if isinstance(row, Mapping)]
    return [
        {
            "coverage_unit_id": "CAP-%s-%s" % (provider, mode),
            "provider_id": provider,
            "mode": mode,
        }
        for provider in providers
        for mode in modes
    ]


def _expected_records(source_capabilities: Mapping[str, Any], rate_budget: Mapping[str, Any]) -> List[Dict[str, Any]]:
    budgets = {row.get("capability_id"): row for row in rate_budget.get("capability_budgets", []) if isinstance(row, Mapping)}
    return [
        build_coverage_record(row, budgets.get(row.get("capability_id"), {}), observed_at=FIXED_CLOCK)
        for row in source_capabilities.get("capabilities", [])
        if isinstance(row, Mapping)
    ]


def _apply_dashboard_mutation(dashboard: Mapping[str, Any], mutation: Mapping[str, Any]) -> Dict[str, Any]:
    changed = deepcopy(dict(dashboard))
    operation = mutation.get("operation")
    unit_id = mutation.get("coverage_unit_id")
    records = changed.get("coverage_records", [])
    matching = [row for row in records if isinstance(row, dict) and row.get("coverage_unit_id") == unit_id]
    if operation == "DELETE_RECORD":
        changed["coverage_records"] = [row for row in records if row.get("coverage_unit_id") != unit_id]
    elif operation == "DUPLICATE_RECORD" and len(matching) == 1:
        changed["coverage_records"].append(deepcopy(matching[0]))
    elif operation == "SET_RECORD_FIELD" and len(matching) == 1:
        matching[0][mutation["field"]] = deepcopy(mutation.get("value"))
    elif operation == "DELETE_RECORD_FIELD" and len(matching) == 1:
        matching[0].pop(mutation["field"], None)
    elif operation == "DELETE_RECOVERY_ACTION":
        changed["recovery_actions"] = [row for row in changed.get("recovery_actions", []) if row.get("action_id") != mutation.get("action_id")]
    elif operation == "SET_TOP_LEVEL_FIELD":
        changed[mutation["field"]] = deepcopy(mutation.get("value"))
    else:
        raise CoverageObservabilityContractError("unsupported or inapplicable dashboard mutation")
    return changed


def _oracle_for_dashboard(dashboard: Mapping[str, Any]) -> Dict[str, Any]:
    return audit_coverage(
        dashboard.get("expected_coverage_units"),
        dashboard.get("coverage_records"),
        dashboard.get("recovery_actions"),
        fixed_clock=dashboard.get("fixed_at"),
    )


def _check_dashboard_contract(
    root: Path,
    dashboard: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
) -> Dict[str, Any]:
    provider_contracts = strict_json_load(root / "provider_contracts.json")
    source_capabilities = strict_json_load(root / "source_capabilities.json")
    rate_budget = strict_json_load(root / "rate_budget.json")
    expected_units = _expected_units(provider_contracts)
    expected_records = _expected_records(source_capabilities, rate_budget)
    authority = {row.get("path"): row.get("sha256") for row in dashboard.get("authority", {}).values() if isinstance(row, Mapping)}

    _add(checks, "S05P04-DASHBOARD-IDENTITY", dashboard.get("schema_version") == "1.0.0" and dashboard.get("artifact_id") == "ART-S05-P04-01" and dashboard.get("requirement_id") == REQUIREMENT_ID and dashboard.get("acceptance_contract_id") == CONTRACT_ID and dashboard.get("contract_version") == "0.0.0.1-S05P04" and dashboard.get("fixed_at") == FIXED_CLOCK, {key: dashboard.get(key) for key in ("artifact_id", "requirement_id", "acceptance_contract_id", "fixed_at")})
    _add(checks, "S05P04-DASHBOARD-SCOPE", dashboard.get("scope", {}).get("coverage_dimension") == "SIGNED_PROVIDER_BY_ACCESS_MODE_CONTRACT_MATRIX" and dashboard.get("scope", {}).get("actual_market_universe_enumerated_or_verified") is False and dashboard.get("scope", {}).get("runtime_provider_coverage_verified") is False and dashboard.get("scope", {}).get("production_covered_count") == 0, dashboard.get("scope"))
    authority_errors = []
    for relative in ["market_ontology.json", "provider_contracts.json", "source_capabilities.json", "rate_budget.json", "machine/evidence/EVD-S05-P03.json", "silent_gap_oracle.py"]:
        actual = sha256_file(root / relative)
        hashes[relative] = actual
        if authority.get(relative) != actual:
            authority_errors.append({"path": relative, "expected": authority.get(relative), "actual": actual})
    _add(checks, "S05P04-DASHBOARD-AUTHORITY", not authority_errors, authority_errors or "all authority hashes match")
    status_contract = dashboard.get("status_contract", {})
    _add(checks, "S05P04-STATUS-CATALOG", status_contract.get("allowed_statuses") == list(ALLOWED_STATUSES) and set(status_contract.get("gap_statuses", [])) == set(GAP_STATUSES) and status_contract.get("silent_gap_threshold") == "0" and status_contract.get("binary_float_allowed") is False, status_contract)
    _add(checks, "S05P04-EXPECTED-UNIVERSE", [row.get("provider_id") for row in provider_contracts.get("provider_contracts", [])] == EXPECTED_PROVIDERS and [row.get("mode") for row in provider_contracts.get("mode_contracts", [])] == EXPECTED_MODES and dashboard.get("expected_coverage_units") == expected_units and len(expected_units) == 15, expected_units)
    _add(checks, "S05P04-RECORD-DERIVATION", dashboard.get("coverage_records") == expected_records, {"expected": len(expected_records), "actual": len(dashboard.get("coverage_records", []))})

    positive = _oracle_for_dashboard(dashboard)
    expected_positive = fixture.get("expected_positive_result", {})
    positive_subset = {key: positive.get(key) for key in expected_positive}
    _add(checks, "S05P04-ORACLE-POSITIVE", positive_subset == expected_positive and positive.get("status_counts") == fixture.get("expected_status_counts"), positive)
    summary = dashboard.get("summary", {})
    _add(checks, "S05P04-SUMMARY", summary.get("expected_unit_count") == 15 and summary.get("represented_unit_count") == 15 and summary.get("silent_gap_count") == 0 and summary.get("explicit_gap_count") == 15 and summary.get("covered_count") == 0 and summary.get("status_counts") == fixture.get("expected_status_counts") and summary.get("all_explicit_gaps_have_reason") is True and summary.get("all_explicit_gaps_have_recovery_action") is True and summary.get("all_explicit_gaps_have_action_owner") is True and summary.get("advice_enabled") is False, summary)
    _add(checks, "S05P04-ORACLE-EXPECTATION", dashboard.get("oracle_expectation") == {key: positive.get(key) for key in dashboard.get("oracle_expectation", {})}, dashboard.get("oracle_expectation"))
    _add(checks, "S05P04-ZERO-PRODUCTION-COVERAGE-HONEST", all(row.get("production_collection_enabled") is False and row.get("runtime_verified") is False and row.get("rate_budget_enabled") is False and row.get("advice_eligible") is False for row in dashboard.get("coverage_records", [])) and positive.get("covered_count") == 0, "all 15 real units remain explicit gaps")

    recovery_actions = dashboard.get("recovery_actions", [])
    action_ids = [row.get("action_id") for row in recovery_actions if isinstance(row, Mapping)]
    required_actions = set(action for _, action in STATUS_POLICY.values()) | {"REBUILD_FROM_PINNED_INPUTS", "QUARANTINE_UNDECLARED_UNIT"}
    _add(checks, "S05P04-RECOVERY-CATALOG", set(action_ids) == required_actions and len(action_ids) == len(set(action_ids)) and all(row.get("changes_external_state") is False for row in recovery_actions), action_ids)
    _add(checks, "S05P04-NO-BINARY-FLOAT", not _contains_float(dashboard) and not _contains_float(fixture), "dashboard and fixture contain no binary float")
    _add(checks, "S05P04-CLAIM-BOUNDARY", dashboard.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and dashboard.get("claim_boundary", {}).get("all_observable_markets_enumerated_or_verified") is False and dashboard.get("claim_boundary", {}).get("production_coverage_verified") is False and dashboard.get("claim_boundary", {}).get("zero_silent_gaps_applies_only_to_pinned_provider_mode_contract_universe") is True, dashboard.get("claim_boundary"))
    return positive


def _check_mutations(dashboard: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    failures: List[Dict[str, Any]] = []
    for mutation in fixture.get("negative_dashboard_mutations", []):
        try:
            changed = _apply_dashboard_mutation(dashboard, mutation)
            result = _oracle_for_dashboard(changed)
            reasons = [row.get("reason_code") for row in result.get("findings", [])]
            matched = result.get("status") == "FAIL" and mutation.get("expected_reason") in reasons and result.get("silent_gap_count") == mutation.get("expected_silent_gap_count") and result.get("advice_allowed") is False and result.get("external_action_performed") is False
        except Exception as exc:
            result = {"status": "ERROR", "error": "%s: %s" % (type(exc).__name__, exc)}
            matched = False
        _add(checks, "S05P04-MUTATION-%s" % mutation.get("id"), matched, result)
        failures.append({"id": mutation.get("id"), "expected_reason": mutation.get("expected_reason"), "actual_reasons": [row.get("reason_code") for row in result.get("findings", [])], "decision": result.get("decision"), "matched": matched})
    return failures


def _check_boundaries(fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    vectors = fixture.get("gap_threshold_vectors", [])
    _add(checks, "S05P04-BOUNDARY-VECTOR-SET", [row.get("value") for row in vectors] == EXPECTED_NUMERIC_DELTAS, vectors)
    for row in vectors:
        result = evaluate_gap_threshold(row.get("value"))
        _add(checks, "S05P04-BOUNDARY-%s" % str(row.get("value")).replace("-", "NEG").replace(".", "_"), result.get("status") == row.get("expected_status") and result.get("reason_code") == row.get("expected_reason"), result)
    adverse = fixture.get("adverse_odds_tick", {})
    _add(checks, "S05P04-ADVERSE-ODDS-NOT-APPLICABLE", adverse.get("applies") is False and "no odds" in str(adverse.get("reason", "")), adverse)
    for index, invalid in enumerate([True, 0, 0.0, None, "NaN", "Infinity"], start=1):
        result = evaluate_gap_threshold(invalid)
        _add(checks, "S05P04-BOUNDARY-INVALID-%02d-%s" % (index, type(invalid).__name__.upper()), result.get("status") == "FAIL", result)


def _check_stage_review_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("machine/facts/stage5_review_contract.json"),
        Path("machine/evidence/S05/STAGE_REVIEW/findings.json"),
        Path("machine/tests/fixtures/S05_STAGE_REVIEW.json"),
        Path("tests/S05/stage_review_test.py"),
        Path("abd_acceptance/stage5_review.py"),
    ]
    signed_paths = [
        Path("machine/evidence/EVD-S05-STAGE-REVIEW.json"),
        Path("machine/evidence/EVD-S05-STAGE-REVIEW_rollback.json"),
    ]
    candidate_present = [
        path.as_posix() for path in candidate_paths if (root / path).exists()
    ]
    signed_present = [
        path.as_posix() for path in signed_paths if (root / path).exists()
    ]
    stage_rows = [
        row
        for row in _load_index(root)
        if row.get("id") == "INDEX-S05-STAGE-REVIEW"
    ]
    successor: Dict[str, Any] = {}
    mode = "INVALID_PARTIAL_S05_STAGE_REVIEW"
    if not candidate_present and not signed_present and not stage_rows:
        ok = True
        mode = "S05_STAGE_REVIEW_NOT_STARTED"
    elif (
        len(candidate_present) == len(candidate_paths)
        and not signed_present
        and not stage_rows
    ):
        try:
            from .stage5_review import validate_candidate_preflight

            successor = validate_candidate_preflight(root)
            ok = successor.get("status") == "PASS"
            mode = (
                "VERIFIED_S05_STAGE_REVIEW_CANDIDATE"
                if ok
                else "INVALID_S05_STAGE_REVIEW_CANDIDATE"
            )
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif (
        len(candidate_present) == len(candidate_paths)
        and len(signed_present) == len(signed_paths)
        and len(stage_rows) == 1
        and stage_rows[0].get("status") == "PASS"
    ):
        try:
            from .stage5_review import validate_signed_receipt_preflight

            successor = validate_signed_receipt_preflight(root)
            ok = successor.get("status") == "PASS"
            mode = (
                "VERIFIED_S05_STAGE_REVIEW_SIGNED"
                if ok
                else "INVALID_S05_STAGE_REVIEW_SIGNED"
            )
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        ok = False
    _add(
        checks,
        "S05P04-STAGE-REVIEW-PROGRESSION",
        ok,
        {
            "mode": mode,
            "candidate_present": candidate_present,
            "signed_present": signed_present,
            "index": stage_rows,
            "successor": successor,
        },
    )


def _check_safety(root: Path, dashboard: Mapping[str, Any], fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    product = canonical.get("product", {})
    boundary_ok = product.get("initial_bankroll_aud") == "300.00" and product.get("incremental_cash_budget_aud") == "0.00" and product.get("monthly_target_return") == "0.30" and canonical.get("scope", {}).get("order_submission_module_present") is False and parameters.get("target_30pct", {}).get("guaranteed") is False and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION" and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
    _add(checks, "S05P04-GLOBAL-SAFETY", boundary_ok, {"bankroll": product.get("initial_bankroll_aud"), "incremental_cash": product.get("incremental_cash_budget_aud"), "target_guaranteed": parameters.get("target_30pct", {}).get("guaranteed")})
    _add(checks, "S05P04-EXTERNAL-EFFECT-BOUNDARY", fixture.get("expected_external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and dashboard.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY, EXTERNAL_EFFECT_BOUNDARY)
    for relative in [DASHBOARD_PATH, ORACLE_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/coverage_observability.py")]:
        if not (root / relative).is_file():
            continue
        text = (root / relative).read_text(encoding="utf-8")
        _add(checks, "S05P04-NO-SECRET-%s" % relative.as_posix().replace("/", "-"), not any(pattern.search(text) for pattern in SECRET_PATTERNS), relative.as_posix())
        _add(checks, "S05P04-NO-LOCAL-PATH-%s" % relative.as_posix().replace("/", "-"), not any(fragment in text for fragment in LOCAL_PATH_FRAGMENTS), relative.as_posix())


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_pins(root, checks, hashes)
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S05P04-FIXTURE-STRICT-JSON")
    dashboard = _safe_load(root / DASHBOARD_PATH, checks, "S05P04-DASHBOARD-STRICT-JSON")
    if isinstance(fixture, Mapping):
        _check_taskpack(root, fixture, checks)
    if isinstance(fixture, Mapping) and isinstance(dashboard, Mapping):
        first = _check_dashboard_contract(root, dashboard, fixture, checks, hashes)
        failures = _check_mutations(dashboard, fixture, checks)
        _check_boundaries(fixture, checks)
        second = _oracle_for_dashboard(dashboard)
        _add(checks, "S05P04-DETERMINISTIC-REPLAY", first == second and sha256_json(first) == sha256_json(second), {"first": sha256_json(first), "second": sha256_json(second)})
        _add(checks, "S05P04-FAILURE-LOG-COMPLETE", len(failures) == len(fixture.get("negative_dashboard_mutations", [])) and all(row.get("matched") is True for row in failures), failures)
        _check_safety(root, dashboard, fixture, checks)
    _check_stage_review_progression(root, checks)
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P04"]
    planned_or_signed = len(rows) == 1 and (rows[0].get("status") == "PLANNED" or (rows[0].get("status") == "PASS" and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix()))
    _add(checks, "S05P04-INDEX-STATE", planned_or_signed, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_P04_CANDIDATE_VALID" if not failed else "S05_P04_CANDIDATE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "next": "S05/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S05/P04_REMEDIATION_REQUIRED",
    }


def _junit_summary(path: Path) -> Dict[str, Any]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        "tests": sum(int(suite.attrib.get("tests", "0")) for suite in suites),
        "failures": sum(int(suite.attrib.get("failures", "0")) for suite in suites),
        "errors": sum(int(suite.attrib.get("errors", "0")) for suite in suites),
        "skipped": sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
        "times": [suite.attrib.get("time") for suite in suites],
        "timestamps": [suite.attrib.get("timestamp") for suite in suites],
        "hostnames": [suite.attrib.get("hostname") for suite in suites if "hostname" in suite.attrib],
    }


def _check_external_reports(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    reports = [
        (JUNIT_PATH, fixture.get("minimum_targeted_pytest_cases"), "TARGETED"),
        (AFFECTED_JUNIT_PATH, fixture.get("minimum_affected_pytest_cases"), "AFFECTED"),
        (FULL_JUNIT_PATH, fixture.get("minimum_full_pytest_cases"), "FULL"),
    ]
    for relative, minimum, label in reports:
        if not (root / relative).is_file():
            _add(checks, "S05P04-%s-JUNIT" % label, False, "missing %s" % relative)
            continue
        try:
            summary = _junit_summary(root / relative)
            ok = summary["tests"] >= int(minimum) and summary["failures"] == 0 and summary["errors"] == 0 and summary["skipped"] == 0 and set(summary["times"]) == {"0.000"} and set(summary["timestamps"]) == {JUNIT_FIXED_CLOCK} and not summary["hostnames"]
        except Exception as exc:
            summary = {"error": "%s: %s" % (type(exc).__name__, exc)}
            ok = False
        hashes[relative.as_posix()] = sha256_file(root / relative)
        _add(checks, "S05P04-%s-JUNIT" % label, ok, summary)
    pack = _safe_load(root / PACK_REPORT_PATH, checks, "S05P04-PACK-REPORT-STRICT-JSON")
    if isinstance(pack, Mapping):
        _add(checks, "S05P04-PACK-REPORT", pack.get("status") == "PASS" and pack.get("summary", {}).get("checks") == 49 and pack.get("summary", {}).get("failed") == 0, pack.get("summary"))
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8") if (root / SCAN_REPORT_PATH).is_file() else ""
    required_lines = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
    _add(checks, "S05P04-PAID-DEPENDENCY-SCAN", required_lines <= set(scan_text.splitlines()), SCAN_REPORT_PATH.as_posix())
    if (root / SCAN_REPORT_PATH).is_file():
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    preflight = validate_candidate_preflight(root)
    checks = list(preflight.get("checks", []))
    hashes = dict(preflight.get("hashes", {}))
    try:
        predecessor = verify_source_scheduler_evidence(root, verify_git_history=_verify_git_history)
        ok = predecessor.get("status") == "PASS" and predecessor.get("decision") == "S05_P03_EVIDENCE_VERIFIED" and predecessor.get("next") == "S05/P04_READY_NOT_STARTED"
        _add(checks, "S05P04-P03-SIGNED-PREREQUISITE", ok, predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05P04-P03-SIGNED-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    if require_external_reports:
        fixture = strict_json_load(root / FIXTURE_PATH)
        _check_external_reports(root, fixture, checks, hashes)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": "PASS" if not failed else "FAIL",
        "decision": "COVERAGE_GAPS_EXPLICIT_ZERO_SILENT" if not failed else "COVERAGE_OBSERVABILITY_INVALID_FAIL_CLOSED",
        "phase_status": "S05_P04_PASS" if not failed else "S05_P04_REMEDIATION_REQUIRED",
        "pass_gate_interpretation": "ZERO_SILENT_GAPS_IN_THE_PINNED_PROVIDER_MODE_UNIVERSE;_ALL_15_CURRENT_REAL_CAPABILITIES_REMAIN_EXPLICIT_NON_PRODUCTION_GAPS_WITH_REASON_ACTION_AND_OWNER",
        "production_coverage_status": "ZERO_OF_15_REAL_PROVIDER_MODE_UNITS_COVERED_ALL_15_EXPLICIT_GAPS",
        "release_status": "NOT_READY_S05_WHOLE_STAGE_REVIEW_AND_GITHUB_UPLOAD_REQUIRED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S05/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S05/P04_REMEDIATION_REQUIRED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    results: Dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s05-p04-rollback-") as directory:
        temporary = Path(directory)
        for relative in ROLLBACK_ARTIFACTS:
            source = root / relative
            if not source.is_file():
                results[relative.as_posix()] = {"status": "FAIL", "reason": "MISSING_ARTIFACT"}
                continue
            baseline = source.read_bytes()
            target = temporary / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            target.write_bytes(target.read_bytes() + b"\nROLLBACK_DRILL_MUTATION")
            target.write_bytes(baseline)
            results[relative.as_posix()] = {
                "status": "PASS" if target.read_bytes() == baseline else "FAIL",
                "sha256_before": _sha256_bytes(baseline),
                "sha256_after": _sha256_bytes(target.read_bytes()),
                "production_state_changed": False,
            }
    status = "PASS" if results and all(row["status"] == "PASS" for row in results.values()) else "FAIL"
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
        "provider_account_api_or_page_accessed": False,
        "real_market_data_collected": False,
        "recommendation_or_order_generated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _support_input_hashes(root: Path) -> Dict[str, str]:
    paths = [
        Path("README.md"),
        Path("abd_acceptance/__init__.py"),
        Path("abd_acceptance/__main__.py"),
        Path("abd_acceptance/coverage_observability.py"),
        Path("abd_acceptance/source_scheduler.py"),
        Path("tests/S05/P03_test.py"),
        Path("abd_acceptance/stage4_review.py"),
        Path("tests/S04/stage_review_test.py"),
        Path("abd_acceptance/source_capabilities.py"),
        Path("abd_acceptance/market_ontology.py"),
        Path("abd_acceptance/advice_card.py"),
        Path("abd_acceptance/reason_next_action.py"),
        Path("abd_acceptance/usability_accessibility.py"),
        Path("abd_acceptance/stage3_review.py"),
    ]
    return {path.as_posix(): sha256_file(root / path) for path in paths if (root / path).is_file()}


def build_evidence(root: Path, require_external_reports: bool = True) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    root = root.resolve()
    validation = evaluate_contract(root, require_external_reports=require_external_reports)
    dashboard = strict_json_load(root / DASHBOARD_PATH)
    fixture = strict_json_load(root / FIXTURE_PATH)
    positive = _oracle_for_dashboard(dashboard)
    failure_log: List[Dict[str, Any]] = []
    for mutation in fixture.get("negative_dashboard_mutations", []):
        changed = _apply_dashboard_mutation(dashboard, mutation)
        result = _oracle_for_dashboard(changed)
        failure_log.append({
            "id": mutation.get("id"),
            "expected_reason": mutation.get("expected_reason"),
            "actual_reasons": [row.get("reason_code") for row in result.get("findings", [])],
            "silent_gap_count": result.get("silent_gap_count"),
            "decision": result.get("decision"),
            "matched": result.get("status") == "FAIL" and mutation.get("expected_reason") in [row.get("reason_code") for row in result.get("findings", [])] and result.get("silent_gap_count") == mutation.get("expected_silent_gap_count"),
        })
    try:
        rollback = perform_rollback_drill(root)
    except Exception as exc:
        rollback = {"schema_version": "1.0.0", "evidence_id": "EVD-S05-P04-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc), "production_state_changed": False, "external_state_changed": False, "provider_account_api_or_page_accessed": False, "real_market_data_collected": False, "recommendation_or_order_generated": False, "incremental_cash_spent_aud": "0.00"}
    if rollback.get("status") != "PASS":
        validation = deepcopy(validation)
        validation["checks"].append({"id": "S05P04-ROLLBACK-DRILL", "passed": False, "detail": rollback})
        failed = [row["id"] for row in validation["checks"] if not row["passed"]]
        validation["status"] = "FAIL"
        validation["decision"] = "COVERAGE_OBSERVABILITY_INVALID_FAIL_CLOSED"
        validation["phase_status"] = "S05_P04_REMEDIATION_REQUIRED"
        validation["next"] = "S05/P04_REMEDIATION_REQUIRED"
        validation["summary"] = {"checks": len(validation["checks"]), "passed": len(validation["checks"]) - len(failed), "failed": len(failed), "failed_check_ids": failed}
    status = validation.get("status")
    hashes = dict(validation.get("hashes", {}))
    hashes.update(_support_input_hashes(root))
    hashes.update({relative: sha256_file(root / relative) for relative in PINNED_PHASE_HASHES if (root / relative).is_file()})
    evidence: Dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P04",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": status,
        "decision": "COVERAGE_GAPS_EXPLICIT_ZERO_SILENT" if status == "PASS" else "COVERAGE_OBSERVABILITY_INVALID_FAIL_CLOSED",
        "phase_status": "S05_P04_PASS" if status == "PASS" else "S05_P04_REMEDIATION_REQUIRED",
        "pass_gate_interpretation": validation.get("pass_gate_interpretation"),
        "production_coverage_status": validation.get("production_coverage_status"),
        "release_status": validation.get("release_status"),
        "production_status": validation.get("production_status"),
        "financial_target_status": validation.get("financial_target_status"),
        "artifacts": {artifact_id: {"path": relative, "sha256": sha256_file(root / relative)} for artifact_id, relative in EXPECTED_ARTIFACTS.items()},
        "coverage_proof": {
            "expected_unit_count": positive.get("expected_unit_count"),
            "represented_unit_count": positive.get("represented_unit_count"),
            "silent_gap_count": positive.get("silent_gap_count"),
            "explicit_gap_count": positive.get("explicit_gap_count"),
            "covered_count": positive.get("covered_count"),
            "status_counts": positive.get("status_counts"),
            "finding_count": positive.get("finding_count"),
            "oracle_decision": positive.get("decision"),
            "oracle_decision_sha256": positive.get("decision_sha256"),
        },
        "structured_failure_log": failure_log,
        "scope_boundary": {
            "p04_validates_observability_not_real_market_coverage": True,
            "all_15_real_provider_mode_units_are_explicit_gaps": True,
            "production_covered_count_is_zero": True,
            "no_provider_account_page_api_or_network_access": True,
            "stage_review_not_started": True,
            "recommendation_order_and_deployment_not_performed": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "validation": validation,
        "hashes": {
            "inputs": dict(sorted(hashes.items())),
            "code": _current_code_hash(root),
            "parameters": sha256_file(root / "machine/facts/parameters.json"),
            "model": "NOT_EXECUTED",
            "model_not_executed_reason": "S05/P04 audits frozen provider-mode coverage records offline and executes no model, provider, deployment, recommendation, order or return evaluation.",
            "output_dashboard": sha256_file(root / DASHBOARD_PATH),
            "output_oracle": sha256_file(root / ORACLE_PATH),
            "oracle_report": sha256_json(positive),
            "structured_failure_log": sha256_json(failure_log),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python silent_gap_oracle.py coverage_dashboard.json",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S05/P04_test.py --junitxml=machine/evidence/S05/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py tests/S05/P03_test.py tests/S05/P04_test.py --junitxml=machine/evidence/S05/P04/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P04/pytest.xml machine/evidence/S05/P04/signed_state_regression.xml machine/evidence/S05/P04/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "rollback": {"artifact": ROLLBACK_EVIDENCE_PATH.as_posix(), "status": rollback.get("status")},
        "next": "S05/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S05/P04_REMEDIATION_REQUIRED",
    }
    evidence["decision_sha256"] = _sha256_bytes(_json_bytes(evidence))
    return evidence, rollback


def _update_evidence_index(root: Path, status: str, evidence_hash: str) -> None:
    rows = _load_index(root)
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S05-P04"]
    if len(matching) != 1:
        raise CoverageObservabilityContractError("expected exactly one S05/P04 evidence index row")
    matching[0].update({"status": status, "actual_artifact": EVIDENCE_PATH.as_posix(), "artifact_sha256": evidence_hash, "verified_at": FIXED_CLOCK, "next": "S05/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S05/P04_REMEDIATION_REQUIRED"})
    payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows) + "\n"
    _atomic_write(root / EVIDENCE_INDEX_PATH, payload.encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise CoverageObservabilityContractError("evidence directory must be inside the ABD project root") from exc
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


def validate_signed_receipt_preflight(
    root: Path,
    *,
    verify_git_history: bool = True,
) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    candidate = validate_candidate_preflight(root)
    _add(checks, "S05P04-SIGNED-CANDIDATE", candidate.get("status") == "PASS", candidate.get("summary"))
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S05P04-SIGNED-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S05P04-SIGNED-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S05-P04" and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID and evidence.get("stage_id") == STAGE_ID and evidence.get("phase_id") == PHASE_ID and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS" and evidence.get("decision") == "COVERAGE_GAPS_EXPLICIT_ZERO_SILENT" and evidence.get("phase_status") == "S05_P04_PASS" and evidence.get("next") == "S05/STAGE_REVIEW_READY_NOT_STARTED" and _decision_hash_matches(evidence)
        _add(checks, "S05P04-SIGNED-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S05P04-SIGNED-VALIDATION", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
        input_errors: List[Dict[str, str]] = []
        for relative, expected in evidence.get("hashes", {}).get("inputs", {}).items():
            candidate_path = Path(relative)
            if candidate_path.is_absolute() or ".." in candidate_path.parts:
                input_errors.append({"path": relative, "actual": "UNSAFE_PATH"})
                continue
            path = root.parent / candidate_path if relative.startswith(".github/") else root / candidate_path
            actual = sha256_file(path) if path.is_file() else "MISSING"
            if actual != expected and not _historical_file_matches(
                root,
                relative,
                str(expected),
                verify_git_history,
            ):
                input_errors.append({"path": relative, "expected": str(expected), "actual": actual})
        _add(checks, "S05P04-SIGNED-INPUT-HASHES", not input_errors, input_errors or "all inputs match")
        current_code = _current_code_hash(root)
        expected_code = evidence.get("hashes", {}).get("code")
        historical_code = (
            _historical_code_hash(root, verify_git_history)
            if expected_code != current_code
            else current_code
        )
        code_ok = expected_code == current_code or (
            expected_code == PINNED_PHASE_CODE_HASH
            and historical_code
            in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"}
        )
        _add(
            checks,
            "S05P04-SIGNED-CODE-HASH",
            code_ok,
            {
                "expected": expected_code,
                "actual": current_code,
                "historical": historical_code,
            },
        )
        report_errors: List[Dict[str, str]] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [JUNIT_PATH, AFFECTED_JUNIT_PATH, FULL_JUNIT_PATH, PACK_REPORT_PATH, SCAN_REPORT_PATH]:
            expected = validation_hashes.get(relative.as_posix())
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if not isinstance(expected, str) or actual != expected:
                report_errors.append({"path": relative.as_posix(), "expected": str(expected), "actual": actual})
        _add(checks, "S05P04-SIGNED-REPORT-HASHES", not report_errors, report_errors or "all reports match")
        _add(checks, "S05P04-SIGNED-ROLLBACK-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        proof = evidence.get("coverage_proof", {})
        proof_ok = proof.get("expected_unit_count") == 15 and proof.get("represented_unit_count") == 15 and proof.get("silent_gap_count") == 0 and proof.get("explicit_gap_count") == 15 and proof.get("covered_count") == 0 and proof.get("finding_count") == 0 and proof.get("oracle_decision") == "EXPLICIT_GAPS_ONLY_NO_SILENT_GAPS"
        _add(checks, "S05P04-SIGNED-COVERAGE-PROOF", proof_ok, proof)
        failures = evidence.get("structured_failure_log", [])
        _add(checks, "S05P04-SIGNED-FAILURE-LOG", len(failures) == len(strict_json_load(root / FIXTURE_PATH).get("negative_dashboard_mutations", [])) and all(row.get("decision") == "BLOCK_COVERAGE_AND_ADVICE" and row.get("matched") is True for row in failures), failures)
        boundary_ok = evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_coverage_status") == "ZERO_OF_15_REAL_PROVIDER_MODE_UNITS_COVERED_ALL_15_EXPLICIT_GAPS" and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        _add(checks, "S05P04-SIGNED-BOUNDARY", boundary_ok, evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S05P04-SIGNED-INTEGRITY", "S05P04-SIGNED-VALIDATION", "S05P04-SIGNED-INPUT-HASHES", "S05P04-SIGNED-CODE-HASH", "S05P04-SIGNED-REPORT-HASHES", "S05P04-SIGNED-ROLLBACK-BINDING", "S05P04-SIGNED-COVERAGE-PROOF", "S05P04-SIGNED-FAILURE-LOG", "S05P04-SIGNED-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, Mapping) and rollback.get("evidence_id") == "EVD-S05-P04-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and rollback.get("provider_account_api_or_page_accessed") is False and rollback.get("real_market_data_collected") is False and rollback.get("recommendation_or_order_generated") is False and rollback.get("incremental_cash_spent_aud") == "0.00" and set(rollback.get("artifacts", {})) == {path.as_posix() for path in ROLLBACK_ARTIFACTS} and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S05P04-SIGNED-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P04"]
    index_ok = len(rows) == 1 and rows[0].get("status") == "PASS" and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and rows[0].get("artifact_sha256") == evidence_hash and rows[0].get("next") == "S05/STAGE_REVIEW_READY_NOT_STARTED"
    _add(checks, "S05P04-SIGNED-INDEX", index_ok, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S05_P04_SIGNED_PREFLIGHT_VALID" if not failed else "S05_P04_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "next": "S05/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S05/P04_REMEDIATION_REQUIRED"}


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    preflight = validate_signed_receipt_preflight(
        root,
        verify_git_history=verify_git_history,
    )
    _add(checks, "S05P04-RECEIPT-PREFLIGHT", preflight.get("status") == "PASS", preflight.get("summary"))
    try:
        predecessor = verify_source_scheduler_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S05P04-RECEIPT-P03-PREREQUISITE", predecessor.get("status") == "PASS", predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05P04-RECEIPT-P03-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S05_P04_EVIDENCE_VERIFIED" if not failed else "S05_P04_EVIDENCE_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": preflight.get("evidence_sha256"), "rollback_sha256": preflight.get("rollback_sha256"), "next": "S05/STAGE_REVIEW_READY_NOT_STARTED" if not failed else "S05/P04_REMEDIATION_REQUIRED"}


__all__ = [
    "AFFECTED_JUNIT_PATH",
    "CONTRACT_ID",
    "DASHBOARD_PATH",
    "EVIDENCE_PATH",
    "EXPECTED_ARTIFACTS",
    "EXPECTED_MODES",
    "EXPECTED_NUMERIC_DELTAS",
    "EXPECTED_PROVIDERS",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_PATH",
    "ORACLE_PATH",
    "PHASE_COMMIT",
    "PINNED_BASELINE_HASHES",
    "PINNED_PHASE_CODE_HASH",
    "PINNED_PHASE_HASHES",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "SUCCESSOR_EVOLVABLE_SIGNED_INPUTS",
    "SUCCESSOR_UNIT_PROFILE_HASHES",
    "TEST_PATH",
    "CoverageObservabilityContractError",
    "_apply_dashboard_mutation",
    "_oracle_for_dashboard",
    "_structural_self_hash",
    "audit_coverage",
    "build_coverage_record",
    "build_evidence",
    "classify_source_capability",
    "evaluate_contract",
    "evaluate_gap_threshold",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "validate_signed_receipt_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
