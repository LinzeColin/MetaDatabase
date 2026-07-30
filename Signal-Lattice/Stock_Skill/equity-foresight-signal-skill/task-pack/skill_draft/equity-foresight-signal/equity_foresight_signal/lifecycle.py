from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

from .canonical import canonical_decimal, canonical_json_bytes, decimal_from, sha256_hex, strict_json_loads
from .engine import (
    BUNDLE_SCHEMA,
    DEFAULT_LIMITS,
    HEAD_STATUS_MAP,
    MATURITY_ORDER,
    RESULT_SCHEMA,
    RUNTIME_VERSION,
    STABLE_ID,
    _normalize_json_mapping,
    _parse_time,
    _require_int,
    _require_machine_id,
    _require_sha256,
    self_check,
    validate_bundle,
)
from .errors import EFSError

HEALTH_SCHEMA = "efs.health_snapshot.v1"
COMPATIBILITY_SCHEMA = "efs.bundle_compatibility_report.v1"


def _safe_error(error: EFSError) -> dict[str, str]:
    return {"code": error.code, "message_zh": error.message}


def health_snapshot(
    bundle: dict[str, Any] | str | bytes | None = None,
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic, side-effect-free health snapshot.

    The caller supplies ``as_of``. The function never reads the wall clock, opens a
    network connection, invokes an agent, or mutates host state.
    """
    result: dict[str, Any] = {
        "schema": HEALTH_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "runtime": self_check(),
        "bundle_state": "NOT_PROVIDED",
        "status": "HEALTHY_RUNTIME_ONLY",
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    if bundle is None:
        if as_of is not None:
            _parse_time(as_of, "health.as_of")
            result["as_of"] = as_of
        result["snapshot_sha256"] = sha256_hex(result)
        return result

    try:
        normalized = _normalize_json_mapping(bundle, "bundle", DEFAULT_LIMITS["bundle_bytes"])
        validation = validate_bundle(normalized)
        result.update(
            {
                "bundle_state": "VALID",
                "status": "HEALTHY",
                "bundle_id": normalized["bundle_id"],
                "bundle_sha256": validation["bundle_sha256"],
                "model_set_sha256": validation["model_set_sha256"],
                "scope_type": normalized["scope"]["type"],
                "horizons": list(normalized["horizons"]),
                "head_maturity": {
                    "baseline": normalized["baseline"]["status"],
                    "direction": normalized["calibration"]["status"],
                    "magnitude": normalized["magnitude_head"]["status"],
                    "timing": normalized["timing_head"]["status"],
                    "economic_edge": normalized["economic_edge_head"]["status"],
                    "reliability": normalized["reliability_head"]["status"],
                },
            }
        )
        if as_of is not None:
            requested = _parse_time(as_of, "health.as_of")
            result["as_of"] = as_of
            if requested < _parse_time(normalized["created_at"], "bundle.created_at"):
                result["bundle_state"] = "NOT_YET_VALID"
                result["status"] = "DEGRADED"
            elif requested > _parse_time(normalized["expires_at"], "bundle.expires_at"):
                result["bundle_state"] = "EXPIRED"
                result["status"] = "DEGRADED"
            elif requested > _parse_time(normalized["calibration"]["expires_at"], "calibration.expires_at"):
                result["bundle_state"] = "CALIBRATION_EXPIRED"
                result["status"] = "DEGRADED"
    except EFSError as error:
        result.update({"bundle_state": "INVALID", "status": "UNHEALTHY", "error": _safe_error(error)})
    except Exception:
        result.update(
            {
                "bundle_state": "INVALID",
                "status": "UNHEALTHY",
                "error": {"code": "INTERNAL_ERROR", "message_zh": "deterministic health evaluation failed"},
            }
        )
    result["snapshot_sha256"] = sha256_hex(result)
    return result


def _minimum_maturity(bundle: dict[str, Any], mode: str) -> str:
    return bundle["usage_policy"][mode]["minimum_head_status"]


def compare_candidate_to_lkg(
    candidate: dict[str, Any] | str | bytes,
    lkg: dict[str, Any] | str | bytes,
) -> dict[str, Any]:
    """Compare a candidate bundle to Last Known Good without promoting either.

    This is intentionally conservative: v0 only accepts an in-place model refresh.
    Scope, universe, labels, costs, feature contracts, horizons, calendar and usage
    gates must remain byte-equivalent. Any migration requires a new host contract.
    """
    report: dict[str, Any] = {
        "schema": COMPATIBILITY_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "compatible_for_in_place_refresh": False,
        "automatic_promotion_permitted": False,
        "blocking_reasons": [],
        "warnings": [],
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    try:
        candidate_map = _normalize_json_mapping(candidate, "candidate", DEFAULT_LIMITS["bundle_bytes"])
        lkg_map = _normalize_json_mapping(lkg, "lkg", DEFAULT_LIMITS["bundle_bytes"])
        validate_bundle(candidate_map)
        validate_bundle(lkg_map)
        report.update(
            {
                "candidate_bundle_id": candidate_map["bundle_id"],
                "candidate_bundle_sha256": candidate_map["payload_sha256"],
                "lkg_bundle_id": lkg_map["bundle_id"],
                "lkg_bundle_sha256": lkg_map["payload_sha256"],
            }
        )
        exact_fields = (
            "schema",
            "stable_id",
            "runtime_version",
            "scope",
            "horizons",
            "calendar_id",
            "label_contract",
            "cost_contract",
            "feature_contracts",
            "usage_policy",
        )
        for field in exact_fields:
            if canonical_json_bytes(candidate_map[field]) != canonical_json_bytes(lkg_map[field]):
                report["blocking_reasons"].append(f"INCOMPATIBLE_{field.upper()}")

        if candidate_map["created_at"] < lkg_map["created_at"]:
            report["blocking_reasons"].append("CANDIDATE_CREATED_AT_REGRESSION")
        if candidate_map["expires_at"] <= candidate_map["created_at"]:
            report["blocking_reasons"].append("CANDIDATE_VALIDITY_WINDOW_INVALID")
        if candidate_map["payload_sha256"] == lkg_map["payload_sha256"]:
            report["warnings"].append("CANDIDATE_IDENTICAL_TO_LKG")

        for mode in ("RESEARCH", "SHADOW", "DECISION_SUPPORT"):
            candidate_required = _minimum_maturity(candidate_map, mode)
            lkg_required = _minimum_maturity(lkg_map, mode)
            if MATURITY_ORDER[candidate_required] < MATURITY_ORDER[lkg_required]:
                report["blocking_reasons"].append(f"USAGE_GATE_WEAKENED_{mode}")

        report["compatible_for_in_place_refresh"] = not report["blocking_reasons"]
        report["decision"] = "COMPATIBLE_REVIEW_REQUIRED" if report["compatible_for_in_place_refresh"] else "REJECT_IN_PLACE_REFRESH"
    except EFSError as error:
        report["blocking_reasons"].append(error.code)
        report["error"] = _safe_error(error)
        report["decision"] = "REJECT_INVALID_INPUT"
    except Exception:
        report["blocking_reasons"].append("INTERNAL_ERROR")
        report["error"] = {"code": "INTERNAL_ERROR", "message_zh": "deterministic compatibility comparison failed"}
        report["decision"] = "REJECT_INTERNAL_ERROR"
    report["report_sha256"] = sha256_hex(report)
    return report

PROMOTION_DECISION_SCHEMA = "efs.promotion_decision.v1"
VALIDATION_REPORT_SCHEMA = "efs.validation_report.v1"
_PROMOTION_DECISION_KEYS = {
    "schema", "stable_id", "runtime_version", "intended_mode",
    "eligible_for_separate_host_approval", "automatic_promotion_permitted",
    "blocking_reasons", "warnings", "agent_invocations_total",
    "llm_requests_total", "llm_input_tokens_total", "llm_output_tokens_total",
    "network_requests_total", "compatibility_report_sha256",
    "candidate_bundle_sha256", "lkg_bundle_sha256", "oos_report_sha256",
    "untouched_holdout_report_sha256", "decision", "error", "decision_sha256",
}
_VALIDATION_REPORT_KEYS = {
    "schema", "policy_id", "policy_sha256", "subject_model_set_sha256",
    "trial_manifest_sha256", "dataset_snapshot_sha256", "evaluation_role",
    "evaluation_as_of", "horizon", "record_count", "cluster_count",
    "evaluation_start", "evaluation_end", "records_sha256", "direction",
    "magnitude", "timing", "economic_edge", "automatic_promotion_permitted",
    "promotion_semantics", "agent_invocations_total", "llm_requests_total",
    "llm_input_tokens_total", "llm_output_tokens_total", "network_requests_total",
    "overall_status", "report_sha256",
}

_SECTION_STATUS = {"PASS", "FAIL", "INSUFFICIENT_SUPPORT"}


def _exact_mapping(value: Any, *, field: str, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EFSError("CONTRACT_INVALID", f"{field} shape mismatch")
    return value


def _boolean_checks(value: Any, *, field: str, keys: set[str]) -> dict[str, bool]:
    checks = _exact_mapping(value, field=field, keys=keys)
    if any(not isinstance(checks[key], bool) for key in keys):
        raise EFSError("CONTRACT_INVALID", f"{field} values must be boolean")
    return checks


def _section_status(value: Any, checks: dict[str, bool], *, field: str) -> str:
    if not isinstance(value, str) or value not in _SECTION_STATUS:
        raise EFSError("CONTRACT_INVALID", f"{field}.status is invalid")
    expected = "INSUFFICIENT_SUPPORT" if checks.get("support") is False else ("PASS" if all(checks.values()) else "FAIL")
    if value != expected:
        raise EFSError("CONTRACT_INVALID", f"{field}.status conflicts with checks")
    return value


def _non_negative_decimal(value: Any, *, field: str) -> Decimal:
    result = decimal_from(value, field)
    if result < 0:
        raise EFSError("CONTRACT_INVALID", f"{field} must be non-negative")
    return result


def _validate_report_sections(report: dict[str, Any]) -> None:
    direction = _exact_mapping(
        report.get("direction"),
        field="validation report.direction",
        keys={
            "status", "checks", "model_brier", "baseline_brier", "brier_skill",
            "auc", "ece", "monotonicity_violations", "calibration_bins",
        },
    )
    direction_checks = _boolean_checks(
        direction.get("checks"),
        field="validation report.direction.checks",
        keys={"support", "brier_skill", "auc", "ece", "monotonicity"},
    )
    _section_status(direction.get("status"), direction_checks, field="validation report.direction")
    _non_negative_decimal(direction.get("model_brier"), field="validation report.direction.model_brier")
    _non_negative_decimal(direction.get("baseline_brier"), field="validation report.direction.baseline_brier")
    if direction.get("brier_skill") is not None:
        decimal_from(direction.get("brier_skill"), "validation report.direction.brier_skill")
    if direction.get("auc") is not None:
        auc = decimal_from(direction.get("auc"), "validation report.direction.auc")
        if auc < 0 or auc > 1:
            raise EFSError("CONTRACT_INVALID", "validation report.direction.auc must be between zero and one")
    ece = decimal_from(direction.get("ece"), "validation report.direction.ece")
    if ece < 0 or ece > 1:
        raise EFSError("CONTRACT_INVALID", "validation report.direction.ece must be between zero and one")
    _require_int(
        direction.get("monotonicity_violations"),
        "validation report.direction.monotonicity_violations",
        minimum=0,
        maximum=50,
    )
    bins = direction.get("calibration_bins")
    if not isinstance(bins, list) or len(bins) > 50:
        raise EFSError("CONTRACT_INVALID", "validation report.direction.calibration_bins is invalid")
    total_bin_count = 0
    previous_upper = Decimal(0)
    for index, raw_bin in enumerate(bins):
        item = _exact_mapping(
            raw_bin,
            field=f"validation report.direction.calibration_bins[{index}]",
            keys={"lower", "upper", "count", "mean_prediction", "observed_rate", "absolute_gap"},
        )
        lower = decimal_from(item.get("lower"), f"validation report.direction.calibration_bins[{index}].lower")
        upper = decimal_from(item.get("upper"), f"validation report.direction.calibration_bins[{index}].upper")
        if lower < 0 or upper > 1 or lower >= upper or lower < previous_upper:
            raise EFSError("CONTRACT_INVALID", "validation report calibration-bin bounds are invalid")
        previous_upper = upper
        count = _require_int(
            item.get("count"),
            f"validation report.direction.calibration_bins[{index}].count",
            minimum=1,
            maximum=100_000_000,
        )
        total_bin_count += count
        for key in ("mean_prediction", "observed_rate", "absolute_gap"):
            value = decimal_from(item.get(key), f"validation report.direction.calibration_bins[{index}].{key}")
            if value < 0 or value > 1:
                raise EFSError("CONTRACT_INVALID", "validation report calibration-bin probability is invalid")
    if total_bin_count != report["record_count"]:
        raise EFSError("CONTRACT_INVALID", "validation report calibration-bin counts do not match record_count")

    magnitude = _exact_mapping(
        report.get("magnitude"),
        field="validation report.magnitude",
        keys={"status", "checks", "p10_p90_coverage", "pinball_loss"},
    )
    magnitude_checks = _boolean_checks(
        magnitude.get("checks"),
        field="validation report.magnitude.checks",
        keys={"support", "coverage_lower", "coverage_upper"},
    )
    _section_status(magnitude.get("status"), magnitude_checks, field="validation report.magnitude")
    coverage = decimal_from(magnitude.get("p10_p90_coverage"), "validation report.magnitude.p10_p90_coverage")
    if coverage < 0 or coverage > 1:
        raise EFSError("CONTRACT_INVALID", "validation report magnitude coverage must be between zero and one")
    pinball = _exact_mapping(
        magnitude.get("pinball_loss"),
        field="validation report.magnitude.pinball_loss",
        keys={"p10", "p50", "p90"},
    )
    for key in ("p10", "p50", "p90"):
        _non_negative_decimal(pinball.get(key), field=f"validation report.magnitude.pinball_loss.{key}")

    timing = _exact_mapping(
        report.get("timing"),
        field="validation report.timing",
        keys={"status", "checks", "multiclass_brier"},
    )
    timing_checks = _boolean_checks(
        timing.get("checks"),
        field="validation report.timing.checks",
        keys={"support", "brier"},
    )
    _section_status(timing.get("status"), timing_checks, field="validation report.timing")
    _non_negative_decimal(timing.get("multiclass_brier"), field="validation report.timing.multiclass_brier")

    economic = _exact_mapping(
        report.get("economic_edge"),
        field="validation report.economic_edge",
        keys={
            "status", "checks", "mean_net_return_1x_cost",
            "mean_net_return_stressed_cost", "cost_stress_multiplier",
        },
    )
    economic_checks = _boolean_checks(
        economic.get("checks"),
        field="validation report.economic_edge.checks",
        keys={"support", "stressed_mean"},
    )
    _section_status(economic.get("status"), economic_checks, field="validation report.economic_edge")
    decimal_from(economic.get("mean_net_return_1x_cost"), "validation report.economic_edge.mean_net_return_1x_cost")
    decimal_from(
        economic.get("mean_net_return_stressed_cost"),
        "validation report.economic_edge.mean_net_return_stressed_cost",
    )
    multiplier = decimal_from(
        economic.get("cost_stress_multiplier"),
        "validation report.economic_edge.cost_stress_multiplier",
    )
    if multiplier < 1:
        raise EFSError("CONTRACT_INVALID", "validation report cost stress multiplier must be at least one")

    expected_overall = "PASS" if all(
        report[key]["status"] == "PASS" for key in ("direction", "magnitude", "timing", "economic_edge")
    ) else "FAIL"
    if report.get("overall_status") != expected_overall:
        raise EFSError("CONTRACT_INVALID", "validation report overall status conflicts with section status")


def _validation_report(value: dict[str, Any] | str | bytes, field: str) -> dict[str, Any]:
    report = _normalize_json_mapping(value, field, 2_000_000)
    unknown = sorted(set(report) - _VALIDATION_REPORT_KEYS)
    if unknown:
        raise EFSError("CONTRACT_INVALID", f"{field} contains unknown keys")
    if report.get("schema") != VALIDATION_REPORT_SCHEMA:
        raise EFSError("CONTRACT_INVALID", f"{field} has unsupported schema")
    claimed = report.get("report_sha256")
    if not isinstance(claimed, str) or len(claimed) != 64:
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", f"{field} lacks report SHA-256")
    payload = copy.deepcopy(report)
    payload.pop("report_sha256", None)
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", f"{field} report SHA-256 mismatch")
    _require_machine_id(report.get("policy_id"), f"{field}.policy_id")
    for key in ("subject_model_set_sha256", "trial_manifest_sha256", "dataset_snapshot_sha256", "records_sha256", "policy_sha256"):
        _require_sha256(report.get(key), f"{field}.{key}")
    role = _require_machine_id(report.get("evaluation_role"), f"{field}.evaluation_role")
    if role not in {"DISCOVERY", "OOS", "UNTOUCHED_HOLDOUT"}:
        raise EFSError("CONTRACT_INVALID", f"{field} has unsupported evaluation role")
    evaluation_as_of = _parse_time(report.get("evaluation_as_of"), f"{field}.evaluation_as_of")
    evaluation_start = _parse_time(report.get("evaluation_start"), f"{field}.evaluation_start")
    evaluation_end = _parse_time(report.get("evaluation_end"), f"{field}.evaluation_end")
    if evaluation_start > evaluation_end or evaluation_end > evaluation_as_of:
        raise EFSError("POINT_IN_TIME_VIOLATION", f"{field} evaluation interval is invalid")
    _require_int(report.get("horizon"), f"{field}.horizon", minimum=1, maximum=2520)
    record_count = _require_int(report.get("record_count"), f"{field}.record_count", minimum=1, maximum=100_000_000)
    cluster_count = _require_int(report.get("cluster_count"), f"{field}.cluster_count", minimum=1, maximum=record_count)
    overall_status = report.get("overall_status")
    if not isinstance(overall_status, str) or overall_status not in {"PASS", "FAIL"}:
        raise EFSError("CONTRACT_INVALID", f"{field} has invalid overall status")
    if report.get("automatic_promotion_permitted") is not False:
        raise EFSError("CONTRACT_INVALID", f"{field} cannot grant automatic promotion")
    if report.get("promotion_semantics") != "EVIDENCE_REPORT_ONLY_REQUIRES_SEPARATE_LIFECYCLE_DECISION":
        raise EFSError("CONTRACT_INVALID", f"{field} promotion semantics mismatch")
    for counter in (
        "agent_invocations_total", "llm_requests_total", "llm_input_tokens_total",
        "llm_output_tokens_total", "network_requests_total",
    ):
        if report.get(counter) != 0:
            raise EFSError("CONTRACT_INVALID", f"{field} violates zero-agent runtime evidence")
    _validate_report_sections(report)
    return report


def _evidence_set_sha256(oos: dict[str, Any], holdout: dict[str, Any] | None) -> str:
    return sha256_hex(
        {
            "oos_report_sha256": oos["report_sha256"],
            "untouched_holdout_report_sha256": holdout["report_sha256"] if holdout else None,
        }
    )


def _promotion_decision(value: dict[str, Any] | str | bytes, field: str) -> dict[str, Any]:
    decision = _normalize_json_mapping(value, field, 1_000_000)
    unknown = sorted(set(decision) - _PROMOTION_DECISION_KEYS)
    if unknown:
        raise EFSError("CONTRACT_INVALID", f"{field} contains unknown keys")
    if decision.get("schema") != PROMOTION_DECISION_SCHEMA:
        raise EFSError("CONTRACT_INVALID", f"{field} has unsupported schema")
    if decision.get("stable_id") != STABLE_ID or decision.get("runtime_version") != RUNTIME_VERSION:
        raise EFSError("CONTRACT_INVALID", f"{field} runtime identity mismatch")
    claimed = _require_sha256(decision.get("decision_sha256"), f"{field}.decision_sha256")
    payload = copy.deepcopy(decision)
    payload.pop("decision_sha256", None)
    if claimed != sha256_hex(payload):
        raise EFSError("EVIDENCE_INTEGRITY_FAILED", f"{field} SHA-256 mismatch")
    mode = _require_machine_id(decision.get("intended_mode"), f"{field}.intended_mode")
    if mode not in {"SHADOW", "DECISION_SUPPORT"}:
        raise EFSError("CONTRACT_INVALID", f"{field} intended mode mismatch")
    eligible = decision.get("eligible_for_separate_host_approval")
    if not isinstance(eligible, bool):
        raise EFSError("CONTRACT_INVALID", f"{field} eligibility must be boolean")
    if decision.get("automatic_promotion_permitted") is not False:
        raise EFSError("CONTRACT_INVALID", f"{field} cannot grant automatic promotion")
    blocking = decision.get("blocking_reasons")
    warnings = decision.get("warnings")
    if not isinstance(blocking, list) or not isinstance(warnings, list):
        raise EFSError("CONTRACT_INVALID", f"{field} reasons and warnings must be arrays")
    for name, values in (("blocking_reasons", blocking), ("warnings", warnings)):
        if len(values) > 256:
            raise EFSError("RESOURCE_LIMIT", f"{field}.{name} exceeds limit")
        for index, item in enumerate(values):
            _require_machine_id(item, f"{field}.{name}[{index}]")
        if values != sorted(set(values)):
            raise EFSError("CONTRACT_INVALID", f"{field}.{name} must be sorted and unique")
    result = decision.get("decision")
    expected = "ELIGIBLE_FOR_SEPARATE_HOST_APPROVAL" if eligible else "KEEP_LKG"
    if result != expected:
        raise EFSError("CONTRACT_INVALID", f"{field} decision conflicts with eligibility")
    if eligible and blocking:
        raise EFSError("CONTRACT_INVALID", f"{field} eligible decision cannot have blocking reasons")
    if not eligible and not blocking:
        raise EFSError("CONTRACT_INVALID", f"{field} ineligible decision must state a blocking reason")
    if eligible:
        required_hashes = {
            "compatibility_report_sha256", "candidate_bundle_sha256",
            "lkg_bundle_sha256", "oos_report_sha256",
        }
        if mode == "DECISION_SUPPORT":
            required_hashes.add("untouched_holdout_report_sha256")
        if not required_hashes.issubset(decision):
            raise EFSError("CONTRACT_INVALID", f"{field} eligible decision lacks bound evidence hashes")
    for key in (
        "compatibility_report_sha256", "candidate_bundle_sha256", "lkg_bundle_sha256",
        "oos_report_sha256", "untouched_holdout_report_sha256",
    ):
        if key in decision:
            _require_sha256(decision.get(key), f"{field}.{key}")
    error = decision.get("error")
    if error is not None:
        error_map = _exact_mapping(error, field=f"{field}.error", keys={"code", "message_zh"})
        _require_machine_id(error_map.get("code"), f"{field}.error.code")
        if not isinstance(error_map.get("message_zh"), str) or not error_map["message_zh"] or len(error_map["message_zh"]) > 512:
            raise EFSError("CONTRACT_INVALID", f"{field}.error.message_zh is invalid")
    for counter in (
        "agent_invocations_total", "llm_requests_total", "llm_input_tokens_total",
        "llm_output_tokens_total", "network_requests_total",
    ):
        if decision.get(counter) != 0:
            raise EFSError("CONTRACT_INVALID", f"{field} violates zero-agent evidence")
    return decision


def bind_validation_evidence(
    candidate: dict[str, Any] | str | bytes,
    oos_report: dict[str, Any] | str | bytes,
    untouched_holdout_report: dict[str, Any] | str | bytes | None = None,
) -> dict[str, Any]:
    """Bind exact validation reports to an already-matured candidate.

    This function never changes model/head maturity and never grants promotion.
    It only replaces placeholder evidence with hashes from exact, verified reports.
    """
    candidate_map = _normalize_json_mapping(candidate, "candidate", DEFAULT_LIMITS["bundle_bytes"])
    validate_bundle(candidate_map)
    oos = _validation_report(oos_report, "oos_report")
    holdout = _validation_report(untouched_holdout_report, "untouched_holdout_report") if untouched_holdout_report is not None else None
    if oos["evaluation_role"] != "OOS":
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "OOS report role mismatch")
    if holdout is not None and holdout["evaluation_role"] != "UNTOUCHED_HOLDOUT":
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "holdout report role mismatch")
    for report in (oos, holdout):
        if report is None:
            continue
        if report["subject_model_set_sha256"] != candidate_map["model_set_sha256"]:
            raise EFSError("PROMOTION_EVIDENCE_INVALID", "validation report subject mismatch")
        if report["horizon"] not in candidate_map["horizons"]:
            raise EFSError("PROMOTION_EVIDENCE_INVALID", "validation report horizon mismatch")
        if report["overall_status"] != "PASS":
            raise EFSError("PROMOTION_EVIDENCE_INVALID", "failed validation report cannot be bound as passing evidence")
    if holdout is not None and holdout["trial_manifest_sha256"] != oos["trial_manifest_sha256"]:
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "OOS and holdout trial manifests differ")
    if holdout is not None and holdout["dataset_snapshot_sha256"] == oos["dataset_snapshot_sha256"]:
        raise EFSError("PROMOTION_EVIDENCE_INVALID", "untouched holdout must use a distinct dataset snapshot")

    result = copy.deepcopy(candidate_map)
    evidence = result["promotion_evidence"]
    evidence["trial_ledger_sha256"] = oos["trial_manifest_sha256"]
    evidence["evidence_set_sha256"] = _evidence_set_sha256(oos, holdout)
    for logical, bundle_key in HEAD_STATUS_MAP.items():
        status = result[bundle_key]["status"]
        head = evidence["heads"][logical]
        if MATURITY_ORDER[status] >= MATURITY_ORDER["OOS_VALIDATED"]:
            head["effective_sample_size"] = oos["record_count"]
            head["oos_predictions_sha256"] = oos["records_sha256"]
            head["evaluation_start"] = oos["evaluation_start"]
            head["evaluation_end"] = oos["evaluation_end"]
        if MATURITY_ORDER[status] >= MATURITY_ORDER["OUTCOME_PROVEN"]:
            if holdout is None:
                raise EFSError("PROMOTION_EVIDENCE_INVALID", "outcome-proven candidate requires untouched holdout")
            head["untouched_holdout_sha256"] = holdout["records_sha256"]
            head["cost_stress_2x_pass"] = holdout["economic_edge"]["checks"].get("stressed_mean") is True
    evidence.pop("receipt_sha256", None)
    evidence["receipt_sha256"] = sha256_hex(evidence)
    result.pop("payload_sha256", None)
    result["payload_sha256"] = sha256_hex(result)
    validate_bundle(result)
    return result


def assess_candidate_promotion(
    candidate: dict[str, Any] | str | bytes,
    lkg: dict[str, Any] | str | bytes,
    oos_report: dict[str, Any] | str | bytes,
    *,
    intended_mode: str,
    untouched_holdout_report: dict[str, Any] | str | bytes | None = None,
) -> dict[str, Any]:
    """Deterministically assess eligibility; never install or promote a bundle."""
    report: dict[str, Any] = {
        "schema": PROMOTION_DECISION_SCHEMA,
        "stable_id": STABLE_ID,
        "runtime_version": RUNTIME_VERSION,
        "intended_mode": intended_mode,
        "eligible_for_separate_host_approval": False,
        "automatic_promotion_permitted": False,
        "blocking_reasons": [],
        "warnings": [],
        "agent_invocations_total": 0,
        "llm_requests_total": 0,
        "llm_input_tokens_total": 0,
        "llm_output_tokens_total": 0,
        "network_requests_total": 0,
    }
    try:
        if intended_mode not in {"SHADOW", "DECISION_SUPPORT"}:
            raise EFSError("CONTRACT_INVALID", "promotion assessment supports SHADOW or DECISION_SUPPORT")
        candidate_map = _normalize_json_mapping(candidate, "candidate", DEFAULT_LIMITS["bundle_bytes"])
        lkg_map = _normalize_json_mapping(lkg, "lkg", DEFAULT_LIMITS["bundle_bytes"])
        validate_bundle(candidate_map)
        validate_bundle(lkg_map)
        compatibility = compare_candidate_to_lkg(candidate_map, lkg_map)
        report["compatibility_report_sha256"] = compatibility["report_sha256"]
        report["candidate_bundle_sha256"] = candidate_map["payload_sha256"]
        report["lkg_bundle_sha256"] = lkg_map["payload_sha256"]
        if not compatibility["compatible_for_in_place_refresh"]:
            report["blocking_reasons"].extend(compatibility["blocking_reasons"])
        if candidate_map["payload_sha256"] == lkg_map["payload_sha256"]:
            report["blocking_reasons"].append("NO_CHANGE_KEEP_LKG")
        if _parse_time(candidate_map["created_at"], "candidate.created_at") <= _parse_time(lkg_map["created_at"], "lkg.created_at"):
            report["blocking_reasons"].append("CANDIDATE_NOT_NEWER_THAN_LKG")

        oos = _validation_report(oos_report, "oos_report")
        holdout = _validation_report(untouched_holdout_report, "untouched_holdout_report") if untouched_holdout_report is not None else None
        report["oos_report_sha256"] = oos["report_sha256"]
        if holdout is not None:
            report["untouched_holdout_report_sha256"] = holdout["report_sha256"]
        if oos["evaluation_role"] != "OOS" or oos["overall_status"] != "PASS":
            report["blocking_reasons"].append("OOS_EVIDENCE_NOT_PASSING")
        if oos["subject_model_set_sha256"] != candidate_map["model_set_sha256"]:
            report["blocking_reasons"].append("OOS_SUBJECT_MISMATCH")
        required_status = "OOS_VALIDATED" if intended_mode == "SHADOW" else "OUTCOME_PROVEN"
        for logical, bundle_key in HEAD_STATUS_MAP.items():
            if MATURITY_ORDER[candidate_map[bundle_key]["status"]] < MATURITY_ORDER[required_status]:
                report["blocking_reasons"].append(f"HEAD_MATURITY_INSUFFICIENT_{logical.upper()}")
        evidence = candidate_map["promotion_evidence"]
        if evidence["trial_ledger_sha256"] != oos["trial_manifest_sha256"]:
            report["blocking_reasons"].append("TRIAL_MANIFEST_MISMATCH")
        if evidence["evidence_set_sha256"] != _evidence_set_sha256(oos, holdout):
            report["blocking_reasons"].append("EVIDENCE_SET_MISMATCH")
        for logical in HEAD_STATUS_MAP:
            head = evidence["heads"][logical]
            if head.get("oos_predictions_sha256") != oos["records_sha256"]:
                report["blocking_reasons"].append(f"OOS_RECORD_BINDING_MISMATCH_{logical.upper()}")
            if int(head.get("effective_sample_size") or 0) != int(oos["record_count"]):
                report["blocking_reasons"].append(f"OOS_SAMPLE_BINDING_MISMATCH_{logical.upper()}")
        if intended_mode == "DECISION_SUPPORT":
            if holdout is None:
                report["blocking_reasons"].append("UNTOUCHED_HOLDOUT_REQUIRED")
            else:
                if holdout["evaluation_role"] != "UNTOUCHED_HOLDOUT" or holdout["overall_status"] != "PASS":
                    report["blocking_reasons"].append("UNTOUCHED_HOLDOUT_NOT_PASSING")
                if holdout["subject_model_set_sha256"] != candidate_map["model_set_sha256"]:
                    report["blocking_reasons"].append("HOLDOUT_SUBJECT_MISMATCH")
                for logical in HEAD_STATUS_MAP:
                    if evidence["heads"][logical].get("untouched_holdout_sha256") != holdout["records_sha256"]:
                        report["blocking_reasons"].append(f"HOLDOUT_BINDING_MISMATCH_{logical.upper()}")
        report["blocking_reasons"] = sorted(set(report["blocking_reasons"]))
        report["eligible_for_separate_host_approval"] = not report["blocking_reasons"]
        report["decision"] = "ELIGIBLE_FOR_SEPARATE_HOST_APPROVAL" if report["eligible_for_separate_host_approval"] else "KEEP_LKG"
    except EFSError as error:
        report["blocking_reasons"].append(error.code)
        report["error"] = _safe_error(error)
        report["decision"] = "KEEP_LKG"
    except Exception:
        report["blocking_reasons"].append("INTERNAL_ERROR")
        report["error"] = {"code": "INTERNAL_ERROR", "message_zh": "deterministic promotion assessment failed"}
        report["decision"] = "KEEP_LKG"
    report["decision_sha256"] = sha256_hex(report)
    return report
