"""Independent fail-closed acceptance oracle for ABD S09/P02.

The oracle only replays frozen synthetic tennis and combat feature histories.
It proves that feature selection is bounded by the decision timestamp and that
unavailable or unconfirmed features retain the market-only zero-residual
fallback.  It has no network, account, recommendation, order, or soak path.
"""

from __future__ import annotations

import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping

from combat_model import (
    CombatModelInputError,
    build_combat_market_anchored_prediction,
    load_feature_availability_registry as load_combat_feature_registry,
)
from generic_residual import (
    MINIMUM_MARKET_PRIOR_WEIGHT,
    PROBABILITY_SUM_TOLERANCE,
    canonical_json_bytes,
    validate_market_family_registry,
)
from tennis_model import (
    TennisModelInputError,
    build_tennis_market_anchored_prediction,
    load_feature_availability_registry as load_tennis_feature_registry,
)

from .budget import scan_dependency_budget
from .canonical_facts import sha256_file, strict_json_load


CONTRACT_ID = "AC-S09-P02"
REQUIREMENT_ID = "REQ-S09-P02"
STAGE_ID = "S09"
PHASE_ID = "P02"
VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-07-30T00:00:00+10:00"

TENNIS_PATH = Path("tennis_model.py")
COMBAT_PATH = Path("combat_model.py")
FEATURE_REGISTRY_PATH = Path("feature_availability.json")
MARKET_REGISTRY_PATH = Path("market_family_registry.json")
ORACLE_PATH = Path("abd_acceptance/tennis_combat_models.py")
CLI_PATH = Path("abd_acceptance/__main__.py")
INIT_PATH = Path("abd_acceptance/__init__.py")
TEST_PATH = Path("tests/S09/P02_test.py")
FIXTURE_PATH = Path("machine/tests/fixtures/S09_P02.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P01.json")
EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P02.json")
ROLLBACK_EVIDENCE_PATH = Path("machine/evidence/EVD-S09-P02_rollback.json")
EVIDENCE_INDEX_PATH = Path("machine/evidence/evidence_index.jsonl")
JUNIT_PATH = Path("machine/evidence/S09/P02/pytest.xml")
SCAN_REPORT_PATH = Path("machine/evidence/S09/P02/paid_dependency_scan.txt")
PACK_REPORT_PATH = Path("machine/evidence/validation_report.json")
FEATURE_FLAGS = ("model:tennis_surface_serve_return", "model:combat_rating_style_readiness")
SHARED_RUNTIME_EXCLUSIONS = (CLI_PATH, INIT_PATH)

_P01_PREDECESSOR = {
    "sha256": "46883601e3117534fa91ba8f1574c7e0e57188dccd371d0b8581f2707f4a6b6f",
    "contract_id": "AC-S09-P01",
    "status": "PASS",
    "next": "S09/P02_READY_NOT_STARTED",
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
    TENNIS_PATH,
    COMBAT_PATH,
    FEATURE_REGISTRY_PATH,
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


class TennisCombatAcceptanceError(ValueError):
    """Raised for malformed P02 evidence or a non-replayable model input."""


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
        raise TennisCombatAcceptanceError("path is outside the ABD root") from exc


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
            raise TennisCombatAcceptanceError("blank JSONL row: %d" % line_number)
        value = json.loads(line)
        if not isinstance(value, dict):
            raise TennisCombatAcceptanceError("JSONL row %d is not an object" % line_number)
        rows.append(value)
    return rows


def _row(rows: Iterable[Mapping[str, Any]], identifier: str) -> Mapping[str, Any]:
    matches = [row for row in rows if row.get("id") == identifier]
    if len(matches) != 1:
        raise TennisCombatAcceptanceError("expected exactly one id=%s" % identifier)
    return matches[0]


def _junit_summary(path: Path) -> Dict[str, int]:
    import xml.etree.ElementTree as ElementTree

    root = ElementTree.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    if not suites:
        raise TennisCombatAcceptanceError("JUnit report has no suites")
    summary = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for suite in suites:
        for key in summary:
            summary[key] += int(suite.attrib.get(key, "0"))
    return summary


def _decimal(value: Any, *, label: str) -> Decimal:
    if not isinstance(value, str):
        raise TennisCombatAcceptanceError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise TennisCombatAcceptanceError("%s is not decimal" % label) from exc
    if not parsed.is_finite():
        raise TennisCombatAcceptanceError("%s must be finite" % label)
    return parsed


def _run_case(
    row: Mapping[str, Any],
    feature_registry: Mapping[str, Any],
    market_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Mapping[str, Any]:
    model = row.get("model")
    case = row.get("input")
    if not isinstance(case, Mapping):
        raise TennisCombatAcceptanceError("fixture case input must be an object")
    if model == "tennis":
        return build_tennis_market_anchored_prediction(case, feature_registry, market_registry, parameters)
    if model == "combat":
        return build_combat_market_anchored_prediction(case, feature_registry, market_registry, parameters)
    raise TennisCombatAcceptanceError("fixture case model is unsupported")


def build_report(
    fixture: Mapping[str, Any],
    feature_registry: Mapping[str, Any],
    market_registry: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> Dict[str, Any]:
    """Replay every frozen P02 case into a canonical no-side-effect report."""

    if not isinstance(fixture, Mapping) or fixture.get("input_mode") != "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT":
        raise TennisCombatAcceptanceError("fixture must be frozen synthetic input with no network or account")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise TennisCombatAcceptanceError("fixture must contain cases")
    rendered = []
    for row in cases:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str):
            raise TennisCombatAcceptanceError("fixture case must contain case_id")
        rendered.append({"case_id": row["case_id"], "model": row.get("model"), "result": _run_case(row, feature_registry, market_registry, parameters)})
    identifiers = [row["case_id"] for row in rendered]
    if len(set(identifiers)) != len(identifiers):
        raise TennisCombatAcceptanceError("fixture case identifiers must be unique")
    rendered.sort(key=lambda row: row["case_id"])
    safe = [row for row in rendered if row["result"].get("temporal_safe") is True]
    market_only = [row for row in rendered if row["result"].get("temporal_safe") is False]
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
        "feature_registry_sha256": _sha256_bytes(_json_bytes(feature_registry)),
        "market_registry_sha256": _sha256_bytes(_json_bytes(market_registry)),
        "cases": rendered,
        "summary": {
            "case_count": len(rendered),
            "time_safe_increment_case_count": len(safe),
            "market_only_fallback_case_count": len(market_only),
            "all_time_safe_results_remain_market_anchored": all(
                _decimal(
                    row["result"].get("market_anchored_prediction", {}).get("market_prior_weight"),
                    label="market_prior_weight",
                )
                >= MINIMUM_MARKET_PRIOR_WEIGHT
                for row in safe
            ),
            "all_fallback_results_zero_residual": all(
                row["result"].get("market_anchored_prediction", {}).get("residual_weight") == "0" for row in market_only
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
            _add(checks, "S09P02-BASELINE-%s" % Path(relative).stem.upper(), False, "%s: %s" % (type(exc).__name__, exc))
            continue
        hashes[relative] = actual
        _add(checks, "S09P02-BASELINE-%s" % Path(relative).stem.upper(), actual == expected, {"expected": expected, "actual": actual})


def _check_taskpack(root: Path, checks: List[Dict[str, Any]]) -> None:
    requirements = _safe_load(root, root / "machine/facts/requirements.json", checks, "S09P02-REQUIREMENTS-STRICT-JSON")
    contracts = _safe_load(root, root / "machine/facts/acceptance_contracts.json", checks, "S09P02-CONTRACTS-STRICT-JSON")
    task_graph = _safe_load(root, root / "machine/facts/task_graph.json", checks, "S09P02-TASK-GRAPH-STRICT-JSON")
    if not isinstance(requirements, list) or not isinstance(contracts, list) or not isinstance(task_graph, Mapping):
        _add(checks, "S09P02-TASKPACK-EXACT", False, "task pack inputs malformed")
        return
    try:
        requirement = _row(requirements, REQUIREMENT_ID)
        contract = _row(contracts, CONTRACT_ID)
        tasks = task_graph.get("tasks")
        if not isinstance(tasks, list):
            raise TennisCombatAcceptanceError("task graph tasks missing")
        phase_tasks = [task for task in tasks if task.get("stage_id") == STAGE_ID and task.get("phase_id") == PHASE_ID]
        outputs = set(requirement.get("scope", []))
        task_outputs = set(item for task in phase_tasks for item in task.get("outputs", []))
        exact = (
            requirement.get("primary_acceptance_criteria_id") == CONTRACT_ID
            and requirement.get("target") == "只使用建议时已知信息，时间外推通过。"
            and outputs == {"tennis_model.py", "combat_model.py", "feature_availability.json"}
            and contract.get("requirement_id") == REQUIREMENT_ID
            and contract.get("oracle", {}).get("type") == "EXECUTABLE"
            and contract.get("oracle", {}).get("command") == "python -m abd_acceptance --contract AC-S09-P02 --evidence machine/evidence"
            and contract.get("pass_gate") == requirement.get("target")
            and [task.get("id") for task in phase_tasks] == ["T-S09-P02-01", "T-S09-P02-02", "T-S09-P02-03"]
            and outputs.issubset(task_outputs)
            and TEST_PATH.as_posix() in task_outputs
            and FIXTURE_PATH.as_posix() in task_outputs
            and EVIDENCE_PATH.as_posix() in task_outputs
            and ROLLBACK_EVIDENCE_PATH.as_posix() in task_outputs
        )
        _add(checks, "S09P02-TASKPACK-EXACT", exact, {"tasks": [task.get("id") for task in phase_tasks], "outputs": sorted(task_outputs)})
    except Exception as exc:
        _add(checks, "S09P02-TASKPACK-EXACT", False, "%s: %s" % (type(exc).__name__, exc))


def _check_p01_predecessor(root: Path, checks: List[Dict[str, Any]], hashes: MutableMapping[str, str]) -> None:
    evidence = _safe_load(root, root / P01_EVIDENCE_PATH, checks, "S09P02-P01-PREDECESSOR-STRICT-JSON")
    try:
        actual = sha256_file(root / P01_EVIDENCE_PATH)
    except Exception as exc:
        _add(checks, "S09P02-P01-PREDECESSOR-PASS", False, "%s: %s" % (type(exc).__name__, exc))
        return
    hashes[P01_EVIDENCE_PATH.as_posix()] = actual
    passed = isinstance(evidence, Mapping) and actual == _P01_PREDECESSOR["sha256"] and all(
        evidence.get(key) == value for key, value in _P01_PREDECESSOR.items() if key != "sha256"
    )
    _add(checks, "S09P02-P01-PREDECESSOR-PASS", passed, {"actual": actual, "expected": _P01_PREDECESSOR["sha256"]})


def _check_parameters(root: Path, checks: List[Dict[str, Any]]) -> Mapping[str, Any] | None:
    parameters = _safe_load(root, root / "machine/facts/parameters.json", checks, "S09P02-PARAMETERS-STRICT-JSON")
    if not isinstance(parameters, Mapping):
        return None
    market_model = parameters.get("market_model")
    expected = {
        "market_prior_weight_min": "0.50",
        "residual_weight_alpha_beta_max": "0.35",
        "residual_weight_when_no_increment": "0.00",
        "future_leakage_tolerance": 0,
    }
    exact = isinstance(market_model, Mapping) and all(market_model.get(key) == value for key, value in expected.items())
    _add(checks, "S09P02-MARKET-PRIOR-RESIDUAL-AND-TIME-PARAMETERS", exact, market_model if isinstance(market_model, Mapping) else "missing")
    return parameters


def _check_models_and_fixture(
    root: Path,
    checks: List[Dict[str, Any]],
    hashes: MutableMapping[str, str],
    parameters: Mapping[str, Any] | None,
) -> None:
    feature_registry = _safe_load(root, root / FEATURE_REGISTRY_PATH, checks, "S09P02-FEATURE-REGISTRY-STRICT-JSON")
    market_registry = _safe_load(root, root / MARKET_REGISTRY_PATH, checks, "S09P02-MARKET-REGISTRY-STRICT-JSON")
    fixture = _safe_load(root, root / FIXTURE_PATH, checks, "S09P02-FIXTURE-STRICT-JSON")
    if not isinstance(feature_registry, Mapping) or not isinstance(market_registry, Mapping) or not isinstance(fixture, Mapping) or parameters is None:
        return
    try:
        load_tennis_feature_registry(root / FEATURE_REGISTRY_PATH)
        load_combat_feature_registry(root / FEATURE_REGISTRY_PATH)
        validate_market_family_registry(market_registry)
        required_fixture_values = {
            "schema_version": "1.0.0",
            "fixture_id": "FIX-S09-P02-TENNIS-COMBAT-TIME-SAFE",
            "contract_id": CONTRACT_ID,
            "requirement_id": REQUIREMENT_ID,
            "stage_id": STAGE_ID,
            "phase_id": PHASE_ID,
            "input_mode": "FROZEN_SYNTHETIC_NO_NETWORK_NO_ACCOUNT",
            "expected_next": "S09/P03_READY_NOT_STARTED",
            "replay_count": 100,
            "adverse_replay_count": 10000,
        }
        _add(checks, "S09P02-FIXTURE-CONTRACT-EXACT", all(fixture.get(key) == value for key, value in required_fixture_values.items()), sorted(required_fixture_values))
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
        _add(checks, "S09P02-FIXTURE-NO-EXTERNAL-CLAIM", safe_claim, claim)
        report = build_report(fixture, feature_registry, market_registry, parameters)
        report_hash = _sha256_bytes(_json_bytes(report))
        _add(checks, "S09P02-REPORT-REPLAY-EXACT", fixture.get("expected_report_sha256") == report_hash, {"expected": fixture.get("expected_report_sha256"), "actual": report_hash})
        case_rows = {row["case_id"]: row for row in report["cases"]}
        expected_ids = {"TENNIS_POSITIVE", "TENNIS_BOUNDARY_AT_DECISION", "TENNIS_UNCONFIRMED", "COMBAT_POSITIVE", "COMBAT_FUTURE_REQUIRED_FEATURE"}
        _add(checks, "S09P02-EXACT-FROZEN-CASE-SET", set(case_rows) == expected_ids, sorted(case_rows))
        expected_by_id = {row.get("case_id"): row.get("expected") for row in fixture.get("cases", []) if isinstance(row, Mapping)}
        for case_id, rendered in case_rows.items():
            result = rendered.get("result")
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
            _add(checks, "S09P02-CASE-%s" % case_id, valid, result)
        tennis_base = next(row for row in fixture["cases"] if row.get("case_id") == "TENNIS_POSITIVE")
        tennis_future = deepcopy(tennis_base["input"])
        tennis_future["players"]["PLAYER_A"]["surface_dynamic_rating"].append(
            {"known_at": "2026-08-15T10:00:00.0001+10:00", "value": "3000"}
        )
        tennis_base_result = build_tennis_market_anchored_prediction(tennis_base["input"], feature_registry, market_registry, parameters)
        tennis_future_result = build_tennis_market_anchored_prediction(tennis_future, feature_registry, market_registry, parameters)
        _add(checks, "S09P02-FUTURE-OBSERVATION-EXCLUDED-FROM-TENNIS-ASOF", tennis_base_result == tennis_future_result, tennis_future_result)
        boundary = case_rows.get("TENNIS_BOUNDARY_AT_DECISION", {}).get("result", {})
        future = case_rows.get("COMBAT_FUTURE_REQUIRED_FEATURE", {}).get("result", {})
        _add(
            checks,
            "S09P02-EXACT-TIME-ALLOWED-PLUS-0001-FALLS-BACK",
            boundary.get("temporal_safe") is True
            and boundary.get("market_anchored_prediction", {}).get("residual_weight") == "0.35"
            and future.get("temporal_safe") is False
            and future.get("market_anchored_prediction", {}).get("residual_weight") == "0",
            {"boundary": boundary, "future": future},
        )
        probability_safe = True
        for rendered in report["cases"]:
            result = rendered["result"]
            prediction = result["market_anchored_prediction"]
            try:
                outcomes = prediction["outcomes"]
                total = sum((_decimal(outcome["fused_probability"], label="fused_probability") for outcome in outcomes), Decimal("0"))
                market_weight = _decimal(prediction["market_prior_weight"], label="market_prior_weight")
                probability_safe = probability_safe and abs(total - Decimal("1")) <= PROBABILITY_SUM_TOLERANCE and market_weight >= MINIMUM_MARKET_PRIOR_WEIGHT
            except Exception:
                probability_safe = False
                break
        _add(checks, "S09P02-FUSED-PROBABILITIES-COMPLETE-AND-MARKET-PRIOR-AT-LEAST-50PCT", probability_safe, report["summary"])
        for relative in (TENNIS_PATH, COMBAT_PATH, FEATURE_REGISTRY_PATH, ORACLE_PATH, TEST_PATH, FIXTURE_PATH):
            hashes[relative.as_posix()] = sha256_file(root / relative)
    except (TennisModelInputError, CombatModelInputError, TennisCombatAcceptanceError, KeyError, TypeError, ValueError) as exc:
        _add(checks, "S09P02-MODELS-AND-FIXTURE", False, "%s: %s" % (type(exc).__name__, exc))


def _check_static_boundary(root: Path, checks: List[Dict[str, Any]]) -> None:
    prohibited_imports = {"socket", "subprocess", "requests", "urllib", "http", "time", "asyncio", "os"}
    all_safe = True
    detail: Dict[str, Any] = {}
    for relative in (TENNIS_PATH, COMBAT_PATH):
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
    _add(checks, "S09P02-CORES-NO-NETWORK-PROCESS-SOAK-FLOAT-OR-ORDER-CAPABILITY", all_safe, detail)


def _check_budget(root: Path, checks: List[Dict[str, Any]]) -> None:
    scan = scan_dependency_budget(root)
    passed = scan.get("status") == "PASS" and scan.get("external_network_access_performed") is False and scan.get("external_account_or_billing_access_performed") is False
    _add(checks, "S09P02-PAID-DEPENDENCY-SCAN", passed, scan.get("summary"))


def _check_reports(root: Path, checks: List[Dict[str, Any]], *, require_test_reports: bool) -> None:
    if not require_test_reports:
        return
    try:
        junit = _junit_summary(root / JUNIT_PATH)
        junit_ok = junit["tests"] >= 18 and not junit["failures"] and not junit["errors"] and not junit["skipped"]
        _add(checks, "S09P02-TARGETED-PYTEST-REPORT", junit_ok, junit)
    except Exception as exc:
        _add(checks, "S09P02-TARGETED-PYTEST-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    try:
        scan_text = (root / SCAN_REPORT_PATH).read_text(encoding="utf-8")
        scan_ok = "STATUS: PASS" in scan_text and "PAID_OR_UNKNOWN_DEPENDENCIES: 0" in scan_text
        _add(checks, "S09P02-SCAN-REPORT", scan_ok, SCAN_REPORT_PATH.as_posix())
    except Exception as exc:
        _add(checks, "S09P02-SCAN-REPORT", False, "%s: %s" % (type(exc).__name__, exc))
    pack = _safe_load(root, root / PACK_REPORT_PATH, checks, "S09P02-PACK-REPORT-STRICT-JSON")
    _add(checks, "S09P02-PACK-REPORT-PASS", isinstance(pack, Mapping) and pack.get("status") == "PASS", pack.get("summary") if isinstance(pack, Mapping) else "unavailable")


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
        "decision": "TIME_SAFE_TENNIS_COMBAT_RESIDUALS_READY_DOWNSTREAM_GATES_REQUIRED" if status == "PASS" else "BLOCKED_FAIL_CLOSED",
        "next": "S09/P03_READY_NOT_STARTED" if status == "PASS" else "S09/P02_BLOCKED",
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
    _check_p01_predecessor(root, checks, hashes)
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
        "evidence_id": "EVD-S09-P02-ROLLBACK",
        "contract_id": CONTRACT_ID,
        "status": "PASS" if all(item["status"] == "PASS" for item in artifacts.values()) else "FAIL",
        "mode": "DISABLE_TENNIS_AND_COMBAT_SCOPED_MODEL_FLAGS_RESTORE_P01_RECEIPT_KEEP_ALL_EVIDENCE",
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
        TENNIS_PATH,
        COMBAT_PATH,
        FEATURE_REGISTRY_PATH,
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
        P01_EVIDENCE_PATH,
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
        "evidence_id": "EVD-S09-P02",
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
            "uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py --output machine/evidence/S09/P02/paid_dependency_scan.txt",
            "uv run --frozen --python 3.12 python machine/tools/validate_pack.py",
            "uv run --frozen --python 3.12 python -m pytest -q tests/S09/P02_test.py --junitxml=machine/evidence/S09/P02/pytest.xml",
            "uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S09/P02/pytest.xml",
            "uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S09-P02 --evidence machine/evidence",
            "uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py",
        ],
        "deterministic_replay": {"replay_iterations": 100, "adverse_perturbation_iterations": 10000, "real_time_wait_performed": False},
        "external_effect_boundary": dict(EXTERNAL_EFFECT_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
        "release_status": "S09_P02_LOCAL_EVIDENCE_ONLY_STAGE_REVIEW_REQUIRED_BEFORE_UPLOAD",
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
        "id": "INDEX-AC-S09-P02",
        "kind": "PHASE_EVIDENCE",
        "stage_id": STAGE_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "status": "PASS",
        "actual_artifact": EVIDENCE_PATH.as_posix(),
        "artifact_sha256": evidence_hash,
        "next": "S09/P03_READY_NOT_STARTED",
        "verified_at": FIXED_CLOCK,
    }
    output = [updated if row.get("id") == updated["id"] else row for row in rows]
    if sum(row.get("id") == updated["id"] for row in rows) != 1:
        raise TennisCombatAcceptanceError("planned S09/P02 evidence index row is missing or duplicated")
    _atomic_write(root / EVIDENCE_INDEX_PATH, b"".join(_jsonl_bytes(row) for row in output))


def write_phase_evidence(root: Path, evidence_dir: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence_dir = evidence_dir.resolve()
    if evidence_dir != (root / "machine/evidence").resolve():
        raise TennisCombatAcceptanceError("evidence directory must be the canonical machine/evidence directory")
    evidence, rollback = build_evidence(root, require_test_reports=True)
    if evidence["status"] != "PASS" or rollback["status"] != "PASS":
        raise TennisCombatAcceptanceError("cannot write evidence for a failed phase")
    _atomic_write(root / EVIDENCE_PATH, _json_bytes(evidence))
    _atomic_write(root / ROLLBACK_EVIDENCE_PATH, _json_bytes(rollback))
    _update_evidence_index(root, sha256_file(root / EVIDENCE_PATH))
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S09/P03_READY_NOT_STARTED"}


def verify_existing_phase_evidence(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    evidence = strict_json_load(root / EVIDENCE_PATH)
    rollback = strict_json_load(root / ROLLBACK_EVIDENCE_PATH)
    if not isinstance(evidence, Mapping) or not isinstance(rollback, Mapping):
        raise TennisCombatAcceptanceError("existing evidence must be objects")
    validation = evaluate_contract(root, require_test_reports=True)
    current_inputs = _input_hashes(root, require_test_reports=True)
    valid = (
        evidence.get("status") == "PASS"
        and evidence.get("contract_id") == CONTRACT_ID
        and evidence.get("decision") == "TIME_SAFE_TENNIS_COMBAT_RESIDUALS_READY_DOWNSTREAM_GATES_REQUIRED"
        and evidence.get("next") == "S09/P03_READY_NOT_STARTED"
        and evidence.get("hashes", {}).get("inputs") == current_inputs
        and evidence.get("shared_runtime_contract") == _shared_runtime_contract()
        and evidence.get("decision_sha256") == _decision_hash(evidence)
        and validation.get("status") == "PASS"
        and rollback.get("status") == "PASS"
        and rollback.get("external_state_changed") is False
        and rollback.get("feature_flags") == list(FEATURE_FLAGS)
    )
    if not valid:
        raise TennisCombatAcceptanceError("existing S09/P02 evidence is not reproducible")
    return {"contract_id": CONTRACT_ID, "status": "PASS", "evidence_path": EVIDENCE_PATH.as_posix(), "evidence_sha256": sha256_file(root / EVIDENCE_PATH), "next": "S09/P03_READY_NOT_STARTED"}
