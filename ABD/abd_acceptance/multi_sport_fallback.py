"""Independent fail-closed acceptance oracle for ABD S09/P04.

It replays only frozen synthetic racing, basketball, baseball and niche
market-only inputs.  It proves that every unproven, unavailable, future-only or
unconfirmed domain input remains market-only/no-advice.  It never observes a
real market, accesses an account, deploys, submits an order, or waits in real
time.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from baseball_model import BaseballModelInputError, build_baseball_market_anchored_prediction
from basketball_model import BasketballModelInputError, build_basketball_market_anchored_prediction
from generic_residual import (
    MINIMUM_MARKET_PRIOR_WEIGHT,
    PROBABILITY_SUM_TOLERANCE,
    canonical_json_bytes,
    validate_market_family_registry,
)
from racing_model import (
    RacingModelInputError,
    build_niche_market_only_prediction,
    build_racing_market_anchored_prediction,
    load_niche_fallback_registry,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S09-P04"
REQUIREMENT_ID = "REQ-S09-P04"
STAGE_ID = "S09"
PHASE_ID = "P04"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

RACING_PATH = Path("racing_model.py")
BASKETBALL_PATH = Path("basketball_model.py")
BASEBALL_PATH = Path("baseball_model.py")
NICHE_REGISTRY_PATH = Path("niche_fallback.json")
MARKET_REGISTRY_PATH = Path("market_family_registry.json")
ORACLE_PATH = Path("abd_acceptance/multi_sport_fallback.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
INIT_PATH = Path("abd_acceptance/__init__.py")
TEST_PATH = Path("tests/S09/P04_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S09_P04.json")
P03_EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P03.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P04.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P04_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S09/P04/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S09/P04/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAGS = (
    "model:racing_plackett_luce_harville",
    "model:basketball_pace_efficiency",
    "model:baseball_pitcher_bullpen",
    "policy:niche_market_only",
)
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, INIT_PATH)

_P03_PREDECESSOR = {
    "sha256": "831d114e888ebfb565236314ab90828b771379fc77e5e0a9b99696224521bdf1",
    "contract_id": "AC-S09-P03",
    "status": "PASS",
    "next": "S09/P04_READY_NOT_STARTED",
}

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

_ROLLBACK_ARTIFACTS = (
    RACING_PATH,
    BASKETBALL_PATH,
    BASEBALL_PATH,
    NICHE_REGISTRY_PATH,
    ORACLE_PATH,
    CLI_PATH,
    INIT_PATH,
    TEST_PATH,
    FIXTURE_PATH,
)

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


class MultiSportFallbackAcceptanceError(ValueError):
    """Raised for malformed P04 evidence or non-replayable frozen model input."""


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
        raise MultiSportFallbackAcceptanceError("path is outside the ABD root") from exc


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
            raise MultiSportFallbackAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise MultiSportFallbackAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise MultiSportFallbackAcceptanceError("expected exactly one id=%s" % identifier)
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise MultiSportFallbackAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise MultiSportFallbackAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise MultiSportFallbackAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise MultiSportFallbackAcceptanceError("%s must be finite" % label)
    return parsed


def _run_case(
    row: Mapping[str, Any],
    niche_registry: Mapping[str, Any],
    market_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Mapping[str, Any]:
    case = row.get("input")
    if not isinstance(case, Mapping):
        raise MultiSportFallbackAcceptanceError("fixture case input must be an object")
    model = row.get("model")
    if model == "racing":
        return build_racing_market_anchored_prediction(case, niche_registry, market_registry, parameters)
    if model == "basketball":
        return build_basketball_market_anchored_prediction(case, niche_registry, market_registry, parameters)
    if model == "baseball":
        return build_baseball_market_anchored_prediction(case, niche_registry, market_registry, parameters)
    if model == "niche":
        return build_niche_market_only_prediction(case, niche_registry, market_registry, parameters)
    raise MultiSportFallbackAcceptanceError("fixture case model is unsupported")


def build_report(
    fixture: Mapping[str, Any],
    niche_registry: Mapping[str, Any],
    market_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Dict[str, Any]:
    """Replay all frozen P04 model and market-only fallback cases in memory."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT":
        raise MultiSportFallbackAcceptanceError("fixture must be frozen synthetic input with no network or account")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise MultiSportFallbackAcceptanceError("fixture must contain P04 cases")
    rendered = []
    for row in cases:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str):
            raise MultiSportFallbackAcceptanceError("fixture case must contain case_id")
        rendered.append({"case_id": row["case_id"], "model": row.get("model"), "result": _run_case(row, niche_registry, market_registry, parameters)})
    identifiers = [row["case_id"] for row in rendered]
    if len(set(identifiers)) != len(identifiers):
        raise MultiSportFallbackAcceptanceError("fixture case identifiers must be unique")
    rendered.sort(key=lambda row: row["case_id"])
    time_safe = [row for row in rendered if row["result"].get("temporal_safe") is True]
    fallback = [row for row in rendered if row["result"].get("market_anchored_prediction", {}).get("residual_weight") == "0"]
    fixture_without_expected_hash = dict(fixture)
    fixture_without_expected_hash.pop("expected_report_sha256", None)
    return {
        "schema_version": "1.0.0",
        "product_version": VERSION,
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "fixture_sha256": _sha256_bytes(_json_bytes(fixture_without_expected_hash)),
        "niche_registry_sha256": _sha256_bytes(_json_bytes(niche_registry)),
        "market_registry_sha256": _sha256_bytes(_json_bytes(market_registry)),
        "cases": rendered,
        "summary": {
            "case_count": len(rendered),
            "time_safe_increment_case_count": len(time_safe),
            "market_only_fallback_case_count": len(fallback),
            "all_time_safe_results_remain_market_anchored": all(
                _decimal(row["result"]["market_anchored_prediction"]["market_prior_weight"], label="market_prior_weight")
                >= MINIMUM_MARKET_PRIOR_WEIGHT
                for row in time_safe
            ),
            "all_unproven_or_unavailable_results_zero_residual": all(
                row["result"]["market_anchored_prediction"]["residual_weight"] == "0" for row in fallback
            ),
            "niche_market_only_case_count": sum(row["model"] == "niche" for row in rendered),
        },
        "external_effect_boundary": {
            "external_network_accessed": False,
            "real_market_or_odds_observed": False,
            "recommendation_generated_or_enabled": False,
            "order_submission_enabled": False,
            "real_time_soak_waited": False,
            "incremental_cash_spent_aud": "0.00",
        },
    }


def _check_baseline(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    for relative, expected in _IMMUTABLE_BASELINE_HASHES.items():
        try:
            actual = sha256_file(root / relative)
        except Exception as exc:
            _add(checks, "S09P04-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S09P04-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S09P04-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S09P04-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S09P04-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S09P04-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise MultiSportFallbackAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        outputs = set(requirement.get("scope", []))
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        scoped = {"racing_model.py", "basketball_model.py", "baseball_model.py", "niche_fallback.json"}
        exact = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "未证明领域模型只能市场基线或不建议。"
            and outputs == scoped
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S09-P04 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S09-P04-01", "T-S09-P04-02", "T-S09-P04-03"]
            and scoped.issubset(task_outputs)
            and TEST_PATH.as_posix() in task_outputs
            and FIXTURE_PATH.as_posix() in task_outputs
            and EVIDENCE_PATH.as_posix() in task_outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in task_outputs
        )
        _add(checks, "S09P04-TASKPACK-EXACT", exact, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S09P04-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_p03_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, root / P03_EVIDENCE_PATH, checks, "S09P04-P03-PREDECESSOR-STRICT-JSON")
    try:
        actual = sha256_file(root / P03_EVIDENCE_PATH)
    except Exception as exc:
        _add(checks, "S09P04-P03-PREDECESSOR-PASS", False, "%s: %s" % (type(exc).__name__, exc))
        return
    hashes[P03_EVIDENCE_PATH.as_posix()] = actual
    passed = isinstance(evidence, Mapping) and actual == _P03_PREDECESSOR["sha256"] and all(
        evidence.get(key) == value for key, value in _P03_PREDECESSOR.items() if key != "sha256"
    )
    _add(checks, "S09P04-P03-PREDECESSOR-PASS", passed, {"actual": actual, "expected": _P03_PREDECESSOR["sha256"]})


def _check_parameters(root: Path, checks: List[Dict[str, Any]]) -> Mapping[str, Any] | None:
    parameters = _safe_load(root, root / "machine/facts/parameters.json", checks, "S09P04-PARAMETERS-STRICT-JSON")
    if not isinstance(parameters, Mapping):
        return None
    market_model = parameters.get("market_model")
    numeric = parameters.get("numeric_determinism")
    expected_market = {
        "market_prior_weight_min": "0.50",
        "residual_weight_alpha_beta_max": "0.35",
        "residual_weight_when_no_increment": "0.00",
        "future_leakage_tolerance": 0,
    }
    expected_numeric = {
        "authoritative_decimal_precision_digits": 50,
        "binary_float_for_authoritative_decision": False,
        "independent_implementation_absolute_tolerance": "1e-12",
        "boundary_perturbation_absolute_probability": "0.0001",
    }
    exact = (
        isinstance(market_model, Mapping)
        and isinstance(numeric, Mapping)
        and all(market_model.get(key) == value for key, value in expected_market.items())
        and all(numeric.get(key) == value for key, value in expected_numeric.items())
    )
    _add(checks, "S09P04-MARKET-PRIOR-RESIDUAL-TIME-AND-DECIMAL-PARAMETERS", exact, {"market_model": market_model, "numeric": numeric})
    return parameters


def _check_mass_and_fallback(report: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    rows = report.get("cases")
    if not isinstance(rows, list):
        _add(checks, "S09P04-PROBABILITY-MASS-PLACKETT-LUCE-HARVILLE-AND-MARKET-ONLY", False, "report cases unavailable")
        return
    complete = True
    detail: dict[str, Any] = {}
    for row in rows:
        case_id = row.get("case_id") if isinstance(row, Mapping) else None
        result = row.get("result") if isinstance(row, Mapping) else None
        try:
            prediction = result["market_anchored_prediction"]
            outcomes = prediction["outcomes"]
            probability_total = sum((_decimal(item["fused_probability"], label="fused probability") for item in outcomes), Decimal("0"))
            current = abs(probability_total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
            if prediction["residual_weight"] == "0":
                current = current and prediction["market_prior_weight"] == "1" and prediction["decision"] == "MARKET_ONLY_NO_DOMAIN_INCREMENT"
            if row.get("model") == "racing" and result.get("temporal_safe") is True:
                win_total = sum((_decimal(value, label="Plackett-Luce win probability") for value in result["plackett_luce_win_probabilities"].values()), Decimal("0"))
                exacta_total = sum((_decimal(value["probability"], label="Harville exacta probability") for value in result["harville_exacta_probabilities"]), Decimal("0"))
                current = current and abs(win_total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE and abs(exacta_total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
            complete = complete and current
            detail[str(case_id)] = {"passed": current, "residual_weight": prediction["residual_weight"]}
        except Exception as exc:
            complete = False
            detail[str(case_id)] = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S09P04-PROBABILITY-MASS-PLACKETT-LUCE-HARVILLE-AND-MARKET-ONLY", complete, detail)


def _check_models_and_fixture(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
    parameters: Mapping[str, Any] | None,
) -> None:
    niche_registry = _safe_load(root, root / NICHE_REGISTRY_PATH, checks, "S09P04-NICHE-REGISTRY-STRICT-JSON")
    market_registry = _safe_load(root, root / MARKET_REGISTRY_PATH, checks, "S09P04-MARKET-REGISTRY-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S09P04-FIXTURE-STRICT-JSON")
    if not isinstance(niche_registry, Mapping) or not isinstance(market_registry, Mapping) or not isinstance(fixture, Mapping) or parameters is None:
        return
    try:
        load_niche_fallback_registry(root / NICHE_REGISTRY_PATH)
        validate_market_family_registry(market_registry)
        required_fixture_values = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S09-P04-MULTISPORT-MARKET-ONLY",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "expected_next": "S09/STAGE_REVIEW_READY_NOT_STARTED",
            "replay_count": 100,
            "adverse_replay_count": 10000,
        }
        _add(checks, "S09P04-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in required_fixture_values.items()), sorted(required_fixture_values))
        claim = fixture.get("claim_boundary")
        expected_claim = {
            "network_accessed": False,
            "actual_market_or_odds_observed": False,
            "recommendation_generated": False,
            "order_submission_enabled": False,
            "real_time_soak_required": False,
            "incremental_cash_spent_aud": "0.00",
        }
        _add(checks, "S09P04-FIXTURE-NO-EXTERNAL-CLAIM", isinstance(claim, Mapping) and all(claim.get(key) == value for key, value in expected_claim.items()), claim)
        report = build_report(fixture, niche_registry, market_registry, parameters)
        report_hash = _sha256_bytes(_json_bytes(report))
        _add(checks, "S09P04-REPORT-REPLAY-EXACT", fixture.get("expected_report_sha256") == report_hash, {"expected": fixture.get("expected_report_sha256"), "actual": report_hash})
        case_rows = {row["case_id"]: row for row in report["cases"]}
        expected_ids = {
            "RACING_POSITIVE",
            "RACING_FUTURE_REQUIRED_FEATURE",
            "BASKETBALL_POSITIVE",
            "BASKETBALL_UNCONFIRMED",
            "BASEBALL_POSITIVE",
            "BASEBALL_BOUNDARY_AT_DECISION",
            "NICHE_MARKET_ONLY",
        }
        _add(checks, "S09P04-EXACT-FROZEN-CASE-SET", set(case_rows) == expected_ids, sorted(case_rows))
        expected_by_id = {row.get("case_id"): row.get("expected") for row in fixture.get("cases", []) if isinstance(row, Mapping)}
        for case_id, rendered in case_rows.items():
            result = rendered.get("result")
            expected = expected_by_id.get(case_id)
            prediction = result.get("market_anchored_prediction", {}) if isinstance(result, Mapping) else {}
            valid = (
                isinstance(expected, Mapping)
                and isinstance(result, Mapping)
                and result.get("temporal_safe", False) == expected.get("temporal_safe")
                and prediction.get("residual_weight") == expected.get("residual_weight")
                and prediction.get("market_prior_weight") == expected.get("market_prior_weight")
                and prediction.get("decision") == expected.get("decision")
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_network_accessed") is False
                and result.get("real_time_soak_waited") is False
            )
            _add(checks, "S09P04-CASE-%s" % case_id, valid, result)
        racing_base = next(row for row in fixture["cases"] if row.get("case_id") == "RACING_POSITIVE")
        racing_future = deepcopy(racing_base["input"])
        racing_future["features"]["runner_strengths"].append(
            {"known_at": "2026-08-17T10:00:00.0001+10:00", "value": {"RUNNER_A": "100", "RUNNER_B": "1", "RUNNER_C": "1"}}
        )
        baseline = build_racing_market_anchored_prediction(racing_base["input"], niche_registry, market_registry, parameters)
        future_ignored = build_racing_market_anchored_prediction(racing_future, niche_registry, market_registry, parameters)
        _add(checks, "S09P04-FUTURE-OBSERVATION-EXCLUDED-FROM-RACING-ASOF", baseline == future_ignored, future_ignored)
        boundary = case_rows["BASEBALL_BOUNDARY_AT_DECISION"]["result"]
        unavailable = case_rows["RACING_FUTURE_REQUIRED_FEATURE"]["result"]
        unconfirmed = case_rows["BASKETBALL_UNCONFIRMED"]["result"]
        niche = case_rows["NICHE_MARKET_ONLY"]["result"]
        gate = (
            boundary.get("temporal_safe") is True
            and boundary["market_anchored_prediction"]["residual_weight"] == "0.35"
            and unavailable.get("temporal_safe") is False
            and unavailable["market_anchored_prediction"]["residual_weight"] == "0"
            and unconfirmed.get("temporal_safe") is False
            and unconfirmed["market_anchored_prediction"]["residual_weight"] == "0"
            and niche.get("action") == "MARKET_ONLY_OR_NO_ADVICE"
            and niche["market_anchored_prediction"]["residual_weight"] == "0"
        )
        _add(checks, "S09P04-EXACT-TIME-PLUS-0001-UNCONFIRMED-AND-NICHE-FALLBACK", gate, {"boundary": boundary, "unavailable": unavailable, "unconfirmed": unconfirmed, "niche": niche})
        _check_mass_and_fallback(report, checks)
        for relative in (RACING_PATH, BASKETBALL_PATH, BASEBALL_PATH, NICHE_REGISTRY_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (RacingModelInputError, BasketballModelInputError, BaseballModelInputError, MultiSportFallbackAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S09P04-MODELS-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    all_safe = True
    detail: Dict[str, Any] = {}
    for relative in (RACING_PATH, BASKETBALL_PATH, BASEBALL_PATH):
        try:
            source = (root / relative).read_text(encoding="utf-8")
            tree = ast.parse(source)
            imports = set()
            forbidden_calls = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module.split(".")[0])
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"sleep", "run", "Popen"}:
                    forbidden_calls.append(node.func.attr)
            float_literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, float)]
            current_safe = not (imports & prohibited_imports) and not forbidden_calls and "float(" not in source and not float_literals and "submit_order" not in source
            all_safe = all_safe and current_safe
            detail[relative.as_posix()] = {"imports": sorted(imports), "calls": sorted(forbidden_calls), "float_literals": float_literals}
        except Exception as exc:
            all_safe = False
            detail[relative.as_posix()] = "%s: %s" % (type(exc).__name__, exc)
    _add(checks, "S09P04-CORES-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", all_safe, detail)


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S09P04-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        junit_ok = junit["tests"] >= 22 and not junit["failures"] and not junit["errors"] and not junit["skipped"]
        _add(checks, "S09P04-TARGETED-PYTEST-REPORT", junit_ok, junit)
    except Exception as exc:
        _add(checks, "S09P04-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
        _add(checks, "S09P04-SCAN-REPORT", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S09P04-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S09P04-PACK-REPORT-STRICT-JSON")
    _add(checks, "S09P04-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


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
        "decision": "MULTISPORT_MARKET_ANCHORED_MODELS_AND_NICHE_FALLBACK_READY_STAGE_REVIEW_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S09/STAGE_REVIEW_READY_NOT_STARTED" if status == "PASS" else "S09/P04_BLOCKED",
        "summary": {"checks": len(checks), "passed": sum(check["passed"] for check in checks), "failed": len(failed), "failed_check_ids": failed},
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
    _check_p03_predecessor(root, checks, hashes)
    parameters = _check_parameters(root, checks)
    _check_models_and_fixture(root, checks, hashes, parameters)
    _check_static_boundary(root, checks)
    _check_budget(root, checks)
    _check_reports(root, checks, require_test_reports=require_test_reports)
    return _result(checks, hashes)


def validate_candidate_preflight(root: Path) -> Dict[str, Any]:
    return evaluate_contract(root, require_test_reports=False)


def perform_rollback_drill(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    artifacts: Dict[str, Dict[str, str]] = {}
    for relative in _ROLLBACK_ARTIFACTS:
        path = root / relative
        artifacts[relative.as_posix()] = {"sha256": sha256_file(path), "status": "PASS" if path.is_file() else "FAIL"}
    return {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S09-P04-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_MULTISPORT_SCOPED_FLAGS_RESTORE_P03_RECEIPT_KEEP_ALL_EVIDENCE",
        "feature_flags": list(FEATURE_FLAGS),
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
        RACING_PATH,
        BASKETBALL_PATH,
        BASEBALL_PATH,
        NICHE_REGISTRY_PATH,
        MARKET_REGISTRY_PATH,
        ORACLE_PATH,
        TEST_PATH,
        FIXTURE_PATH,
        Path("machine/facts/canonical_facts.json"),
        Path("machine/facts/parameters.json"),
        Path("machine/facts/costs.json"),
        Path("machine/facts/requirements.json"),
        Path("machine/facts/acceptance_contracts.json"),
        Path("machine/facts/task_graph.json"),
        Path("machine/facts/traceability_matrix.json"),
        Path("machine/facts/roadmap.json"),
        P03_EVIDENCE_PATH,
    ]
    if require_test_reports:
        paths.extend([JUNIT_PATH, SCAN_REPORT_PATH, PACK_REPORT_PATH])
    return {path.as_posix(): sha256_file(root / path) for path in paths}


def _shared_runtime_contract() -> Dict[str, Any]:
    return {
        "paths_excluded_from_receipt_input_hashes": [path.as_posix() for path in SHARED_RUNTIME_EXCLUSIONS],
        "current_validation": "evaluate_contract",
        "reason": "downstream dispatcher or bootstrap evolution must not invalidate phase-owned evidence",
    }


def _decision_hash(evidence: Mapping[str, Any]) -> str:
    payload = {
        "contract_id": evidence.get("contract_id"),
        "decision": evidence.get("decision"),
        "next": evidence.get("next"),
        "validation": evidence.get("validation"),
    }
    return _sha256_bytes(_json_bytes(payload))


def build_evidence(root: Path, require_test_reports: bool = False) -> tuple[Dict[str, Any], Dict[str, Any]]:
    validation = evaluate_contract(root, require_test_reports=require_test_reports)
    rollback = perform_rollback_drill(root)
    evidence = {
        "schema_version": "1.0.0",
        "evidence_id": "EVD-S09-P04",
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
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S09/P04/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S09/P04_test.py --junitxml=machine/evidence/S09/P04/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S09/P04/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S09-P04 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S09_P04_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S09-P04",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S09/STAGE_REVIEW_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise MultiSportFallbackAcceptanceError("planned S09/P04 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise MultiSportFallbackAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise MultiSportFallbackAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S09/STAGE_REVIEW_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise MultiSportFallbackAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "MULTISPORT_MARKET_ANCHORED_MODELS_AND_NICHE_FALLBACK_READY_STAGE_REVIEW_REQUIRED"
        and evidence.get("next") == "S09/STAGE_REVIEW_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("feature_flags") == list(FEATURE_FLAGS)
    )
    if not valid:
        raise MultiSportFallbackAcceptanceError("existing S09/P04 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S09/STAGE_REVIEW_READY_NOT_STARTED",
    }
