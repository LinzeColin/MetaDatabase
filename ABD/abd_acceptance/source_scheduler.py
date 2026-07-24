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
from .source_capabilities import verify_existing_phase_evidence as verify_source_capability_evidence


_scheduler = importlib.import_module("scheduler")
ADVICE_USABLE_SECONDS = _scheduler.ADVICE_USABLE_SECONDS
CADENCE_ORDER = _scheduler.CADENCE_ORDER
DISTANCE_RECALCULATION_SECONDS = _scheduler.DISTANCE_RECALCULATION_SECONDS
MAX_DISPATCH_DEVIATION_MICROSECONDS = _scheduler.MAX_DISPATCH_DEVIATION_MICROSECONDS
QUOTE_USABLE_SECONDS = _scheduler.QUOTE_USABLE_SECONDS
REFRESH_SECONDS = _scheduler.REFRESH_SECONDS
SchedulerContractError = _scheduler.SchedulerContractError
calculate_backoff_seconds = _scheduler.calculate_backoff_seconds
classify_cadence = _scheduler.classify_cadence
dispatch_timing = _scheduler.dispatch_timing
evaluate_freshness = _scheduler.evaluate_freshness
next_due_at = _scheduler.next_due_at
parse_timestamp = _scheduler.parse_timestamp
plan_refresh = _scheduler.plan_refresh


CONTRACT_ID = "AC-S05-P03"
REQUIREMENT_ID = "REQ-S05-P03"
STAGE_ID = "S05"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-23T18:00:00+10:00"
JUNIT_FIXED_CLOCK = "2026-07-19T00:00:00+10:00"

SCHEDULER_PATH = Path("scheduler.py")
CADENCE_TESTS_PATH = Path("cadence_tests.json")
RATE_BUDGET_PATH = Path("rate_budget.json")
FIXTURE_PATH = Path("machine/tests/fixtures/S05_P03.json")
TEST_PATH = Path("tests/S05/P03_test.py")
JUNIT_PATH = Path("machine/evidence/S05/P03/pytest.xml")
AFFECTED_JUNIT_PATH = Path("machine/evidence/S05/P03/signed_state_regression.xml")
FULL_JUNIT_PATH = Path("machine/evidence/S05/P03/full_regression.xml")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SCAN_REPORT_PATH = Path("machine/evidence/S00/P03/paid_dependency_scan.txt")
EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S05-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
WORKFLOW_PATH = Path(".github/workflows/abd-stage0-validation.yml")

EXPECTED_TASK_IDS = ["T-S05-P03-01", "T-S05-P03-02", "T-S05-P03-03"]
EXPECTED_TEST_IDS = ["TEST-S05-P03", "TEST-S05-P03-BOUNDARY", "TEST-S05-P03-REPLAY"]
EXPECTED_ARTIFACTS = {
    "ART-S05-P03-01": SCHEDULER_PATH.as_posix(),
    "ART-S05-P03-02": CADENCE_TESTS_PATH.as_posix(),
    "ART-S05-P03-03": RATE_BUDGET_PATH.as_posix(),
}
EXPECTED_NUMERIC_DELTAS = ["-0.0001", "0", "0.0001"]

STRUCTURAL_SELF_NORMALIZED_SHA256 = "1c05d651033ae67ee440463ead917674b80a08c97db69352dda3d22f25dfc1a0"
PHASE_COMMIT = "3adc22b9e8bbe0b4df4def6a45caa4ebdd5df89a"
PINNED_PHASE_CODE_HASH = "0ee10fd13b29f901f4ba9e2cd64291aeef7ecdb0b8ec659bcfeb66fc3ddbcdac"
SUCCESSOR_EVOLVABLE_SIGNED_INPUTS = {
    "README.md",
    "abd_acceptance/__init__.py",
    "abd_acceptance/__main__.py",
    "abd_acceptance/advice_card.py",
    "abd_acceptance/market_ontology.py",
    "abd_acceptance/reason_next_action.py",
    "abd_acceptance/source_capabilities.py",
    "abd_acceptance/source_scheduler.py",
    "abd_acceptance/stage3_review.py",
    "abd_acceptance/stage4_review.py",
    "abd_acceptance/usability_accessibility.py",
    "tests/S04/stage_review_test.py",
    "tests/S05/P02_test.py",
    "tests/S05/P03_test.py",
}
SUCCESSOR_UNIT_PROFILE_HASHES: Dict[str, str] = {
    "README.md": "d687fc424a8ca00602acaa5627c337db020dd58f114acfa5cfe81b6393b6f881",
    "abd_acceptance/__init__.py": "b211116e0eca203b261c8ea73afb905c0bdc028c15693172f6dd7ff53cbc99fb",
    "abd_acceptance/__main__.py": "f1203c182f2da4121d809b613b0b5ade3143c63654d096de6502c05ebf6fe02c",
    "abd_acceptance/advice_card.py": "e97ff5ae3d4b748bd13a99fc846cc5e4be4cc68f7c04d975daf99e7131ccbffd",
    "abd_acceptance/market_ontology.py": "c0048d0dbf8720d9dff19d2da71d2a9338ef7db64557f0a6222d5466986eba96",
    "abd_acceptance/reason_next_action.py": "eaf72f13b895c590283230ca4e029385be68593262aa2571932135dc61004176",
    "abd_acceptance/source_capabilities.py": "dc6b4559bb99ba208f2dfdd3cebb3471e7330bb54159196ee9a7bb4bec14e9a2",
    "abd_acceptance/stage3_review.py": "48b98ecd0f7d424ed06c46917608467f7022706ee3f3cec65688aeaa4deee96f",
    "abd_acceptance/stage4_review.py": "6df3066a68ef40ea2f014edee454f17fb0d07b0a3b7b850c32cee6ac0007b592",
    "abd_acceptance/usability_accessibility.py": "e80420ca90a2d1cb9278f728dedc77cd00524597d262a47495acb7946225b829",
    "tests/S04/stage_review_test.py": "c0ffce73ea7fda1771db9634e3883902b12a7c473adb06f5ec882acffa8c8686",
    "tests/S05/P02_test.py": "da9cacf2f864cb60bf0866c072da34685c4d57ff2180acced4b79f1567819cd2",
    "tests/S05/P03_test.py": "082b057150b1d4325d3528b100b27f9b4537a3daafcaa6547138be60e2f0ded4",
}
PINNED_PHASE_HASHES: Dict[str, str] = {
    SCHEDULER_PATH.as_posix(): "c290df6ef3a6228108c916d456c08e4ff3781289831fe5fb5ed0d19833f95b91",
    CADENCE_TESTS_PATH.as_posix(): "f9afb627048ea10219545a04082ee2402a16deb549ea792aeced85d78c1aadbc",
    RATE_BUDGET_PATH.as_posix(): "7dc8db47146f38ab3e3b888d9e2757ac38ff53a3785fb2bd66580a4b0a970323",
    FIXTURE_PATH.as_posix(): "a8e33c573f5aaf1236ec7069d2090a72fe0852707c25dd0cab94f6f782767ca2",
    TEST_PATH.as_posix(): "89b196e9da57bb96a5743c4267806c1749aad770f166a19cb4303b19cabe2e34",
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
    "machine/tests/fixtures/schedule_boundary_vectors.json": "4b23ecbdaa11e4bd5df20c06d717ea8d60cf705f2ed86f3329912b4e848fd35b",
    "provider_contracts.json": "1b45c2991e7c91b497a01003237ad883ba6a2831f25d83caa4cb4a1dac9fd8b6",
    "source_capabilities.json": "fe248aeb82cfd10410287114fb822c327d1463b3ea68359c31c82549a90b9539",
    "machine/evidence/EVD-S05-P02.json": "c7594b54822a0292911c696533e199b97f3af3bba4e363149ab35f154388988b",
    "machine/evidence/EVD-S05-P02_rollback.json": "e86db1976846b8c6dd59f0fe83e20158feeb969fb4a324dc2d3e4651a3a40856",
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
    SCHEDULER_PATH,
    CADENCE_TESTS_PATH,
    RATE_BUDGET_PATH,
    FIXTURE_PATH,
    TEST_PATH,
    Path("abd_acceptance/source_scheduler.py"),
    Path("abd_acceptance/source_capabilities.py"),
    Path("tests/S05/P02_test.py"),
    Path("abd_acceptance/market_ontology.py"),
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


class SourceSchedulerContractError(ValueError):
    """Raised when S05/P03 cannot be evaluated without weakening a gate."""


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
    text = (root / "abd_acceptance/source_scheduler.py").read_text(encoding="utf-8")
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
    if relative == "abd_acceptance/source_scheduler.py":
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
                raise SourceSchedulerContractError("evidence index rows must be objects")
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
            "S05P03-PHASE-PIN-%s" % relative.replace("/", "-").replace(".", "_"),
            actual == expected or (successor not in {None, "TO_BE_FILLED"} and actual == successor),
            {"expected": expected, "successor": successor, "actual": actual},
        )
    structural = _structural_self_hash(root)
    _add(checks, "S05P03-ORACLE-STRUCTURAL-HASH", structural == STRUCTURAL_SELF_NORMALIZED_SHA256, {"expected": STRUCTURAL_SELF_NORMALIZED_SHA256, "actual": structural})
    for relative, expected in sorted(PINNED_BASELINE_HASHES.items()):
        actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S05P03-BASELINE-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})
    for relative, expected in sorted(PINNED_REPO_HASHES.items()):
        actual = sha256_file(root.parent / relative) if (root.parent / relative).is_file() else "MISSING"
        hashes[relative] = actual
        _add(checks, "S05P03-REPO-PIN-%s" % relative.replace("/", "-").replace(".", "_"), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, fixture: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    requirement = _select_id(strict_json_load(root / "machine/facts/requirements.json"), REQUIREMENT_ID)
    acceptance = _select_id(strict_json_load(root / "machine/facts/acceptance_contracts.json"), CONTRACT_ID)
    task_rows = strict_json_load(root / "machine/facts/task_graph.json").get("tasks", [])
    tasks = [row for row in task_rows if isinstance(row, Mapping) and row.get("id") in EXPECTED_TASK_IDS]
    trace_rows = strict_json_load(root / "machine/facts/traceability_matrix.json")
    traces = [row for row in trace_rows if isinstance(row, Mapping) and row.get("acceptance_criteria_id") == CONTRACT_ID]
    roadmap = strict_json_load(root / "machine/facts/roadmap.json")
    stages = [row for row in roadmap.get("stages", []) if row.get("id") == STAGE_ID]
    _add(checks, "S05P03-TASKPACK-REQUIREMENT", requirement.get("scope") == list(EXPECTED_ARTIFACTS.values()) and requirement.get("target") == "固定时钟测试中刷新偏差≤2秒，过期数据不进入建议。", requirement)
    _add(checks, "S05P03-TASKPACK-ACCEPTANCE", acceptance.get("requirement_id") == REQUIREMENT_ID and acceptance.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S05-P03 --evidence machine/evidence" and [row.get("id") for row in acceptance.get("tests", [])] == EXPECTED_TEST_IDS, acceptance)
    _add(checks, "S05P03-TASKPACK-TASKS", [row.get("id") for row in tasks] == EXPECTED_TASK_IDS and tasks[0].get("depends_on") == ["T-S05-P02-03"] and all(row.get("acceptance_criteria_ids") == [CONTRACT_ID] for row in tasks), [row.get("id") for row in tasks])
    _add(checks, "S05P03-TASKPACK-TRACE", len(traces) == 1 and traces[0].get("requirement_id") == REQUIREMENT_ID and traces[0].get("task_ids") == EXPECTED_TASK_IDS and traces[0].get("test_ids") == EXPECTED_TEST_IDS and traces[0].get("artifact_ids") == list(EXPECTED_ARTIFACTS), traces)
    phase = next((row for row in stages[0].get("phases", []) if row.get("id") == PHASE_ID), {}) if len(stages) == 1 else {}
    _add(checks, "S05P03-TASKPACK-ROADMAP", phase.get("outputs") == list(EXPECTED_ARTIFACTS.values()) and phase.get("pass_gate") == "固定时钟测试中刷新偏差≤2秒，过期数据不进入建议。", phase)
    _add(checks, "S05P03-FIXTURE-BINDING", fixture.get("expected_task_ids") == EXPECTED_TASK_IDS and fixture.get("expected_test_ids") == EXPECTED_TEST_IDS and fixture.get("expected_artifacts") == EXPECTED_ARTIFACTS, fixture.get("expected_artifacts"))


def _check_cadence_contract(
    root: Path,
    cadence: Mapping[str, Any],
    rate_budget: Mapping[str, Any],
    fixture: Mapping[str, Any],
    checks: List[Dict[str, Any]],
) -> None:
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    source_capabilities = strict_json_load(root / "source_capabilities.json")
    authority = {row.get("path"): row.get("sha256") for row in cadence.get("authority", {}).values() if isinstance(row, Mapping)}
    authority_ok = all(relative in PINNED_BASELINE_HASHES or relative == SCHEDULER_PATH.as_posix() for relative in authority) and all(sha256_file(root / relative) == digest for relative, digest in authority.items())
    _add(checks, "S05P03-CADENCE-AUTHORITY-HASHES", authority_ok and len(authority) == 5, authority)
    rate_authority = {row.get("path"): row.get("sha256") for row in rate_budget.get("authority", {}).values() if isinstance(row, Mapping)}
    _add(checks, "S05P03-RATE-AUTHORITY-HASHES", len(rate_authority) == 3 and all(sha256_file(root / relative) == digest for relative, digest in rate_authority.items()), rate_authority)
    _add(checks, "S05P03-ARTIFACT-IDENTITY", cadence.get("artifact_id") == "ART-S05-P03-02" and rate_budget.get("artifact_id") == "ART-S05-P03-03" and cadence.get("contract_version") == rate_budget.get("contract_version") == "0.0.0.1-S05P03", {"cadence": cadence.get("artifact_id"), "rate": rate_budget.get("artifact_id")})
    rows = cadence.get("cadence_bands", [])
    _add(checks, "S05P03-CADENCE-BAND-ORDER", [row.get("band") for row in rows] == list(CADENCE_ORDER), [row.get("band") for row in rows])
    expected_refresh = parameters.get("coverage_and_freshness", {}).get("refresh_seconds", {})
    expected_quote = parameters.get("coverage_and_freshness", {}).get("quote_usable_seconds", {})
    expected_advice = parameters.get("coverage_and_freshness", {}).get("advice_usable_seconds", {})
    for row in rows:
        band = row.get("band")
        ok = row.get("refresh_seconds") == expected_refresh.get(band) == REFRESH_SECONDS.get(band) and row.get("quote_usable_seconds") == expected_quote.get(band) == QUOTE_USABLE_SECONDS.get(band) and row.get("advice_usable_seconds") == expected_advice.get(band) == ADVICE_USABLE_SECONDS.get(band) and row.get("advice_usable_seconds", 0) < row.get("quote_usable_seconds", 0)
        _add(checks, "S05P03-CADENCE-BAND-%s" % str(band).upper(), ok, row)
    scheduling = canonical.get("scheduling", {})
    canonical_refresh = [scheduling.get("event_more_than_24h_refresh_seconds"), scheduling.get("event_2h_to_24h_refresh_seconds"), scheduling.get("event_15m_to_2h_refresh_seconds"), scheduling.get("event_0_to_15m_refresh_seconds"), scheduling.get("live_refresh_seconds_when_supported")]
    _add(checks, "S05P03-CANONICAL-REFRESH-EXACT", canonical_refresh == [REFRESH_SECONDS[band] for band in CADENCE_ORDER], canonical_refresh)
    fixed = cadence.get("fixed_clock_gate", {})
    _add(checks, "S05P03-FIXED-CLOCK-GATE", fixed.get("distance_recalculation_seconds") == DISTANCE_RECALCULATION_SECONDS and fixed.get("maximum_dispatch_deviation_seconds") == 2 and MAX_DISPATCH_DEVIATION_MICROSECONDS == 2_000_000 and fixed.get("comparison_unit") == "INTEGER_MICROSECONDS", fixed)
    boundary = cadence.get("boundary_policy", {})
    _add(checks, "S05P03-ADVERSE-BOUNDARY-POLICY", boundary.get("exact_24h_band") == "2h_to_24h" and boundary.get("exact_2h_band") == "15m_to_2h" and boundary.get("exact_15m_band") == "0_to_15m", boundary)
    taskpack_vectors = strict_json_load(root / "machine/tests/fixtures/schedule_boundary_vectors.json").get("vectors", [])
    for index, vector in enumerate(taskpack_vectors):
        status = vector.get("status", "PREMATCH")
        result = classify_cadence(vector.get("time_to_start_seconds", 0), status=status, source_live_supported=vector.get("source_supported", False))
        expected_action = vector.get("expected_action")
        ok = result.get("refresh_seconds") == vector.get("expected_refresh_seconds") if "expected_refresh_seconds" in vector else result.get("decision") == "NO_DISPATCH_NO_ADVICE" and expected_action == "OBSERVE_OR_NO_RECOMMENDATION"
        _add(checks, "S05P03-TASKPACK-SCHEDULE-VECTOR-%02d" % index, ok, {"vector": vector, "result": result})
    for vector in cadence.get("cadence_vectors", []):
        result = classify_cadence(vector.get("time_to_start_seconds"), status=vector.get("status"), source_live_supported=vector.get("source_live_supported"))
        ok = result.get("band") == vector.get("expected_band") and result.get("refresh_seconds") == vector.get("expected_refresh_seconds") if "expected_band" in vector else result.get("decision") == vector.get("expected_action") and result.get("reason_code") == vector.get("expected_reason")
        _add(checks, "S05P03-CADENCE-VECTOR-%s" % vector.get("id"), ok, result)
    for vector in cadence.get("dispatch_vectors", []):
        result = dispatch_timing(vector.get("scheduled_at"), vector.get("actual_dispatch_at"))
        passed = result.get("decision") == "DISPATCH_TIMING_PASS"
        _add(checks, "S05P03-DISPATCH-VECTOR-%s" % vector.get("id"), passed is vector.get("expected_pass") and result.get("deviation_microseconds") == vector.get("expected_deviation_microseconds"), result)
    for vector in cadence.get("freshness_vectors", []):
        inputs = {key: value for key, value in vector.items() if key in {"now", "band", "source_timestamp", "observed_timestamp", "content_sha256", "source_clock_trusted", "advice_created_at"}}
        result = evaluate_freshness(**inputs)
        _add(checks, "S05P03-FRESHNESS-VECTOR-%s" % vector.get("id"), result.get("quote_usable") is vector.get("expected_quote_usable") and result.get("advice_input_eligible") is vector.get("expected_advice_input_eligible") and result.get("recommendation_generated") is False, result)
    budgets = rate_budget.get("capability_budgets", [])
    capability_rows = source_capabilities.get("capabilities", [])
    capability_ids = [row.get("capability_id") for row in capability_rows]
    budget_ids = [row.get("capability_id") for row in budgets]
    _add(checks, "S05P03-REAL-BUDGET-MATRIX-COMPLETE", len(budgets) == 15 and len(set(budget_ids)) == 15 and set(budget_ids) == set(capability_ids), budget_ids)
    _add(checks, "S05P03-ALL-REAL-BUDGETS-ZERO", all(row.get("production_collection_enabled") is False and row.get("max_dispatches_per_window") == 0 and row.get("window_seconds") == 0 for row in budgets), budgets)
    for capability in capability_rows:
        budget = next((row for row in budgets if row.get("capability_id") == capability.get("capability_id")), {})
        ok = budget.get("provider_id") == capability.get("provider_id") and budget.get("mode") == capability.get("mode") and budget.get("provider_contract_version") == capability.get("provider_contract_version") and capability.get("production_collection_enabled") is False and capability.get("max_requests_per_period") == 0
        _add(checks, "S05P03-BUDGET-BINDING-%s" % capability.get("capability_id"), ok, budget)
    synthetic = rate_budget.get("frozen_test_only_budget", {})
    _add(checks, "S05P03-SYNTHETIC-BUDGET-ISOLATED", synthetic.get("test_fixture_only") is True and synthetic.get("production_collection_enabled") is True and synthetic.get("external_action_permitted") is False and synthetic.get("capability_id") not in budget_ids, synthetic)
    policy = rate_budget.get("backoff_policy", {})
    _add(checks, "S05P03-DETERMINISTIC-BACKOFF-POLICY", policy == {"algorithm": "DETERMINISTIC_EXPONENTIAL_NO_JITTER", "initial_seconds": 30, "multiplier": 2, "maximum_seconds": 1800, "jitter_seconds": 0, "challenge_action": "STOP_RETRY_AND_SURFACE_GAP", "unknown_failure_action": "STOP_RETRY_AND_SURFACE_GAP"}, policy)
    for vector in fixture.get("backoff_vectors", []):
        actual = calculate_backoff_seconds(vector.get("failure_count"), policy)
        _add(checks, "S05P03-BACKOFF-%s" % vector.get("failure_count"), actual == vector.get("expected_seconds"), {"expected": vector.get("expected_seconds"), "actual": actual})
    positive = plan_refresh(fixture.get("frozen_test_only_positive_request", {}), rate_budget)
    expected_positive = fixture.get("expected_positive_result", {})
    _add(checks, "S05P03-SYNTHETIC-PLAN-PASS", all(positive.get(key) == value for key, value in expected_positive.items()) and positive.get("external_action_performed") is False and positive.get("advice_enabled") is False and positive.get("order_enabled") is False, positive)
    failures: List[Dict[str, Any]] = []
    for mutation in fixture.get("negative_schedule_mutations", []):
        request = deepcopy(fixture.get("frozen_test_only_positive_request", {}))
        key = mutation.get("path", [None])[0]
        if mutation.get("delete") is True:
            request.pop(key, None)
        else:
            request[key] = mutation.get("value")
        result = plan_refresh(request, rate_budget)
        passed = result.get("decision") == "NO_DISPATCH_NO_ADVICE" and result.get("reason_code") == mutation.get("expected_reason")
        failures.append({"id": mutation.get("id"), "passed": passed, "expected": mutation.get("expected_reason"), "actual": result.get("reason_code")})
    _add(checks, "S05P03-NEGATIVE-SCHEDULE-CATALOG", bool(failures) and all(row["passed"] for row in failures), failures)
    freshness_failures: List[Dict[str, Any]] = []
    for vector in fixture.get("freshness_fault_vectors", []):
        request = deepcopy(fixture.get("freshness_base", {}))
        request[vector.get("mutation")] = vector.get("value")
        result = evaluate_freshness(**request)
        passed = result.get("reason_code") == vector.get("expected_reason") and result.get("advice_enabled") is False
        freshness_failures.append({"id": vector.get("id"), "passed": passed, "expected": vector.get("expected_reason"), "actual": result.get("reason_code")})
    _add(checks, "S05P03-FRESHNESS-FAULT-CATALOG", bool(freshness_failures) and all(row["passed"] for row in freshness_failures), freshness_failures)
    for capability in capability_rows:
        request = deepcopy(fixture.get("frozen_test_only_positive_request", {}))
        request.update({"capability_id": capability.get("capability_id"), "capability_decision": "ALLOW_VERIFIED_READ_ONLY", "execution_environment": "PRODUCTION"})
        result = plan_refresh(request, rate_budget)
        _add(checks, "S05P03-REAL-CAPABILITY-DENIED-%s" % capability.get("capability_id"), result.get("decision") == "NO_DISPATCH_NO_ADVICE" and result.get("reason_code") == "CAPABILITY_BUDGET_DISABLED", result)
    for delta in fixture.get("allowed_numeric_boundary_deltas", []):
        request = deepcopy(fixture.get("frozen_test_only_positive_request", {}))
        request["numeric_probe"] = delta
        request["adverse_odds_tick"] = True
        result = plan_refresh(request, rate_budget)
        _add(checks, "S05P03-NUMERIC-STABILITY-%s" % delta.replace("-", "NEG").replace(".", "_"), result == positive, {"delta": delta, "adverse_odds_tick": "NOT_APPLICABLE_TO_INTEGER_TIME_CLASSIFICATION"})
    replay = plan_refresh(deepcopy(fixture.get("frozen_test_only_positive_request", {})), deepcopy(rate_budget))
    _add(checks, "S05P03-DETERMINISTIC-REPLAY", replay == positive and _sha256_bytes(_json_bytes(replay)) == _sha256_bytes(_json_bytes(positive)), replay)
    _add(checks, "S05P03-NO-BINARY-FLOAT", not _contains_float(cadence) and not _contains_float(rate_budget) and not _contains_float(fixture), "all authoritative numeric values are integers or decimal strings")
    scheduler_text = (root / SCHEDULER_PATH).read_text(encoding="utf-8")
    forbidden_imports = ["import requests", "import httpx", "import urllib", "import socket", "import subprocess", "from selenium", "from playwright"]
    _add(checks, "S05P03-SCHEDULER-NO-NETWORK-OR-PROCESS-IO", not any(token in scheduler_text for token in forbidden_imports), forbidden_imports)
    cadence_claims = cadence.get("claim_boundary", {})
    rate_claims = rate_budget.get("claim_boundary", {})
    cadence_claim_ok = cadence_claims.get("fixed_clock_contract_implemented") is True and all(value is False for key, value in cadence_claims.items() if key != "fixed_clock_contract_implemented")
    _add(checks, "S05P03-CLAIM-BOUNDARY", cadence_claim_ok and bool(rate_claims) and set(rate_claims.values()) == {False}, {"cadence": cadence_claims, "rate": rate_claims})


def _check_progression(root: Path, checks: List[Dict[str, Any]]) -> None:
    candidate_paths = [
        Path("coverage_dashboard.json"),
        Path("silent_gap_oracle.py"),
        Path("tests/S05/P04_test.py"),
        Path("machine/tests/fixtures/S05_P04.json"),
        Path("abd_acceptance/coverage_observability.py"),
    ]
    signed_paths = [Path("machine/evidence/EVD-S05-P04.json"), Path("machine/evidence/EVD-S05-P04_rollback.json")]
    candidate_present = [path.as_posix() for path in candidate_paths if (root / path).exists()]
    signed_present = [path.as_posix() for path in signed_paths if (root / path).exists()]
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P04"]
    verify_history = (root.parent / ".git").exists()
    planned = len(rows) == 1 and rows[0].get("status") == "PLANNED" and "actual_artifact" not in rows[0] and "artifact_sha256" not in rows[0]
    successor: Dict[str, Any] = {}
    mode = "INVALID_PARTIAL_S05_P04"
    if not candidate_present and not signed_present and planned:
        ok = True
        mode = "S05_P04_NOT_STARTED"
    elif len(candidate_present) == len(candidate_paths) and not signed_present and planned:
        try:
            from .coverage_observability import validate_candidate_preflight as validate_p04_candidate

            successor = validate_p04_candidate(root)
            ok = successor.get("status") == "PASS" and successor.get("next") == "S05/STAGE_REVIEW_READY_NOT_STARTED"
            mode = "VERIFIED_S05_P04_CANDIDATE" if ok else "INVALID_S05_P04_CANDIDATE"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    elif len(candidate_present) == len(candidate_paths) and len(signed_present) == len(signed_paths) and len(rows) == 1 and rows[0].get("status") == "PASS" and rows[0].get("actual_artifact") == "machine/evidence/EVD-S05-P04.json" and isinstance(rows[0].get("artifact_sha256"), str):
        try:
            from .coverage_observability import validate_signed_receipt_preflight as validate_p04_signed

            successor = validate_p04_signed(root, verify_git_history=verify_history)
            ok = successor.get("status") == "PASS" and successor.get("next") == "S05/STAGE_REVIEW_READY_NOT_STARTED"
            mode = "VERIFIED_S05_P04_SIGNED" if ok else "INVALID_S05_P04_SIGNED"
        except Exception as exc:
            ok = False
            successor = {"error": "%s: %s" % (type(exc).__name__, exc)}
    else:
        ok = False
    _add(checks, "S05P03-P04-PROGRESSION", ok, {"mode": mode, "candidate_present": candidate_present, "signed_present": signed_present, "index": rows, "successor_summary": successor.get("summary") if isinstance(successor, Mapping) else successor})


def _check_no_leaks(root: Path, checks: List[Dict[str, Any]]) -> None:
    paths = [SCHEDULER_PATH, CADENCE_TESTS_PATH, RATE_BUDGET_PATH, FIXTURE_PATH, TEST_PATH, Path("abd_acceptance/source_scheduler.py")]
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
    _add(checks, "S05P03-NO-SECRET-OR-LOCAL-PATH", not leaks, leaks or "none")


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
        ("S05P03-TARGETED-PYTEST", JUNIT_PATH, "minimum_targeted_pytest_cases"),
        ("S05P03-AFFECTED-REGRESSION", AFFECTED_JUNIT_PATH, "minimum_affected_pytest_cases"),
        ("S05P03-FULL-REGRESSION", FULL_JUNIT_PATH, "minimum_full_pytest_cases"),
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
        _add(checks, "S05P03-TASKPACK-49-PASS", ok, summary)
        hashes[PACK_REPORT_PATH.as_posix()] = sha256_file(root / PACK_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S05P03-TASKPACK-49-PASS", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        required = {"STATUS: PASS", "MAX_INCREMENTAL_CASH_AUD: 0.00", "PAID_OR_UNKNOWN_DEPENDENCIES: 0", "EXTERNAL_NETWORK_ACCESS_PERFORMED: false", "EXTERNAL_ACCOUNT_OR_BILLING_ACCESS_PERFORMED: false"}
        _add(checks, "S05P03-PAID-DEPENDENCY-SCAN", required.issubset(set(text.splitlines())), text.splitlines()[:10])
        hashes[SCAN_REPORT_PATH.as_posix()] = sha256_file(root / SCAN_REPORT_PATH)
    except Exception as exc:
        _add(checks, "S05P03-PAID-DEPENDENCY-SCAN", False, "%s: %s" % (type(exc).__name__, exc))


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    cadence = _safe_load(root / CADENCE_TESTS_PATH, checks, "S05P03-CADENCE-STRICT-JSON")
    rate_budget = _safe_load(root / RATE_BUDGET_PATH, checks, "S05P03-RATE-BUDGET-STRICT-JSON")
    fixture = _safe_load(root / FIXTURE_PATH, checks, "S05P03-FIXTURE-STRICT-JSON")
    _check_pins(root, checks, hashes)
    if isinstance(cadence, Mapping) and isinstance(rate_budget, Mapping) and isinstance(fixture, Mapping):
        try:
            _check_taskpack(root, fixture, checks)
            _check_cadence_contract(root, cadence, rate_budget, fixture, checks)
            _check_progression(root, checks)
            _check_no_leaks(root, checks)
        except Exception as exc:
            _add(checks, "S05P03-CANDIDATE-PREFLIGHT", False, "%s: %s" % (type(exc).__name__, exc))
    else:
        _add(checks, "S05P03-CANDIDATE-INPUTS-AVAILABLE", False, "cadence, rate budget or fixture unavailable")
    minimum = int(fixture.get("minimum_oracle_checks", 0)) if isinstance(fixture, Mapping) else 0
    if len(checks) < minimum:
        _add(checks, "S05P03-ORACLE-CHECK-COUNT-MINIMUM", False, {"actual": len(checks), "minimum": minimum})
    ids = [row["id"] for row in checks]
    if len(ids) != len(set(ids)):
        _add(checks, "S05P03-CHECK-IDS-UNIQUE", False, "duplicate check ids")
    failed = [row["id"] for row in checks if not row["passed"]]
    return {
        "schema_version": "1.0.0",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if not failed else "FAIL",
        "decision": "S05_P03_CANDIDATE_VALID" if not failed else "S05_P03_CANDIDATE_INVALID_FAIL_CLOSED",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "next": "S05/P04_READY_NOT_STARTED" if not failed else "S05/P03_REMEDIATION_REQUIRED",
    }


def evaluate_contract(root: Path, require_external_reports: bool = False, *, _verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    preflight = validate_candidate_preflight(root)
    checks = list(preflight.get("checks", []))
    hashes = dict(preflight.get("hashes", {}))
    try:
        predecessor = verify_source_capability_evidence(root, verify_git_history=_verify_git_history)
        ok = predecessor.get("status") == "PASS" and predecessor.get("decision") == "S05_P02_EVIDENCE_VERIFIED" and predecessor.get("next") == "S05/P03_READY_NOT_STARTED"
        _add(checks, "S05P03-P02-SIGNED-PREREQUISITE", ok, predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05P03-P02-SIGNED-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    canonical = strict_json_load(root / "machine/facts/canonical_facts.json")
    parameters = strict_json_load(root / "machine/facts/parameters.json")
    costs = strict_json_load(root / "machine/facts/costs.json")
    safety = canonical.get("product", {}).get("initial_bankroll_aud") == "300.00" and canonical.get("product", {}).get("incremental_cash_budget_aud") == "0.00" and canonical.get("scope", {}).get("order_submission_module_present") is False and parameters.get("target_30pct", {}).get("guaranteed") is False and parameters.get("target_30pct", {}).get("shortfall_behavior") == "REPORT_ONLY_NO_GATE_RELAXATION" and set(costs.get("incremental_cash_budget", {}).values()) == {"0.00"}
    _add(checks, "S05P03-A300-A0-NO-ORDER-NO-GUARANTEE", safety, {"product": canonical.get("product"), "target": parameters.get("target_30pct")})
    if require_external_reports:
        _check_external_reports(root, strict_json_load(root / FIXTURE_PATH), checks, hashes)
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
        "decision": "ADAPTIVE_REFRESH_SCHEDULE_FROZEN_FAIL_CLOSED" if status == "PASS" else "ADAPTIVE_REFRESH_SCHEDULE_BLOCKED_FAIL_CLOSED",
        "phase_status": "S05_P03_PASS" if status == "PASS" else "S05_P03_FAIL",
        "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": hashes,
        "pass_gate_interpretation": "FIXED_CLOCK_DISPATCH_DEVIATION_IS_AT_MOST_TWO_SECONDS_AND_STALE_OR_UNTRUSTED_DATA_NEVER_ENTERS_ADVICE_EVALUATION",
        "production_collection_status": "ALL_15_REAL_PROVIDER_MODE_BUDGETS_REMAIN_ZERO_AND_DISABLED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "NOT_READY_S05_P04_AND_WHOLE_STAGE_REVIEW_REQUIRED",
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "next": "S05/P04_READY_NOT_STARTED" if status == "PASS" else "S05/P03_REMEDIATION_REQUIRED",
    }


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    results: Dict[str, Dict[str, str]] = {}
    with tempfile.TemporaryDirectory(prefix="abd-s05-p03-rollback-") as directory:
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
        "evidence_id": "EVD-S05-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "fixed_clock": FIXED_CLOCK,
        "mode": "EPHEMERAL_SIGNED_SCHEDULER_CONTRACT_RESTORE",
        "status": status,
        "artifacts": results,
        "production_state_changed": False,
        "external_state_changed": False,
        "provider_account_api_or_page_accessed": False,
        "real_market_data_collected": False,
        "real_provider_dispatch_performed": False,
        "recommendation_or_order_generated": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _structured_failure_log(root: Path) -> List[Dict[str, Any]]:
    fixture = strict_json_load(root / FIXTURE_PATH)
    budget = strict_json_load(root / RATE_BUDGET_PATH)
    rows: List[Dict[str, Any]] = []
    for mutation in fixture.get("negative_schedule_mutations", []):
        request = deepcopy(fixture.get("frozen_test_only_positive_request", {}))
        key = mutation["path"][0]
        if mutation.get("delete") is True:
            request.pop(key, None)
        else:
            request[key] = mutation.get("value")
        result = plan_refresh(request, budget)
        rows.append({"case_id": mutation["id"], "decision": result.get("decision"), "reason_code": result.get("reason_code"), "expected_reason": mutation.get("expected_reason"), "matched": result.get("reason_code") == mutation.get("expected_reason")})
    return rows


def _input_hashes(root: Path) -> Dict[str, str]:
    paths = sorted({
        *PINNED_PHASE_HASHES,
        *PINNED_BASELINE_HASHES,
        "abd_acceptance/source_scheduler.py",
        "abd_acceptance/source_capabilities.py",
        "tests/S05/P02_test.py",
        "abd_acceptance/market_ontology.py",
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
        rollback = {"schema_version": "1.0.0", "evidence_id": "EVD-S05-P03-ROLLBACK", "contract_id": CONTRACT_ID, "fixed_clock": FIXED_CLOCK, "status": "FAIL", "error": "%s: %s" % (type(exc).__name__, exc), "production_state_changed": False, "external_state_changed": False, "real_provider_dispatch_performed": False, "recommendation_or_order_generated": False, "incremental_cash_spent_aud": "0.00"}
    if rollback.get("status") != "PASS":
        validation = deepcopy(validation)
        validation.update({"status": "FAIL", "decision": "ADAPTIVE_REFRESH_SCHEDULE_BLOCKED_FAIL_CLOSED", "phase_status": "S05_P03_FAIL", "next": "S05/P03_REMEDIATION_REQUIRED"})
    fixture = strict_json_load(root / FIXTURE_PATH)
    budget = strict_json_load(root / RATE_BUDGET_PATH)
    positive = plan_refresh(fixture.get("frozen_test_only_positive_request", {}), budget)
    failure_log = _structured_failure_log(root)
    inputs = _input_hashes(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S05-P03",
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
        "schedule_proof": {
            "cadence_band_count": len(CADENCE_ORDER),
            "maximum_dispatch_deviation_microseconds": MAX_DISPATCH_DEVIATION_MICROSECONDS,
            "distance_recalculation_seconds": DISTANCE_RECALCULATION_SECONDS,
            "real_capability_budget_count": len(budget.get("capability_budgets", [])),
            "real_enabled_budget_count": sum(row.get("production_collection_enabled") is True for row in budget.get("capability_budgets", [])),
            "positive_fixture_result": positive,
            "positive_fixture_external_action_performed": False,
        },
        "structured_failure_log": failure_log,
        "scope_boundary": {
            "p03_plans_refresh_and_freshness_only": True,
            "all_real_provider_budgets_remain_zero": True,
            "synthetic_fixture_is_not_provider_permission_or_runtime_evidence": True,
            "no_scheduler_daemon_or_network_dispatch_started": True,
            "p04_coverage_gap_oracle_not_started": True,
            "advice_order_and_deployment_not_performed": True,
        },
        "external_effect_boundary": EXTERNAL_EFFECT_BOUNDARY,
        "hashes": {
            "inputs": inputs,
            "parameters": inputs["machine/facts/parameters.json"],
            "model": inputs["machine/facts/model_system_card.json"],
            "model_not_executed_reason": "S05/P03 validates offline integer-time planning, zero real-source budgets and stale-input exclusion only; it accesses no provider, market, account, Gmail, host, model, recommendation, order or return.",
            "code": _current_code_hash(root),
            "output_scheduler": sha256_file(root / SCHEDULER_PATH),
            "output_cadence_tests": sha256_file(root / CADENCE_TESTS_PATH),
            "output_rate_budget": sha256_file(root / RATE_BUDGET_PATH),
            "positive_result": _sha256_bytes(_json_bytes(positive)),
            "structured_failure_log": _sha256_bytes(_json_bytes(failure_log)),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S05/P03_test.py --junitxml=machine/evidence/S05/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py tests/S05/P03_test.py --junitxml=machine/evidence/S05/P03/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P03/signed_state_regression.xml",
            "uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P03/full_regression.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P03 --evidence machine/evidence",
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
    matching = [row for row in rows if row.get("id") == "INDEX-AC-S05-P03"]
    if len(matching) != 1:
        raise SourceSchedulerContractError("expected exactly one INDEX-AC-S05-P03 row")
    matching[0].update({"status": status, "actual_artifact": EVIDENCE_PATH.as_posix(), "artifact_sha256": evidence_hash, "verified_at": FIXED_CLOCK, "next": "S05/P04_READY_NOT_STARTED" if status == "PASS" else "S05/P03_REMEDIATION_REQUIRED"})
    _atomic_write(root / EVIDENCE_INDEX_PATH, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8"))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    try:
        evidence_dir.relative_to(root)
    except ValueError as exc:
        raise SourceSchedulerContractError("evidence directory must be inside the ABD project root") from exc
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
    _add(checks, "S05P03-SIGNED-CANDIDATE", candidate.get("status") == "PASS", candidate.get("summary"))
    evidence = _safe_load(root / EVIDENCE_PATH, checks, "S05P03-SIGNED-EVIDENCE-STRICT-JSON")
    rollback = _safe_load(root / ROLLBACK_EVIDENCE_PATH, checks, "S05P03-SIGNED-ROLLBACK-STRICT-JSON")
    evidence_hash = sha256_file(root / EVIDENCE_PATH) if (root / EVIDENCE_PATH).is_file() else "MISSING"
    rollback_hash = sha256_file(root / ROLLBACK_EVIDENCE_PATH) if (root / ROLLBACK_EVIDENCE_PATH).is_file() else "MISSING"
    if isinstance(evidence, Mapping):
        shape_ok = evidence.get("schema_version") == "1.0.0" and evidence.get("evidence_id") == "EVD-S05-P03" and evidence.get("contract_id") == CONTRACT_ID and evidence.get("requirement_id") == REQUIREMENT_ID and evidence.get("stage_id") == STAGE_ID and evidence.get("phase_id") == PHASE_ID and evidence.get("fixed_clock") == FIXED_CLOCK and evidence.get("status") == "PASS" and evidence.get("decision") == "ADAPTIVE_REFRESH_SCHEDULE_FROZEN_FAIL_CLOSED" and evidence.get("phase_status") == "S05_P03_PASS" and evidence.get("next") == "S05/P04_READY_NOT_STARTED" and _decision_hash_matches(evidence)
        _add(checks, "S05P03-SIGNED-INTEGRITY", shape_ok, evidence.get("status"))
        validation = evidence.get("validation", {})
        validation_ok = isinstance(validation, Mapping) and validation.get("status") == "PASS" and validation.get("summary", {}).get("failed") == 0 and all(row.get("passed") is True for row in validation.get("checks", []))
        _add(checks, "S05P03-SIGNED-VALIDATION", validation_ok, validation.get("summary") if isinstance(validation, Mapping) else validation)
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
        _add(checks, "S05P03-SIGNED-INPUT-HASHES", not input_errors, input_errors or "all inputs match current files or the exact signed P03 commit")
        current_code = _current_code_hash(root)
        expected_code = evidence.get("hashes", {}).get("code")
        historical_code = _historical_code_hash(root, verify_git_history) if expected_code != current_code else current_code
        code_ok = expected_code == current_code or (expected_code == PINNED_PHASE_CODE_HASH and historical_code in {PINNED_PHASE_CODE_HASH, "UNVERIFIED_UNIT_TEST_HISTORY"})
        _add(checks, "S05P03-SIGNED-CODE-HASH", code_ok, {"expected": expected_code, "actual": current_code, "historical": historical_code})
        report_errors: List[Dict[str, str]] = []
        validation_hashes = validation.get("hashes", {}) if isinstance(validation, Mapping) else {}
        for relative in [JUNIT_PATH, AFFECTED_JUNIT_PATH, FULL_JUNIT_PATH, PACK_REPORT_PATH, SCAN_REPORT_PATH]:
            expected = validation_hashes.get(relative.as_posix())
            actual = sha256_file(root / relative) if (root / relative).is_file() else "MISSING"
            if not isinstance(expected, str) or actual != expected:
                report_errors.append({"path": relative.as_posix(), "expected": str(expected), "actual": actual})
        _add(checks, "S05P03-SIGNED-REPORT-HASHES", not report_errors, report_errors or "all reports match")
        _add(checks, "S05P03-SIGNED-ROLLBACK-BINDING", evidence.get("hashes", {}).get("rollback_evidence") == rollback_hash, {"expected": evidence.get("hashes", {}).get("rollback_evidence"), "actual": rollback_hash})
        proof = evidence.get("schedule_proof", {})
        proof_ok = proof.get("cadence_band_count") == 5 and proof.get("maximum_dispatch_deviation_microseconds") == 2_000_000 and proof.get("distance_recalculation_seconds") == 60 and proof.get("real_capability_budget_count") == 15 and proof.get("real_enabled_budget_count") == 0 and proof.get("positive_fixture_external_action_performed") is False
        _add(checks, "S05P03-SIGNED-SCHEDULE-PROOF", proof_ok, proof)
        failures = evidence.get("structured_failure_log", [])
        _add(checks, "S05P03-SIGNED-FAILURE-LOG", len(failures) == len(strict_json_load(root / FIXTURE_PATH).get("negative_schedule_mutations", [])) and all(row.get("decision") == "NO_DISPATCH_NO_ADVICE" and row.get("matched") is True for row in failures), failures)
        boundary_ok = evidence.get("external_effect_boundary") == EXTERNAL_EFFECT_BOUNDARY and evidence.get("production_collection_status") == "ALL_15_REAL_PROVIDER_MODE_BUDGETS_REMAIN_ZERO_AND_DISABLED" and evidence.get("production_status") == "NOT_DEPLOYED_OR_ACTIVATED"
        _add(checks, "S05P03-SIGNED-BOUNDARY", boundary_ok, evidence.get("external_effect_boundary"))
    else:
        for check_id in ["S05P03-SIGNED-INTEGRITY", "S05P03-SIGNED-VALIDATION", "S05P03-SIGNED-INPUT-HASHES", "S05P03-SIGNED-CODE-HASH", "S05P03-SIGNED-REPORT-HASHES", "S05P03-SIGNED-ROLLBACK-BINDING", "S05P03-SIGNED-SCHEDULE-PROOF", "S05P03-SIGNED-FAILURE-LOG", "S05P03-SIGNED-BOUNDARY"]:
            _add(checks, check_id, False, "evidence unavailable")
    rollback_ok = isinstance(rollback, Mapping) and rollback.get("evidence_id") == "EVD-S05-P03-ROLLBACK" and rollback.get("contract_id") == CONTRACT_ID and rollback.get("fixed_clock") == FIXED_CLOCK and rollback.get("status") == "PASS" and rollback.get("production_state_changed") is False and rollback.get("external_state_changed") is False and rollback.get("provider_account_api_or_page_accessed") is False and rollback.get("real_market_data_collected") is False and rollback.get("real_provider_dispatch_performed") is False and rollback.get("recommendation_or_order_generated") is False and rollback.get("incremental_cash_spent_aud") == "0.00" and set(rollback.get("artifacts", {})) == {path.as_posix() for path in ROLLBACK_ARTIFACTS} and all(row.get("status") == "PASS" for row in rollback.get("artifacts", {}).values())
    _add(checks, "S05P03-SIGNED-ROLLBACK-INTEGRITY", rollback_ok, rollback.get("status") if isinstance(rollback, Mapping) else "unavailable")
    rows = [row for row in _load_index(root) if row.get("id") == "INDEX-AC-S05-P03"]
    index_ok = len(rows) == 1 and rows[0].get("status") == "PASS" and rows[0].get("actual_artifact") == EVIDENCE_PATH.as_posix() and rows[0].get("artifact_sha256") == evidence_hash and rows[0].get("next") == "S05/P04_READY_NOT_STARTED"
    _add(checks, "S05P03-SIGNED-INDEX", index_ok, rows)
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S05_P03_SIGNED_PREFLIGHT_VALID" if not failed else "S05_P03_SIGNED_PREFLIGHT_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_sha256": evidence_hash, "rollback_sha256": rollback_hash, "next": "S05/P04_READY_NOT_STARTED" if not failed else "S05/P03_REMEDIATION_REQUIRED"}


def verify_existing_phase_evidence(root: Path, *, verify_git_history: bool = True) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    preflight = validate_signed_receipt_preflight(root, verify_git_history=verify_git_history)
    _add(checks, "S05P03-RECEIPT-PREFLIGHT", preflight.get("status") == "PASS", preflight.get("summary"))
    try:
        predecessor = verify_source_capability_evidence(root, verify_git_history=verify_git_history)
        _add(checks, "S05P03-RECEIPT-P02-PREREQUISITE", predecessor.get("status") == "PASS", predecessor.get("summary"))
    except Exception as exc:
        _add(checks, "S05P03-RECEIPT-P02-PREREQUISITE", False, "%s: %s" % (type(exc).__name__, exc))
    failed = [row["id"] for row in checks if not row["passed"]]
    return {"schema_version": "1.0.0", "contract_id": CONTRACT_ID, "status": "PASS" if not failed else "FAIL", "decision": "S05_P03_EVIDENCE_VERIFIED" if not failed else "S05_P03_EVIDENCE_INVALID_FAIL_CLOSED", "summary": {"checks": len(checks), "passed": len(checks) - len(failed), "failed": len(failed), "failed_check_ids": failed}, "checks": checks, "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": preflight.get("evidence_sha256"), "rollback_sha256": preflight.get("rollback_sha256"), "next": "S05/P04_READY_NOT_STARTED" if not failed else "S05/P03_REMEDIATION_REQUIRED"}


__all__ = [
    "AFFECTED_JUNIT_PATH",
    "CADENCE_TESTS_PATH",
    "CONTRACT_ID",
    "EVIDENCE_PATH",
    "EXPECTED_ARTIFACTS",
    "EXPECTED_NUMERIC_DELTAS",
    "EXTERNAL_EFFECT_BOUNDARY",
    "FIXTURE_PATH",
    "FULL_JUNIT_PATH",
    "JUNIT_PATH",
    "PINNED_BASELINE_HASHES",
    "PINNED_PHASE_HASHES",
    "RATE_BUDGET_PATH",
    "ROLLBACK_ARTIFACTS",
    "ROLLBACK_EVIDENCE_PATH",
    "SCHEDULER_PATH",
    "STRUCTURAL_SELF_NORMALIZED_SHA256",
    "SourceSchedulerContractError",
    "_structural_self_hash",
    "build_evidence",
    "evaluate_contract",
    "perform_rollback_drill",
    "validate_candidate_preflight",
    "validate_signed_receipt_preflight",
    "verify_existing_phase_evidence",
    "write_phase_evidence",
]
