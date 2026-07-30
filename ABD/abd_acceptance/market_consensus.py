"""Independent fail-closed acceptance oracle for ABD S08/P03.

The oracle validates only frozen synthetic probabilities and the immutable P02
source-independence receipt. It never reads a live market, accesses an
account, produces advice, submits an order, or waits for elapsed wall time.
"""

from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from market_consensus import (
    CONSENSUS_ESTIMATOR,
    CONSENSUS_SPACE,
    DECIMAL_PRECISION,
    INDEPENDENT_IMPLEMENTATION_TOLERANCE,
    INPUT_MODE,
    MarketConsensusError,
    build_report,
    calculate_consensus,
    canonical_json_bytes,
)
from source_independence import SourceIndependenceError, cluster_sources

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S08-P03"
REQUIREMENT_ID = "REQ-S08-P03"
STAGE_ID = "S08"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

CORE_PATH = Path("market_consensus.py")
VECTORS_PATH = Path("consensus_vectors.json")
ORACLE_PATH = Path("abd_acceptance/market_consensus.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
BUDGET_PATH = Path("abd_acceptance/budget.py")
TEST_PATH = Path("tests/S08/P03_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S08_P03.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P02.json")
P02_CLUSTERS_PATH = Path("source_clusters.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S08-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S08/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S08/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, BUDGET_PATH)

_PREDECESSOR = {
    "sha256": "4e72c6bb9794f9b3eee7bc719c8b0f464cd149c03276752e49046e1000ca9b4c",
    "contract_id": "AC-S08-P02",
    "status": "PASS",
    "next": "S08/P03_READY_NOT_STARTED",
}
_P02_CLUSTERS_SHA256 = "4a07e67e11ee990b8e16ae649f819cfbf7ef490726fc442b981c1a451ebff54b"
_IMMUTABLE_BASELINE_HASHES = {
    "PURSUE_GOAL_PROMPT.txt": "e7625de0ec648567ea604fb1edf66f654b270cf29c06194a9313c8b186e0e8e5",
    "VERSION": "4cca2fc0530515f50d0da9fa2b782868757e182c0773fbdc0ca979b8260253b3",
    "machine/facts/canonical_facts.json": "f7008c057f317c704daca041e1f85c81c1f77b23dcdd70d38ce828aca8000385",
    "machine/facts/parameters.json": "ac8dc796247fe4b0074e5ccb722af9661c0228f13cbd44c9ffda2d8d3804d63d",
    "machine/facts/costs.json": "bf753ab094133102b31496f8f05150883b8fce94aaf6927ff85bfbf5a37d0e65",
    "machine/facts/roadmap.json": "75e2d62e734488c7c4128642dc28872edcb0160e2705dc2ccb363f69845aefeb",
    "machine/facts/requirements.json": "54d4a849ebb1266e8a01c99259f0a54728e901007657ec44e04178dcbc8bea12",
    "machine/facts/acceptance_contracts.json": "b91a48288cc3fec26233a5a0c8170d164cfec0e66e9b0f28f2012c96128d1342",
    "machine/facts/task_graph.json": "78ae36747193003a24a0d15a620664b1cb406609356242a003bf821b775cd778",
    "machine/facts/traceability_matrix.json": "e2e703bb8bd6db6bc44d0597b496d7fd5dac4a6f3c633e464c40348175a1ad1a",
}
_ROLLBACK_ARTIFACTS = (CORE_PATH, VECTORS_PATH, ORACLE_PATH, CLI_PATH, BUDGET_PATH, TEST_PATH, FIXTURE_PATH)
EXTERNAL_EFFECT_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "incremental_cash_spent_aud": "0.00",
}


class MarketConsensusAcceptanceError(ValueError):
    """Raised when the phase receipt cannot be reproduced safely."""


def _json_bytes(value: Any) -> bytes:
    return canonical_json_bytes(value)


def _jsonl_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(", ", ": ")) + "\n").encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _add(checks: List[Dict[str, Any]], identifier: str, passed: bool, detail: Any) -> None:
    checks.append({"id": identifier, "passed": bool(passed), "detail": detail})


def _portable(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise MarketConsensusAcceptanceError("path is outside the ABD root") from exc


def _safe_load(root: Path, path: Path, checks: List[Dict[str, Any]], identifier: str) -> Any:
    try:
        portable = _portable(root, path)
        value = strict_json_load(path)
    except Exception as exc:
        _add(checks, identifier, False, "%s: %s" % (type(exc).__name__, exc))
        return None
    _add(checks, identifier, True, portable)
    return value


def _strict_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not line:
            raise MarketConsensusAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise MarketConsensusAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise MarketConsensusAcceptanceError("expected exactly one id=%s" % identifier)
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise MarketConsensusAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _decimal(value: Any, *, label: str, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise MarketConsensusAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise MarketConsensusAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite() or (positive and parsed <= Decimal("0")):
        raise MarketConsensusAcceptanceError("%s is outside the accepted range" % label)
    return parsed


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _IMMUTABLE_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S08P03-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S08P03-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S08P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S08P03-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S08P03-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S08P03-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise MarketConsensusAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        outputs = set(requirement.get("scope", []))
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        passed = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "增加复制来源不改变共识；结果跨实现一致。"
            and outputs == {"market_consensus.py", "consensus_vectors.json"}
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S08-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S08-P03-01", "T-S08-P03-02", "T-S08-P03-03"]
            and {"market_consensus.py", "consensus_vectors.json"}.issubset(task_outputs)
        )
        _add(checks, "S08P03-TASKPACK-EXACT", passed, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S08P03-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, root / P02_EVIDENCE_PATH, checks, "S08P03-P02-EVIDENCE-STRICT-JSON")
    clusters = _safe_load(root, root / P02_CLUSTERS_PATH, checks, "S08P03-P02-CLUSTERS-STRICT-JSON")
    try:
        evidence_hash = sha256_file(root / P02_EVIDENCE_PATH)
        clusters_hash = sha256_file(root / P02_CLUSTERS_PATH)
        hashes[P02_EVIDENCE_PATH.as_posix()] = evidence_hash
        hashes[P02_CLUSTERS_PATH.as_posix()] = clusters_hash
        evidence_ok = isinstance(evidence, Mapping) and evidence_hash == _PREDECESSOR["sha256"] and all(
            evidence.get(key) == value for key, value in _PREDECESSOR.items() if key != "sha256"
        )
        clusters_ok = (
            isinstance(clusters, Mapping)
            and clusters_hash == _P02_CLUSTERS_SHA256
            and clusters.get("contract_id") == "AC-S08-P02"
            and clusters.get("phase_id") == "P02"
        )
        rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
        index = _row(rows, "INDEX-AC-S08-P02")
        index_ok = index.get("status") == "PASS" and index.get("artifact_sha256") == evidence_hash
        _add(checks, "S08P03-P02-RECEIPT-IMMUTABLE", evidence_ok, {"expected": _PREDECESSOR["sha256"], "actual": evidence_hash})
        _add(checks, "S08P03-P02-CLUSTERS-IMMUTABLE", clusters_ok, {"expected": _P02_CLUSTERS_SHA256, "actual": clusters_hash})
        _add(checks, "S08P03-P02-EVIDENCE-INDEX", index_ok, index)
    except Exception as exc:
        _add(checks, "S08P03-P02-PREDECESSOR-CHECK", False, "%s: %s" % (type(exc).__name__, exc))


def _check_parameter_alignment(root: Path, checks: List[Dict[str, Any]]) -> None:
    parameters = _safe_load(root, root / "machine/facts/parameters.json", checks, "S08P03-PARAMETERS-STRICT-JSON")
    if not isinstance(parameters, Mapping):
        return
    numeric = parameters.get("numeric_determinism")
    market = parameters.get("market_model")
    passed = (
        isinstance(numeric, Mapping)
        and isinstance(market, Mapping)
        and numeric.get("authoritative_decimal_precision_digits") == DECIMAL_PRECISION
        and numeric.get("binary_float_for_authoritative_decision") is False
        and numeric.get("independent_implementation_absolute_tolerance") == "1e-12"
        and numeric.get("boundary_perturbation_absolute_probability") == "0.0001"
        and market.get("consensus_space") == CONSENSUS_SPACE
        and market.get("consensus_estimator") == CONSENSUS_ESTIMATOR
    )
    _add(checks, "S08P03-PARAMETER-ALIGNMENT", passed, {"numeric_determinism": numeric, "market_model": market})


def _reference_consensus(case: Mapping[str, Any]) -> Dict[str, Decimal | int]:
    """A separate consensus implementation sharing only the P02 cluster result."""

    try:
        clusters = cluster_sources(case)
    except SourceIndependenceError as exc:
        raise MarketConsensusAcceptanceError("P02 cluster reference failed: %s" % exc) from exc
    raw_sources = case.get("sources")
    if not isinstance(raw_sources, list):
        raise MarketConsensusAcceptanceError("sources must be a list")
    probability_by_source: Dict[str, Decimal] = {}
    for index, raw in enumerate(raw_sources):
        if not isinstance(raw, Mapping) or not isinstance(raw.get("source_id"), str):
            raise MarketConsensusAcceptanceError("sources[%d] lacks source_id" % index)
        source_id = raw["source_id"]
        if source_id in probability_by_source:
            raise MarketConsensusAcceptanceError("duplicate source_id")
        probability = _decimal(raw.get("probability"), label="sources[%d].probability" % index, positive=True)
        if probability >= Decimal("1"):
            raise MarketConsensusAcceptanceError("probability must be less than one")
        probability_by_source[source_id] = probability
    with localcontext() as context:
        context.prec = DECIMAL_PRECISION
        contributions: List[tuple[Decimal, Decimal, Decimal, str]] = []
        for cluster in clusters.get("clusters", []):
            if not isinstance(cluster, Mapping):
                raise MarketConsensusAcceptanceError("cluster must be an object")
            eligible = [item for item in cluster.get("members", []) if isinstance(item, Mapping) and item.get("eligible") is True]
            if not eligible:
                continue
            probabilities = {probability_by_source.get(item.get("source_id")) for item in eligible}
            if None in probabilities or len(probabilities) != 1:
                raise MarketConsensusAcceptanceError("cluster has no single canonical probability")
            probability = next(iter(probabilities))
            if not isinstance(probability, Decimal):
                raise MarketConsensusAcceptanceError("cluster probability invalid")
            weight = sum((Decimal(str(item.get("weight"))) for item in eligible), Decimal("0"))
            expected_weight = Decimal(str(cluster.get("independent_weight")))
            if weight != expected_weight or weight <= Decimal("0"):
                raise MarketConsensusAcceptanceError("cluster independent weight invalid")
            log_odds = probability.ln() - (Decimal("1") - probability).ln()
            cluster_id = cluster.get("cluster_id")
            if not isinstance(cluster_id, str):
                raise MarketConsensusAcceptanceError("cluster id invalid")
            contributions.append((log_odds, probability, weight, cluster_id))
        if not contributions:
            raise MarketConsensusAcceptanceError("no eligible independent cluster")
        total = sum((item[2] for item in contributions), Decimal("0"))
        threshold = total / Decimal("2")
        cumulative = Decimal("0")
        for log_odds, probability, weight, _ in sorted(contributions, key=lambda item: (item[0], item[3])):
            cumulative += weight
            if cumulative >= threshold:
                return {
                    "weighted_median_logit": log_odds,
                    "consensus_probability": probability,
                    "effective_independent_weight": total,
                    "eligible_independent_cluster_count": len(contributions),
                }
    raise MarketConsensusAcceptanceError("reference weighted median unresolved")


def _check_vectors(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S08P03-FIXTURE-STRICT-JSON")
    report = _safe_load(root, root / VECTORS_PATH, checks, "S08P03-VECTORS-STRICT-JSON")
    if not isinstance(fixture, Mapping) or not isinstance(report, Mapping):
        return
    try:
        expected_report = build_report(fixture)
        _add(checks, "S08P03-VECTORS-REPLAY-EXACT", report == expected_report, "recomputed from frozen consensus fixture")
        required_fixture = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S08-P03-WEIGHTED-MEDIAN-CONSENSUS",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": INPUT_MODE,
            "expected_next": "S08/P04_READY_NOT_STARTED",
            "fixed_clock": FIXED_CLOCK,
            "replay_count": 100,
            "adverse_replay_count": 10000,
            "fixed_seed": 8003,
            "expected_oracle_check_minimum": 30,
            "predecessor_evidence_sha256": _PREDECESSOR["sha256"],
            "predecessor_source_clusters_sha256": _P02_CLUSTERS_SHA256,
            "probability_tolerance": "0.000000000001",
            "boundary_perturbation_probability": "0.0001",
            "required_consensus_space": CONSENSUS_SPACE,
            "required_consensus_estimator": CONSENSUS_ESTIMATOR,
        }
        _add(checks, "S08P03-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in required_fixture.items()), sorted(required_fixture))
        claim = fixture.get("claim_boundary")
        safe_claim = isinstance(claim, Mapping) and all(
            claim.get(key) is value
            for key, value in {
                "network_accessed": False,
                "actual_market_or_odds_observed": False,
                "recommendation_generated": False,
                "order_submission_enabled": False,
                "real_time_soak_required": False,
            }.items()
        ) and claim.get("incremental_cash_spent_aud") == "0.00"
        _add(checks, "S08P03-FIXTURE-NO-EXTERNAL-CLAIM", safe_claim, claim)
        report_boundary = report.get("external_effect_boundary")
        _add(checks, "S08P03-REPORT-BOUNDARY", report_boundary == {
            "external_network_accessed": False,
            "real_market_or_odds_observed": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        }, report_boundary)
        fixture_cases = fixture.get("cases")
        report_cases = {item.get("id"): item for item in report.get("cases", []) if isinstance(item, Mapping)}
        if not isinstance(fixture_cases, list) or len(fixture_cases) != 4:
            raise MarketConsensusAcceptanceError("exactly four frozen consensus cases are required")
        tolerance = _decimal(fixture.get("probability_tolerance"), label="probability_tolerance", positive=True)
        for fixture_case in fixture_cases:
            if not isinstance(fixture_case, Mapping) or not isinstance(fixture_case.get("id"), str):
                raise MarketConsensusAcceptanceError("fixture consensus case invalid")
            identifier = fixture_case["id"]
            expected = fixture_case.get("expected")
            actual = report_cases.get(identifier)
            if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
                _add(checks, "S08P03-CASE-%s" % identifier, False, "expected or report case missing")
                continue
            exact = (
                actual.get("consensus_probability") == expected.get("consensus_probability")
                and actual.get("eligible_independent_cluster_count") == expected.get("eligible_independent_cluster_count")
                and actual.get("effective_independent_weight") == expected.get("effective_independent_weight")
                and actual.get("consensus_space") == CONSENSUS_SPACE
                and actual.get("consensus_estimator") == CONSENSUS_ESTIMATOR
            )
            _add(checks, "S08P03-CASE-%s" % identifier, exact, {"expected": expected, "actual": actual})
            reference = _reference_consensus(fixture_case)
            reference_ok = (
                abs(_decimal(actual.get("consensus_probability"), label="actual.probability") - reference["consensus_probability"]) <= tolerance
                and abs(_decimal(actual.get("weighted_median_logit"), label="actual.logit") - reference["weighted_median_logit"]) <= tolerance
                and _decimal(actual.get("effective_independent_weight"), label="actual.weight", positive=True) == reference["effective_independent_weight"]
                and actual.get("eligible_independent_cluster_count") == reference["eligible_independent_cluster_count"]
            )
            reference_detail = {
                key: format(value, "f") if isinstance(value, Decimal) else value
                for key, value in reference.items()
            }
            _add(checks, "S08P03-CROSS-IMPLEMENTATION-%s" % identifier, reference_ok, reference_detail)
        pairs = fixture.get("equivalence_pairs")
        pair_ok = isinstance(pairs, list) and len(pairs) == 2
        if isinstance(pairs, list):
            for pair in pairs:
                baseline = report_cases.get(pair.get("baseline_id")) if isinstance(pair, Mapping) else None
                copy_variant = report_cases.get(pair.get("copy_variant_id")) if isinstance(pair, Mapping) else None
                if not isinstance(baseline, Mapping) or not isinstance(copy_variant, Mapping):
                    pair_ok = False
                    continue
                pair_ok = pair_ok and baseline.get("consensus_probability") == copy_variant.get("consensus_probability") and baseline.get("weighted_median_logit") == copy_variant.get("weighted_median_logit") and baseline.get("effective_independent_weight") == copy_variant.get("effective_independent_weight")
        _add(checks, "S08P03-COPIES-DO-NOT-CHANGE-CONSENSUS", pair_ok, pairs)
        invalid_cases = fixture.get("invalid_cases")
        invalid_ok = isinstance(invalid_cases, list) and len(invalid_cases) == 4
        if isinstance(invalid_cases, list):
            for invalid_case in invalid_cases:
                try:
                    calculate_consensus(invalid_case)
                except MarketConsensusError:
                    continue
                invalid_ok = False
        _add(checks, "S08P03-INVALID-CONSENSUS-INPUT-FAILS-CLOSED", invalid_ok, "probability bounds, divergent cluster values and unavailable clusters")
        for relative in (CORE_PATH, VECTORS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (MarketConsensusError, MarketConsensusAcceptanceError, SourceIndependenceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S08P03-VECTORS-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    try:
        source = (root / CORE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception as exc:
        _add(checks, "S08P03-CORE-PARSE", False, "%s: %s" % (type(exc).__name__, exc))
        return
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    imports = set()
    forbidden_calls: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen"}:
            forbidden_calls.append(node.func.attr)
    _add(checks, "S08P03-CORE-NO-NETWORK-PROCESS-OR-SOAK", not (imports & prohibited_imports) and not forbidden_calls, {"imports": sorted(imports), "calls": sorted(forbidden_calls)})
    float_literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]
    _add(checks, "S08P03-CORE-DECIMAL-ONLY", "float(" not in source and not float_literals, "authoritative consensus is Decimal-only")


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S08P03-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        _add(checks, "S08P03-TARGETED-PYTEST-REPORT", junit["tests"] >= 20 and not junit["failures"] and not junit["errors"] and not junit["skipped"], junit)
    except Exception as exc:
        _add(checks, "S08P03-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        _add(checks, "S08P03-SCAN-REPORT", "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S08P03-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S08P03-PACK-REPORT-STRICT-JSON")
    _add(checks, "S08P03-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


def _result(checks: List[Dict[str, Any]], hashes: Mapping[str, str]) -> Dict[str, Any]:
    failed = [check["id"] for check in checks if not check["passed"]]
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
        "decision": "MARKET_CONSENSUS_READY_OUTLIER_GATE_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S08/P04_READY_NOT_STARTED" if status == "PASS" else "S08/P03_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
        "checks": checks,
        "hashes": dict(hashes),
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }


def evaluate_contract(root: Path, require_test_reports: bool = False) -> Dict[str, Any]:
    root = root.resolve()
    checks: List[Dict[str, Any]] = []
    hashes: Dict[str, str] = {}
    _check_baseline(root, checks, hashes)
    _check_taskpack(root, checks)
    _check_predecessor(root, checks, hashes)
    _check_parameter_alignment(root, checks)
    _check_vectors(root, checks, hashes)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts = {
        relative.as_posix(): {"sha256": sha256_file(root / relative), "status": "PASS" if (root / relative).is_file() else "FAIL"}
        for relative in _ROLLBACK_ARTIFACTS
    }
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_S08_P03_CONSENSUS_DERIVATION_KEEP_P02_SOURCE_INDEPENDENCE_EVIDENCE",
        "artifacts": artifacts,
        "external_state_changed": False,
        "production_state_changed": False,
        "recommendation_generated": False,
        "order_submission_enabled": False,
        "real_time_soak_waited": False,
        "incremental_cash_spent_aud": "0.00",
    }


def _input_hashes(root: Path, *, require_test_reports: bool) -> Dict[str, str]:
    paths = [
        CORE_PATH, VECTORS_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH,
        Path("source_independence.py"), Path("abd_acceptance/source_independence.py"),
        Path("machine/facts/canonical_facts.json"), Path("machine/facts/parameters.json"), Path("machine/facts/costs.json"),
        Path("machine/facts/requirements.json"), Path("machine/facts/acceptance_contracts.json"), Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"), Path("machine/facts/roadmap.json"), P02_EVIDENCE_PATH, P02_CLUSTERS_PATH,
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "downstream dispatcher or budget-scanner evolution must not invalidate phase-owned evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    return _sha256_bytes(_json_bytes({
        "contract_id": evidence.get("contract_id"),
        "decision": evidence.get("decision"),
        "next": evidence.get("next"),
        "validation": evidence.get("validation"),
    }))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S08-P03",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": VERSION,
        "fixed_clock": FIXED_CLOCK,
        "status": validation["status"],
        "decision": validation["decision"],
        "next": validation["next"],
        "validation": validation,
        "hashes": {
            "code": sha256_file(root / ORACLE_PATH),
            "inputs": _input_hashes(root, require_test_reports=require_test_reports),
            "rollback_evidence": _sha256_bytes(_json_bytes(rollback)),
        },
        "shared_runtime_contract": _shared_runtime_contract(),
        "commands": [
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S08/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S08/P03_test.py --junitxml=machine/evidence/S08/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S08/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S08-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S08_P03_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
        "rollback": rollback,
    }
    evidence["decision_sha256"] = _decision_hash(evidence)
    return evidence, rollback


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def _update_evidence_index(root: Path, evidence_hash: str) -> None:
    rows = _strict_jsonl(root / EVIDENCE_INDEX_PATH)
    updated = {
        "id": "INDEX-AC-S08-P03",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S08/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise MarketConsensusAcceptanceError("planned S08/P03 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise MarketConsensusAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise MarketConsensusAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S08/P04_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise MarketConsensusAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    index = _row(_strict_jsonl(root / EVIDENCE_INDEX_PATH), "INDEX-AC-S08-P03")
    current_hash = sha256_file(root / EVIDENCE_PATH)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "MARKET_CONSENSUS_READY_OUTLIER_GATE_REQUIRED"
        and evidence.get("next") == "S08/P04_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and index.get("status") == "PASS"
        and index.get("artifact_sha256") == current_hash
    )
    if not valid:
        raise MarketConsensusAcceptanceError("existing S08/P03 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": current_hash, "next": "S08/P04_READY_NOT_STARTED"}
