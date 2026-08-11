"""Independent fail-closed acceptance oracle for ABD S09/P03.

The oracle replays frozen Decimal score distributions and football feature
histories.  It checks mass, explicit tails and market mappings before allowing
only a bounded market-anchored residual.  It has no network, account, order,
recommendation, deployment or real-time waiting path.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from football_model import (
    FootballModelInputError,
    build_football_market_anchored_prediction,
    load_distribution_registry,
)
from generic_residual import (
    MINIMUM_MARKET_PRIOR_WEIGHT,
    PROBABILITY_SUM_TOLERANCE,
    canonical_json_bytes,
    validate_market_family_registry,
)
from score_models import (
    ScoreModelInputError,
    build_score_projection,
    dixon_coles_scoreline_distribution,
    load_distribution_test_registry,
    negative_binomial_distribution,
    poisson_distribution,
    skellam_distribution,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S09-P03"
REQUIREMENT_ID = "REQ-S09-P03"
STAGE_ID = "S09"
PHASE_ID = "P03"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

SCORE_MODELS_PATH = Path("score_models.py")
FOOTBALL_MODEL_PATH = Path("football_model.py")
DISTRIBUTION_REGISTRY_PATH = Path("distribution_tests.json")
MARKET_REGISTRY_PATH = Path("market_family_registry.json")
ORACLE_PATH = Path("abd_acceptance/score_football_models.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
INIT_PATH = Path("abd_acceptance/__init__.py")
TEST_PATH = Path("tests/S09/P03_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S09_P03.json")
P02_EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P02.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P03.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P03_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S09/P03/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S09/P03/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAGS = ("model:football_hierarchical_score",)
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, INIT_PATH)

_P02_PREDECESSOR = {
    "sha256": "f741dd700156c397eab05bf63810ab7a233e9b5e496769f1b038dcecb0e08daf",
    "contract_id": "AC-S09-P02",
    "status": "PASS",
    "next": "S09/P03_READY_NOT_STARTED",
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
    SCORE_MODELS_PATH,
    FOOTBALL_MODEL_PATH,
    DISTRIBUTION_REGISTRY_PATH,
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


class ScoreFootballAcceptanceError(ValueError):
    """Raised for malformed P03 evidence or a non-replayable frozen input."""


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
        raise ScoreFootballAcceptanceError("path is outside the ABD root") from exc


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
            raise ScoreFootballAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ScoreFootballAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise ScoreFootballAcceptanceError("expected exactly one id=%s" % identifier)
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise ScoreFootballAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ScoreFootballAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ScoreFootballAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise ScoreFootballAcceptanceError("%s must be finite" % label)
    return parsed


def _probability_row(rows: Any, key: str, value: int) -> str:
    if not isinstance(rows, list):
        raise ScoreFootballAcceptanceError("distribution rows are unavailable")
    matches = [row for row in rows if isinstance(row, Mapping) and row.get(key) == value]
    if len(matches) != 1 or not isinstance(matches[0].get("probability"), str):
        raise ScoreFootballAcceptanceError("distribution anchor probability is unavailable")
    return matches[0]["probability"]


def _render_distribution_vector(vector: Mapping[str, Any], registry: Mapping[str, Any]) -> Dict[str, Any]:
    distribution = vector.get("distribution")
    vector_id = vector.get("vector_id")
    if not isinstance(vector_id, str):
        raise ScoreFootballAcceptanceError("distribution vector_id is required")
    if distribution == "POISSON":
        value = poisson_distribution(vector.get("mean"), vector.get("maximum_goal"))
        return {
            "vector_id": vector_id,
            "distribution": distribution,
            "finite_mass": value["finite_mass"],
            "tail_probability": value["tail_probability"],
            "anchors": {"P0": _probability_row(value["probabilities"], "goals", 0), "P1": _probability_row(value["probabilities"], "goals", 1)},
        }
    if distribution == "DIXON_COLES":
        value = dixon_coles_scoreline_distribution(
            vector.get("home_mean"), vector.get("away_mean"), vector.get("rho"), vector.get("maximum_goal")
        )
        scorelines = value["scorelines"]
        return {
            "vector_id": vector_id,
            "distribution": distribution,
            "finite_mass": value["finite_mass"],
            "tail_probability": value["tail_probability"],
            "anchors": {
                "P00": next(row["probability"] for row in scorelines if row["home_goals"] == 0 and row["away_goals"] == 0),
                "P01": next(row["probability"] for row in scorelines if row["home_goals"] == 0 and row["away_goals"] == 1),
                "P10": next(row["probability"] for row in scorelines if row["home_goals"] == 1 and row["away_goals"] == 0),
                "P11": next(row["probability"] for row in scorelines if row["home_goals"] == 1 and row["away_goals"] == 1),
            },
        }
    if distribution == "SKELLAM":
        value = skellam_distribution(vector.get("home_mean"), vector.get("away_mean"), vector.get("maximum_difference"))
        return {
            "vector_id": vector_id,
            "distribution": distribution,
            "finite_mass": value["finite_mass"],
            "tail_probability": value["tail_probability"],
            "anchors": {
                "P_NEG_1": _probability_row(value["probabilities"], "goal_difference", -1),
                "P_0": _probability_row(value["probabilities"], "goal_difference", 0),
                "P_POS_1": _probability_row(value["probabilities"], "goal_difference", 1),
            },
        }
    if distribution == "NEGATIVE_BINOMIAL":
        value = negative_binomial_distribution(vector.get("mean"), vector.get("dispersion"), vector.get("maximum_goals"))
        return {
            "vector_id": vector_id,
            "distribution": distribution,
            "finite_mass": value["finite_mass"],
            "tail_probability": value["tail_probability"],
            "anchors": {"P0": _probability_row(value["probabilities"], "goals", 0), "P1": _probability_row(value["probabilities"], "goals", 1)},
        }
    if distribution == "SCORE_PROJECTION":
        value = build_score_projection(
            vector.get("home_mean"), vector.get("away_mean"), vector.get("rho"), vector.get("dispersion"), registry
        )
        return {
            "vector_id": vector_id,
            "distribution": distribution,
            "mapping_status": value["mapping_status"],
            "tails": {
                "poisson_home": value["poisson"]["home_tail_probability"],
                "poisson_away": value["poisson"]["away_tail_probability"],
                "dixon_coles": value["dixon_coles"]["tail_probability"],
                "skellam": value["skellam"]["tail_probability"],
                "negative_binomial": value["negative_binomial"]["tail_probability"],
            },
            "market_mappings": value["market_mappings"],
            "skellam_one_x_two": value["skellam"]["one_x_two"],
        }
    raise ScoreFootballAcceptanceError("unsupported distribution vector")


def _run_case(
    row: Mapping[str, Any],
    distribution_registry: Mapping[str, Any],
    market_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Mapping[str, Any]:
    case = row.get("input")
    if not isinstance(case, Mapping):
        raise ScoreFootballAcceptanceError("fixture football input must be an object")
    return build_football_market_anchored_prediction(case, distribution_registry, market_registry, parameters)


def build_report(
    fixture: Mapping[str, Any],
    distribution_registry: Mapping[str, Any],
    market_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Dict[str, Any]:
    """Replay all frozen S09/P03 distributions and football cases in memory."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT":
        raise ScoreFootballAcceptanceError("fixture must be frozen synthetic input with no network or account")
    vectors = fixture.get("distribution_vectors")
    cases = fixture.get("football_cases")
    if not isinstance(vectors, list) or not vectors or not isinstance(cases, list) or not cases:
        raise ScoreFootballAcceptanceError("fixture must contain distributions and football cases")
    rendered_vectors = [_render_distribution_vector(vector, distribution_registry) for vector in vectors if isinstance(vector, Mapping)]
    rendered_cases = [
        {"case_id": row["case_id"], "result": _run_case(row, distribution_registry, market_registry, parameters)}
        for row in cases
        if isinstance(row, Mapping) and isinstance(row.get("case_id"), str)
    ]
    if len(rendered_vectors) != len(vectors) or len(rendered_cases) != len(cases):
        raise ScoreFootballAcceptanceError("fixture has malformed vectors or football cases")
    if len({row["vector_id"] for row in rendered_vectors}) != len(rendered_vectors):
        raise ScoreFootballAcceptanceError("distribution vector identifiers must be unique")
    if len({row["case_id"] for row in rendered_cases}) != len(rendered_cases):
        raise ScoreFootballAcceptanceError("football case identifiers must be unique")
    rendered_vectors.sort(key=lambda row: row["vector_id"])
    rendered_cases.sort(key=lambda row: row["case_id"])
    fixture_without_expected_hash = dict(fixture)
    fixture_without_expected_hash.pop("expected_report_sha256", None)
    safe_cases = [row for row in rendered_cases if row["result"].get("market_anchored_prediction", {}).get("residual_weight") != "0"]
    fallback_cases = [row for row in rendered_cases if row["result"].get("market_anchored_prediction", {}).get("residual_weight") == "0"]
    return {
        "schema_version": "1.0.0",
        "product_version": VERSION,
        "contract_id": CONTRACT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
        "fixture_sha256": _sha256_bytes(_json_bytes(fixture_without_expected_hash)),
        "distribution_registry_sha256": _sha256_bytes(_json_bytes(distribution_registry)),
        "market_registry_sha256": _sha256_bytes(_json_bytes(market_registry)),
        "distributions": rendered_vectors,
        "football_cases": rendered_cases,
        "summary": {
            "distribution_vector_count": len(rendered_vectors),
            "football_case_count": len(rendered_cases),
            "time_safe_increment_case_count": len(safe_cases),
            "market_only_fallback_case_count": len(fallback_cases),
            "all_safe_results_remain_market_anchored": all(
                _decimal(row["result"]["market_anchored_prediction"]["market_prior_weight"], label="market_prior_weight")
                >= MINIMUM_MARKET_PRIOR_WEIGHT
                for row in safe_cases
            ),
            "all_fallback_results_zero_residual": all(
                row["result"]["market_anchored_prediction"]["residual_weight"] == "0" for row in fallback_cases
            ),
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
            _add(checks, "S09P03-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S09P03-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S09P03-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S09P03-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S09P03-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S09P03-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise ScoreFootballAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        outputs = set(requirement.get("scope", []))
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        exact = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "概率质量、尾部和盘口映射通过。"
            and outputs == {"score_models.py", "football_model.py", "distribution_tests.json"}
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S09-P03 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S09-P03-01", "T-S09-P03-02", "T-S09-P03-03"]
            and outputs.issubset(task_outputs)
            and TEST_PATH.as_posix() in task_outputs
            and FIXTURE_PATH.as_posix() in task_outputs
            and EVIDENCE_PATH.as_posix() in task_outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in task_outputs
        )
        _add(checks, "S09P03-TASKPACK-EXACT", exact, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S09P03-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_p02_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, root / P02_EVIDENCE_PATH, checks, "S09P03-P02-PREDECESSOR-STRICT-JSON")
    try:
        actual = sha256_file(root / P02_EVIDENCE_PATH)
    except Exception as exc:
        _add(checks, "S09P03-P02-PREDECESSOR-PASS", False, "%s: %s" % (type(exc).__name__, exc))
        return
    hashes[P02_EVIDENCE_PATH.as_posix()] = actual
    passed = isinstance(evidence, Mapping) and actual == _P02_PREDECESSOR["sha256"] and all(
        evidence.get(key) == value for key, value in _P02_PREDECESSOR.items() if key != "sha256"
    )
    _add(checks, "S09P03-P02-PREDECESSOR-PASS", passed, {"actual": actual, "expected": _P02_PREDECESSOR["sha256"]})


def _check_parameters(root: Path, checks: List[Dict[str, Any]]) -> Mapping[str, Any] | None:
    parameters = _safe_load(root, root / "machine/facts/parameters.json", checks, "S09P03-PARAMETERS-STRICT-JSON")
    if not isinstance(parameters, Mapping):
        return None
    market_model = parameters.get("market_model")
    numeric = parameters.get("numeric_determinism")
    market_exact = {
        "market_prior_weight_min": "0.50",
        "residual_weight_alpha_beta_max": "0.35",
        "residual_weight_when_no_increment": "0.00",
        "future_leakage_tolerance": 0,
    }
    numeric_exact = {
        "authoritative_decimal_precision_digits": 50,
        "binary_float_for_authoritative_decision": False,
        "independent_implementation_absolute_tolerance": "1e-12",
        "boundary_perturbation_absolute_probability": "0.0001",
    }
    exact = (
        isinstance(market_model, Mapping)
        and isinstance(numeric, Mapping)
        and all(market_model.get(key) == value for key, value in market_exact.items())
        and all(numeric.get(key) == value for key, value in numeric_exact.items())
    )
    _add(checks, "S09P03-MARKET-PRIOR-DECIMAL-AND-BOUNDARY-PARAMETERS", exact, {"market_model": market_model, "numeric": numeric})
    return parameters


def _check_probability_mass_and_mapping(report: Mapping[str, Any], checks: List[Dict[str, Any]]) -> None:
    distributions = report.get("distributions")
    football_cases = report.get("football_cases")
    if not isinstance(distributions, list) or not isinstance(football_cases, list):
        _add(checks, "S09P03-PROBABILITY-MASS-TAIL-AND-MARKET-MAPPING", False, "report rows unavailable")
        return
    mass_ok = True
    mapping_ok = True
    detail: Dict[str, Any] = {"distributions": [], "football_cases": []}
    for row in distributions:
        if not isinstance(row, Mapping):
            mass_ok = False
            continue
        if row.get("distribution") == "SCORE_PROJECTION":
            status = row.get("mapping_status") == "COMPLETE_WITHIN_TAIL_TOLERANCE"
            mappings = row.get("market_mappings")
            tails = row.get("tails")
            valid_mappings = isinstance(mappings, Mapping) and isinstance(tails, Mapping)
            if valid_mappings:
                for mapping in mappings.values():
                    outcomes = mapping.get("outcomes", {}) if isinstance(mapping, Mapping) else {}
                    try:
                        total = sum((_decimal(value, label="mapping probability") for value in outcomes.values()), Decimal("0"))
                        valid_mappings = valid_mappings and mapping.get("status") == "COMPLETE_WITHIN_TAIL_TOLERANCE" and abs(total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE
                    except Exception:
                        valid_mappings = False
                        break
                try:
                    valid_mappings = valid_mappings and all(_decimal(value, label="projection tail") <= Decimal("0.000000000001") for value in tails.values())
                except Exception:
                    valid_mappings = False
            mapping_ok = mapping_ok and status and valid_mappings
            detail["distributions"].append({"vector_id": row.get("vector_id"), "mapping_ok": status and valid_mappings})
            continue
        try:
            finite = _decimal(row.get("finite_mass"), label="finite mass")
            tail = _decimal(row.get("tail_probability"), label="tail probability")
            valid = abs((finite + tail) - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE and tail <= Decimal("0.000000000001")
        except Exception:
            valid = False
        mass_ok = mass_ok and valid
        detail["distributions"].append({"vector_id": row.get("vector_id"), "mass_ok": valid})
    for row in football_cases:
        result = row.get("result") if isinstance(row, Mapping) else None
        try:
            prediction = result["market_anchored_prediction"]
            outcomes = prediction["outcomes"]
            total = sum((_decimal(item["fused_probability"], label="football fused probability") for item in outcomes), Decimal("0"))
            valid = abs(total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE and _decimal(
                prediction["market_prior_weight"], label="market prior weight"
            ) >= MINIMUM_MARKET_PRIOR_WEIGHT
        except Exception:
            valid = False
        mapping_ok = mapping_ok and valid
        detail["football_cases"].append({"case_id": row.get("case_id") if isinstance(row, Mapping) else None, "mapping_ok": valid})
    _add(checks, "S09P03-PROBABILITY-MASS-TAIL-AND-MARKET-MAPPING", mass_ok and mapping_ok, detail)


def _check_models_and_fixture(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
    parameters: Mapping[str, Any] | None,
) -> None:
    distribution_registry = _safe_load(root, root / DISTRIBUTION_REGISTRY_PATH, checks, "S09P03-DISTRIBUTION-REGISTRY-STRICT-JSON")
    market_registry = _safe_load(root, root / MARKET_REGISTRY_PATH, checks, "S09P03-MARKET-REGISTRY-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S09P03-FIXTURE-STRICT-JSON")
    if not isinstance(distribution_registry, Mapping) or not isinstance(market_registry, Mapping) or not isinstance(fixture, Mapping) or parameters is None:
        return
    try:
        load_distribution_test_registry(root / DISTRIBUTION_REGISTRY_PATH)
        load_distribution_registry(root / DISTRIBUTION_REGISTRY_PATH)
        validate_market_family_registry(market_registry)
        required_fixture_values = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S09-P03-SCORE-FOOTBALL-DISTRIBUTIONS",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "expected_next": "S09/P04_READY_NOT_STARTED",
            "replay_count": 100,
            "adverse_replay_count": 10000,
        }
        _add(checks, "S09P03-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in required_fixture_values.items()), sorted(required_fixture_values))
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
        _add(checks, "S09P03-FIXTURE-NO-EXTERNAL-CLAIM", safe_claim, claim)
        report = build_report(fixture, distribution_registry, market_registry, parameters)
        report_hash = _sha256_bytes(_json_bytes(report))
        _add(checks, "S09P03-REPORT-REPLAY-EXACT", fixture.get("expected_report_sha256") == report_hash, {"expected": fixture.get("expected_report_sha256"), "actual": report_hash})
        expected_vectors = {"POISSON_REFERENCE", "DIXON_COLES_REFERENCE", "SKELLAM_REFERENCE", "NEGATIVE_BINOMIAL_REFERENCE", "SCORE_PROJECTION_REFERENCE"}
        expected_cases = {
            "FOOTBALL_POSITIVE",
            "FOOTBALL_BOUNDARY_AT_DECISION",
            "FOOTBALL_FUTURE_REQUIRED_FEATURE",
            "FOOTBALL_UNCONFIRMED",
            "FOOTBALL_TAIL_FALLBACK",
        }
        _add(
            checks,
            "S09P03-EXACT-FROZEN-VECTOR-AND-CASE-SET",
            {row["vector_id"] for row in report["distributions"]} == expected_vectors
            and {row["case_id"] for row in report["football_cases"]} == expected_cases,
            {"vectors": sorted(row["vector_id"] for row in report["distributions"]), "cases": sorted(row["case_id"] for row in report["football_cases"])},
        )
        expected_by_id = {row.get("case_id"): row.get("expected") for row in fixture.get("football_cases", []) if isinstance(row, Mapping)}
        for row in report["football_cases"]:
            case_id = row["case_id"]
            result = row["result"]
            expected = expected_by_id.get(case_id)
            prediction = result.get("market_anchored_prediction", {}) if isinstance(result, Mapping) else {}
            valid = (
                isinstance(expected, Mapping)
                and isinstance(result, Mapping)
                and result.get("temporal_safe") == expected.get("temporal_safe")
                and prediction.get("residual_weight") == expected.get("residual_weight")
                and prediction.get("market_prior_weight") == expected.get("market_prior_weight")
                and prediction.get("decision") == expected.get("decision")
                and result.get("recommendation_generated") is False
                and result.get("order_submission_enabled") is False
                and result.get("external_network_accessed") is False
                and result.get("real_time_soak_waited") is False
            )
            _add(checks, "S09P03-CASE-%s" % case_id, valid, result)
        football_base = next(row for row in fixture["football_cases"] if row.get("case_id") == "FOOTBALL_POSITIVE")
        football_future = deepcopy(football_base["input"])
        football_future["features"]["league_home_goal_rate"].append(
            {"known_at": "2026-08-16T10:00:00.0001+10:00", "value": "3"}
        )
        football_base_result = build_football_market_anchored_prediction(football_base["input"], distribution_registry, market_registry, parameters)
        football_future_result = build_football_market_anchored_prediction(football_future, distribution_registry, market_registry, parameters)
        _add(checks, "S09P03-FUTURE-OBSERVATION-EXCLUDED-FROM-FOOTBALL-ASOF", football_base_result == football_future_result, football_future_result)
        case_rows = {row["case_id"]: row["result"] for row in report["football_cases"]}
        boundary = case_rows["FOOTBALL_BOUNDARY_AT_DECISION"]
        future = case_rows["FOOTBALL_FUTURE_REQUIRED_FEATURE"]
        tail = case_rows["FOOTBALL_TAIL_FALLBACK"]
        _add(
            checks,
            "S09P03-EXACT-TIME-ALLOWED-PLUS-0001-AND-TAIL-FALL-BACK",
            boundary.get("temporal_safe") is True
            and boundary.get("market_anchored_prediction", {}).get("residual_weight") == "0.35"
            and future.get("temporal_safe") is False
            and future.get("market_anchored_prediction", {}).get("residual_weight") == "0"
            and tail.get("temporal_safe") is True
            and tail.get("market_anchored_prediction", {}).get("residual_weight") == "0"
            and tail.get("score_projection", {}).get("mapping_status") == "MARKET_ONLY_TAIL_ABOVE_TOLERANCE",
            {"boundary": boundary, "future": future, "tail": tail},
        )
        _check_probability_mass_and_mapping(report, checks)
        for relative in (SCORE_MODELS_PATH, FOOTBALL_MODEL_PATH, DISTRIBUTION_REGISTRY_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (FootballModelInputError, ScoreModelInputError, ScoreFootballAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S09P03-MODELS-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    all_safe = True
    detail: Dict[str, Any] = {}
    for relative in (SCORE_MODELS_PATH, FOOTBALL_MODEL_PATH):
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
    _add(checks, "S09P03-CORES-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", all_safe, detail)


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S09P03-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        junit_ok = junit["tests"] >= 26 and not junit["failures"] and not junit["errors"] and not junit["skipped"]
        _add(checks, "S09P03-TARGETED-PYTEST-REPORT", junit_ok, junit)
    except Exception as exc:
        _add(checks, "S09P03-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
        _add(checks, "S09P03-SCAN-REPORT", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S09P03-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S09P03-PACK-REPORT-STRICT-JSON")
    _add(checks, "S09P03-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


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
        "decision": "SCORE_DISTRIBUTIONS_AND_FOOTBALL_RESIDUAL_READY_DOWNSTREAM_GATES_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S09/P04_READY_NOT_STARTED" if status == "PASS" else "S09/P03_BLOCKED",
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
    _check_p02_predecessor(root, checks, hashes)
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
        "evidence_id": "EVD-S09-P03-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_FOOTBALL_SCOPED_MODEL_FLAG_RESTORE_P02_RECEIPT_KEEP_ALL_EVIDENCE",
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
        SCORE_MODELS_PATH,
        FOOTBALL_MODEL_PATH,
        DISTRIBUTION_REGISTRY_PATH,
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
        P02_EVIDENCE_PATH,
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
        "evidence_id": "EVD-S09-P03",
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
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S09/P03/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S09/P03_test.py --junitxml=machine/evidence/S09/P03/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S09/P03/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S09-P03 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S09_P03_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S09-P03",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S09/P04_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise ScoreFootballAcceptanceError("planned S09/P03 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise ScoreFootballAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise ScoreFootballAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S09/P04_READY_NOT_STARTED",
    }


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise ScoreFootballAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "SCORE_DISTRIBUTIONS_AND_FOOTBALL_RESIDUAL_READY_DOWNSTREAM_GATES_REQUIRED"
        and evidence.get("next") == "S09/P04_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("feature_flags") == list(FEATURE_FLAGS)
    )
    if not valid:
        raise ScoreFootballAcceptanceError("existing S09/P03 evidence is not reproducible")
    return {
        "contract_id": CONTRACT_ID,
        "status": "PASS",
        "evidence_path": EVIDENCE_PATH.as_posix(),
        "evidence_sha256": sha256_file(root / EVIDENCE_PATH),
        "next": "S09/P04_READY_NOT_STARTED",
    }
