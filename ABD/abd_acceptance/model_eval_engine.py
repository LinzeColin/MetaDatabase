"""Deterministic S16/P02 frozen capability, calibration, and return evaluator.

The evaluator computes proper-score, calibration, closing-line, and
friction-adjusted log-growth diagnostics from a pre-registered synthetic
fixture.  It is deliberately not a live market, account, recommendation, or
order interface.  A passing synthetic fixture never changes a Challenger
weight and cannot prove an empirical increment or a financial return.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, localcontext
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


CONTRACT_ID = "AC-S16-P02"
REQUIREMENT_ID = "REQ-S16-P02"
STAGE_ID = "S16"
PHASE_ID = "P02"
PRODUCT_VERSION = "0.0.0.1"
FIXED_CLOCK = "2026-08-09T00:00:00+10:00"
INPUT_MODE = "FROZEN_SYNTHETIC_EVALUATION_NO_NETWORK_NO_ACCOUNT"
FIXTURE_PATH = Path("machine/tests/fixtures/S16_P02.json")
MODEL_REGISTRY_PATH = Path("model_registry.json")
BASELINE_REPORT_PATH = Path("baseline_report.json")
CHALLENGER_REPORT_PATH = Path("challenger_report.json")
EVAL_CATALOG_PATH = Path("eval_catalog.json")
EVAL_REPORT_PATH = Path("eval_report.json")
METRICS_PATH = Path("metrics.json")
STRATEGY_SPEC_PATH = Path("machine/facts/strategy_spec.json")
P01_EVIDENCE_PATH = Path("machine/evidence/EVD-S16-P01.json")
SOURCE_ARTIFACT_ID = "ART-S16-P02-01"
CATALOG_ARTIFACT_ID = "ART-S16-P02-02"
REPORT_ARTIFACT_ID = "ART-S16-P02-03"
_IDENTIFIER = re.compile(r"[A-Z][A-Z0-9_:-]{2,79}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ZERO = Decimal("0")
_ONE = Decimal("1")

METRIC_IDS = (
    "MET-S01-P04-009",
    "MET-S01-P04-010",
    "MET-S01-P04-011",
    "MET-S01-P04-012",
    "MET-S01-P04-013",
    "MET-S01-P04-014",
    "MET-S01-P04-015",
    "MET-S01-P04-016",
)
LOWER_BOUND_METRICS = (
    "brier_skill_95pct_lower_bound",
    "logloss_skill_95pct_lower_bound",
    "closing_price_advantage_95pct_lower_bound",
    "net_log_growth_95pct_lower_bound",
)
CLAIM_BOUNDARY = {
    "external_network_accessed": False,
    "real_market_or_odds_observed": False,
    "empirical_model_increment_verified": False,
    "recommendation_generated_or_enabled": False,
    "order_submission_enabled": False,
    "real_account_balance_read_or_written": False,
    "gmail_account_or_api_accessed": False,
    "ovh_or_cloudflare_runtime_accessed": False,
    "production_deployed_or_activated": False,
    "financial_return_verified_or_guaranteed": False,
    "real_time_soak_waited": False,
    "synthetic_evaluation_only": True,
    "incremental_cash_spent_aud": "0.00",
}


class ModelEvalInputError(ValueError):
    """Raised when the frozen S16/P02 evaluation contract is malformed."""


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ModelEvalInputError("decimal result must be finite")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def strict_json_load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelEvalInputError("cannot read JSON artifact: %s" % path.as_posix()) from exc


def _closed_mapping(value: Any, fields: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ModelEvalInputError("%s fields are not exact" % label)
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ModelEvalInputError("%s must be a stable uppercase identifier" % label)
    return value


def _decimal(value: Any, label: str) -> Decimal:
    if not isinstance(value, str):
        raise ModelEvalInputError("%s must be a decimal string" % label)
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ModelEvalInputError("%s is not a decimal" % label) from exc
    if not parsed.is_finite():
        raise ModelEvalInputError("%s must be finite" % label)
    return parsed


def _probability(value: Any, label: str) -> Decimal:
    parsed = _decimal(value, label)
    if not _ZERO < parsed < _ONE:
        raise ModelEvalInputError("%s must be strictly between zero and one" % label)
    return parsed


def _positive(value: Any, label: str) -> Decimal:
    parsed = _decimal(value, label)
    if parsed <= _ZERO:
        raise ModelEvalInputError("%s must be positive" % label)
    return parsed


def _nonnegative(value: Any, label: str) -> Decimal:
    parsed = _decimal(value, label)
    if parsed < _ZERO:
        raise ModelEvalInputError("%s must be non-negative" % label)
    return parsed


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ModelEvalInputError("%s must be an integer >= %d" % (label, minimum))
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise ModelEvalInputError("%s must be ISO-8601 text" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ModelEvalInputError("%s is not ISO-8601" % label) from exc
    if parsed.tzinfo is None:
        raise ModelEvalInputError("%s must include an offset" % label)
    return parsed


def _parameters(root: Path) -> Mapping[str, Any]:
    value = strict_json_load(root / "machine/facts/parameters.json")
    if not isinstance(value, Mapping):
        raise ModelEvalInputError("parameters must be an object")
    market = value.get("market_model")
    calibration = value.get("calibration")
    if not isinstance(market, Mapping) or not isinstance(calibration, Mapping):
        raise ModelEvalInputError("market-model or calibration parameters are unavailable")
    expected_market = {
        "temporal_folds_min": 8,
        "evaluation_block_bootstrap_iterations": 2000,
        "conservative_probability_percentile": 10,
        "future_leakage_tolerance": 0,
    }
    expected_calibration = {
        "slope_min": "0.90",
        "slope_max": "1.10",
        "intercept_abs_max": "0.02",
        "calibration_error_main_max": "0.025",
        "calibration_error_niche_max": "0.04",
        "brier_skill_95pct_lower_bound": ">0",
        "logloss_skill_95pct_lower_bound": ">0",
        "closing_price_advantage_95pct_lower_bound": ">0",
        "net_log_growth_95pct_lower_bound": ">0",
    }
    if any(market.get(key) != item for key, item in expected_market.items()) or any(
        calibration.get(key) != item for key, item in expected_calibration.items()
    ):
        raise ModelEvalInputError("frozen S16/P02 parameter gates have drifted")
    return value


def _validate_metric_sources(root: Path) -> dict[str, str]:
    metrics = strict_json_load(root / METRICS_PATH)
    strategy = strict_json_load(root / STRATEGY_SPEC_PATH)
    rows = metrics.get("metrics") if isinstance(metrics, Mapping) else None
    if not isinstance(rows, list):
        raise ModelEvalInputError("metrics catalog is unavailable")
    selected = [row for row in rows if isinstance(row, Mapping) and row.get("id") in METRIC_IDS]
    if [row.get("id") for row in selected] != list(METRIC_IDS):
        raise ModelEvalInputError("required metric contract identities are unavailable")
    names = [row.get("name") for row in selected]
    if names != [
        "calibration_slope",
        "calibration_intercept_absolute",
        "calibration_error_main_market",
        "calibration_error_niche_market",
        "brier_skill_95pct_lower_bound",
        "logloss_skill_95pct_lower_bound",
        "closing_price_advantage_95pct_lower_bound",
        "net_log_growth_95pct_lower_bound",
    ]:
        raise ModelEvalInputError("metric names have drifted")
    formula = strategy.get("formulas", {}).get("ticket_log_growth") if isinstance(strategy, Mapping) else None
    if formula != "g=p_L*ln(1+f*(odds-1))+(1-p_L)*ln(1-f)":
        raise ModelEvalInputError("ticket log-growth formula has drifted")
    return {METRICS_PATH.as_posix(): sha256_file(root / METRICS_PATH), STRATEGY_SPEC_PATH.as_posix(): sha256_file(root / STRATEGY_SPEC_PATH)}


def _validate_p01_surface(root: Path, expected: Mapping[str, Any]) -> dict[str, str]:
    row = _closed_mapping(expected, {"evidence_path", "evidence_sha256", "status", "next"}, "p01_evidence")
    if (
        row["evidence_path"] != P01_EVIDENCE_PATH.as_posix()
        or not isinstance(row["evidence_sha256"], str)
        or not _SHA256.fullmatch(row["evidence_sha256"])
        or row["status"] != "PASS"
        or row["next"] != "S16/P02_READY_NOT_STARTED"
    ):
        raise ModelEvalInputError("P01 prerequisite metadata is invalid")
    receipt = strict_json_load(root / P01_EVIDENCE_PATH)
    actual_receipt_hash = sha256_file(root / P01_EVIDENCE_PATH)
    if (
        actual_receipt_hash != row["evidence_sha256"]
        or not isinstance(receipt, Mapping)
        or receipt.get("contract_id") != "AC-S16-P01"
        or receipt.get("status") != "PASS"
        or receipt.get("next") != "S16/P02_READY_NOT_STARTED"
    ):
        raise ModelEvalInputError("P01 signed receipt is not reproducible")
    input_hashes = receipt.get("hashes", {}).get("inputs") if isinstance(receipt.get("hashes"), Mapping) else None
    if not isinstance(input_hashes, Mapping):
        raise ModelEvalInputError("P01 receipt does not bind its artifacts")
    artifacts = (MODEL_REGISTRY_PATH, BASELINE_REPORT_PATH, CHALLENGER_REPORT_PATH)
    hashes = {P01_EVIDENCE_PATH.as_posix(): actual_receipt_hash}
    for path in artifacts:
        actual = sha256_file(root / path)
        if input_hashes.get(path.as_posix()) != actual:
            raise ModelEvalInputError("P01 artifact hash is not bound: %s" % path.as_posix())
        hashes[path.as_posix()] = actual
    registry = strict_json_load(root / MODEL_REGISTRY_PATH)
    if (
        not isinstance(registry, Mapping)
        or registry.get("contract_id") != "AC-S16-P01"
        or registry.get("champion", {}).get("model_id") != "MARKET_CONSENSUS_CHAMPION"
        or registry.get("champion", {}).get("active_weight") != "1.00"
        or not isinstance(registry.get("challengers"), list)
        or len(registry["challengers"]) != 6
        or any(item.get("active_weight") != "0.00" for item in registry["challengers"] if isinstance(item, Mapping))
    ):
        raise ModelEvalInputError("P01 market-champion safety surface has drifted")
    return hashes


def _validate_templates(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != 4:
        raise ModelEvalInputError("exactly four frozen aggregate cell templates are required")
    required = {
        "cell_id",
        "market_segment",
        "sample_count",
        "candidate_probability",
        "market_probability",
        "outcome_successes",
        "conservative_margin",
        "recommended_odds",
        "closing_odds",
        "stake_fraction",
        "friction_log_penalty",
    }
    templates: list[Mapping[str, Any]] = []
    identifiers: set[str] = set()
    segments: set[str] = set()
    for index, raw in enumerate(value):
        row = _closed_mapping(raw, required, "block_templates[%d]" % index)
        cell_id = _identifier(row["cell_id"], "block_templates[%d].cell_id" % index)
        if cell_id in identifiers or row["market_segment"] not in {"MAIN", "NICHE"}:
            raise ModelEvalInputError("cell identities or segments are invalid")
        count = _integer(row["sample_count"], "block_templates[%d].sample_count" % index, minimum=1)
        candidate = _probability(row["candidate_probability"], "candidate_probability")
        _probability(row["market_probability"], "market_probability")
        successes = _integer(row["outcome_successes"], "outcome_successes", minimum=0)
        margin = _nonnegative(row["conservative_margin"], "conservative_margin")
        if successes > count or candidate <= margin:
            raise ModelEvalInputError("cell outcome or conservative probability is invalid")
        recommended = _positive(row["recommended_odds"], "recommended_odds")
        closing = _positive(row["closing_odds"], "closing_odds")
        stake = _positive(row["stake_fraction"], "stake_fraction")
        _nonnegative(row["friction_log_penalty"], "friction_log_penalty")
        if recommended <= _ONE or closing <= _ONE or stake >= _ONE:
            raise ModelEvalInputError("odds and stake must remain in their safe domains")
        identifiers.add(cell_id)
        segments.add(str(row["market_segment"]))
        templates.append(row)
    if segments != {"MAIN", "NICHE"}:
        raise ModelEvalInputError("main and niche calibration segments are both required")
    return templates


def _validate_blocks(value: Any, template_count: int, temporal_folds: int) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or len(value) != temporal_folds:
        raise ModelEvalInputError("evaluation block count must equal the frozen temporal fold count")
    required = {
        "block_id",
        "start_at",
        "end_at",
        "classification",
        "candidate_probability_shift",
        "market_probability_shift",
        "outcome_success_deltas",
        "recommended_odds_multiplier",
        "closing_odds_multiplier",
    }
    blocks: list[Mapping[str, Any]] = []
    identifiers: set[str] = set()
    previous_end: datetime | None = None
    for index, raw in enumerate(value):
        row = _closed_mapping(raw, required, "evaluation_blocks[%d]" % index)
        block_id = _identifier(row["block_id"], "evaluation_blocks[%d].block_id" % index)
        start = _timestamp(row["start_at"], "evaluation_blocks[%d].start_at" % index)
        end = _timestamp(row["end_at"], "evaluation_blocks[%d].end_at" % index)
        deltas = row["outcome_success_deltas"]
        if (
            block_id in identifiers
            or start >= end
            or (previous_end is not None and start < previous_end)
            or row["classification"] != "FROZEN_SYNTHETIC_EVALUATION_NOT_EMPIRICAL"
            or not isinstance(deltas, list)
            or len(deltas) != template_count
            or any(type(item) is not int or item < -1 or item > 1 for item in deltas)
        ):
            raise ModelEvalInputError("evaluation block identity, ordering, or synthetic boundary is invalid")
        if abs(_decimal(row["candidate_probability_shift"], "candidate_probability_shift")) > Decimal("0.005") or abs(
            _decimal(row["market_probability_shift"], "market_probability_shift")
        ) > Decimal("0.005"):
            raise ModelEvalInputError("frozen probability shifts exceed the bounded fixture envelope")
        if _positive(row["recommended_odds_multiplier"], "recommended_odds_multiplier") < Decimal("0.99") or _positive(
            row["recommended_odds_multiplier"], "recommended_odds_multiplier"
        ) > Decimal("1.01"):
            raise ModelEvalInputError("recommended odds multiplier exceeds the bounded fixture envelope")
        if _positive(row["closing_odds_multiplier"], "closing_odds_multiplier") < Decimal("0.99") or _positive(
            row["closing_odds_multiplier"], "closing_odds_multiplier"
        ) > Decimal("1.01"):
            raise ModelEvalInputError("closing odds multiplier exceeds the bounded fixture envelope")
        identifiers.add(block_id)
        previous_end = end
        blocks.append(row)
    return blocks


def validate_fixture(root: Path, value: Any) -> Mapping[str, Any]:
    fields = {
        "schema_version",
        "fixture_id",
        "contract_id",
        "requirement_id",
        "stage_id",
        "phase_id",
        "product_version",
        "fixed_clock",
        "input_mode",
        "parameters_sha256",
        "p01_evidence",
        "evaluation_candidate_model_id",
        "evaluation_protocol",
        "block_templates",
        "evaluation_blocks",
        "minimum_targeted_pytest_cases",
        "expected_decision",
        "expected_next",
        "claim_boundary",
    }
    fixture = _closed_mapping(value, fields, "S16/P02 fixture")
    expected = {
        "schema_version": "1.0.0",
        "fixture_id": "FIX-S16-P02-CAPABILITY-CALIBRATION-EVALUATION",
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "evaluation_candidate_model_id": "GENERIC_RESIDUAL_CHALLENGER",
        "expected_decision": "S16_P02_SYNTHETIC_EVALUATION_LCB_GATES_PASS_P03_REDTEAM_REQUIRED",
        "expected_next": "S16/P03_READY_NOT_STARTED",
    }
    if any(fixture.get(key) != expected_value for key, expected_value in expected.items()):
        raise ModelEvalInputError("fixture identity has drifted")
    if not isinstance(fixture["parameters_sha256"], str) or fixture["parameters_sha256"] != sha256_file(root / "machine/facts/parameters.json"):
        raise ModelEvalInputError("fixture parameters hash is not bound")
    parameters = _parameters(root)
    market = parameters["market_model"]
    protocol = _closed_mapping(
        fixture["evaluation_protocol"],
        {
            "cohort_classification",
            "confidence_level",
            "lower_tail_quantile",
            "bootstrap_iterations",
            "minimum_sample_count",
            "temporal_fold_count",
            "fixed_seed",
        },
        "evaluation_protocol",
    )
    if (
        protocol["cohort_classification"] != "FROZEN_SYNTHETIC_EVALUATION_NOT_EMPIRICAL"
        or protocol["confidence_level"] != "0.95"
        or protocol["lower_tail_quantile"] != "0.05"
        or protocol["bootstrap_iterations"] != market["evaluation_block_bootstrap_iterations"]
        or protocol["minimum_sample_count"] != 2000
        or protocol["temporal_fold_count"] != market["temporal_folds_min"]
        or _integer(protocol["fixed_seed"], "fixed_seed", minimum=1) < 1
    ):
        raise ModelEvalInputError("evaluation protocol is not the frozen 95 percent lower-bound contract")
    if fixture["claim_boundary"] != CLAIM_BOUNDARY:
        raise ModelEvalInputError("fixture claim boundary has drifted")
    _integer(fixture["minimum_targeted_pytest_cases"], "minimum_targeted_pytest_cases", minimum=1)
    templates = _validate_templates(fixture["block_templates"])
    blocks = _validate_blocks(fixture["evaluation_blocks"], len(templates), int(protocol["temporal_fold_count"]))
    if sum(int(row["sample_count"]) for row in templates) * len(blocks) != int(protocol["minimum_sample_count"]):
        raise ModelEvalInputError("synthetic cohort must contain exactly the preregistered 2000 observations")
    p01_hashes = _validate_p01_surface(root, fixture["p01_evidence"])
    return {"fixture": fixture, "templates": templates, "blocks": blocks, "parameters": parameters, "p01_hashes": p01_hashes}


def load_fixture(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> Mapping[str, Any]:
    return validate_fixture(root, strict_json_load(root / fixture_path))


def _materialize_block(template_rows: Sequence[Mapping[str, Any]], block: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidate_shift = _decimal(block["candidate_probability_shift"], "candidate_probability_shift")
    market_shift = _decimal(block["market_probability_shift"], "market_probability_shift")
    recommended_multiplier = _positive(block["recommended_odds_multiplier"], "recommended_odds_multiplier")
    closing_multiplier = _positive(block["closing_odds_multiplier"], "closing_odds_multiplier")
    deltas = block["outcome_success_deltas"]
    cells: list[dict[str, Any]] = []
    for template, outcome_delta in zip(template_rows, deltas):
        count = int(template["sample_count"])
        candidate = _probability(decimal_text(_probability(template["candidate_probability"], "candidate_probability") + candidate_shift), "candidate_probability")
        market = _probability(decimal_text(_probability(template["market_probability"], "market_probability") + market_shift), "market_probability")
        successes = int(template["outcome_successes"]) + int(outcome_delta)
        conservative = candidate - _nonnegative(template["conservative_margin"], "conservative_margin")
        recommended = _positive(template["recommended_odds"], "recommended_odds") * recommended_multiplier
        closing = _positive(template["closing_odds"], "closing_odds") * closing_multiplier
        stake = _positive(template["stake_fraction"], "stake_fraction")
        penalty = _nonnegative(template["friction_log_penalty"], "friction_log_penalty")
        if successes < 0 or successes > count or conservative <= _ZERO or stake >= _ONE:
            raise ModelEvalInputError("materialized frozen cell is outside its safe evaluation domain")
        cells.append(
            {
                "cell_id": template["cell_id"],
                "market_segment": template["market_segment"],
                "sample_count": count,
                "candidate_probability": candidate,
                "market_probability": market,
                "outcome_successes": successes,
                "conservative_probability": conservative,
                "recommended_odds": recommended,
                "closing_odds": closing,
                "stake_fraction": stake,
                "friction_log_penalty": penalty,
            }
        )
    return cells


def _brier(probability: Decimal, successes: int, count: int) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return (Decimal(successes) * (_ONE - probability) ** 2 + Decimal(count - successes) * probability**2) / Decimal(count)


def _logloss(probability: Decimal, successes: int, count: int) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return -(Decimal(successes) * probability.ln() + Decimal(count - successes) * (_ONE - probability).ln()) / Decimal(count)


def _calibration_error(cells: Sequence[Mapping[str, Any]]) -> Decimal:
    if not cells:
        raise ModelEvalInputError("calibration segment has no cells")
    buckets: dict[int, dict[str, Decimal]] = {}
    for cell in cells:
        probability = cell["candidate_probability"]
        count = Decimal(cell["sample_count"])
        bucket = min(9, int((probability * Decimal("10")).to_integral_value(rounding=ROUND_FLOOR)))
        bucket_row = buckets.setdefault(bucket, {"count": _ZERO, "probability": _ZERO, "successes": _ZERO})
        bucket_row["count"] += count
        bucket_row["probability"] += probability * count
        bucket_row["successes"] += Decimal(cell["outcome_successes"])
    total = sum((row["count"] for row in buckets.values()), _ZERO)
    with localcontext() as context:
        context.prec = 50
        return sum(
            (row["count"] / total) * abs(row["successes"] / row["count"] - row["probability"] / row["count"])
            for row in buckets.values()
        )


def _block_metrics(cells: Sequence[Mapping[str, Any]]) -> dict[str, Decimal]:
    total = sum((Decimal(cell["sample_count"]) for cell in cells), _ZERO)
    if total <= _ZERO:
        raise ModelEvalInputError("evaluation block has no observations")
    with localcontext() as context:
        context.prec = 50
        candidate_brier = sum(
            _brier(cell["candidate_probability"], int(cell["outcome_successes"]), int(cell["sample_count"])) * Decimal(cell["sample_count"])
            for cell in cells
        ) / total
        market_brier = sum(
            _brier(cell["market_probability"], int(cell["outcome_successes"]), int(cell["sample_count"])) * Decimal(cell["sample_count"])
            for cell in cells
        ) / total
        candidate_logloss = sum(
            _logloss(cell["candidate_probability"], int(cell["outcome_successes"]), int(cell["sample_count"])) * Decimal(cell["sample_count"])
            for cell in cells
        ) / total
        market_logloss = sum(
            _logloss(cell["market_probability"], int(cell["outcome_successes"]), int(cell["sample_count"])) * Decimal(cell["sample_count"])
            for cell in cells
        ) / total
        closing_advantage = sum(
            (cell["recommended_odds"] / cell["closing_odds"] - _ONE) * Decimal(cell["sample_count"]) for cell in cells
        ) / total
        net_log_growth = sum(
            (
                cell["conservative_probability"] * (_ONE + cell["stake_fraction"] * (cell["recommended_odds"] - _ONE)).ln()
                + (_ONE - cell["conservative_probability"]) * (_ONE - cell["stake_fraction"]).ln()
                - cell["friction_log_penalty"]
            )
            * Decimal(cell["sample_count"])
            for cell in cells
        ) / total
        probabilities = [cell["candidate_probability"] for cell in cells]
        weights = [Decimal(cell["sample_count"]) for cell in cells]
        outcomes = [Decimal(cell["outcome_successes"]) / Decimal(cell["sample_count"]) for cell in cells]
        mean_probability = sum((probability * weight for probability, weight in zip(probabilities, weights)), _ZERO) / total
        mean_outcome = sum((outcome * weight for outcome, weight in zip(outcomes, weights)), _ZERO) / total
        variance = sum((weight * (probability - mean_probability) ** 2 for probability, weight in zip(probabilities, weights)), _ZERO)
        if variance <= _ZERO:
            raise ModelEvalInputError("calibration probability variance is zero")
        covariance = sum(
            (weight * (probability - mean_probability) * (outcome - mean_outcome) for probability, outcome, weight in zip(probabilities, outcomes, weights)),
            _ZERO,
        )
        slope = covariance / variance
        intercept = mean_outcome - slope * mean_probability
    main_cells = [cell for cell in cells if cell["market_segment"] == "MAIN"]
    niche_cells = [cell for cell in cells if cell["market_segment"] == "NICHE"]
    return {
        "candidate_brier": candidate_brier,
        "market_brier": market_brier,
        "brier_skill": market_brier - candidate_brier,
        "candidate_logloss": candidate_logloss,
        "market_logloss": market_logloss,
        "logloss_skill": market_logloss - candidate_logloss,
        "closing_price_advantage": closing_advantage,
        "net_log_growth": net_log_growth,
        "calibration_slope": slope,
        "calibration_intercept": intercept,
        "calibration_error_main": _calibration_error(main_cells),
        "calibration_error_niche": _calibration_error(niche_cells),
    }


def _bootstrap_lower_bound(values: Sequence[Decimal], *, iterations: int, fixed_seed: int) -> Decimal:
    if not values or iterations < 1:
        raise ModelEvalInputError("bootstrap requires values and iterations")
    state = fixed_seed
    count = len(values)
    draws: list[Decimal] = []
    with localcontext() as context:
        context.prec = 50
        for _ in range(iterations):
            sample_total = _ZERO
            for _ in range(count):
                state = (1664525 * state + 1013904223) & 0xFFFFFFFF
                index = ((state >> 8) * count) >> 24
                sample_total += values[index]
            draws.append(sample_total / Decimal(count))
    draws.sort()
    lower_index = (iterations * 5 + 99) // 100 - 1
    return draws[lower_index]


def _gate_payload(value: Decimal, *, threshold: str, passed: bool, source_metric_id: str) -> dict[str, Any]:
    return {"value": decimal_text(value), "threshold": threshold, "passed": bool(passed), "source_metric_id": source_metric_id}


def build_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    validated = validate_fixture(root, fixture["fixture"] if "fixture" in fixture else fixture)
    raw_fixture = validated["fixture"]
    templates = validated["templates"]
    blocks = validated["blocks"]
    parameters = validated["parameters"]
    p01_hashes = validated["p01_hashes"]
    source_hashes = _validate_metric_sources(root)
    protocol = raw_fixture["evaluation_protocol"]
    block_rows: list[dict[str, Any]] = []
    metric_vectors: dict[str, list[Decimal]] = {name: [] for name in ("brier_skill", "logloss_skill", "closing_price_advantage", "net_log_growth")}
    all_cells: list[dict[str, Any]] = []
    for block in blocks:
        cells = _materialize_block(templates, block)
        metrics = _block_metrics(cells)
        all_cells.extend(cells)
        for name in metric_vectors:
            metric_vectors[name].append(metrics[name])
        block_rows.append(
            {
                "block_id": block["block_id"],
                "start_at": block["start_at"],
                "end_at": block["end_at"],
                "classification": block["classification"],
                "sample_count": sum(cell["sample_count"] for cell in cells),
                "metrics": {name: decimal_text(value) for name, value in metrics.items()},
            }
        )
    aggregate = _block_metrics(all_cells)
    iterations = int(protocol["bootstrap_iterations"])
    seed = int(protocol["fixed_seed"])
    lcb = {
        "brier_skill_95pct_lower_bound": _bootstrap_lower_bound(metric_vectors["brier_skill"], iterations=iterations, fixed_seed=seed),
        "logloss_skill_95pct_lower_bound": _bootstrap_lower_bound(metric_vectors["logloss_skill"], iterations=iterations, fixed_seed=seed + 1),
        "closing_price_advantage_95pct_lower_bound": _bootstrap_lower_bound(metric_vectors["closing_price_advantage"], iterations=iterations, fixed_seed=seed + 2),
        "net_log_growth_95pct_lower_bound": _bootstrap_lower_bound(metric_vectors["net_log_growth"], iterations=iterations, fixed_seed=seed + 3),
    }
    calibration = parameters["calibration"]
    calibration_gates = {
        "calibration_slope": _gate_payload(
            aggregate["calibration_slope"],
            threshold="[0.90,1.10]",
            passed=Decimal(calibration["slope_min"]) <= aggregate["calibration_slope"] <= Decimal(calibration["slope_max"]),
            source_metric_id="MET-S01-P04-009",
        ),
        "calibration_intercept_absolute": _gate_payload(
            abs(aggregate["calibration_intercept"]),
            threshold="<=0.02",
            passed=abs(aggregate["calibration_intercept"]) <= Decimal(calibration["intercept_abs_max"]),
            source_metric_id="MET-S01-P04-010",
        ),
        "calibration_error_main_market": _gate_payload(
            aggregate["calibration_error_main"],
            threshold="<=0.025",
            passed=aggregate["calibration_error_main"] <= Decimal(calibration["calibration_error_main_max"]),
            source_metric_id="MET-S01-P04-011",
        ),
        "calibration_error_niche_market": _gate_payload(
            aggregate["calibration_error_niche"],
            threshold="<=0.04",
            passed=aggregate["calibration_error_niche"] <= Decimal(calibration["calibration_error_niche_max"]),
            source_metric_id="MET-S01-P04-012",
        ),
    }
    lower_bound_gates = {
        "brier_skill_95pct_lower_bound": _gate_payload(lcb["brier_skill_95pct_lower_bound"], threshold=">0", passed=lcb["brier_skill_95pct_lower_bound"] > _ZERO, source_metric_id="MET-S01-P04-013"),
        "logloss_skill_95pct_lower_bound": _gate_payload(lcb["logloss_skill_95pct_lower_bound"], threshold=">0", passed=lcb["logloss_skill_95pct_lower_bound"] > _ZERO, source_metric_id="MET-S01-P04-014"),
        "closing_price_advantage_95pct_lower_bound": _gate_payload(lcb["closing_price_advantage_95pct_lower_bound"], threshold=">0", passed=lcb["closing_price_advantage_95pct_lower_bound"] > _ZERO, source_metric_id="MET-S01-P04-015"),
        "net_log_growth_95pct_lower_bound": _gate_payload(lcb["net_log_growth_95pct_lower_bound"], threshold=">0", passed=lcb["net_log_growth_95pct_lower_bound"] > _ZERO, source_metric_id="MET-S01-P04-016"),
    }
    all_gates_pass = all(row["passed"] for row in calibration_gates.values()) and all(row["passed"] for row in lower_bound_gates.values())
    catalog = {
        "schema_version": "1.0.0",
        "artifact_id": CATALOG_ARTIFACT_ID,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "evaluation_candidate": {
            "model_id": raw_fixture["evaluation_candidate_model_id"],
            "p01_active_weight": "0.00",
            "evaluation_scope": "FROZEN_SYNTHETIC_CAPABILITY_AND_CALIBRATION_ONLY",
            "activation_status": "NOT_ACTIVATED_PENDING_S16_P03_AND_S16_P04",
        },
        "metric_contract": [
            {"metric_id": row["id"], "name": row["name"], "target": row["target"], "failure_default": row["failure_default"]}
            for row in [item for item in strict_json_load(root / METRICS_PATH)["metrics"] if item["id"] in METRIC_IDS]
        ],
        "formula_contract": {"ticket_log_growth": "g=p_L*ln(1+f*(odds-1))+(1-p_L)*ln(1-f)"},
        "frozen_protocol": dict(protocol),
        "source_hashes": {**source_hashes, **p01_hashes},
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    report = {
        "schema_version": "1.0.0",
        "artifact_id": REPORT_ARTIFACT_ID,
        "contract_id": CONTRACT_ID,
        "requirement_id": REQUIREMENT_ID,
        "stage_id": STAGE_ID,
        "phase_id": PHASE_ID,
        "product_version": PRODUCT_VERSION,
        "fixed_clock": FIXED_CLOCK,
        "input_mode": INPUT_MODE,
        "eval_catalog_sha256": artifact_sha256(catalog),
        "evaluation_scope": {
            "classification": protocol["cohort_classification"],
            "temporal_fold_count": protocol["temporal_fold_count"],
            "synthetic_observation_count": sum(cell["sample_count"] for cell in all_cells),
            "real_market_or_execution_observation_count": 0,
            "confidence_level": protocol["confidence_level"],
            "lower_tail_quantile": protocol["lower_tail_quantile"],
            "bootstrap_iterations": protocol["bootstrap_iterations"],
        },
        "block_metrics": block_rows,
        "aggregate_metrics": {name: decimal_text(value) for name, value in aggregate.items()},
        "calibration_gates": calibration_gates,
        "lower_confidence_bound_gates": lower_bound_gates,
        "gate_summary": {
            "all_95pct_lower_bound_gates_pass": all(row["passed"] for row in lower_bound_gates.values()),
            "all_calibration_gates_pass": all(row["passed"] for row in calibration_gates.values()),
            "all_s16_p02_gates_pass": all_gates_pass,
            "scope": "FROZEN_SYNTHETIC_EVALUATION_ONLY_NOT_EMPIRICAL_OR_FINANCIAL_RETURN",
        },
        "model_promotion": {
            "model_id": raw_fixture["evaluation_candidate_model_id"],
            "weight_before": "0.00",
            "weight_after": "0.00",
            "weight_change_allowed": False,
            "activation_status": "NOT_ACTIVATED_PENDING_S16_P03_AND_S16_P04",
            "next_required_gates": ["AC-S16-P03", "AC-S16-P04"],
        },
        "source_hashes": {**source_hashes, **p01_hashes},
        "claim_boundary": dict(CLAIM_BOUNDARY),
        "financial_target_status": "UNVERIFIED_NOT_GUARANTEED",
        "production_status": "NOT_DEPLOYED_OR_ACTIVATED",
    }
    return {EVAL_CATALOG_PATH.as_posix(): catalog, EVAL_REPORT_PATH.as_posix(): report}


def validate_artifacts(root: Path, fixture: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    expected = build_artifacts(root, fixture)
    for relative, value in expected.items():
        if strict_json_load(root / relative) != value:
            raise ModelEvalInputError("artifact differs from frozen local replay: %s" % relative)
    return expected


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".%s.tmp" % path.name)
    temporary.write_bytes(data)
    temporary.replace(path)


def write_artifacts(root: Path, fixture_path: Path | str = FIXTURE_PATH) -> dict[str, Mapping[str, Any]]:
    root = root.resolve()
    fixture = strict_json_load(root / fixture_path)
    artifacts = build_artifacts(root, fixture)
    for relative, value in artifacts.items():
        _atomic_write(root / relative, canonical_json_bytes(value))
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="write deterministic S16/P02 local evaluation artifacts")
    parser.add_argument("--root", default=".", help="ABD project root")
    parser.add_argument("--fixture", default=FIXTURE_PATH.as_posix(), help="fixture relative to root")
    args = parser.parse_args()
    artifacts = write_artifacts(Path(args.root), args.fixture)
    print(json.dumps({"status": "PASS", "artifacts": sorted(artifacts)}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
